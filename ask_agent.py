#!/usr/bin/env python3
# agent/ask_agent.py
"""
ask_agent.py — interactive chat loop using the classic Agents API (threads + runs).

Supports two modes:
- Pipeline mode (default): Multi-stage Research → Write → Review flow
- Single-agent mode: Legacy single LLM call

Env (read from .env via python-dotenv):
- PROJECT_ENDPOINT          (required)
- AGENT_ID                  (optional; else read from ./.agent_id)
- USE_PIPELINE              (optional; default "true")
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import queue
import threading
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv, find_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import (
    AgentEventHandler,
    MessageDeltaChunk,
    ThreadMessage,
    ThreadRun,
    RunStep,
    RunStepToolCallDetails,
    RunStepMcpToolCall,
    RunStepBingGroundingToolCall,
    McpTool,
)

from tsg_constants import (
    TSG_BEGIN,
    TSG_END,
    QUESTIONS_BEGIN,
    QUESTIONS_END,
    get_user_prompt_builder,
    DEFAULT_PROMPT_STYLE,
    validate_tsg_output,
    build_retry_prompt,
)

from pipeline import run_pipeline, PipelineStage


# ANSI color codes for terminal output
class Colors:
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    DIM = "\033[2m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


# Stage icons and colors
STAGE_STYLES = {
    PipelineStage.RESEARCH: ("🔍", Colors.CYAN),
    PipelineStage.WRITE: ("✏️", Colors.BLUE),
    PipelineStage.REVIEW: ("🔎", Colors.MAGENTA),
    PipelineStage.COMPLETE: ("✅", Colors.GREEN),
    PipelineStage.FAILED: ("❌", Colors.YELLOW),
}


class TSGEventHandler(AgentEventHandler):
    """Event handler that provides real-time feedback on agent activities."""
    
    def __init__(self):
        super().__init__()
        self.response_text = ""
        self._current_status = ""
    
    def on_thread_run(self, run: ThreadRun) -> None:
        """Called when the run status changes."""
        status_icons = {
            "queued": "⏳",
            "in_progress": "🔄",
            "requires_action": "⚡",
            "completed": "✅",
            "failed": "❌",
            "cancelled": "🚫",
            "expired": "⏰",
        }
        icon = status_icons.get(run.status, "•")
        
        if run.status != self._current_status:
            self._current_status = run.status
            print(f"\n{Colors.CYAN}{icon} Run status: {run.status}{Colors.RESET}", flush=True)
        
        if run.status == "failed":
            print(f"{Colors.YELLOW}   Error: {run.last_error}{Colors.RESET}", file=sys.stderr)
    
    def on_run_step(self, step: RunStep) -> None:
        """Called when a run step is created or updated."""
        if step.type == "tool_calls" and hasattr(step, "step_details"):
            self._handle_tool_calls(step)
        elif step.type == "message_creation":
            if step.status == "in_progress":
                print(f"{Colors.BLUE}📝 Generating response...{Colors.RESET}", flush=True)
    
    def _handle_tool_calls(self, step: RunStep) -> None:
        """Extract and display tool call information."""
        if not isinstance(step.step_details, RunStepToolCallDetails):
            return
        
        for tool_call in step.step_details.tool_calls:
            tool_name = None
            tool_detail = ""
            
            if isinstance(tool_call, RunStepMcpToolCall):
                tool_name = "Microsoft Learn MCP"
                if hasattr(tool_call, "mcp") and tool_call.mcp:
                    server = getattr(tool_call.mcp, "server_label", "learn")
                    tool_detail = f" ({server})"
            elif isinstance(tool_call, RunStepBingGroundingToolCall):
                tool_name = "Bing Search"
                if hasattr(tool_call, "bing_grounding") and tool_call.bing_grounding:
                    # Try to get search query if available
                    pass
            elif hasattr(tool_call, "type"):
                tool_name = str(tool_call.type).replace("_", " ").title()
            
            if tool_name and step.status == "in_progress":
                print(f"{Colors.GREEN}🔧 Using tool: {tool_name}{tool_detail}{Colors.RESET}", flush=True)
            elif tool_name and step.status == "completed":
                print(f"{Colors.DIM}   ✓ {tool_name} completed{Colors.RESET}", flush=True)
    
    def on_message_delta(self, delta: MessageDeltaChunk) -> None:
        """Called when message content is streamed."""
        if delta.text:
            self.response_text += delta.text
    
    def on_thread_message(self, message: ThreadMessage) -> None:
        """Called when a complete message is available."""
        if message.role == "assistant" and message.content:
            # Extract final text from message
            for content_item in message.content:
                if hasattr(content_item, "text") and content_item.text:
                    self.response_text = content_item.text.value
    
    def on_error(self, data: str) -> None:
        """Called when an error occurs."""
        print(f"\n{Colors.YELLOW}⚠️  Error: {data}{Colors.RESET}", file=sys.stderr)
    
    def on_done(self) -> None:
        """Called when the stream is complete."""
        print(f"{Colors.CYAN}✓ Agent completed{Colors.RESET}\n", flush=True)
    
    def on_unhandled_event(self, event_type: str, event_data: Any) -> None:
        """Handle any events not covered by other methods."""
        pass  # Silently ignore unhandled events


def run_agent_with_streaming(project: AIProjectClient, thread_id: str, agent_id: str, tool_resources: Any = None) -> str:
    """Run the agent with streaming to get real-time feedback."""
    handler = TSGEventHandler()
    
    # Build streaming run kwargs
    stream_kwargs = {
        "thread_id": thread_id,
        "agent_id": agent_id,
        "event_handler": handler,
    }
    if tool_resources is not None:
        stream_kwargs["tool_resources"] = tool_resources
    
    with project.agents.runs.stream(**stream_kwargs) as stream:
        stream.until_done()
    
    return handler.response_text


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
    parser.add_argument("--single-agent", action="store_true", help="Use single-agent mode instead of pipeline.")
    args = parser.parse_args()

    load_dotenv(find_dotenv())

    # Determine mode
    use_pipeline = not args.single_agent
    if os.getenv("USE_PIPELINE", "true").lower() in ("false", "0", "no"):
        use_pipeline = False
    
    notes = load_notes(args.notes_file)
    if not notes.strip():
        print("ERROR: No notes provided.", file=sys.stderr)
        sys.exit(1)
    
    if use_pipeline:
        run_pipeline_cli(notes, args.output)
    else:
        run_single_agent_cli(notes, args.output, args.agent_id)


def run_pipeline_cli(notes: str, output_path: str | None = None):
    """Run TSG generation using the multi-stage pipeline."""
    print(f"{Colors.BOLD}🚀 Starting TSG Pipeline (Research → Write → Review){Colors.RESET}\n")
    
    event_queue: queue.Queue = queue.Queue()
    result_holder: dict = {"result": None}
    
    def run_thread():
        result = run_pipeline(
            notes=notes,
            event_queue=event_queue,
        )
        result_holder["result"] = result
        event_queue.put(None)
    
    # Start pipeline
    thread = threading.Thread(target=run_thread)
    thread.start()
    
    current_stage = None
    
    # Process events
    while True:
        try:
            event = event_queue.get(timeout=180)
            if event is None:
                break
            
            event_type = event.get("type", "")
            data = event.get("data", {})
            stage = data.get("stage", "")
            
            # Track stage transitions
            if stage and stage != current_stage:
                current_stage = stage
                try:
                    stage_enum = PipelineStage(stage)
                    icon, color = STAGE_STYLES.get(stage_enum, ("•", Colors.RESET))
                    print(f"\n{color}{icon} Stage: {stage.upper()}{Colors.RESET}")
                except ValueError:
                    pass
            
            # Handle different event types
            if event_type == "stage_start":
                print(f"   {Colors.DIM}{data.get('message', '')}{Colors.RESET}")
            elif event_type == "stage_complete":
                print(f"   {Colors.GREEN}✓ {data.get('message', 'Complete')}{Colors.RESET}")
            elif event_type == "status":
                msg = data.get("message", data.get("status", ""))
                if msg:
                    print(f"   {Colors.DIM}{msg}{Colors.RESET}")
            elif event_type == "tool_call":
                tool_name = data.get("name", data.get("type", "Tool"))
                print(f"   {Colors.GREEN}🔧 {tool_name}{Colors.RESET}")
            elif event_type == "error":
                print(f"   {Colors.YELLOW}⚠️  {data.get('message', 'Error')}{Colors.RESET}")
            elif event_type == "pipeline_complete":
                if data.get("success"):
                    print(f"\n{Colors.GREEN}✅ Pipeline complete!{Colors.RESET}")
                    if data.get("retries", 0) > 0:
                        print(f"   {Colors.DIM}(took {data['retries']} retry iterations){Colors.RESET}")
        
        except queue.Empty:
            print(".", end="", flush=True)
    
    thread.join()
    
    # Get result
    result = result_holder.get("result")
    if not result:
        print(f"\n{Colors.YELLOW}ERROR: Pipeline did not produce a result.{Colors.RESET}")
        sys.exit(1)
    
    if not result.success:
        print(f"\n{Colors.YELLOW}ERROR: {result.error or 'Pipeline failed'}{Colors.RESET}")
        sys.exit(1)
    
    # Print TSG
    print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}GENERATED TSG{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}\n")
    print(result.tsg_content)
    
    # Print review warnings if any
    if result.review_result:
        warnings = (
            result.review_result.get("accuracy_issues", []) +
            result.review_result.get("suggestions", [])
        )
        if warnings:
            print(f"\n{Colors.YELLOW}{'='*60}{Colors.RESET}")
            print(f"{Colors.YELLOW}REVIEW NOTES{Colors.RESET}")
            print(f"{Colors.YELLOW}{'='*60}{Colors.RESET}")
            for warning in warnings:
                print(f"  • {warning}")
    
    # Handle questions/follow-up
    if result.questions_content and result.questions_content.strip() != "NO_MISSING":
        print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
        print(f"{Colors.CYAN}FOLLOW-UP QUESTIONS{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*60}{Colors.RESET}\n")
        print(result.questions_content)
        print(f"\n{Colors.DIM}(Answer these questions and re-run to complete the TSG){Colors.RESET}")
    else:
        print(f"\n{Colors.GREEN}✓ TSG is complete - no missing information.{Colors.RESET}")
    
    # Save output
    if output_path and result.tsg_content:
        path = Path(output_path)
        path.write_text(result.tsg_content, encoding="utf-8")
        print(f"\n{Colors.GREEN}TSG saved to: {path.resolve()}{Colors.RESET}")


def run_single_agent_cli(notes: str, output_path: str | None = None, agent_id_override: str | None = None):
    """Run TSG generation using single-agent mode (legacy)."""
    endpoint = os.getenv("PROJECT_ENDPOINT")
    if not endpoint:
        print("ERROR: PROJECT_ENDPOINT is required.", file=sys.stderr)
        sys.exit(1)

    agent_id = (
        agent_id_override
        or os.getenv("AGENT_ID")
        or Path(".agent_id").read_text(encoding="utf-8").strip()
    )

    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
    
    # Get the appropriate prompt builder based on configured style
    prompt_style = os.getenv("PROMPT_STYLE", DEFAULT_PROMPT_STYLE)
    prompt_builder = get_user_prompt_builder(prompt_style)
    print(f"{Colors.DIM}Using single-agent mode with prompt style: {prompt_style}{Colors.RESET}")

    # Create MCP tool with approval mode set to "never" for automatic tool execution
    mcp_tool = McpTool(server_label="learn", server_url="https://learn.microsoft.com/api/mcp")
    mcp_tool.set_approval_mode("never")

    with project:
        # Create a thread for the conversation
        thread = project.agents.threads.create()
        print(f"{Colors.DIM}Created thread: {thread.id}{Colors.RESET}")

        prior_tsg = None
        final_tsg = None
        
        while True:
            user_content = prompt_builder(notes, prior_tsg=prior_tsg, user_answers=None)
            
            # Add user message to thread
            project.agents.messages.create(
                thread_id=thread.id,
                role="user",
                content=user_content,
            )

            print(f"\n{Colors.BOLD}🚀 Starting agent...{Colors.RESET}")
            assistant_text = run_agent_with_streaming(project, thread.id, agent_id, tool_resources=mcp_tool.resources)
            
            tsg_block, questions_block = extract_blocks(assistant_text)
            if not tsg_block:
                print(f"{Colors.YELLOW}ERROR: Model output did not include a TSG block.{Colors.RESET}")
                print("Full response:")
                print(assistant_text)
                break

            final_tsg = tsg_block
            print(f"\n{Colors.BOLD}--- TSG ---{Colors.RESET}\n")
            print(tsg_block)

            if not questions_block or questions_block.strip() == "NO_MISSING":
                print(f"\n{Colors.GREEN}✓ No missing items. Done.{Colors.RESET}")
                break

            print(f"\n{Colors.BOLD}--- Follow-up questions ---{Colors.RESET}\n")
            print(questions_block)
            print(f"\n{Colors.CYAN}Paste answers (blank line to finish, or type 'done' to exit).{Colors.RESET}")
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

            print(f"\n{Colors.BOLD}🚀 Refining TSG...{Colors.RESET}")
            assistant_text = run_agent_with_streaming(project, thread.id, agent_id, tool_resources=mcp_tool.resources)
            
            tsg_block, questions_block = extract_blocks(assistant_text)
            if not tsg_block:
                print(f"{Colors.YELLOW}ERROR: Model output did not include a TSG block on refinement.{Colors.RESET}")
                break
            final_tsg = tsg_block
            print(f"\n{Colors.BOLD}--- TSG (updated) ---{Colors.RESET}\n")
            print(tsg_block)
            if not questions_block or questions_block.strip() == "NO_MISSING":
                print(f"\n{Colors.GREEN}✓ No missing items. Done.{Colors.RESET}")
                break
            prior_tsg = tsg_block
            continue

        # Save output if --output was specified
        if output_path and final_tsg:
            output_file = Path(output_path)
            output_file.write_text(final_tsg, encoding="utf-8")
            print(f"\n{Colors.GREEN}TSG saved to: {output_file.resolve()}{Colors.RESET}")


if __name__ == "__main__":
    main()
