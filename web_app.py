#!/usr/bin/env python3
"""
web_app.py — Simple Flask web UI for TSG Builder.

Provides an easy-to-use web interface for generating TSGs from notes.
"""

from __future__ import annotations

import json
import os
import threading
import queue
from pathlib import Path
from typing import Any, Generator

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from dotenv import load_dotenv, find_dotenv, set_key
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    PromptAgentDefinition,
    MCPTool,
    BingGroundingAgentTool,
    BingGroundingSearchToolParameters,
    BingGroundingSearchConfiguration,
)

from tsg_constants import (
    TSG_BEGIN,
    TSG_END,
    QUESTIONS_BEGIN,
    QUESTIONS_END,
    # Stage instructions for pipeline agents
    RESEARCH_STAGE_INSTRUCTIONS,
    WRITER_STAGE_INSTRUCTIONS,
    REVIEW_STAGE_INSTRUCTIONS,
)

# Import pipeline for multi-stage generation
from pipeline import run_pipeline

# Microsoft Learn MCP URL for agent creation
LEARN_MCP_URL = "https://learn.microsoft.com/api/mcp"

# Load environment variables
load_dotenv(find_dotenv())

# Check for test mode from environment variable
TEST_MODE = os.getenv("TSG_TEST_MODE", "").strip() in ("1", "true", "True", "yes")
if TEST_MODE:
    print("🧪 Test mode enabled - stage outputs will be captured to test_output_*.json")

app = Flask(__name__)

# Store active sessions (thread_id -> session data)
sessions: dict[str, dict] = {}


def get_project_client() -> AIProjectClient:
    """Create and return an AIProjectClient."""
    endpoint = os.getenv("PROJECT_ENDPOINT")
    if not endpoint:
        raise ValueError("PROJECT_ENDPOINT environment variable is required")
    return AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())


# Agent IDs JSON file path
AGENT_IDS_FILE = Path(".agent_ids.json")


def get_agent_ids() -> dict:
    """Get all pipeline agent info from JSON file.
    
    Returns dict with keys: researcher, writer, reviewer, name_prefix
    Each agent value is a dict with: name, version, id (v2 format)
    Raises ValueError if agents not configured.
    """
    if not AGENT_IDS_FILE.exists():
        raise ValueError("No agents configured. Use Setup to create agents.")
    
    data = json.loads(AGENT_IDS_FILE.read_text(encoding="utf-8"))
    
    required = ["researcher", "writer", "reviewer"]
    missing = [k for k in required if not data.get(k)]
    if missing:
        raise ValueError(f"Missing agent IDs: {', '.join(missing)}. Use Setup to recreate agents.")
    
    return data


def get_agent_id(agent_info) -> str | None:
    """Extract agent ID from v1 (string) or v2 (dict with 'id') format.
    
    Args:
        agent_info: Either a string (v1) or dict with 'id' key (v2)
    
    Returns:
        The agent ID string, or None if not found
    """
    if isinstance(agent_info, dict):
        return agent_info.get("id")
    return agent_info  # v1 format: direct string ID


def save_agent_ids(researcher: dict, writer: dict, reviewer: dict, name_prefix: str):
    """Save all pipeline agent info to JSON file (v2 format with name/version/id)."""
    data = {
        "researcher": researcher,
        "writer": writer,
        "reviewer": reviewer,
        "name_prefix": name_prefix,
    }
    AGENT_IDS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def extract_blocks(content: str) -> tuple[str, str]:
    """Extract TSG and questions blocks from agent response."""
    def between(s: str, start: str, end: str) -> str:
        i = s.find(start)
        j = s.find(end)
        if i == -1 or j == -1 or j <= i:
            return ""
        return s[i + len(start) : j].strip()

    return between(content, TSG_BEGIN, TSG_END), between(content, QUESTIONS_BEGIN, QUESTIONS_END)


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
        "agents": {
            "configured": False,
            "researcher": None,
            "writer": None,
            "reviewer": None,
            "name_prefix": None,
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
    
    # Check agents
    try:
        agent_ids = get_agent_ids()
        result["agents"]["configured"] = True
        # Handle v2 format (dict with name/version) vs v1 format (string ID)
        for role in ["researcher", "writer", "reviewer"]:
            agent_info = agent_ids.get(role, "")
            if isinstance(agent_info, dict):
                result["agents"][role] = agent_info.get("name", "")[:20] + "..."
            else:
                result["agents"][role] = str(agent_info)[:8] + "..."
        result["agents"]["name_prefix"] = agent_ids.get("name_prefix")
    except ValueError:
        result["agents"]["configured"] = False
    
    # Determine overall status
    config_complete = all([
        result["config"]["has_endpoint"],
        result["config"]["has_model"],
        result["config"]["has_bing"],
    ])
    
    if config_complete and result["agents"]["configured"]:
        result["ready"] = True
    elif not config_complete:
        result["needs_setup"] = True
        result["error"] = "Configuration incomplete. Please configure your Azure settings."
    else:
        result["needs_setup"] = True
        result["error"] = "Agents not created. Please run Setup to create agents."
    
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
        ("MODEL_DEPLOYMENT_NAME", "Model deployment name (e.g., gpt-5.2)"),
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
    
    # 5. Check agent IDs (not critical)
    try:
        agent_ids = get_agent_ids()
        prefix = agent_ids.get("name_prefix", "TSG")
        checks.append({
            "name": "Pipeline Agents",
            "passed": True,
            "message": f"3 agents configured ({prefix})",
            "critical": False,
        })
    except ValueError:
        checks.append({
            "name": "Pipeline Agents",
            "passed": False,
            "message": "Not found. Create agents to continue.",
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
    """Create all three pipeline agents (Researcher, Writer, Reviewer)."""
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
        
        # Build tools for research agent (Bing + MCP) - v2 patterns
        bing_tool = BingGroundingAgentTool(
            bing_grounding=BingGroundingSearchToolParameters(
                search_configurations=[
                    BingGroundingSearchConfiguration(
                        project_connection_id=conn_id
                    )
                ]
            )
        )
        
        mcp_tool = MCPTool(
            server_label="learn",
            server_url=LEARN_MCP_URL,
            require_approval="never",
        )
        
        research_tools = [bing_tool, mcp_tool]
        
        created_agents = {}
        
        with project:
            # Create Researcher agent (with tools) - v2 pattern
            researcher = project.agents.create_version(
                agent_name=f"{agent_name}-Researcher",
                definition=PromptAgentDefinition(
                    model=model,
                    instructions=RESEARCH_STAGE_INSTRUCTIONS,
                    tools=research_tools,
                    temperature=0,
                ),
            )
            created_agents["researcher"] = {"name": researcher.name, "version": researcher.version, "id": researcher.id}
            
            # Create Writer agent (no tools) - v2 pattern
            writer = project.agents.create_version(
                agent_name=f"{agent_name}-Writer",
                definition=PromptAgentDefinition(
                    model=model,
                    instructions=WRITER_STAGE_INSTRUCTIONS,
                    temperature=0,
                ),
            )
            created_agents["writer"] = {"name": writer.name, "version": writer.version, "id": writer.id}
            
            # Create Reviewer agent (no tools) - v2 pattern
            reviewer = project.agents.create_version(
                agent_name=f"{agent_name}-Reviewer",
                definition=PromptAgentDefinition(
                    model=model,
                    instructions=REVIEW_STAGE_INSTRUCTIONS,
                    temperature=0,
                ),
            )
            created_agents["reviewer"] = {"name": reviewer.name, "version": reviewer.version, "id": reviewer.id}
        
        # Save all agent IDs (v2 format with name + version)
        save_agent_ids(
            researcher=created_agents["researcher"],
            writer=created_agents["writer"],
            reviewer=created_agents["reviewer"],
            name_prefix=agent_name,
        )
        
        return jsonify({
            "success": True,
            "agents": {
                # Return v2 format (dict) - frontend handles display
                "researcher": created_agents["researcher"],
                "writer": created_agents["writer"],
                "reviewer": created_agents["reviewer"],
            },
            "agent_name": agent_name,
            "message": f"Created 3 pipeline agents: {agent_name}-Researcher, {agent_name}-Writer, {agent_name}-Reviewer",
        })
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


def build_message_content(text: str, images: list[dict] | None = None) -> list | str:
    """Build message content with text and optional images.
    
    Args:
        text: The text content of the message
        images: Optional list of image dicts with 'data' (base64) and 'type' (mime type) keys
        
    Returns:
        Either a string (text only) or list of content blocks (with images)
    """
    if not images:
        return text
    
    # Build content blocks: text first, then images
    content_blocks = [MessageInputTextBlock(text=text)]
    
    for img in images:
        # Construct data URL from base64 data
        mime_type = img.get("type", "image/png")
        base64_data = img.get("data", "")
        data_url = f"data:{mime_type};base64,{base64_data}"
        
        url_param = MessageImageUrlParam(url=data_url, detail="high")
        content_blocks.append(MessageInputImageUrlBlock(image_url=url_param))
    
    return content_blocks


def generate_pipeline_sse_events(
    notes: str,
    thread_id: str | None = None,
    answers: str | None = None,
    images: list[dict] | None = None
) -> Generator[str, None, None]:
    """Generator that yields SSE events during multi-stage pipeline execution.
    
    This is the new multi-stage pipeline that separates:
    1. Research: Gather docs/info using tools
    2. Write: Create TSG from notes + research
    3. Review: Validate and fix issues
    
    Args:
        notes: The troubleshooting notes text
        thread_id: Optional existing thread ID for follow-up
        answers: Optional answers to follow-up questions
        images: Optional list of image dicts with 'data' (base64) and 'type' (mime type)
    """
    event_queue: queue.Queue = queue.Queue()
    result_holder: dict[str, Any] = {"result": None, "error": None}
    
    def run_pipeline_thread():
        try:
            result = run_pipeline(
                notes=notes,
                images=images,
                event_queue=event_queue,
                thread_id=thread_id,
                prior_tsg=sessions.get(thread_id, {}).get("current_tsg") if thread_id else None,
                user_answers=answers,
                test_mode=TEST_MODE,
            )
            result_holder["result"] = result
        except Exception as e:
            result_holder["error"] = str(e)
            event_queue.put({"type": "error", "data": {"message": str(e)}})
        finally:
            event_queue.put(None)  # Signal end of events
    
    # Start pipeline in background thread
    pipeline_thread = threading.Thread(target=run_pipeline_thread)
    pipeline_thread.start()
    
    # Yield SSE events as they arrive
    while True:
        try:
            event = event_queue.get(timeout=30)  # 30s keepalive interval to prevent connection drops
            if event is None:
                break
            
            yield f"data: {json.dumps(event)}\n\n"
            
        except queue.Empty:
            # Send keepalive to prevent connection timeout
            yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
    
    pipeline_thread.join()
    
    # Send final result
    if result_holder["error"]:
        yield f"data: {json.dumps({'type': 'error', 'data': {'message': result_holder['error']}})}\n\n"
    elif result_holder["result"]:
        result = result_holder["result"]
        
        if result.success:
            has_questions = result.questions_content and result.questions_content.strip() != "NO_MISSING"
            
            # Store session
            if result.thread_id:
                sessions[result.thread_id] = {
                    "notes": notes,
                    "current_tsg": result.tsg_content,
                    "questions": result.questions_content if has_questions else None,
                    "research_report": result.research_report,
                }
            
            # Include review warnings if any
            review_warnings = []
            if result.review_result and not result.review_result.get("approved", True):
                review_warnings = (
                    result.review_result.get("accuracy_issues", []) +
                    result.review_result.get("suggestions", [])
                )
            
            yield f"data: {json.dumps({'type': 'result', 'data': {'thread_id': result.thread_id, 'tsg': result.tsg_content, 'questions': result.questions_content if has_questions else None, 'complete': not has_questions, 'stages_completed': [s.value for s in result.stages_completed], 'retries': result.retry_count, 'warnings': review_warnings}})}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'error', 'data': {'message': result.error or 'Pipeline failed to produce TSG', 'stages_completed': [s.value for s in result.stages_completed]}})}\n\n"


@app.route("/api/generate/stream", methods=["POST"])
def api_generate_stream():
    """Start TSG generation with SSE streaming for real-time updates.
    
    Accepts JSON with:
        - notes: str - The troubleshooting notes text (required)
        - images: list[dict] - Optional list of images, each with:
            - data: str - Base64-encoded image data (without data URL prefix)
            - type: str - MIME type (e.g., "image/png", "image/jpeg")
    """
    data = request.get_json()
    notes = data.get("notes", "").strip()
    images = data.get("images", None)  # List of {data: base64, type: mime_type}
    
    if not notes:
        return jsonify({"error": "No notes provided"}), 400
    
    # Validate images if provided
    if images:
        if not isinstance(images, list):
            return jsonify({"error": "Images must be a list"}), 400
        for i, img in enumerate(images):
            if not isinstance(img, dict) or "data" not in img:
                return jsonify({"error": f"Image {i} must have 'data' field"}), 400
            # Default type to png if not specified
            if "type" not in img:
                img["type"] = "image/png"
    
    return Response(
        stream_with_context(generate_pipeline_sse_events(notes, images=images)),
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
        stream_with_context(generate_pipeline_sse_events(notes, thread_id, answers)),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@app.route("/api/session/<thread_id>", methods=["DELETE"])
def api_delete_session(thread_id):
    """Clean up a session."""
    if thread_id in sessions:
        del sessions[thread_id]
    return jsonify({"success": True})


@app.route("/api/example")
def api_example():
    """Return the example input file content."""
    example_path = Path("examples/capability-host-input.txt")
    if not example_path.exists():
        return jsonify({"error": "Example file not found"}), 404
    
    content = example_path.read_text(encoding="utf-8")
    return jsonify({"content": content})


def main():
    """Run the Flask development server."""
    # Check configuration before starting
    endpoint = os.getenv("PROJECT_ENDPOINT")
    if not endpoint:
        print("WARNING: PROJECT_ENDPOINT not set. The app will start but won't be functional.")
        print("Please configure your .env file and restart.")
    
    try:
        agent_ids = get_agent_ids()
        prefix = agent_ids.get("name_prefix", "TSG")
        print(f"Pipeline agents: 3 configured ({prefix})")
    except Exception as e:
        print(f"WARNING: {e}")
        print("Use the Setup wizard in the web UI to create agents.")
    
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    
    print(f"\n🚀 TSG Builder UI starting at http://localhost:{port}")
    print("Press Ctrl+C to stop\n")
    
    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    main()
