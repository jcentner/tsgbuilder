#!/usr/bin/env python3
# agent/ask_agent.py
"""
ask_agent.py — interactive chat loop using the new Agents API (conversations + responses).

Env (read from .env via python-dotenv):
- PROJECT_ENDPOINT          (required)
- AGENT_REF                 (optional; else read from ./.agent_ref as name:version)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv, find_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

from tsg_constants import (
    TSG_BEGIN,
    TSG_END,
    QUESTIONS_BEGIN,
    QUESTIONS_END,
    agent_reference,
    build_user_prompt,
)


LEARN_MCP_URL = "https://learn.microsoft.com/api/mcp"  # public, no auth required


def stream_response(project: AIProjectClient, conversation_id: str, agent_name: str) -> str:
    """Stream a response and return full assistant text."""
    buffer: list[str] = []
    stream = project.responses.create_stream(
        conversation=conversation_id,
        input=None,
        extra_body={"agent": agent_reference(agent_name)},
    )
    for event in stream:
        outputs = getattr(event, "output", None) or []
        for item in outputs:
            item_type = getattr(item, "type", None)
            if item_type == "message_delta":
                text = getattr(item, "text", None) or ""
                if text:
                    print(text, end="", flush=True)
                    buffer.append(text)
            elif item_type == "message":
                content = getattr(item, "content", None) or ""
                if content:
                    buffer.append(str(content))
    print()  # newline after stream
    return "".join(buffer)


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
    parser.add_argument("--agent-ref", help="Override the agent reference (name:version) otherwise read from .agent_ref or AGENT_REF env.")
    parser.add_argument("--output", "-o", help="Path to save the final TSG markdown file.")
    args = parser.parse_args()

    load_dotenv(find_dotenv())

    endpoint = os.getenv("PROJECT_ENDPOINT")
    if not endpoint:
        print("ERROR: PROJECT_ENDPOINT is required.", file=sys.stderr)
        sys.exit(1)

    agent_ref = (
        args.agent_ref
        or os.getenv("AGENT_REF")
        or Path(".agent_ref").read_text(encoding="utf-8").strip()
    )
    # agent_ref is name:version
    agent_name = agent_ref.split(":")[0]

    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())

    notes = load_notes(args.notes_file)
    if not notes.strip():
        print("ERROR: No notes provided.", file=sys.stderr)
        sys.exit(1)

    with project:
        prior_tsg = None
        final_tsg = None
        while True:
            user_content = build_user_prompt(notes, prior_tsg=prior_tsg, user_answers=None)
            conversation = project.conversations.create(
                items=[{"type": "message", "role": "user", "content": user_content}],
                store=True,
            )

            assistant_text = stream_response(project, conversation.id, agent_name)
            tsg_block, questions_block = extract_blocks(assistant_text)
            if not tsg_block:
                print("ERROR: Model output did not include a TSG block.")
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
            notes = notes
            # Append answers as next turn and continue
            conversation = project.conversations.create(
                items=[{"type": "message", "role": "user", "content": answers}],
                store=True,
            )
            assistant_text = stream_response(project, conversation.id, agent_name)
            notes = notes  # keep original
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
