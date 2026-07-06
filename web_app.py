#!/usr/bin/env python3
"""
web_app.py — Simple Flask web UI for TSG Builder.

Provides an easy-to-use web interface for generating TSGs from notes.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import sys

# --- Immediate startup feedback for compiled executable ---
if getattr(sys, 'frozen', False):
    print("TSG Builder is starting...", flush=True)

import json
import os
import subprocess
import threading
import queue
import uuid
import webbrowser
from pathlib import Path
from typing import Any, Generator

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from dotenv import load_dotenv, set_key
from azure.core.exceptions import (
    HttpResponseError,
    ClientAuthenticationError,
    ServiceRequestError,
    ResourceNotFoundError,
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
)
from error_utils import classify_azure_sdk_error, classify_model, ModelTier
from pii_check import check_for_pii
from version import APP_VERSION, GITHUB_URL, GITHUB_API_LATEST
import telemetry

if getattr(sys, 'frozen', False):
    print("Starting web server...", flush=True)

# Microsoft Learn MCP URL for agent creation
LEARN_MCP_URL = "https://learn.microsoft.com/api/mcp"

AGENT_DEFINITION_CONTRACT_VERSION = "2026-07-06.1"
AGENT_ROLES = ("researcher", "writer", "reviewer")
AGENT_REQUIRED_FIELDS = ("name", "version", "id")
MAX_IMAGES_PER_REQUEST = 10
ALLOWED_IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})

# ---------------------------------------------------------------------------
# Version check (background, fail-silent)
# ---------------------------------------------------------------------------

_latest_version: str | None = None
_update_url: str | None = None
_update_check_done: bool = False


def _is_newer(latest: str, current: str) -> bool:
    """Return True if *latest* is strictly newer than *current* (semver).

    Compares major.minor.patch integers.  Pre-release suffixes (e.g. -beta.1)
    are treated as older than the same version without a suffix.
    Malformed input returns False (safe default).
    """
    import re
    _semver_re = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-(.+))?$")
    m_latest = _semver_re.match(latest.strip())
    m_current = _semver_re.match(current.strip())
    if not m_latest or not m_current:
        return False
    l_tuple = tuple(int(m_latest.group(i)) for i in (1, 2, 3))
    c_tuple = tuple(int(m_current.group(i)) for i in (1, 2, 3))
    if l_tuple != c_tuple:
        return l_tuple > c_tuple
    # Same numeric version — pre-release is older than stable
    l_pre = m_latest.group(4)
    c_pre = m_current.group(4)
    if c_pre and not l_pre:
        return True  # latest is stable, current is pre-release
    return False


def _check_for_updates() -> None:
    """Hit the GitHub releases API and cache the result.  Fail-silent."""
    global _latest_version, _update_url, _update_check_done
    try:
        # Opt-out via TSG_UPDATE_CHECK=0
        opt = os.getenv("TSG_UPDATE_CHECK", "1").strip().lower()
        if opt in ("0", "false", "no"):
            _update_check_done = True
            return

        import urllib.request
        req = urllib.request.Request(
            GITHUB_API_LATEST,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"TSGBuilder/{APP_VERSION}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        tag = data.get("tag_name", "").lstrip("v")
        if tag:
            _latest_version = tag
            _update_url = data.get("html_url", f"{GITHUB_URL}/releases")

            if _is_newer(tag, APP_VERSION):
                telemetry.track_event(
                    "update_available",
                    properties={
                        "current_version": APP_VERSION,
                        "latest_version": _latest_version,
                    },
                )
    except Exception:
        pass  # Network errors, rate limits, airgapped — all fine
    finally:
        _update_check_done = True


def _get_platform() -> str:
    """Detect the runtime platform for telemetry."""
    if sys.platform == "darwin":
        return "macos"
    elif sys.platform == "win32":
        return "windows"
    elif sys.platform == "linux":
        try:
            with open("/proc/version", "r", encoding="utf-8") as f:
                if "microsoft" in f.read().lower():
                    return "wsl2"
        except (FileNotFoundError, PermissionError):
            pass
        return "linux"
    return sys.platform


def _get_run_mode() -> str:
    """Detect whether running from source or as a compiled executable."""
    return "executable" if getattr(sys, "frozen", False) else "source"


def _extract_missing_sections(questions_content: str | None) -> list[str]:
    """Extract section names from MISSING placeholders in questions content."""
    import re
    if not questions_content or questions_content.strip() == "NO_MISSING":
        return []
    return re.findall(r'\{\{MISSING::([^:}]+)::', questions_content)


def _validate_images(images: Any) -> str | None:
    """Return an error message when an image payload is invalid."""
    if images is None:
        return None

    if not isinstance(images, list):
        return "Images must be a list"

    if len(images) > MAX_IMAGES_PER_REQUEST:
        return f"Maximum {MAX_IMAGES_PER_REQUEST} images allowed"

    for index, image in enumerate(images):
        if not isinstance(image, dict):
            return f"Image {index} must be an object"

        image_type = image.get("type")
        if not isinstance(image_type, str) or not image_type.strip():
            return f"Image {index} must include a MIME type"
        image_type = image_type.strip().lower()
        if image_type not in ALLOWED_IMAGE_TYPES:
            allowed = ", ".join(sorted(ALLOWED_IMAGE_TYPES))
            return f"Image {index} has unsupported MIME type '{image_type}'. Supported types: {allowed}"
        image["type"] = image_type

        image_data = image.get("data")
        if not isinstance(image_data, str) or not image_data.strip():
            return f"Image {index} must include base64 data"
        try:
            base64.b64decode(image_data, validate=True)
        except (binascii.Error, ValueError):
            return f"Image {index} has invalid base64 data"

    return None

# Default .env content (created automatically on first run)
# These provide sensible defaults; users still need to fill in their Azure-specific values
DEFAULT_ENV_CONTENT = """# Azure AI Foundry Configuration
# example: https://<YOUR_RESOURCE>.services.ai.azure.com/api/projects/<YOUR_PROJECT>
PROJECT_ENDPOINT=

# Supported non-chat deployments: gpt-5.1, gpt-5.2, gpt-5.4, gpt-5.5
MODEL_DEPLOYMENT_NAME=gpt-5.2

AGENT_NAME=TSG-Builder

# Set to 0 to disable update checks
# TSG_UPDATE_CHECK=0
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
    """Ensure .env file exists, creating from defaults if needed.
    
    Returns the path to the .env file.
    """
    app_dir = _get_app_dir()
    env_path = app_dir / ".env"
    
    if not env_path.exists():
        env_path.write_text(DEFAULT_ENV_CONTENT, encoding="utf-8")
        print(f"📝 Created {env_path}")
    
    return env_path


# Load existing environment variables without creating files at import time.
load_dotenv(_get_app_dir() / ".env")

# Check for test mode from environment variable
TEST_MODE = os.getenv("TSG_TEST_MODE", "").strip() in ("1", "true", "True", "yes")
if TEST_MODE:
    print("🧪 Test mode enabled - stage outputs will be captured to test_output_*.json")

# Configure Flask with proper paths for PyInstaller executable mode.
# In --onedir + --contents-directory mode, sys._MEIPASS points to the
# _internal/ subdirectory where PyInstaller places bundled data files
# (templates, static). sys.executable is in the parent (top-level) folder.
if getattr(sys, 'frozen', False):
    _bundle_dir = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    app = Flask(
        __name__,
        template_folder=_bundle_dir / 'templates',
        static_folder=_bundle_dir / 'static'
    )
else:
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
    if isinstance(error, (ClientAuthenticationError, ServiceRequestError,
                          ResourceNotFoundError, HttpResponseError)):
        user_msg, hint, _ = classify_azure_sdk_error(error)
        return (user_msg, hint)
    
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


def get_project_client() -> "AIProjectClient":
    """Create and return an AIProjectClient."""
    from azure.identity import DefaultAzureCredential
    from azure.ai.projects import AIProjectClient
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
    
    missing = [role for role in AGENT_ROLES if not data.get(role)]
    if missing:
        raise ValueError(f"Missing agent IDs: {', '.join(missing)}. Use Setup to recreate agents.")

    for role in AGENT_ROLES:
        agent_info = data.get(role)
        if not isinstance(agent_info, dict):
            raise ValueError("Legacy agent configuration detected. Use Setup to recreate agents.")
        missing_fields = [field for field in AGENT_REQUIRED_FIELDS if not agent_info.get(field)]
        if missing_fields:
            raise ValueError(
                f"Incomplete {role} agent configuration. Use Setup to recreate agents."
            )
    
    return data


def get_agent_definition_signature(model_deployment_name: str, underlying_model_name: str | None = None) -> str:
    """Return the deterministic signature for the persisted agent definition."""
    payload = {
        "contract_version": AGENT_DEFINITION_CONTRACT_VERSION,
        "model_deployment_name": model_deployment_name or "",
        "underlying_model_name": underlying_model_name or "",
        "learn_mcp_url": LEARN_MCP_URL,
        "stages": {
            "researcher": {
                "instructions": RESEARCH_STAGE_INSTRUCTIONS,
                "temperature": 0,
                "tools": [
                    {"type": "mcp", "server_label": "learn", "require_approval": "never"},
                    {"type": "web_search_preview", "search_context_size": "high"},
                ],
            },
            "writer": {
                "instructions": WRITER_STAGE_INSTRUCTIONS,
                "temperature": 0,
                "tools": [],
            },
            "reviewer": {
                "instructions": REVIEW_STAGE_INSTRUCTIONS,
                "temperature": 0,
                "tools": [],
            },
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _agent_metadata(model_deployment_name: str | None, underlying_model_name: str | None) -> dict[str, str]:
    """Build persisted metadata for setup-created agents."""
    model_name = model_deployment_name or ""
    underlying = underlying_model_name or ""
    return {
        "model_deployment_name": model_name,
        "underlying_model_name": underlying,
        "agent_definition_signature": get_agent_definition_signature(model_name, underlying),
    }


def _get_agent_readiness(
    agent_ids: dict,
    current_model_deployment_name: str | None = None,
    current_underlying_model_name: str | None = None,
) -> dict[str, Any]:
    """Compare persisted agent metadata with the current setup."""
    current_model = current_model_deployment_name or os.getenv("MODEL_DEPLOYMENT_NAME", "")
    metadata_keys = ("model_deployment_name", "underlying_model_name", "agent_definition_signature")
    missing_metadata = [key for key in metadata_keys if not str(agent_ids.get(key, "")).strip()]
    stored_model = str(agent_ids.get("model_deployment_name", "")).strip()
    stored_underlying = str(agent_ids.get("underlying_model_name", "")).strip()
    stored_signature = str(agent_ids.get("agent_definition_signature", "")).strip()
    signature_underlying = stored_underlying if current_underlying_model_name is None else current_underlying_model_name

    reasons: list[str] = []
    if missing_metadata:
        reasons.append("agent metadata is missing")
    model_changed = False
    if stored_model and current_model and stored_model != current_model:
        model_changed = True
        reasons.append(f"model changed from {stored_model} to {current_model}")
    if not missing_metadata and not model_changed:
        expected_signature = get_agent_definition_signature(current_model, signature_underlying)
        if stored_signature != expected_signature:
            reasons.append("agent definition changed")

    stale = bool(reasons)
    return {
        "ready": not stale,
        "stale": stale,
        "reasons": reasons,
        "agents_created_version": (agent_ids.get("app_version") or "unknown") if stale else None,
        "app_version": agent_ids.get("app_version"),
        "model_deployment_name": stored_model,
        "underlying_model_name": stored_underlying,
        "current_model_deployment_name": current_model,
    }


def _format_agent_recreate_message(readiness: dict[str, Any]) -> str:
    reason_items = readiness.get("reasons") or readiness.get("agents_stale_reasons") or []
    reasons = "; ".join(reason_items) or "agent setup changed"
    return f"Recreate agents to use the current setup ({reasons})."


def _get_generation_agent_blocker() -> str | None:
    """Return an error message when generation must not use persisted agents."""
    try:
        agent_ids = get_agent_ids()
    except ValueError as exc:
        return str(exc)

    current_model = os.getenv("MODEL_DEPLOYMENT_NAME", "")
    try:
        with get_project_client() as project:
            deployment = project.deployments.get(name=current_model)
            current_model = deployment.name
            current_underlying_model = getattr(deployment, "model_name", None) or ""
            classification = classify_model(current_underlying_model, deployment.name)
            if classification.tier == ModelTier.BLOCKED:
                return classification.message
    except Exception as exc:
        return f"Could not verify current model deployment before generation: {str(exc)[:120]}"

    readiness = _get_agent_readiness(agent_ids, current_model, current_underlying_model)
    if not readiness["ready"]:
        return _format_agent_recreate_message(readiness)
    return None


def save_agent_ids(
    researcher: dict,
    writer: dict,
    reviewer: dict,
    name_prefix: str,
    model_deployment_name: str | None = None,
    underlying_model_name: str | None = None,
):
    """Save all pipeline agent info to JSON file (v2 format with name/version/id)."""
    data = {
        "researcher": researcher,
        "writer": writer,
        "reviewer": reviewer,
        "name_prefix": name_prefix,
        "app_version": APP_VERSION,
        **_agent_metadata(model_deployment_name or os.getenv("MODEL_DEPLOYMENT_NAME", ""), underlying_model_name),
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
    
    result["config"]["has_endpoint"] = bool(endpoint)
    result["config"]["has_model"] = bool(model)
    
    # Check agents
    try:
        agent_ids = get_agent_ids()
        result["agents"]["configured"] = True
        for role in ["researcher", "writer", "reviewer"]:
            agent_info = agent_ids.get(role, "")
            result["agents"][role] = agent_info.get("name", "")[:20] + "..."
        result["agents"]["name_prefix"] = agent_ids.get("name_prefix")
        readiness = _get_agent_readiness(agent_ids, model)
        result["agents"]["agents_stale"] = readiness["stale"]
        result["agents"]["agents_ready"] = readiness["ready"]
        result["agents"]["agents_stale_reasons"] = readiness["reasons"]
        result["agents"]["agents_created_version"] = readiness["agents_created_version"]
        result["agents"]["model_deployment_name"] = readiness["model_deployment_name"]
        result["agents"]["current_model_deployment_name"] = readiness["current_model_deployment_name"]
    except ValueError as exc:
        result["agents"]["configured"] = False
        result["agents"]["error"] = str(exc)
    
    # Determine overall status
    config_complete = all([
        result["config"]["has_endpoint"],
        result["config"]["has_model"],
    ])
    
    agents_ready = result["agents"].get("configured") and result["agents"].get("agents_ready", True)
    if config_complete and agents_ready:
        result["ready"] = True
    elif not config_complete:
        result["needs_setup"] = True
        result["error"] = "Configuration incomplete. Please configure your Azure settings."
    elif result["agents"].get("agents_stale"):
        result["needs_setup"] = True
        result["error"] = _format_agent_recreate_message(result["agents"])
    else:
        result["needs_setup"] = True
        result["error"] = "Agents not created. Please run Setup to create agents."
    
    return jsonify(result)


@app.route("/api/about")
def api_about():
    """Return application information for the About dialog."""
    import azure.ai.projects
    
    # Get agent info
    agent_info = {}
    try:
        agent_ids = get_agent_ids()
        agent_info = {
            "name_prefix": agent_ids.get("name_prefix", ""),
            "researcher": agent_ids.get("researcher", {}).get("name", "") if isinstance(agent_ids.get("researcher"), dict) else "",
            "writer": agent_ids.get("writer", {}).get("name", "") if isinstance(agent_ids.get("writer"), dict) else "",
            "reviewer": agent_ids.get("reviewer", {}).get("name", "") if isinstance(agent_ids.get("reviewer"), dict) else "",
        }
    except ValueError:
        agent_info = {"configured": False}
    
    # Version check results (may still be in-flight on first About open)
    update_check_enabled = os.getenv("TSG_UPDATE_CHECK", "1").strip().lower() not in ("0", "false", "no")

    return jsonify({
        "app_name": "TSG Builder",
        "version": APP_VERSION,
        "python_version": sys.version.split()[0],
        "azure_sdk_version": azure.ai.projects.__version__,
        "endpoint": os.getenv("PROJECT_ENDPOINT", ""),
        "model": os.getenv("MODEL_DEPLOYMENT_NAME", ""),
        "agents": agent_info,
        "github_url": GITHUB_URL,
        "latest_version": _latest_version,
        "update_url": _update_url,
        "update_check_enabled": update_check_enabled,
    })


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
        ("MODEL_DEPLOYMENT_NAME", "Supported non-chat deployment name: gpt-5.1, gpt-5.2, gpt-5.4, or gpt-5.5"),
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
            from azure.identity import DefaultAzureCredential
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
    project_client = None
    if env_ok:
        endpoint = os.getenv("PROJECT_ENDPOINT")
        try:
            from azure.identity import DefaultAzureCredential
            from azure.ai.projects import AIProjectClient
            project_client = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
            with project_client:
                # Actually make an API call to verify the token works for this resource
                # This catches tenant mismatches that the auth check alone doesn't catch
                _ = list(project_client.agents.list(limit=1))
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
            project_client = None  # Can't proceed with deployment/connection checks
    
    # 5. Check model deployment exists and validate model compatibility
    # Uses shared classify_model() from error_utils for consistent tier logic.
    deployment_name = os.getenv("MODEL_DEPLOYMENT_NAME", "")
    validated_underlying_model = None
    if project_client and deployment_name:
        try:
            # Re-open project client for deployment check
            from azure.identity import DefaultAzureCredential
            from azure.ai.projects import AIProjectClient
            with AIProjectClient(endpoint=os.getenv("PROJECT_ENDPOINT"), credential=DefaultAzureCredential()) as project:
                deployment = project.deployments.get(name=deployment_name)
                underlying_model = getattr(deployment, "model_name", None) or ""
                validated_underlying_model = underlying_model

                classification = classify_model(underlying_model, deployment.name)

                checks.append({
                    "name": "Model Deployment",
                    "passed": classification.tier != ModelTier.BLOCKED,
                    "message": classification.message,
                    "critical": classification.critical,
                    "warning": False,
                })
        except Exception as e:
            error_str = str(e)
            # Try to list available deployments, filtered to compatible models only
            compatible_names = []
            try:
                from azure.identity import DefaultAzureCredential
                from azure.ai.projects import AIProjectClient
                with AIProjectClient(endpoint=os.getenv("PROJECT_ENDPOINT"), credential=DefaultAzureCredential()) as project:
                    for dep in project.deployments.list():
                        dep_model = getattr(dep, "model_name", None) or ""
                        dep_class = classify_model(dep_model, dep.name)
                        if dep_class.tier != ModelTier.BLOCKED:
                            compatible_names.append(dep.name)
            except Exception:
                pass
            
            if compatible_names:
                message = f"Deployment '{deployment_name}' not found. Compatible deployments: {', '.join(compatible_names[:5])}"
            elif "404" in error_str or "NotFound" in error_str:
                message = f"Deployment '{deployment_name}' not found in project"
            else:
                message = f"Could not verify deployment: {str(e)[:80]}"
            checks.append({
                "name": "Model Deployment",
                "passed": False,
                "message": message,
                "critical": False,  # Warning, not blocking
                "warning": False,
            })
    
    # 6. Check agent IDs (not critical) + staleness detection
    agents_stale = False
    agents_created_version = None
    pipeline_agents_ready = False
    agent_stale_reasons: list[str] = []
    try:
        agent_ids = get_agent_ids()
        prefix = agent_ids.get("name_prefix", "TSG")
        readiness = _get_agent_readiness(agent_ids, deployment_name, validated_underlying_model)
        agents_stale = readiness["stale"]
        pipeline_agents_ready = readiness["ready"]
        agents_created_version = readiness["agents_created_version"]
        agent_stale_reasons = readiness["reasons"]
        message = f"3 agents configured ({prefix})"
        if agents_stale:
            message += f" — {_format_agent_recreate_message(readiness)}"
        checks.append({
            "name": "Pipeline Agents",
            "passed": pipeline_agents_ready,
            "message": message,
            "critical": False,
            "warning": agents_stale,
        })
    except ValueError as exc:
        checks.append({
            "name": "Pipeline Agents",
            "passed": False,
            "message": str(exc),
            "critical": False,
        })
    
    # Calculate overall status
    all_critical_passed = all(c["passed"] for c in checks if c["critical"])
    all_passed = all(c["passed"] for c in checks)
    
    return jsonify({
        "checks": checks,
        "all_passed": all_passed,
        "ready_for_agent": all_critical_passed,
        "ready_for_generation": all_critical_passed and pipeline_agents_ready,
        "agents_stale": agents_stale,
        "agents_created_version": agents_created_version,
        "agent_stale_reasons": agent_stale_reasons,
    })


@app.route("/api/config", methods=["GET"])
def api_config_get():
    """Get current configuration values (masked for security)."""
    config = {
        "PROJECT_ENDPOINT": os.getenv("PROJECT_ENDPOINT", ""),
        "MODEL_DEPLOYMENT_NAME": os.getenv("MODEL_DEPLOYMENT_NAME", ""),
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
    
    allowed_keys = ["PROJECT_ENDPOINT", "MODEL_DEPLOYMENT_NAME", "AGENT_NAME"]
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


# _classify_azure_sdk_error moved to error_utils.py


@app.route("/api/create-agent", methods=["POST"])
def api_create_agent():
    """Create all three pipeline agents (Researcher, Writer, Reviewer)."""
    # Validate required configuration
    endpoint = os.getenv("PROJECT_ENDPOINT")
    model = os.getenv("MODEL_DEPLOYMENT_NAME")
    agent_name = os.getenv("AGENT_NAME", "TSG-Builder")
    
    missing = []
    if not endpoint:
        missing.append("PROJECT_ENDPOINT")
    if not model:
        missing.append("MODEL_DEPLOYMENT_NAME")
    
    if missing:
        return jsonify({
            "success": False,
            "error": f"Missing required configuration: {', '.join(missing)}",
        }), 400
    
    try:
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import PromptAgentDefinition, MCPTool, WebSearchPreviewTool
        project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
        
        # Gate: verify the deployment's underlying model is compatible before
        # creating agents. This prevents agents from being created on
        # unsupported models (for example sibling variants or gpt-4o).
        with project:
            deployment = project.deployments.get(name=model)
            underlying_model = getattr(deployment, "model_name", None) or ""
            classification = classify_model(underlying_model, deployment.name)
            if classification.tier == ModelTier.BLOCKED:
                return jsonify({
                    "success": False,
                    "error": classification.message,
                }), 400
        
        # Re-create client (prior context manager closed it)
        project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
        
        # Build tools for research agent (Web Search + MCP) - v2 patterns
        # WebSearchPreviewTool uses Microsoft-managed Bing — no connection ID required
        # search_context_size="high" allocates more context window for search results,
        # improving code extraction from community sources (GitHub, SO, etc.)
        web_search_tool = WebSearchPreviewTool(search_context_size="high")
        
        mcp_tool = MCPTool(
            server_label="learn",
            server_url=LEARN_MCP_URL,
            require_approval="never",
        )
        
        research_tools = [mcp_tool, web_search_tool]
        
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
            model_deployment_name=model,
            underlying_model_name=underlying_model,
        )
        
        # Telemetry: setup_completed
        telemetry.track_event(
            "setup_completed",
            properties={
                "version": APP_VERSION,
                "model_deployment": model or "",
            },
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
        user_message, hint, status_code = classify_azure_sdk_error(e)
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
        # Log the full error server-side but don't expose internals to client
        print(f"Agent creation unexpected error: {e}")
        return jsonify({
            "success": False,
            "error": "An unexpected error occurred during agent setup.",
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
    # Determine follow-up round (0 = initial generation)
    follow_up_round = 0
    if thread_id and thread_id in sessions:
        follow_up_round = sessions[thread_id].get("follow_up_round", 0) + 1
    
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
                prior_review=session_data.get("review_result"),  # Pass prior review for iteration context
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
            result_holder["raw_error"] = e  # Preserve for telemetry
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
        # Telemetry: pipeline_error (exception during pipeline run)
        raw_error = result_holder.get("raw_error")
        error_stage = "unknown"
        error_class = "unknown"
        if isinstance(raw_error, PipelineError):
            error_stage = raw_error.stage.value
            classification = classify_error(raw_error.original_error, raw_error.stage)
            if classification.is_rate_limit:
                error_class = "rate_limit"
            elif classification.is_timeout:
                error_class = "timeout"
            elif classification.is_auth_error:
                error_class = "auth"
            elif classification.is_tool_error:
                error_class = "tool_error"
            else:
                error_class = "other"
        telemetry.track_event(
            "pipeline_error",
            properties={
                "version": APP_VERSION,
                "stage": error_stage,
                "error_class": error_class,
            },
            measurements={
                "retry_count": 0,
            },
        )
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
                    "review_result": result.review_result,  # For iteration context in next round
                    "follow_up_round": follow_up_round,
                }
                sessions[result.thread_id] = session_data
            
            # Include review warnings if any (regardless of approved status)
            review_warnings = []
            if result.review_result:
                review_warnings = (
                    result.review_result.get("accuracy_issues", []) +
                    result.review_result.get("suggestions", [])
                )
            
            yield f"data: {json.dumps({'type': 'result', 'data': {'thread_id': result.thread_id, 'tsg': result.tsg_content, 'questions': result.questions_content if has_questions else None, 'complete': not has_questions, 'stages_completed': [s.value for s in result.stages_completed], 'retries': result.retry_count, 'warnings': review_warnings, 'follow_up_round': follow_up_round}})}\n\n"
            
            # Telemetry: tsg_generated
            missing_sections = _extract_missing_sections(result.questions_content)
            telemetry.track_event(
                "tsg_generated",
                properties={
                    "version": APP_VERSION,
                    "had_missing": str(has_questions),
                    "missing_sections": ",".join(missing_sections) if missing_sections else "",
                    "follow_up_round": str(follow_up_round),
                    "model": os.getenv("MODEL_DEPLOYMENT_NAME", ""),
                },
                measurements={
                    "duration_seconds": result.duration_seconds,
                    "research_duration_s": result.research_duration_s,
                    "write_duration_s": result.write_duration_s,
                    "review_duration_s": result.review_duration_s,
                    "missing_count": len(missing_sections),
                    "notes_line_count": result.notes_line_count,
                    "image_count": result.image_count,
                    "research_input_tokens": result.research_input_tokens,
                    "research_output_tokens": result.research_output_tokens,
                    "write_input_tokens": result.write_input_tokens,
                    "write_output_tokens": result.write_output_tokens,
                    "review_input_tokens": result.review_input_tokens,
                    "review_output_tokens": result.review_output_tokens,
                    "total_tokens": result.total_tokens,
                },
            )
        else:
            # Telemetry: pipeline_error (result returned but failed)
            error_stage = result.metadata.get("error_stage", "unknown")
            error_class = result.metadata.get("error_class", "unknown")
            telemetry.track_event(
                "pipeline_error",
                properties={
                    "version": APP_VERSION,
                    "stage": error_stage,
                    "error_class": error_class,
                },
                measurements={
                    "retry_count": result.retry_count,
                },
            )
            yield f"data: {json.dumps({'type': 'error', 'data': {'message': result.error or 'Pipeline failed to produce TSG', 'stages_completed': [s.value for s in result.stages_completed]}})}\n\n"


@app.route("/api/pii-check", methods=["POST"])
def api_pii_check():
    """Check notes for personally identifiable information (PII).
    
    Returns 200 with PII results (even when PII is found — that's a data response,
    not an error). Returns 500 when the PII service itself errors.
    """
    data = request.get_json()
    notes = data.get("notes", "").strip() if data else ""
    
    if not notes:
        return jsonify({"error": "No notes provided"}), 400
    
    result = check_for_pii(notes)
    
    # PII service error → 500
    if result["error"]:
        return jsonify({
            "error": result["error"],
            "hint": result["hint"],
        }), 500
    
    # Success (PII found or not) → 200
    return jsonify(result)


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
    
    # Defense-in-depth PII gate (frontend already checks, this prevents bypass)
    pii_result = check_for_pii(notes)
    if pii_result["error"]:
        return jsonify({"error": pii_result["error"], "hint": pii_result["hint"]}), 500
    if pii_result["pii_detected"]:
        telemetry.track_event(
            "pii_blocked",
            properties={
                "version": APP_VERSION,
                "action": "blocked",
                "input_type": "notes",
            },
            measurements={
                "entity_count": len(pii_result.get("findings", [])),
            },
        )
        return jsonify({"error": "PII detected in notes", "findings": pii_result["findings"]}), 400
    
    image_error = _validate_images(images)
    if image_error:
        return jsonify({"error": image_error}), 400

    agent_blocker = _get_generation_agent_blocker()
    if agent_blocker:
        return jsonify({"error": agent_blocker}), 400
    
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
    
    # Defense-in-depth PII gate on follow-up answers
    pii_result = check_for_pii(answers)
    if pii_result["error"]:
        return jsonify({"error": pii_result["error"], "hint": pii_result["hint"]}), 500
    if pii_result["pii_detected"]:
        telemetry.track_event(
            "pii_blocked",
            properties={
                "version": APP_VERSION,
                "action": "blocked",
                "input_type": "followup",
            },
            measurements={
                "entity_count": len(pii_result.get("findings", [])),
            },
        )
        return jsonify({"error": "PII detected in answers", "findings": pii_result["findings"]}), 400
    
    notes = sessions[thread_id].get("notes", "")

    agent_blocker = _get_generation_agent_blocker()
    if agent_blocker:
        return jsonify({"error": agent_blocker}), 400
    
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


@app.route("/api/telemetry/copied", methods=["POST"])
def api_telemetry_copied():
    """Record that the user copied or downloaded the TSG.
    
    Lightweight endpoint — always returns 204 regardless of telemetry state.
    """
    data = request.get_json(silent=True) or {}

    # Clamp/validate client-supplied values to prevent high-cardinality dimensions
    try:
        follow_up_round = max(0, min(int(data.get("follow_up_round", 0)), 20))
    except (TypeError, ValueError):
        follow_up_round = 0
    action = data.get("action", "copy") if data.get("action") in ("copy", "download") else "copy"

    telemetry.track_event(
        "tsg_copied",
        properties={
            "version": APP_VERSION,
            "follow_up_round": str(follow_up_round),
            "action": action,
        },
    )
    return "", 204


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
    env_file = _ensure_env_file()
    load_dotenv(env_file, override=False)

    # Initialize telemetry subsystem (background for speed, or instant if opted out)
    if not telemetry.is_telemetry_enabled():
        print("📊 Telemetry: disabled (opted out)")
    else:
        print("📊 Telemetry: initializing...")

        def _init_telemetry_background():
            telemetry.init_telemetry()

            # Report final status (matches the 3 outcomes from the old sync flow)
            if telemetry.is_active():
                print("📊 Telemetry: enabled", flush=True)
            else:
                print("📊 Telemetry: disabled (no connection string)", flush=True)

            import platform as _platform
            telemetry.track_event(
                "app_started",
                properties={
                    "version": APP_VERSION,
                    "platform": _get_platform(),
                    "python_version": _platform.python_version(),
                    "run_mode": _get_run_mode(),
                },
            )

        threading.Thread(
            target=_init_telemetry_background, daemon=True
        ).start()

    # Background version check (fail-silent, respects TSG_UPDATE_CHECK=0)
    threading.Thread(target=_check_for_updates, daemon=True).start()

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
                with open("/proc/version", "r", encoding="utf-8") as f:
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
