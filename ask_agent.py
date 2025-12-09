#!/usr/bin/env python3
# agent/ask_agent.py
"""
ask_agent.py — interactive chat loop that prints what the agent is doing.

Env (read from .env via python-dotenv):
- PROJECT_ENDPOINT           (required)
- AGENT_ID                   (optional; else read from ./.agent_id)
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
from azure.ai.agents.models import (
    McpTool,
    AgentEventHandler,
    ThreadMessage,
    MessageDeltaChunk,
    RunStep,
)

from tsg_constants import (
    TSG_BEGIN,
    TSG_END,
    QUESTIONS_BEGIN,
    QUESTIONS_END,
    build_user_prompt,
)


# --- Event handler to show what the agent is doing in detail -----------------
class ConsoleEvents(AgentEventHandler):
    """Print run status, token deltas, and MCP tool call details."""

    def __init__(self):
        super().__init__()
        self._buffer: list[str] = []

    def on_thread_run(self, run):
        print(f"\n[run] id={run.id} status={getattr(run, 'status', None)}")

    def on_thread_message(self, message: ThreadMessage):
        role = getattr(message, "role", "?")
        status = getattr(message, "status", None)
        print(f"[message] role={role} id={message.id} status={status}")
        # If the SDK surfaces tool messages/content, show a short excerpt
        content = getattr(message, "content", None)
        if content:
            try:
                text = getattr(content, "text", None) or str(content)
                s = text if isinstance(text, str) else json.dumps(text)
                if s:
                    print(f"  [content] {s[:300]}{'…' if len(s) > 300 else ''}")
            except Exception:
                pass

    def on_message_delta(self, delta: MessageDeltaChunk):
        # Stream assistant tokens live
        if getattr(delta, "text", None):
            print(delta.text, end="", flush=True)
            self._buffer.append(delta.text)

    def on_run_step(self, step: RunStep):
        # Print when steps complete; include MCP tool call info if present
        print(f"\n[step] id={step.id} type={getattr(step, 'type', None)} status={getattr(step, 'status', None)}")
        details = getattr(step, "step_details", None)

        # Helper: safely stringify possibly nested/SDK objects
        def _to_jsonable(obj):
            try:
                if hasattr(obj, "to_dict"):
                    return obj.to_dict()
            except Exception:
                pass
            try:
                if isinstance(obj, str):
                    return json.loads(obj)  # if it's JSON, parse it
            except Exception:
                pass
            return obj

        def _trunc(s, n=400):
            if s is None:
                return ""
            if len(s) <= n:
                return s
            return s[:n] + "…"

        if details:
            # Different SDKs spell this differently
            tool_calls = getattr(details, "tool_calls", None) or getattr(details, "toolCalls", None)
            if tool_calls:
                print(f"  tool_calls={len(tool_calls)}")
                for i, tc in enumerate(tool_calls or [], 1):
                    tc_type = getattr(tc, "type", None)
                    mcp = getattr(tc, "mcp_tool", None) or getattr(tc, "mcpTool", None)
                    print(f"  [tool_call {i}] type={tc_type}")
                    if mcp:
                        name = getattr(mcp, "name", None)
                        server_label = getattr(mcp, "server_label", None) or getattr(mcp, "serverLabel", None)
                        args = getattr(mcp, "arguments", None)
                        # arguments might be dict or JSON string
                        try:
                            if isinstance(args, (dict, list)):
                                args_s = json.dumps(args)
                            else:
                                args_s = str(args)
                        except Exception:
                            args_s = repr(args)
                        print(f"    mcp.server_label={server_label} name={name}")
                        print(f"    mcp.arguments={_trunc(args_s)}")

                    # Try to surface any output/error attached to the tool call
                    # (field names may vary across SDK versions)
                    out = getattr(tc, "output", None) or getattr(tc, "result", None)
                    err = getattr(tc, "error", None)
                    if out is not None:
                        try:
                            out_s = json.dumps(_to_jsonable(out))
                        except Exception:
                            out_s = str(out)
                        print(f"    mcp.output={_trunc(out_s)}")
                    if err:
                        print(f"    mcp.error={err}")

            # Optional full dump of step details
            if os.getenv("VERBOSE_MCP") == "1":
                try:
                    print("  [step_details]")
                    print(json.dumps(_to_jsonable(details), indent=2, default=str))
                except Exception:
                    print(f"  [step_details] {details!r}")

    @property
    def content(self) -> str:
        return "".join(self._buffer)


LEARN_MCP_URL = "https://learn.microsoft.com/api/mcp"  # public, no auth required


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
    parser.add_argument("--agent-id", help="Override the agent id (otherwise read from .agent_id or AGENT_ID env).")
    parser.add_argument("--enable-learn", action="store_true", help="Attach Microsoft Learn MCP during run (if enabled in agent).")
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

    # Optional Learn MCP runtime attachment (no auth required).
    mcp = McpTool(server_label="learn", server_url=LEARN_MCP_URL)
    mcp.set_approval_mode("never")

    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())

    notes = load_notes(args.notes_file)
    if not notes.strip():
        print("ERROR: No notes provided.", file=sys.stderr)
        sys.exit(1)

    with project:
        thread = project.agents.threads.create()
        prior_tsg = None

        while True:
            user_content = build_user_prompt(notes, prior_tsg=prior_tsg, user_answers=None)
            project.agents.messages.create(thread_id=thread.id, role="user", content=user_content)

            handler = ConsoleEvents()
            with project.agents.runs.stream(
                thread_id=thread.id,
                agent_id=agent_id,
                event_handler=handler,
                tool_resources=mcp.resources if args.enable_learn else None,
            ) as stream:
                handler.until_done()

            print()  # ensure newline after stream
            tsg_block, questions_block = extract_blocks(handler.content)
            if not tsg_block:
                print("ERROR: Model output did not include a TSG block.")
                break

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
            # Loop to send answers and continue
            notes = notes  # keep original notes
            continue


if __name__ == "__main__":
    main()
