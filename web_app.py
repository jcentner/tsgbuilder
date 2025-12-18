#!/usr/bin/env python3
"""
web_app.py — Simple Flask web UI for TSG Builder.

Provides an easy-to-use web interface for generating TSGs from notes.
"""

from __future__ import annotations

import json
import os
import sys
import time
import threading
import queue
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Generator, Optional

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from dotenv import load_dotenv, find_dotenv, set_key
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
    BingGroundingTool,
    McpTool,
)

from tsg_constants import (
    TSG_BEGIN,
    TSG_END,
    QUESTIONS_BEGIN,
    QUESTIONS_END,
    build_user_prompt,
    AGENT_INSTRUCTIONS,
)

# Microsoft Learn MCP URL for agent creation
LEARN_MCP_URL = "https://learn.microsoft.com/api/mcp"

# Load environment variables
load_dotenv(find_dotenv())

app = Flask(__name__)

# Store active sessions (thread_id -> session data)
sessions: dict[str, dict] = {}


class SSEEventHandler(AgentEventHandler):
    """Event handler that queues events for SSE streaming."""
    
    def __init__(self, event_queue: queue.Queue):
        super().__init__()
        self.event_queue = event_queue
        self.response_text = ""
        self._current_status = ""
    
    def _send_event(self, event_type: str, data: dict):
        """Queue an event for SSE streaming."""
        self.event_queue.put({"type": event_type, "data": data})
    
    def on_thread_run(self, run: ThreadRun) -> None:
        """Called when the run status changes."""
        if run.status != self._current_status:
            self._current_status = run.status
            self._send_event("status", {
                "status": run.status,
                "message": self._get_status_message(run.status)
            })
        
        if run.status == "failed":
            self._send_event("error", {"message": str(run.last_error)})
    
    def _get_status_message(self, status: str) -> str:
        """Get a user-friendly status message."""
        messages = {
            "queued": "Request queued...",
            "in_progress": "Agent is working...",
            "requires_action": "Processing tool results...",
            "completed": "Generation complete",
            "failed": "Generation failed",
            "cancelled": "Generation cancelled",
            "expired": "Request expired",
        }
        return messages.get(status, status)
    
    def on_run_step(self, step: RunStep) -> None:
        """Called when a run step is created or updated."""
        if step.type == "tool_calls" and hasattr(step, "step_details"):
            self._handle_tool_calls(step)
        elif step.type == "message_creation":
            if step.status == "in_progress":
                self._send_event("activity", {
                    "activity": "generating",
                    "message": "Generating response..."
                })
    
    def _handle_tool_calls(self, step: RunStep) -> None:
        """Extract and display tool call information."""
        if not isinstance(step.step_details, RunStepToolCallDetails):
            return
        
        for tool_call in step.step_details.tool_calls:
            tool_name = None
            tool_icon = "🔧"
            
            if isinstance(tool_call, RunStepMcpToolCall):
                tool_name = "Microsoft Learn"
                tool_icon = "📚"
            elif isinstance(tool_call, RunStepBingGroundingToolCall):
                tool_name = "Bing Search"
                tool_icon = "🔍"
            elif hasattr(tool_call, "type"):
                tool_name = str(tool_call.type).replace("_", " ").title()
            
            if tool_name:
                if step.status == "in_progress":
                    self._send_event("tool", {
                        "tool": tool_name,
                        "icon": tool_icon,
                        "status": "running",
                        "message": f"Using {tool_name}..."
                    })
                elif step.status == "completed":
                    self._send_event("tool", {
                        "tool": tool_name,
                        "icon": "✓",
                        "status": "completed",
                        "message": f"{tool_name} completed"
                    })
    
    def on_message_delta(self, delta: MessageDeltaChunk) -> None:
        """Called when message content is streamed."""
        if delta.text:
            self.response_text += delta.text
    
    def on_thread_message(self, message: ThreadMessage) -> None:
        """Called when a complete message is available."""
        if message.role == "assistant" and message.content:
            for content_item in message.content:
                if hasattr(content_item, "text") and content_item.text:
                    self.response_text = content_item.text.value
    
    def on_error(self, data: str) -> None:
        """Called when an error occurs."""
        self._send_event("error", {"message": data})
    
    def on_done(self) -> None:
        """Called when the stream is complete."""
        self._send_event("done", {"message": "Agent completed"})
    
    def on_unhandled_event(self, event_type: str, event_data: Any) -> None:
        """Handle any events not covered by other methods."""
        pass


def get_project_client() -> AIProjectClient:
    """Create and return an AIProjectClient."""
    endpoint = os.getenv("PROJECT_ENDPOINT")
    if not endpoint:
        raise ValueError("PROJECT_ENDPOINT environment variable is required")
    return AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())


def get_agent_id() -> str:
    """Get the agent ID from environment or file."""
    agent_id = os.getenv("AGENT_ID")
    if agent_id:
        return agent_id
    
    agent_id_file = Path(".agent_id")
    if agent_id_file.exists():
        return agent_id_file.read_text(encoding="utf-8").strip()
    
    raise ValueError("No agent ID found. Run 'make create-agent' first.")


def extract_blocks(content: str) -> tuple[str, str]:
    """Extract TSG and questions blocks from agent response."""
    def between(s: str, start: str, end: str) -> str:
        i = s.find(start)
        j = s.find(end)
        if i == -1 or j == -1 or j <= i:
            return ""
        return s[i + len(start) : j].strip()

    return between(content, TSG_BEGIN, TSG_END), between(content, QUESTIONS_BEGIN, QUESTIONS_END)


def run_agent_with_streaming(
    project: AIProjectClient, 
    thread_id: str, 
    agent_id: str,
    event_queue: queue.Queue
) -> str:
    """Run the agent with streaming and queue events for SSE."""
    handler = SSEEventHandler(event_queue)
    
    with project.agents.runs.stream(
        thread_id=thread_id,
        agent_id=agent_id,
        event_handler=handler
    ) as stream:
        stream.until_done()
    
    return handler.response_text


def run_agent_and_get_response(project: AIProjectClient, thread_id: str, agent_id: str) -> str:
    """Create a run, poll until complete, and return the assistant's response text (fallback)."""
    run = project.agents.runs.create(thread_id=thread_id, agent_id=agent_id)
    
    while run.status in ("queued", "in_progress", "requires_action"):
        time.sleep(1)
        run = project.agents.runs.get(thread_id=thread_id, run_id=run.id)
    
    if run.status == "failed":
        error_msg = getattr(run, "last_error", None)
        raise RuntimeError(f"Agent run failed: {error_msg}")
    
    messages = project.agents.messages.list(thread_id=thread_id)
    
    for message in messages:
        if message.role == "assistant":
            text_parts = []
            for content_item in message.content:
                if hasattr(content_item, "text") and content_item.text:
                    text_parts.append(content_item.text.value)
            return "\n".join(text_parts)
    
    return ""


@app.route("/")
def index():
    """Serve the main page."""
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    """Check if the agent is configured and ready, with detailed setup status."""
    result = {
        "ready": False,
        "needs_setup": False,
        "config": {
            "has_env_file": False,
            "has_endpoint": False,
            "has_model": False,
            "has_bing": False,
        },
        "agent": {
            "exists": False,
            "id": None,
        },
        "error": None,
    }
    
    # Check .env file
    dotenv_path = find_dotenv()
    result["config"]["has_env_file"] = bool(dotenv_path)
    
    # Check environment variables
    endpoint = os.getenv("PROJECT_ENDPOINT")
    model = os.getenv("MODEL_DEPLOYMENT_NAME")
    bing = os.getenv("BING_CONNECTION_NAME")
    
    result["config"]["has_endpoint"] = bool(endpoint)
    result["config"]["has_model"] = bool(model)
    result["config"]["has_bing"] = bool(bing)
    
    # Check agent
    try:
        agent_id = get_agent_id()
        result["agent"]["exists"] = True
        result["agent"]["id"] = agent_id[:8] + "..." if agent_id else None
    except ValueError:
        result["agent"]["exists"] = False
    
    # Determine overall status
    config_complete = all([
        result["config"]["has_endpoint"],
        result["config"]["has_model"],
        result["config"]["has_bing"],
    ])
    
    if config_complete and result["agent"]["exists"]:
        result["ready"] = True
    elif not config_complete:
        result["needs_setup"] = True
        result["error"] = "Configuration incomplete. Please configure your Azure settings."
    else:
        result["needs_setup"] = True
        result["error"] = "Agent not created. Please create the agent first."
    
    return jsonify(result)


@app.route("/api/validate")
def api_validate():
    """Run validation checks and return structured results."""
    checks = []
    
    # 1. Check .env file
    dotenv_path = find_dotenv()
    checks.append({
        "name": ".env file",
        "passed": bool(dotenv_path),
        "message": f"Found at: {dotenv_path}" if dotenv_path else "Not found. Copy .env-sample to .env",
        "critical": True,
    })
    
    # 2. Check environment variables
    required_vars = [
        ("PROJECT_ENDPOINT", "Azure AI Foundry project endpoint"),
        ("MODEL_DEPLOYMENT_NAME", "Model deployment name (e.g., gpt-4.1)"),
        ("BING_CONNECTION_NAME", "Bing Search connection resource ID"),
    ]
    
    env_ok = True
    for var, desc in required_vars:
        value = os.getenv(var)
        if value:
            # Mask long values
            display = value[:40] + "..." if len(value) > 40 else value
            checks.append({
                "name": var,
                "passed": True,
                "message": display,
                "critical": True,
            })
        else:
            checks.append({
                "name": var,
                "passed": False,
                "message": f"Not set. {desc}",
                "critical": True,
            })
            env_ok = False
    
    # 3. Check Azure authentication (only if env vars are set)
    if env_ok:
        try:
            credential = DefaultAzureCredential()
            token = credential.get_token("https://cognitiveservices.azure.com/.default")
            checks.append({
                "name": "Azure Authentication",
                "passed": bool(token),
                "message": "Authenticated via DefaultAzureCredential",
                "critical": True,
            })
        except Exception as e:
            checks.append({
                "name": "Azure Authentication",
                "passed": False,
                "message": f"Failed: {str(e)[:100]}. Run 'az login' first.",
                "critical": True,
            })
            env_ok = False
    
    # 4. Check project connection (only if auth works)
    if env_ok:
        endpoint = os.getenv("PROJECT_ENDPOINT")
        try:
            project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
            with project:
                pass  # Just verify we can create the context
            checks.append({
                "name": "Project Connection",
                "passed": True,
                "message": "Connected successfully",
                "critical": True,
            })
        except Exception as e:
            checks.append({
                "name": "Project Connection",
                "passed": False,
                "message": f"Failed: {str(e)[:100]}",
                "critical": True,
            })
    
    # 5. Check agent ID (not critical)
    agent_id_file = Path(".agent_id")
    agent_id = os.getenv("AGENT_ID")
    if agent_id:
        checks.append({
            "name": "Agent ID",
            "passed": True,
            "message": f"From environment: {agent_id[:8]}...",
            "critical": False,
        })
    elif agent_id_file.exists():
        agent_id = agent_id_file.read_text(encoding="utf-8").strip()
        checks.append({
            "name": "Agent ID",
            "passed": True,
            "message": f"From .agent_id: {agent_id[:8]}...",
            "critical": False,
        })
    else:
        checks.append({
            "name": "Agent ID",
            "passed": False,
            "message": "Not found. Create an agent to continue.",
            "critical": False,
        })
    
    # Calculate overall status
    all_critical_passed = all(c["passed"] for c in checks if c["critical"])
    all_passed = all(c["passed"] for c in checks)
    
    return jsonify({
        "checks": checks,
        "all_passed": all_passed,
        "ready_for_agent": all_critical_passed,
    })


@app.route("/api/config", methods=["GET"])
def api_config_get():
    """Get current configuration values (masked for security)."""
    config = {
        "PROJECT_ENDPOINT": os.getenv("PROJECT_ENDPOINT", ""),
        "MODEL_DEPLOYMENT_NAME": os.getenv("MODEL_DEPLOYMENT_NAME", ""),
        "BING_CONNECTION_NAME": os.getenv("BING_CONNECTION_NAME", ""),
        "AGENT_NAME": os.getenv("AGENT_NAME", "TSG-Builder"),
    }
    return jsonify(config)


@app.route("/api/config", methods=["POST"])
def api_config_set():
    """Update configuration values in .env file."""
    data = request.get_json()
    
    # Find or create .env file
    dotenv_path = find_dotenv()
    if not dotenv_path:
        dotenv_path = Path(".env")
        # Create from sample if it exists
        sample_path = Path(".env-sample")
        if sample_path.exists():
            dotenv_path.write_text(sample_path.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            dotenv_path.touch()
        dotenv_path = str(dotenv_path.absolute())
    
    allowed_keys = ["PROJECT_ENDPOINT", "MODEL_DEPLOYMENT_NAME", "BING_CONNECTION_NAME", "AGENT_NAME"]
    updated = []
    
    for key in allowed_keys:
        if key in data:
            value = data[key].strip()
            set_key(dotenv_path, key, value)
            os.environ[key] = value  # Also update current process
            updated.append(key)
    
    # Reload environment
    load_dotenv(dotenv_path, override=True)
    
    return jsonify({
        "success": True,
        "updated": updated,
        "message": f"Updated {len(updated)} configuration value(s)",
    })


@app.route("/api/create-agent", methods=["POST"])
def api_create_agent():
    """Create the Azure AI Foundry agent."""
    # Validate required configuration
    endpoint = os.getenv("PROJECT_ENDPOINT")
    model = os.getenv("MODEL_DEPLOYMENT_NAME")
    conn_id = os.getenv("BING_CONNECTION_NAME")
    agent_name = os.getenv("AGENT_NAME", "TSG-Builder")
    
    missing = []
    if not endpoint:
        missing.append("PROJECT_ENDPOINT")
    if not model:
        missing.append("MODEL_DEPLOYMENT_NAME")
    if not conn_id:
        missing.append("BING_CONNECTION_NAME")
    
    if missing:
        return jsonify({
            "success": False,
            "error": f"Missing required configuration: {', '.join(missing)}",
        }), 400
    
    try:
        project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
        
        # Build tools list: Bing grounding + Microsoft Learn MCP
        tools = []
        
        # Bing grounding for web/doc lookup
        bing_tool = BingGroundingTool(connection_id=conn_id)
        tools.extend(bing_tool.definitions)
        
        # Microsoft Learn MCP for official documentation
        mcp_tool = McpTool(server_label="learn", server_url=LEARN_MCP_URL)
        tools.extend(mcp_tool.definitions)
        
        with project:
            agent = project.agents.create_agent(
                model=model,
                name=agent_name,
                instructions=AGENT_INSTRUCTIONS,
                tools=tools,
            )
        
        # Save agent ID
        Path(".agent_id").write_text(agent.id + "\n", encoding="utf-8")
        
        return jsonify({
            "success": True,
            "agent_id": agent.id,
            "agent_name": agent_name,
            "message": f"Agent '{agent_name}' created successfully!",
        })
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


def generate_sse_events(notes: str, thread_id: str | None = None, answers: str | None = None) -> Generator[str, None, None]:
    """Generator that yields SSE events during agent execution."""
    event_queue: queue.Queue = queue.Queue()
    result_holder = {"response": "", "error": None}
    
    def run_agent_thread():
        try:
            agent_id = get_agent_id()
            project = get_project_client()
            
            with project:
                if thread_id is None:
                    # New generation - create thread
                    thread = project.agents.threads.create()
                    current_thread_id = thread.id
                    
                    # Send thread ID to client
                    event_queue.put({
                        "type": "thread_created",
                        "data": {"thread_id": current_thread_id}
                    })
                    
                    # Build and send the initial prompt
                    user_content = build_user_prompt(notes, prior_tsg=None, user_answers=None)
                else:
                    current_thread_id = thread_id
                    user_content = answers
                
                project.agents.messages.create(
                    thread_id=current_thread_id,
                    role="user",
                    content=user_content,
                )
                
                # Run with streaming
                response_text = run_agent_with_streaming(
                    project, current_thread_id, agent_id, event_queue
                )
                
                result_holder["response"] = response_text
                result_holder["thread_id"] = current_thread_id
                
        except Exception as e:
            result_holder["error"] = str(e)
            event_queue.put({"type": "error", "data": {"message": str(e)}})
        finally:
            event_queue.put(None)  # Signal end of events
    
    # Start agent in background thread
    agent_thread = threading.Thread(target=run_agent_thread)
    agent_thread.start()
    
    # Yield SSE events as they arrive
    while True:
        try:
            event = event_queue.get(timeout=120)  # 2 minute timeout
            if event is None:
                break
            
            yield f"data: {json.dumps(event)}\n\n"
            
        except queue.Empty:
            # Send keepalive
            yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
    
    agent_thread.join()
    
    # Send final result
    if result_holder["error"]:
        yield f"data: {json.dumps({'type': 'error', 'data': {'message': result_holder['error']}})}\n\n"
    else:
        response_text = result_holder["response"]
        tsg_block, questions_block = extract_blocks(response_text)
        
        if not tsg_block:
            yield f"data: {json.dumps({'type': 'error', 'data': {'message': 'Agent did not produce a valid TSG', 'raw_response': response_text[:500]}})}\n\n"
        else:
            has_questions = questions_block and questions_block.strip() != "NO_MISSING"
            
            # Store session
            final_thread_id = result_holder.get("thread_id", thread_id)
            if final_thread_id:
                sessions[final_thread_id] = {
                    "notes": notes,
                    "current_tsg": tsg_block,
                    "questions": questions_block if has_questions else None,
                }
            
            yield f"data: {json.dumps({'type': 'result', 'data': {'thread_id': final_thread_id, 'tsg': tsg_block, 'questions': questions_block if has_questions else None, 'complete': not has_questions}})}\n\n"


@app.route("/api/generate/stream", methods=["POST"])
def api_generate_stream():
    """Start TSG generation with SSE streaming for real-time updates."""
    data = request.get_json()
    notes = data.get("notes", "").strip()
    
    if not notes:
        return jsonify({"error": "No notes provided"}), 400
    
    return Response(
        stream_with_context(generate_sse_events(notes)),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@app.route("/api/answer/stream", methods=["POST"])
def api_answer_stream():
    """Submit answers with SSE streaming for real-time updates."""
    data = request.get_json()
    thread_id = data.get("thread_id")
    answers = data.get("answers", "").strip()
    
    if not thread_id or thread_id not in sessions:
        return jsonify({"error": "Invalid or expired session"}), 400
    
    if not answers:
        return jsonify({"error": "No answers provided"}), 400
    
    notes = sessions[thread_id].get("notes", "")
    
    return Response(
        stream_with_context(generate_sse_events(notes, thread_id, answers)),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """Start TSG generation from notes."""
    data = request.get_json()
    notes = data.get("notes", "").strip()
    
    if not notes:
        return jsonify({"error": "No notes provided"}), 400
    
    try:
        agent_id = get_agent_id()
        project = get_project_client()
        
        with project:
            # Create a new thread
            thread = project.agents.threads.create()
            thread_id = thread.id
            
            # Build and send the initial prompt
            user_content = build_user_prompt(notes, prior_tsg=None, user_answers=None)
            project.agents.messages.create(
                thread_id=thread_id,
                role="user",
                content=user_content,
            )
            
            # Run the agent
            assistant_text = run_agent_and_get_response(project, thread_id, agent_id)
            
            tsg_block, questions_block = extract_blocks(assistant_text)
            
            if not tsg_block:
                return jsonify({
                    "error": "Agent did not produce a valid TSG; please retry. Ensure you're using a model sophisticated enough to follow detailed instructions.",
                    "raw_response": assistant_text[:500]
                }), 500
            
            # Determine if there are follow-up questions
            has_questions = questions_block and questions_block.strip() != "NO_MISSING"
            
            # Store session for potential follow-up
            sessions[thread_id] = {
                "notes": notes,
                "current_tsg": tsg_block,
                "questions": questions_block if has_questions else None,
            }
            
            return jsonify({
                "thread_id": thread_id,
                "tsg": tsg_block,
                "questions": questions_block if has_questions else None,
                "complete": not has_questions,
            })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/answer", methods=["POST"])
def api_answer():
    """Submit answers to follow-up questions."""
    data = request.get_json()
    thread_id = data.get("thread_id")
    answers = data.get("answers", "").strip()
    
    if not thread_id or thread_id not in sessions:
        return jsonify({"error": "Invalid or expired session"}), 400
    
    if not answers:
        return jsonify({"error": "No answers provided"}), 400
    
    try:
        agent_id = get_agent_id()
        project = get_project_client()
        session = sessions[thread_id]
        
        with project:
            # Add answers as next message
            project.agents.messages.create(
                thread_id=thread_id,
                role="user",
                content=answers,
            )
            
            # Run the agent again
            assistant_text = run_agent_and_get_response(project, thread_id, agent_id)
            
            tsg_block, questions_block = extract_blocks(assistant_text)
            
            if not tsg_block:
                return jsonify({
                    "error": "Agent did not produce a valid TSG on refinement",
                    "raw_response": assistant_text[:500]
                }), 500
            
            has_questions = questions_block and questions_block.strip() != "NO_MISSING"
            
            # Update session
            session["current_tsg"] = tsg_block
            session["questions"] = questions_block if has_questions else None
            
            return jsonify({
                "thread_id": thread_id,
                "tsg": tsg_block,
                "questions": questions_block if has_questions else None,
                "complete": not has_questions,
            })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/session/<thread_id>", methods=["DELETE"])
def api_delete_session(thread_id):
    """Clean up a session."""
    if thread_id in sessions:
        del sessions[thread_id]
    return jsonify({"success": True})


def main():
    """Run the Flask development server."""
    # Check configuration before starting
    endpoint = os.getenv("PROJECT_ENDPOINT")
    if not endpoint:
        print("WARNING: PROJECT_ENDPOINT not set. The app will start but won't be functional.")
        print("Please configure your .env file and restart.")
    
    try:
        agent_id = get_agent_id()
        print(f"Agent ID: {agent_id[:8]}...")
    except Exception as e:
        print(f"WARNING: {e}")
        print("Run 'make create-agent' to create an agent before using the UI.")
    
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    
    print(f"\n🚀 TSG Builder UI starting at http://localhost:{port}")
    print("Press Ctrl+C to stop\n")
    
    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    main()
