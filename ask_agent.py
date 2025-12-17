#!/usr/bin/env python3
# agent/ask_agent.py
"""
ask_agent.py — interactive chat loop using the classic Agents API (threads + runs).

Env (read from .env via python-dotenv):
- PROJECT_ENDPOINT          (required)
- AGENT_ID                  (optional; else read from ./.agent_id)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv, find_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

from tsg_constants import (
    TSG_BEGIN,
    TSG_END,
    QUESTIONS_BEGIN,
    QUESTIONS_END,
    build_user_prompt,
)


def run_agent_and_get_response(project: AIProjectClient, thread_id: str, agent_id: str) -> str:
    """Create a run, poll until complete, and return the assistant's response text."""
    run = project.agents.runs.create(thread_id=thread_id, agent_id=agent_id)
    
    # Poll until run completes
    while run.status in ("queued", "in_progress", "requires_action"):
        time.sleep(1)
        run = project.agents.runs.get(thread_id=thread_id, run_id=run.id)
        print(".", end="", flush=True)
    
    print()  # newline after polling dots
    
    if run.status == "failed":
        error_msg = getattr(run, "last_error", None)
        print(f"Run failed: {error_msg}", file=sys.stderr)
        return ""
    
    # Get messages from the thread (newest first)
    messages = project.agents.messages.list(thread_id=thread_id)
    
    # Find the most recent assistant message
    for message in messages:
        if message.role == "assistant":
            # Extract text content from the message
            text_parts = []
            for content_item in message.content:
                if hasattr(content_item, "text") and content_item.text:
                    text_parts.append(content_item.text.value)
            return "\n".join(text_parts)
    
    return ""


def load_notes(path: str | None) -> str:
    if path:
        if not os.path.exists(path):
            print(f"ERROR: Notes file not found: {path}", file=sys.stderr)
            sys.exit(1)
        return Path(path).read_text(encoding="utf-8")

    print("Paste raw notes about the issue. Press Enter twice to end.")
    return read_multiline_input()


def read_multiline_input() -> str:
    print("(End input with an empty line)")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "":
            break
        lines.append(line)
    return "\n".join(lines)


def extract_blocks(content: str) -> tuple[str, str]:
    def between(s: str, start: str, end: str) -> str:
        i = s.find(start)
        j = s.find(end)
        if i == -1 or j == -1 or j <= i:
            return ""
        return s[i + len(start) : j].strip()

    return between(content, TSG_BEGIN, TSG_END), between(content, QUESTIONS_BEGIN, QUESTIONS_END)


def main():
    parser = argparse.ArgumentParser(description="Run TSG agent inference.")
    parser.add_argument("--notes-file", help="Path to raw notes file (if omitted, you can paste interactively).")
    parser.add_argument("--agent-id", help="Override the agent ID, otherwise read from .agent_id or AGENT_ID env.")
    parser.add_argument("--output", "-o", help="Path to save the final TSG markdown file.")
    args = parser.parse_args()

    load_dotenv(find_dotenv())

    endpoint = os.getenv("PROJECT_ENDPOINT")
    if not endpoint:
        print("ERROR: PROJECT_ENDPOINT is required.", file=sys.stderr)
        sys.exit(1)

    agent_id = (
        args.agent_id
        or os.getenv("AGENT_ID")
        or Path(".agent_id").read_text(encoding="utf-8").strip()
    )

    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())

    notes = load_notes(args.notes_file)
    if not notes.strip():
        print("ERROR: No notes provided.", file=sys.stderr)
        sys.exit(1)

    with project:
        # Create a thread for the conversation
        thread = project.agents.threads.create()
        print(f"Created thread: {thread.id}")

        prior_tsg = None
        final_tsg = None
        
        while True:
            user_content = build_user_prompt(notes, prior_tsg=prior_tsg, user_answers=None)
            
            # Add user message to thread
            project.agents.messages.create(
                thread_id=thread.id,
                role="user",
                content=user_content,
            )

            print("Running agent", end="", flush=True)
            assistant_text = run_agent_and_get_response(project, thread.id, agent_id)
            
            tsg_block, questions_block = extract_blocks(assistant_text)
            if not tsg_block:
                print("ERROR: Model output did not include a TSG block.")
                print("Full response:")
                print(assistant_text)
                break

            final_tsg = tsg_block
            print("\n--- TSG ---\n")
            print(tsg_block)

            if not questions_block or questions_block.strip() == "NO_MISSING":
                print("\nNo missing items. Done.")
                break

            print("\n--- Follow-up questions ---\n")
            print(questions_block)
            print("\nPaste answers (blank line to finish, or type 'done' to exit).")
            answers = read_multiline_input()
            if answers.strip().lower() == "done":
                print("Exiting.")
                break

            prior_tsg = tsg_block
            
            # Add answers as next message in the same thread
            project.agents.messages.create(
                thread_id=thread.id,
                role="user",
                content=answers,
            )

            print("Running agent", end="", flush=True)
            assistant_text = run_agent_and_get_response(project, thread.id, agent_id)
            
            tsg_block, questions_block = extract_blocks(assistant_text)
            if not tsg_block:
                print("ERROR: Model output did not include a TSG block on refinement.")
                break
            final_tsg = tsg_block
            print("\n--- TSG (updated) ---\n")
            print(tsg_block)
            if not questions_block or questions_block.strip() == "NO_MISSING":
                print("\nNo missing items. Done.")
                break
            prior_tsg = tsg_block
            continue

        # Save output if --output was specified
        if args.output and final_tsg:
            output_path = Path(args.output)
            output_path.write_text(final_tsg, encoding="utf-8")
            print(f"\nTSG saved to: {output_path.resolve()}")


if __name__ == "__main__":
    main()
