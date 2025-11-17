#!/usr/bin/env python3
# agent/ask_agent.py
"""
ask_agent.py — interactive chat loop that prints what the agent is doing.

Env (read from .env via python-dotenv):
- PROJECT_ENDPOINT           (required)
- AGENT_ID                   (optional; else read from ./.agent_id)
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv, find_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import (
    McpTool,
    BingGroundingTool,
    AgentEventHandler,
    ThreadMessage,
    MessageDeltaChunk,
    RunStep,
)


# --- Event handler to show what the agent is doing in detail -----------------
class ConsoleEvents(AgentEventHandler):
    """Print run status, token deltas, and MCP tool call details."""

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


LEARN_MCP_URL = "https://learn.microsoft.com/api/mcp"  # public, no auth required


TSG_TEMPLATE = """[[_TOC_]]

# **Title**
_Include, ideally, Error Message/ Error code or Scenario with keywords._
_For example_ **'message': 'ScriptExecutionException was caused by StreamAccessException.\\n StreamAccessException was caused by AuthenticationException.** OR 
**Datareference to ADLSGen2 Datastore fails.**

# **Issue Description / Symptoms**
_Describe what the Customer/CSS Engineer would see as an issue. This would include the error message and the stack trace (if available)_
- **What** is the issue?  
- **Who** does this affect?  
- **Where** does the issue occur? Where does it not occur?  
- **When** does it occur?  
 
# **When does the TSG not Apply**
_For example the TSG might not apply to Private Endpoint workspace etc._

# **Diagnosis**
_How can I debug further and mitigate this issue? Add more details on how to diagnose this issue._  
- [ ] _Put quick steps to check before doing any deep dives._ 
- [ ] _This section can include Kusto queries, Acis commands or ASC actions (preferable) for getting more diagnostic information_  
- [ ] _If is a common query link to a separate How-To Page containing the entire Kusto query, Acis Command or ASC action._  

Don't Remove This Text: Results of the Diagnosis should be attached in the Case notes/ICM.

# **Questions to Ask the Customer**
_If there is no diagnostic information available or to further drill into the issue, list down any questions you can ask the customer.-

# **Cause**
_**Why** does the issue occur? Include both internal and external details about the cause, if possible._

# **Mitigation or Resolution**
_How can I fix this issue? Add more details on how to fix this issue once it has been identified._  
- _This should be a short step by step guide.
- _This section can include Acis commands or scripts/ adhoc steps to perform resolution operations_  
- _Create a script file if possible and place a link to the script file (parameterize the script to take in user specific inputs.)_ 
- _For inline scripts, please give entire script and don’t give instructions_ 
- _Put a link to a How-To Page that contains the above for common steps_ 

# **Root Cause to be shared with Customer**
_**Why** does the issue occur? If applicable, list a short root cause that can be shared with customer.Include both internal and external details about the cause, if possible_

# **Related Information**
_Where can I find more information about this issue? Add links to related content here._  
_This could be links to other TSGs, ICMs, AVA threads, Bugs, Known Issues._ 
_If there is a Public Documentation about this issue, link that here too and make sure you also update the public doc._

# **Tags or Prompts**
_Add common tags or prompts statements that can improve the searchability and copilot recommendation of this TSG._
(E.g.: This TSG helps answer _<prompt>_)
"""


def main():
    # Load repo-root .env
    load_dotenv(find_dotenv())

    endpoint = os.environ["PROJECT_ENDPOINT"]

    # Agent id comes from .agent_id (created by create_agent.py), or env override
    agent_id = os.getenv("AGENT_ID") or Path(".agent_id").read_text(encoding="utf-8").strip()

    # Rebuild the MCP tool, but for inference, attach auth headers AT RUN TIME (not persisted)
    mcp = McpTool(server_label="learn", server_url=LEARN_MCP_URL)

    # Skip approval prompts
    mcp.set_approval_mode("never")

    # Connect to the project and run a simple REPL (TODO: currently just a one-shot, revise to REPL to take feedback)
    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
    with project:
        thread = project.agents.threads.create()
        print("\nChat ready. Input all notes on the TSG issue. Include as much info as possible - TSG topic, symptoms, diagnosis steps, resolution/mitigation steps, links to other material (AVA, ICMs) and docs, etc.")
        print("Type '/exit' to quit.\n")

        while True:
            try:
                notes = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nExiting.")
                break

            if not notes:
                continue
            if notes.lower() in {"/exit", "exit", "quit"}:
                print("Goodbye.")
                break
            
            # Combine user notes with TSG construction prompt
            initial_content_and_prompt = f"""You will transform the raw notes into the strict TSG template provided below.

                === TEMPLATE (use verbatim) ===

                {TSG_TEMPLATE}

                === END TEMPLATE ===

                === RAW NOTES ===

                f"{notes}"

                === END RAW NOTES ===

                Remember the CRITICAL OUTPUT RULES.
                """

            # Add the user message
            project.agents.messages.create(thread_id=thread.id, role="user", content=initial_content_and_prompt)

            # Stream the run so you can see tokens + tool calls live
            handler = ConsoleEvents()
            with project.agents.runs.stream(
                thread_id=thread.id,
                agent_id=agent_id,
                event_handler=handler,
                #tool_resources=mcp.resources,  # runtime-only auth & headers (TODO: re-add later)
            ) as stream:
                handler.until_done()  # block until completion

            print()  # newline after streamed reply
            break  # TODO: remove to make a REPL later


if __name__ == "__main__":
    main()
