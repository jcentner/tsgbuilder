#!/usr/bin/env python3
"""
web_app.py — Simple Flask web UI for TSG Builder.

Provides an easy-to-use web interface for generating TSGs from notes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import queue
import uuid
import webbrowser
from pathlib import Path
from typing import Any, Generator

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from dotenv import load_dotenv, find_dotenv, set_key
from azure.identity import DefaultAzureCredential
from azure.core.exceptions import (
    HttpResponseError,
    ClientAuthenticationError,
    ServiceRequestError,
    ResourceNotFoundError,
)
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
from pipeline import (
    run_pipeline,
    CancelledError,
    classify_error,
    PipelineStage,
    PipelineError,
    # Hint constants for consistent messaging
    HINT_AUTH,
    HINT_PERMISSION,
    HINT_NOT_FOUND,
    HINT_RATE_LIMIT,
    HINT_TIMEOUT,
    HINT_CONNECTION,
    HINT_SERVICE_ERROR,
    HTTP_STATUS_MESSAGES,
)

# Microsoft Learn MCP URL for agent creation
LEARN_MCP_URL = "https://learn.microsoft.com/api/mcp"

# Default .env content (used when .env-sample is not available, e.g., in executable mode)
# These provide sensible defaults; users still need to fill in their Azure-specific values
DEFAULT_ENV_CONTENT = """# Azure AI Foundry Configuration
# example: https://<YOUR_RESOURCE>.services.ai.azure.com/api/projects/<YOUR_PROJECT>
PROJECT_ENDPOINT=

# from management center -> project -> connected resources
# example: /subscriptions/<SUB>/resourceGroups/<RG>/providers/Microsoft.CognitiveServices/accounts/<RESOURCE>/projects/<PROJECT>/connections/<CONNECTION>
BING_CONNECTION_NAME=

# recommend gpt-5.2 for v2 agents
MODEL_DEPLOYMENT_NAME=gpt-5.2

AGENT_NAME=TSG-Builder
"""


def _get_app_dir() -> Path:
    """Get the application directory (where .env and .agent_ids.json should live).
    
    For normal Python execution, this is the current working directory.
    For PyInstaller executables, this is the directory containing the executable.
    """
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller executable
        return Path(sys.executable).parent
    else:
        # Running as normal Python script
        return Path.cwd()


def _ensure_env_file() -> Path:
    """Ensure .env file exists, creating from .env-sample or defaults if needed.
    
    Returns the path to the .env file.
    """
    app_dir = _get_app_dir()
    env_path = app_dir / ".env"
    
    if not env_path.exists():
        # Try to copy from .env-sample first
        sample_path = app_dir / ".env-sample"
        if sample_path.exists():
            env_path.write_text(sample_path.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            # Use embedded defaults (for executable mode)
            env_path.write_text(DEFAULT_ENV_CONTENT, encoding="utf-8")
        print(f"📝 Created {env_path}")
    
    return env_path


# Load environment variables (create .env from defaults if needed)
_env_file = _ensure_env_file()
load_dotenv(_env_file)

# Check for test mode from environment variable
TEST_MODE = os.getenv("TSG_TEST_MODE", "").strip() in ("1", "true", "True", "yes")
if TEST_MODE:
    print("🧪 Test mode enabled - stage outputs will be captured to test_output_*.json")

app = Flask(__name__)


def _get_user_friendly_error(error: Exception) -> tuple[str, str | None]:
    """
    Convert a pipeline exception to a user-friendly error message with optional hint.
    
    Handles Azure SDK exceptions, PipelineError, and falls back to classify_error()
    for consistent messaging. Uses hint constants from pipeline.py for consistency.
    
    Returns:
        Tuple of (user_message, hint) where hint may be None.
    """
    # 1. Handle PipelineError (has stage info directly)
    if isinstance(error, PipelineError):
        stage = error.stage
        classification = classify_error(error.original_error, stage)
        message = classification.user_message
        
        # Use hint from classification (now includes hint field)
        hint = classification.hint
        
        # Make message more final (retries exhausted at this point)
        if 'Retrying' in message:
            message = message.replace('Retrying...', 'Please try again.')
            message = message.replace('Will retry...', 'Please try again.')
        
        return message, hint
    
    # 2. Handle Azure SDK exceptions (may come from non-pipeline code)
    if isinstance(error, ClientAuthenticationError):
        return ("Azure authentication failed.", HINT_AUTH)
    
    if isinstance(error, ServiceRequestError):
        return ("Cannot connect to Azure service.", HINT_CONNECTION)
    
    if isinstance(error, ResourceNotFoundError):
        return ("Azure resource not found.", HINT_NOT_FOUND)
    
    if isinstance(error, HttpResponseError):
        status_code = getattr(error, 'status_code', 500) or 500
        # Use HTTP_STATUS_MESSAGES for consistent messaging
        if status_code in HTTP_STATUS_MESSAGES:
            msg, _, hint = HTTP_STATUS_MESSAGES[status_code]
            return (f"{msg} ({status_code}).", hint)
        elif status_code >= 500:
            return (f"Azure service error ({status_code}).", HINT_SERVICE_ERROR)
    
    # 3. Fall back to string-based stage detection for other exceptions
    error_str = str(error).lower()
    
    if 'research' in error_str:
        stage = PipelineStage.RESEARCH
    elif 'write' in error_str:
        stage = PipelineStage.WRITE
    elif 'review' in error_str:
        stage = PipelineStage.REVIEW
    else:
        stage = PipelineStage.FAILED
    
    classification = classify_error(error, stage)
    
    # Use hint from classification
    hint = classification.hint
    
    # Make message more final (retries exhausted)
    message = classification.user_message
    if 'Retrying' in message:
        message = message.replace('Retrying...', 'Please try again.')
        message = message.replace('Will retry...', 'Please try again.')
    
    return message, hint


def _get_agent_ids_file() -> Path:
    """Get the agent IDs file path (in app directory)."""
    return _get_app_dir() / ".agent_ids.json"


# Store active sessions in memory (thread_id -> session data)
# Sessions only live while the server is running
sessions: dict[str, dict] = {}

# Track active runs for cancellation support
# Maps run_id -> threading.Event (set = cancelled)
active_runs: dict[str, threading.Event] = {}


def _is_valid_thread_id(thread_id: str) -> bool:
    """Validate thread_id format."""
    if not thread_id:
        return False
    return thread_id.replace("-", "").replace("_", "").isalnum()


def get_project_client() -> AIProjectClient:
    """Create and return an AIProjectClient."""
    endpoint = os.getenv("PROJECT_ENDPOINT")
    if not endpoint:
        raise ValueError("PROJECT_ENDPOINT environment variable is required")
    return AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())


def get_agent_ids() -> dict:
    """Get all pipeline agent info from JSON file.
    
    Returns dict with keys: researcher, writer, reviewer, name_prefix
    Each agent value is a dict with: name, version, id (v2 format)
    Raises ValueError if agents not configured.
    """
    agent_ids_file = _get_agent_ids_file()
    if not agent_ids_file.exists():
        raise ValueError("No agents configured. Use Setup to create agents.")
    
    data = json.loads(agent_ids_file.read_text(encoding="utf-8"))
    
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
    _get_agent_ids_file().write_text(json.dumps(data, indent=2), encoding="utf-8")


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
    
    # Check .env file (use app directory, works for both normal and executable mode)
    env_path = _get_app_dir() / ".env"
    result["config"]["has_env_file"] = env_path.exists()
    
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
    
    # 1. Check .env file (use app directory, works for both normal and executable mode)
    env_path = _get_app_dir() / ".env"
    checks.append({
        "name": ".env file",
        "passed": env_path.exists(),
        "message": f"Found at: {env_path}" if env_path.exists() else "Not found. Use Setup to create configuration.",
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
                # Actually make an API call to verify the token works for this resource
                # This catches tenant mismatches that the auth check alone doesn't catch
                _ = list(project.agents.list(limit=1))
            checks.append({
                "name": "Project Connection",
                "passed": True,
                "message": "Connected successfully",
                "critical": True,
            })
        except Exception as e:
            error_str = str(e).lower()
            # Check for tenant mismatch specifically
            if "tenant" in error_str and "does not match" in error_str:
                message = "Wrong subscription. Switch to the subscription containing your AI project."
            else:
                message = f"Failed: {str(e)[:100]}"
            checks.append({
                "name": "Project Connection",
                "passed": False,
                "message": message,
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
    
    # Use app directory for .env (works for both normal and executable mode)
    env_path = _ensure_env_file()
    dotenv_path = str(env_path)
    
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


def _classify_azure_sdk_error(error: Exception) -> tuple[str, str | None, int]:
    """Classify Azure SDK exceptions into user-friendly messages with hints.
    
    Uses shared constants from pipeline.py for consistent messaging across
    the codebase. Returns (user_message, hint, http_status_code).
    """
    # ClientAuthenticationError - credentials/auth issues
    if isinstance(error, ClientAuthenticationError):
        return ("Azure authentication failed.", HINT_AUTH, 401)
    
    # ServiceRequestError - network/connectivity issues
    if isinstance(error, ServiceRequestError):
        return ("Could not connect to Azure service.", HINT_CONNECTION, 0)
    
    # ResourceNotFoundError - resource doesn't exist
    if isinstance(error, ResourceNotFoundError):
        return ("Azure resource not found.", HINT_NOT_FOUND, 404)
    
    # HttpResponseError - general HTTP errors with status codes
    if isinstance(error, HttpResponseError):
        status_code = getattr(error, 'status_code', 500) or 500
        
        # Use shared HTTP_STATUS_MESSAGES for consistent messaging
        if status_code in HTTP_STATUS_MESSAGES:
            msg, _, hint = HTTP_STATUS_MESSAGES[status_code]
            return (f"{msg} ({status_code}).", hint, status_code)
        elif status_code >= 500:
            reason = getattr(error, 'reason', '') or ''
            return (f"Azure service error ({status_code} {reason}).", HINT_SERVICE_ERROR, status_code)
        else:
            # Other 4xx errors - use error message
            error_msg = str(error)
            if hasattr(error, 'message') and error.message:
                error_msg = error.message
            return (f"Request failed ({status_code}): {error_msg[:200]}", None, status_code)
    
    # Generic fallback for unknown exceptions
    return (f"Unexpected error: {str(error)[:200]}", None, 500)


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
        # Note: count limits the number of search results (default 5, max 50)
        # Limiting to 5 to reduce response time and token load
        bing_tool = BingGroundingAgentTool(
            bing_grounding=BingGroundingSearchToolParameters(
                search_configurations=[
                    BingGroundingSearchConfiguration(
                        project_connection_id=conn_id,
                        count=5,  # Limit search results to reduce latency
                    )
                ]
            )
        )
        
        mcp_tool = MCPTool(
            server_label="learn",
            server_url=LEARN_MCP_URL,
            require_approval="never",
        )
        
        research_tools = [mcp_tool, bing_tool]
        
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
    
    except (ClientAuthenticationError, ServiceRequestError, ResourceNotFoundError, HttpResponseError) as e:
        # Classify Azure SDK errors with user-friendly messages and hints
        user_message, hint, status_code = _classify_azure_sdk_error(e)
        response = {
            "success": False,
            "error": user_message,
            "error_type": type(e).__name__,
        }
        if hint:
            response["hint"] = hint
        # Use appropriate HTTP status (minimum 400 for errors)
        http_status = status_code if status_code >= 400 else 500
        return jsonify(response), http_status
    
    except Exception as e:
        # Generic fallback for unexpected errors
        return jsonify({
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "error_type": "UnexpectedError",
            "hint": "Check the server logs for more details.",
        }), 500


def generate_pipeline_sse_events(
    notes: str,
    thread_id: str | None = None,
    answers: str | None = None,
    images: list[dict] | None = None,
    run_id: str | None = None,
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
        run_id: Unique identifier for this run (for cancellation support)
    """
    # Generate run_id if not provided
    if not run_id:
        run_id = str(uuid.uuid4())
    
    # Create cancel event for this run
    cancel_event = threading.Event()
    active_runs[run_id] = cancel_event
    
    event_queue: queue.Queue = queue.Queue()
    result_holder: dict[str, Any] = {"result": None, "error": None, "cancelled": False}
    
    def run_pipeline_thread():
        try:
            # Get session data for follow-ups
            session_data = sessions.get(thread_id, {}) if thread_id else {}
            
            result = run_pipeline(
                notes=notes,
                images=images,
                event_queue=event_queue,
                thread_id=thread_id,
                prior_tsg=session_data.get("current_tsg"),
                prior_research=session_data.get("research_report"),  # Reuse research for follow-ups
                user_answers=answers,
                test_mode=TEST_MODE,
                cancel_event=cancel_event,
            )
            result_holder["result"] = result
        except CancelledError:
            result_holder["cancelled"] = True
            event_queue.put({"type": "cancelled", "data": {"message": "Run cancelled by user"}})
        except Exception as e:
            # Generate user-friendly error message with optional hint
            user_message, hint = _get_user_friendly_error(e)
            result_holder["error"] = user_message
            # Send user-friendly message to UI (fatal = all retries exhausted)
            error_data = {"message": user_message, "fatal": True}
            if hint:
                error_data["hint"] = hint
            event_queue.put({"type": "error", "data": error_data})
        finally:
            event_queue.put(None)  # Signal end of events
    
    # Start pipeline in background thread
    pipeline_thread = threading.Thread(target=run_pipeline_thread)
    pipeline_thread.start()
    
    # Send run_id to client immediately so it can cancel if needed
    yield f"data: {json.dumps({'type': 'run_started', 'data': {'run_id': run_id}})}\n\n"
    
    # Yield SSE events as they arrive
    try:
        while True:
            try:
                event = event_queue.get(timeout=30)  # 30s keepalive interval to prevent connection drops
                if event is None:
                    break
                
                yield f"data: {json.dumps(event)}\n\n"
                
            except queue.Empty:
                # Send keepalive to prevent connection timeout
                yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
    finally:
        # Clean up: remove from active runs when generator exits
        # (this happens when client disconnects or stream completes)
        active_runs.pop(run_id, None)
    
    pipeline_thread.join()
    
    # Send final result (unless cancelled)
    if result_holder["cancelled"]:
        yield f"data: {json.dumps({'type': 'cancelled', 'data': {'message': 'Run cancelled'}})}\n\n"
    elif result_holder["error"]:
        yield f"data: {json.dumps({'type': 'error', 'data': {'message': result_holder['error']}})}\n\n"
    elif result_holder["result"]:
        result = result_holder["result"]
        
        if result.success:
            has_questions = result.questions_content and result.questions_content.strip() != "NO_MISSING"
            
            # Store session in memory
            if result.thread_id:
                session_data = {
                    "notes": notes,
                    "current_tsg": result.tsg_content,
                    "questions": result.questions_content if has_questions else None,
                    "research_report": result.research_report,
                }
                sessions[result.thread_id] = session_data
            
            # Include review warnings if any (regardless of approved status)
            review_warnings = []
            if result.review_result:
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
    
    if not thread_id:
        return jsonify({"error": "No session ID provided"}), 400
    
    if not _is_valid_thread_id(thread_id):
        return jsonify({"error": "Invalid session ID format"}), 400
    
    if thread_id not in sessions:
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


@app.route("/api/cancel/<run_id>", methods=["POST"])
def api_cancel_run(run_id):
    """Cancel an active pipeline run.
    
    The run will stop at the next cancellation checkpoint (between stages or retries).
    Note: This cannot interrupt an in-flight Azure API call, but will prevent the next stage from starting.
    """
    # Validate run_id format (UUID)
    try:
        uuid.UUID(run_id)
    except ValueError:
        return jsonify({"error": "Invalid run ID format"}), 400
    
    cancel_event = active_runs.get(run_id)
    if not cancel_event:
        return jsonify({"error": "Run not found or already completed"}), 404
    
    # Set the cancel event - pipeline will check this at next checkpoint
    cancel_event.set()
    return jsonify({"success": True, "message": "Cancellation requested"})


@app.route("/api/session/<thread_id>", methods=["DELETE"])
def api_delete_session(thread_id):
    """Clean up a session from memory."""
    if not _is_valid_thread_id(thread_id):
        return jsonify({"error": "Invalid session ID format"}), 400
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


@app.route("/api/debug/threads")
def api_debug_threads():
    """Debug endpoint: show active threads and runs (only available in debug mode)."""
    # Only allow in debug mode
    if not app.debug:
        return jsonify({"error": "Debug endpoint not available in production"}), 403
    
    import threading
    threads = []
    for t in threading.enumerate():
        threads.append({
            "name": t.name,
            "daemon": t.daemon,
            "alive": t.is_alive(),
        })
    return jsonify({
        "thread_count": threading.active_count(),
        "threads": threads,
        "active_runs": list(active_runs.keys()),
        "sessions": list(sessions.keys()),
    })


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
    
    url = f"http://localhost:{port}"
    print(f"\n🚀 TSG Builder UI starting at {url}")
    print("Press Ctrl+C to stop\n")
    
    # Auto-open browser after a short delay (skip in debug mode reloader subprocess)
    # The JS checkStatus() has retry logic, so a short delay is fine
    if not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Timer(0.5, lambda: _open_browser(url)).start()
    
    # Listen on localhost only (not 0.0.0.0) for security
    app.run(host="127.0.0.1", port=port, debug=debug)


def _open_browser(url: str) -> None:
    """Open browser in a cross-platform way (Linux, macOS, Windows, WSL2)."""
    try:
        # Check if running in WSL2 by looking for WSL-specific indicators
        is_wsl = False
        if sys.platform == "linux":
            try:
                with open("/proc/version", "r") as f:
                    is_wsl = "microsoft" in f.read().lower()
            except (FileNotFoundError, PermissionError):
                pass
        
        if is_wsl:
            # WSL2: Use Windows' cmd.exe to open the browser
            # Replace localhost with the URL that Windows can access
            subprocess.run(
                ["cmd.exe", "/c", "start", url.replace("&", "^&")],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            # Native Linux, macOS, or Windows: use webbrowser module
            webbrowser.open(url)
    except Exception as e:
        # Silently fail - browser opening is a convenience, not critical
        print(f"Could not open browser automatically: {e}")
        print(f"Please open {url} manually.")


if __name__ == "__main__":
    main()
