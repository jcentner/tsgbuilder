#!/usr/bin/env python3
"""
pipeline.py — Multi-stage TSG generation pipeline.

Orchestrates the Research → Write → Review stages for high-quality TSG generation.
"""

from __future__ import annotations

import os
import queue
import sys
import time
import threading
import httpx
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

from tsg_constants import (
    # Markers
    TSG_BEGIN,
    TSG_END,
    QUESTIONS_BEGIN,
    QUESTIONS_END,
    # Template
    TSG_TEMPLATE,
    # Stage instructions
    RESEARCH_STAGE_INSTRUCTIONS,
    WRITER_STAGE_INSTRUCTIONS,
    REVIEW_STAGE_INSTRUCTIONS,
    # Prompt builders
    build_research_prompt,
    build_writer_prompt,
    build_review_prompt,
    # Validation
    validate_tsg_output,
    extract_research_block,
    extract_review_block,
)


# =============================================================================
# VERBOSE LOGGING SETUP
# =============================================================================
# When PIPELINE_VERBOSE=1, logs go to both console and a file with incrementing
# numbers (logs/pipeline_001.log, logs/pipeline_002.log, etc.)
# =============================================================================

_verbose_logger: logging.Logger | None = None


def _get_verbose_logger() -> logging.Logger | None:
    """Get or create the verbose logger (only if PIPELINE_VERBOSE is enabled)."""
    global _verbose_logger
    
    if _verbose_logger is not None:
        return _verbose_logger
    
    verbose = os.getenv("PIPELINE_VERBOSE", "").lower() in ("1", "true", "yes")
    if not verbose:
        return None
    
    # Create logs directory
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Find next available log number
    existing_logs = list(logs_dir.glob("pipeline_*.log"))
    if existing_logs:
        numbers = []
        for log_file in existing_logs:
            try:
                num = int(log_file.stem.split("_")[1])
                numbers.append(num)
            except (IndexError, ValueError):
                pass
        next_num = max(numbers) + 1 if numbers else 1
    else:
        next_num = 1
    
    log_file = logs_dir / f"pipeline_{next_num:03d}.log"
    
    # Create logger
    logger = logging.getLogger("pipeline_verbose")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()  # Clear any existing handlers
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_format = logging.Formatter("[VERBOSE] %(message)s")
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # File handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)
    
    # Log startup info
    logger.info(f"Pipeline verbose logging started - {datetime.now().isoformat()}")
    logger.info(f"Log file: {log_file}")
    
    _verbose_logger = logger
    return logger


def verbose_log(message: str) -> None:
    """Log a message if verbose mode is enabled (to both console and file)."""
    logger = _get_verbose_logger()
    if logger:
        logger.debug(message)


class CancelledError(Exception):
    """Raised when a pipeline run is cancelled by the user."""
    pass


class ToolTimeoutError(Exception):
    """Raised when a tool call exceeds the timeout threshold."""
    def __init__(self, tool_name: str, elapsed: float, timeout: float):
        self.tool_name = tool_name
        self.elapsed = elapsed
        self.timeout = timeout
        super().__init__(f"Tool '{tool_name}' timed out after {elapsed:.0f}s (limit: {timeout}s)")


# =============================================================================
# TIMEOUT CONFIGURATION
# =============================================================================
# These values balance reliability with responsiveness:
#
# Normal agent completion: 30-60 seconds
# Slow but valid completion: 120+ seconds (should NOT timeout)
# Bing tool call expected: <30 seconds
# Truly stuck operation: Should timeout and retry
#
# The HTTP client has generous timeouts to avoid false "peer closed connection"
# errors. Tool-level hang detection catches stuck Bing/MCP calls separately.
# =============================================================================

# Tool-level timeout: max time for any single tool call (Bing, MCP, etc.)
# Set to 2 min because Bing is expected to complete in <30s
TOOL_CALL_TIMEOUT = 120


@dataclass
class ErrorClassification:
    """Classification of an error for retry logic and user messaging."""
    is_retryable: bool
    is_rate_limit: bool
    is_timeout: bool
    is_tool_error: bool
    user_message: str  # Human-friendly message for UI
    raw_error: str     # Original error for logging


def classify_error(error: Exception, stage: PipelineStage) -> ErrorClassification:
    """
    Classify an error for retry logic and user-friendly messaging.
    
    Centralizes all error categorization to avoid duplication across the pipeline.
    """
    error_str = str(error)
    error_lower = error_str.lower()
    stage_name = stage.value.capitalize()
    
    # Rate limit detection (429 errors)
    is_rate_limit = any(x in error_lower for x in ['429', 'rate limit', 'too many requests'])
    
    # Timeout detection (includes "peer closed connection" which is often a timeout symptom)
    is_timeout = (
        isinstance(error, ToolTimeoutError) or
        any(x in error_lower for x in [
            'timeout', 'timed out', 'peer closed', 'incomplete chunked',
            'connection', 'httpx'
        ])
    )
    
    # Tool-specific errors (MCP/Microsoft Learn or Bing)
    is_tool_error = any(x in error_lower for x in ['mcp', 'bing', 'learn.microsoft.com'])
    
    # Determine if retryable
    is_retryable = is_rate_limit or is_timeout or is_tool_error
    
    # Generate user-friendly message
    if isinstance(error, ToolTimeoutError):
        user_message = f"{stage_name}: {error.tool_name} timed out after {error.elapsed:.0f}s. Retrying..."
    elif is_rate_limit:
        if is_tool_error and 'mcp' in error_lower:
            user_message = f"{stage_name}: Microsoft Learn rate limited. Waiting to retry..."
        else:
            user_message = f"{stage_name}: Rate limited. Waiting to retry..."
    elif is_timeout:
        user_message = f"{stage_name} agent timed out. Retrying..."
    elif is_tool_error:
        if 'mcp' in error_lower or 'learn.microsoft.com' in error_lower:
            user_message = f"{stage_name}: Microsoft Learn error. Retrying..."
        elif 'bing' in error_lower:
            user_message = f"{stage_name}: Bing search error. Retrying..."
        else:
            user_message = f"{stage_name}: Tool error. Retrying..."
    else:
        # Non-retryable error - more descriptive message
        user_message = f"{stage_name} failed unexpectedly. Please try again."
    
    return ErrorClassification(
        is_retryable=is_retryable,
        is_rate_limit=is_rate_limit,
        is_timeout=is_timeout,
        is_tool_error=is_tool_error,
        user_message=user_message,
        raw_error=error_str,
    )


class PipelineStage(Enum):
    """Pipeline stage identifiers."""
    RESEARCH = "research"
    WRITE = "write"
    REVIEW = "review"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class StageResult:
    """Result from a single pipeline stage."""
    stage: PipelineStage
    success: bool
    output: str = ""
    error: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Final result from the complete pipeline."""
    success: bool
    tsg_content: str = ""
    questions_content: str = ""
    research_report: str = ""
    review_result: dict | None = None
    thread_id: str = ""
    error: str | None = None
    stages_completed: list[PipelineStage] = field(default_factory=list)
    retry_count: int = 0
    # Test mode: raw outputs from each stage
    stage_outputs: dict = field(default_factory=dict)


def _send_classified_error(send_event, stage_name: str, error_text: str) -> None:
    """
    Send a classified error event to the UI with user-friendly messaging.
    
    Uses the same classification logic as classify_error() but for string errors
    (used in streaming event processing where we don't have Exception objects).
    """
    error_lower = error_text.lower()
    
    # Rate limit detection
    is_rate_limit = any(x in error_lower for x in ['429', 'rate limit', 'too many requests'])
    
    # Timeout detection
    is_timeout = any(x in error_lower for x in [
        'timeout', 'timed out', 'peer closed', 'incomplete chunked', 'connection', 'httpx'
    ])
    
    # Tool-specific errors
    is_mcp = 'mcp' in error_lower or 'learn.microsoft.com' in error_lower
    is_bing = 'bing' in error_lower
    
    # Generate user-friendly message and choose icon
    if is_rate_limit:
        if is_mcp:
            message = f"{stage_name}: Microsoft Learn rate limited. Will retry..."
        else:
            message = f"{stage_name}: Rate limited. Will retry..."
        icon = "⏳"
        error_type = "rate_limit"
    elif is_timeout:
        message = f"{stage_name} timed out. Will retry..."
        icon = "⚠️"
        error_type = "timeout"
    elif is_mcp:
        message = f"{stage_name}: Microsoft Learn error. Will retry..."
        icon = "⚠️"
        error_type = "mcp_error"
    elif is_bing:
        message = f"{stage_name}: Bing search error. Will retry..."
        icon = "⚠️"
        error_type = "tool_error"
    else:
        # Truncate raw error for display
        truncated = error_text[:100] + "..." if len(error_text) > 100 else error_text
        message = f"{stage_name} error: {truncated}"
        icon = "❌"
        error_type = "unknown"
    
    send_event("error", {
        "message": f"{icon} {message}",
        "icon": icon,
        "error_type": error_type,
    })


def process_pipeline_v2_stream(
    event,
    event_queue: queue.Queue | None,
    stage: PipelineStage,
    response_text_parts: list[str],
    timing_context: dict | None = None,
) -> None:
    """Process a v2 streaming event for pipeline stages.
    
    Args:
        event: The streaming event from responses.create(stream=True)
        event_queue: Optional queue for SSE events (None for non-streaming)
        stage: Current pipeline stage
        response_text_parts: List to accumulate response text
        timing_context: Optional dict to track timing (keys: 'tool_start', 'stage_start')
    
    Set PIPELINE_VERBOSE=1 environment variable to log all events for debugging.
    """
    # Verbose logging for debugging hangs
    verbose = os.getenv("PIPELINE_VERBOSE", "").lower() in ("1", "true", "yes")
    
    event_type = getattr(event, 'type', None)
    stage_name = stage.value.capitalize()
    
    # Log all events when verbose mode is enabled
    if verbose:
        elapsed = 0.0
        if timing_context and 'stage_start' in timing_context:
            elapsed = time.time() - timing_context['stage_start']
        verbose_log(f"[{stage_name}][{elapsed:6.1f}s] {event_type}")
    
    # Stage-specific icons
    stage_icons = {
        "research": "🔍",
        "write": "✏️",
        "review": "🔎",
    }
    stage_icon = stage_icons.get(stage.value, "•")
    
    def send_event(event_type: str, data: dict):
        if event_queue:
            data["stage"] = stage.value
            event_queue.put({"type": event_type, "data": data})
    
    if event_type == "response.created":
        if timing_context is not None:
            timing_context['stage_start'] = time.time()
        send_event("status", {
            "status": "in_progress",
            "message": f"{stage_icon} {stage_name}: Processing...",
            "icon": stage_icon,
        })
    
    elif event_type == "response.in_progress":
        # Model is actively working
        elapsed = ""
        if timing_context and 'tool_end' in timing_context:
            # Time since last tool completed (model thinking time)
            thinking_time = time.time() - timing_context['tool_end']
            if thinking_time > 2:
                elapsed = f" ({thinking_time:.0f}s model processing)"
        send_event("status", {
            "status": "in_progress",
            "message": f"{stage_icon} {stage_name}: Model working...{elapsed}",
            "icon": stage_icon,
        })
    
    elif event_type == "response.output_text.delta":
        delta = getattr(event, 'delta', '')
        if delta:
            response_text_parts.append(delta)
            # Send periodic progress for long outputs (every ~500 chars)
            total_len = sum(len(p) for p in response_text_parts)
            if total_len % 500 < len(delta):
                send_event("progress", {
                    "message": f"{stage_icon} {stage_name}: Writing response... ({total_len:,} chars)",
                    "chars": total_len,
                })
    
    elif event_type == "response.output_item.added":
        item = getattr(event, 'item', None)
        if item and hasattr(item, 'type'):
            item_type = item.type
            
            # Debug: log all output_item.added events
            if verbose:
                verbose_log(f"[{stage_name}] output_item.added: type={item_type}, item={item}")
            
            # Track tool start time and name (include bing_grounding_call which is the actual Bing tool type)
            if timing_context is not None and item_type in ('mcp_call', 'web_search_call', 'bing_grounding_call', 'function_call'):
                timing_context['tool_start'] = time.time()
                # Store tool name for timeout error messages
                if item_type == 'mcp_call':
                    timing_context['tool_name'] = getattr(item, 'name', None) or 'Microsoft Learn'
                elif item_type in ('web_search_call', 'bing_grounding_call'):
                    timing_context['tool_name'] = 'Bing Search'
                else:
                    timing_context['tool_name'] = getattr(item, 'name', 'tool')
            
            if item_type == "mcp_call":
                # Try to get the MCP tool name from the item
                mcp_name = getattr(item, 'name', None) or "Microsoft Learn"
                send_event("tool", {
                    "type": "mcp",
                    "icon": "📚",
                    "name": mcp_name,
                    "message": f"📚 Calling {mcp_name}...",
                    "status": "running"
                })
            elif item_type in ("web_search_call", "bing_grounding_call"):
                # bing_grounding_call is the actual event type from Azure AI Foundry Bing tool
                # Try to get the search query
                query_hint = ""
                if hasattr(item, 'query'):
                    query_hint = f": {item.query[:50]}..." if len(getattr(item, 'query', '')) > 50 else f": {item.query}"
                send_event("tool", {
                    "type": "bing",
                    "icon": "🌐",
                    "name": "Bing Search",
                    "message": f"🌐 Bing Search{query_hint}",
                    "status": "running"
                })
            elif item_type == "function_call":
                func_name = getattr(item, 'name', 'function')
                send_event("tool", {
                    "type": "function",
                    "icon": "⚙️",
                    "name": func_name,
                    "message": f"⚙️ Calling {func_name}...",
                    "status": "running"
                })
            elif item_type == "message":
                # Model is generating a message response
                send_event("status", {
                    "status": "in_progress",
                    "message": f"{stage_icon} {stage_name}: Generating response...",
                    "icon": stage_icon,
                })
            else:
                # Log unknown item types for debugging
                send_event("status", {
                    "status": "in_progress", 
                    "message": f"{stage_icon} {stage_name}: Processing ({item_type})...",
                    "icon": stage_icon,
                })
    
    elif event_type == "response.output_item.done":
        item = getattr(event, 'item', None)
        if item and hasattr(item, 'type'):
            item_type = item.type
            
            # Calculate tool elapsed time and clear tool tracking
            tool_elapsed = ""
            if timing_context and 'tool_start' in timing_context:
                elapsed_sec = time.time() - timing_context['tool_start']
                tool_elapsed = f" ({elapsed_sec:.1f}s)"
                timing_context['tool_end'] = time.time()  # Track when tool finished for model thinking time
                # Clear tool tracking for next tool call
                timing_context.pop('tool_start', None)
                timing_context.pop('tool_name', None)
            
            if item_type == "mcp_call":
                mcp_name = getattr(item, 'name', None) or "Microsoft Learn"
                send_event("tool", {
                    "type": "mcp",
                    "icon": "✅",
                    "name": mcp_name,
                    "message": f"✅ {mcp_name} complete{tool_elapsed}",
                    "status": "completed"
                })
                # After tool completes, indicate model is processing results
                send_event("status", {
                    "status": "in_progress",
                    "message": f"{stage_icon} {stage_name}: Processing search results...",
                    "icon": stage_icon,
                })
            elif item_type in ("web_search_call", "bing_grounding_call"):
                send_event("tool", {
                    "type": "bing",
                    "icon": "✅",
                    "name": "Bing Search",
                    "message": f"✅ Bing Search complete{tool_elapsed}",
                    "status": "completed"
                })
                send_event("status", {
                    "status": "in_progress",
                    "message": f"{stage_icon} {stage_name}: Processing search results...",
                    "icon": stage_icon,
                })
            elif item_type == "function_call":
                func_name = getattr(item, 'name', 'function')
                send_event("tool", {
                    "type": "function",
                    "icon": "✅",
                    "name": func_name,
                    "message": f"✅ {func_name} complete{tool_elapsed}",
                    "status": "completed"
                })
            
            # Check for tool errors in the item
            if hasattr(item, 'error') and item.error:
                _send_classified_error(send_event, stage_name, str(item.error))
            if hasattr(item, 'status') and item.status == 'failed':
                error_detail = str(getattr(item, 'error', 'unknown'))
                _send_classified_error(send_event, stage_name, error_detail)
    
    elif event_type == "response.completed":
        send_event("status", {
            "status": "completed",
            "message": f"✅ {stage_name}: Complete",
            "icon": "✅",
        })
        # Get full output text if available
        if hasattr(event, 'response') and hasattr(event.response, 'output_text'):
            if event.response.output_text:
                response_text_parts.clear()
                response_text_parts.append(event.response.output_text)
    
    elif event_type == "response.failed":
        error_msg = "Unknown error"
        if hasattr(event, 'response') and hasattr(event.response, 'error'):
            error_msg = str(event.response.error)
        _send_classified_error(send_event, stage_name, error_msg)
    
    elif event_type == "error":
        # Handle error events that may occur during tool processing
        error_msg = getattr(event, 'message', None) or getattr(event, 'error', None) or str(event)
        _send_classified_error(send_event, stage_name, str(error_msg))
    
    elif event_type and event_type.startswith("error"):
        # Catch any other error-type events
        _send_classified_error(send_event, stage_name, str(event))


class TSGPipeline:
    """
    Multi-stage TSG generation pipeline.
    
    Stages:
    1. Research: Gather docs and information using tools
    2. Write: Create TSG from notes + research (no tools)
    3. Review: Validate structure and accuracy, auto-fix if possible
    
    Agents are created once during setup and reused across runs.
    """
    
    # Per-stage retry configuration
    STAGE_MAX_RETRIES = {
        PipelineStage.RESEARCH: 3,  # More retries due to tool flakiness (Bing, MCP)
        PipelineStage.WRITE: 2,
        PipelineStage.REVIEW: 2,
    }
    
    # Rate limit backoff: base seconds, multiplied by attempt number (30s, 60s, 90s)
    RATE_LIMIT_BACKOFF_BASE = 30
    
    # Review stage structure validation retries (separate from transient failure retries)
    REVIEW_STRUCTURE_MAX_RETRIES = 2
    
    def __init__(
        self,
        project_endpoint: str,
        researcher_agent_name: str,
        writer_agent_name: str,
        reviewer_agent_name: str,
        bing_connection_id: str | None = None,
        model_name: str | None = None,
        test_mode: bool = False,
        cancel_event: threading.Event | None = None,
    ):
        self.project_endpoint = project_endpoint
        # v2: store agent names instead of IDs
        self.researcher_agent_name = researcher_agent_name
        self.writer_agent_name = writer_agent_name
        self.reviewer_agent_name = reviewer_agent_name
        self.bing_connection_id = bing_connection_id
        self.model_name = model_name or os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-5.2")
        self.test_mode = test_mode
        self._cancel_event = cancel_event
        
        self._event_queue: queue.Queue | None = None
    
    def set_event_queue(self, event_queue: queue.Queue):
        """Set the event queue for SSE streaming."""
        self._event_queue = event_queue
    
    def _check_cancelled(self) -> None:
        """Check if the run has been cancelled, raise CancelledError if so."""
        if self._cancel_event and self._cancel_event.is_set():
            raise CancelledError("Run cancelled by user")
    
    def _send_stage_event(self, stage: PipelineStage, event_type: str, data: dict):
        """Send a stage-specific event."""
        if self._event_queue:
            data["stage"] = stage.value
            self._event_queue.put({"type": event_type, "data": data})
    
    def _get_project_client(self) -> AIProjectClient:
        """Create a project client."""
        return AIProjectClient(
            endpoint=self.project_endpoint,
            credential=DefaultAzureCredential()
        )
    
    def _run_stage(
        self,
        project: AIProjectClient,
        openai_client,
        agent_name: str,
        stage: PipelineStage,
        user_message: str,
        conversation_id: str | None = None,
    ) -> tuple[str, str]:
        """
        Run a single pipeline stage using v2 responses API.
        
        Args:
            project: AIProjectClient instance
            openai_client: OpenAI client from project.get_openai_client()
            agent_name: Name of the agent to run
            stage: Current pipeline stage
            user_message: User prompt for this stage
            conversation_id: Optional existing conversation ID
        
        Returns: (response_text, conversation_id)
        """
        response_text_parts: list[str] = []
        timing_context: dict = {}  # Track timing for tool calls and model processing
        
        try:
            # Build kwargs for responses.create
            stream_kwargs = {
                "stream": True,
                "input": user_message,
                "extra_body": {
                    "agent": {
                        "name": agent_name,
                        "type": "agent_reference"
                    }
                }
            }
            
            if conversation_id:
                stream_kwargs["extra_body"]["conversation"] = conversation_id
            
            # Verbose logging for debugging hangs
            verbose = os.getenv("PIPELINE_VERBOSE", "").lower() in ("1", "true", "yes")
            
            # Stream the response
            stream_response = openai_client.responses.create(**stream_kwargs)
            
            event_count = 0
            last_event_time = time.time()
            last_event_type = None
            
            for event in stream_response:
                event_count += 1
                now = time.time()
                wait_time = now - last_event_time
                event_type = getattr(event, 'type', None)
                
                # Check for tool timeout (tool started but not finished within threshold)
                if 'tool_start' in timing_context and 'tool_end' not in timing_context:
                    tool_elapsed = now - timing_context['tool_start']
                    if tool_elapsed > TOOL_CALL_TIMEOUT:
                        tool_name = timing_context.get('tool_name', 'unknown tool')
                        raise ToolTimeoutError(tool_name, tool_elapsed, TOOL_CALL_TIMEOUT)
                
                # Log when we've been waiting a long time for an event
                if verbose and wait_time > 5:
                    verbose_log(f"[{stage.value}] ⚠️ Long wait: {wait_time:.1f}s after event #{event_count-1} ({last_event_type})")
                
                if verbose:
                    verbose_log(f"[{stage.value}] Event #{event_count}: {event_type} (waited {wait_time:.1f}s)")
                
                last_event_time = now
                last_event_type = event_type
                
                process_pipeline_v2_stream(
                    event, 
                    self._event_queue, 
                    stage, 
                    response_text_parts,
                    timing_context,
                )
                
                # Capture conversation ID or response ID for session persistence
                # The v2 API uses either:
                # 1. conversation_id (if a conversation was explicitly created)
                # 2. response.id (if no conversation was created, the response ID can be used to continue)
                if not conversation_id and event_type == "response.created":
                    if hasattr(event, 'response'):
                        # Try conversation_id first (explicit conversation)
                        conv_id = getattr(event.response, 'conversation_id', None)
                        if conv_id:
                            conversation_id = conv_id
                            if verbose:
                                verbose_log(f"[{stage.value}] Captured conversation_id: {conv_id}")
                        else:
                            # Fall back to response.id for stateful continuation
                            resp_id = getattr(event.response, 'id', None)
                            if resp_id:
                                conversation_id = resp_id
                                if verbose:
                                    verbose_log(f"[{stage.value}] Captured response.id as session ID: {resp_id}")
            
            if verbose:
                verbose_log(f"[{stage.value}] ✅ Stream complete: {event_count} events")
            
            return "".join(response_text_parts), conversation_id or ""
            
        except Exception as e:
            # Don't send error event here - let the caller's retry logic decide
            # whether this is a retryable error or a fatal error
            raise RuntimeError(f"Stage {stage.value} failed: {e}") from e
    
    def _run_stage_with_retry(
        self,
        project: AIProjectClient,
        openai_client,
        agent_name: str,
        stage: PipelineStage,
        prompt: str,
        conversation_id: str | None = None,
    ) -> tuple[str, str]:
        """
        Run a stage with automatic retry on transient failures.
        
        Uses classify_error() for consistent error handling across all stages.
        
        Args:
            project: AIProjectClient instance
            openai_client: OpenAI client
            agent_name: Name of the agent to run
            stage: Current pipeline stage
            prompt: User prompt for this stage
            conversation_id: Optional existing conversation ID
        
        Returns: (response_text, conversation_id)
        
        Raises:
            CancelledError: If the run was cancelled
            RuntimeError: If all retries are exhausted
        """
        max_retries = self.STAGE_MAX_RETRIES.get(stage, 2)
        last_error: Exception | None = None
        
        for attempt in range(max_retries + 1):
            self._check_cancelled()
            
            try:
                if attempt > 0:
                    self._send_stage_event(stage, "status", {
                        "message": f"🔄 {stage.value.capitalize()}: Retrying (attempt {attempt + 1}/{max_retries + 1})...",
                        "icon": "🔄",
                    })
                
                return self._run_stage(
                    project, openai_client, agent_name, stage, prompt, conversation_id
                )
                
            except CancelledError:
                raise  # Don't retry cancellations
                
            except Exception as e:
                last_error = e
                classification = classify_error(e, stage)
                
                if classification.is_retryable and attempt < max_retries:
                    # Send user-friendly status message
                    self._send_stage_event(stage, "status", {
                        "message": f"⚠️ {classification.user_message}",
                        "icon": "⏳" if classification.is_rate_limit else "⚠️",
                    })
                    
                    # Rate limit backoff
                    if classification.is_rate_limit:
                        wait_time = self.RATE_LIMIT_BACKOFF_BASE * (attempt + 1)
                        self._send_stage_event(stage, "status", {
                            "message": f"⏳ {stage.value.capitalize()}: Waiting {wait_time}s before retry...",
                            "icon": "⏳",
                        })
                        time.sleep(wait_time)
                    
                    continue
                
                # Final failure - send user-friendly error
                self._send_stage_event(stage, "error", {
                    "message": f"❌ {classification.user_message.replace('Retrying...', 'All retries exhausted.')}",
                    "icon": "❌",
                    "fatal": True,
                })
                raise
        
        # Should not reach here, but just in case
        if last_error:
            raise last_error
        raise RuntimeError(f"Stage {stage.value} failed unexpectedly")
    
    def run(
        self,
        notes: str,
        images: list[dict] | None = None,
        conversation_id: str | None = None,
        prior_tsg: str | None = None,
        user_answers: str | None = None,
        prior_research: str | None = None,
    ) -> PipelineResult:
        """
        Run the complete TSG generation pipeline.
        
        Args:
            notes: Raw troubleshooting notes
            images: Optional images (base64 encoded) - used in research stage
            conversation_id: Optional existing conversation ID for follow-up (v2)
            prior_tsg: Optional prior TSG for iteration
            user_answers: Optional answers to follow-up questions
            prior_research: Optional prior research report for follow-up iterations
            
        Returns:
            PipelineResult with TSG content and metadata
        """
        result = PipelineResult(success=False, thread_id=conversation_id or "")
        project = self._get_project_client()
        
        # Debug: log when pipeline run starts
        verbose = os.getenv("PIPELINE_VERBOSE", "").lower() in ("1", "true", "yes")
        if verbose:
            verbose_log(f"Pipeline.run() starting on thread {threading.current_thread().name}")
            verbose_log(f"  Notes length: {len(notes)}, Has images: {bool(images)}")
        
        try:
            # Check for cancellation before starting
            self._check_cancelled()
            
            with project:
                # Get OpenAI client for v2 responses API with extended timeout
                openai_client = project.get_openai_client()
                
                if verbose:
                    verbose_log(f"  OpenAI client created: {id(openai_client)}")
                    # Log HTTP client details
                    if hasattr(openai_client, '_client'):
                        client = openai_client._client
                        verbose_log(f"  httpx client: {type(client).__name__}, id={id(client)}")
                        if hasattr(client, '_transport'):
                            verbose_log(f"  transport: {type(client._transport).__name__}")
                
                # Timeout config:
                #   - connect: 60s to establish connection
                #   - read: 600s - generous for streaming (gaps between chunks during model thinking)
                #   - write: 60s to send request data
                #   - pool: 120s to acquire connection from pool
                #   - timeout: 600s overall (10 min) catches truly stuck operations
                # Note: Tool-level hang detection (e.g., Bing stuck) will be handled separately
                # at the event stream level, not via HTTP read timeout.
                openai_client.timeout = httpx.Timeout(
                    timeout=600.0,  # 10 min overall for truly stuck operations
                    connect=60.0,
                    read=600.0,     # Don't timeout between chunks - detect hangs at event level
                    write=60.0,
                    pool=120.0,
                )
                with openai_client:
                    # --- Stage 1: Research ---
                    self._check_cancelled()  # Check before each stage
                    self._send_stage_event(PipelineStage.RESEARCH, "stage_start", {
                        "message": "🔍 Research: Gathering documentation and references...",
                        "icon": "🔍",
                    })
                    
                    research_report = ""
                    if not user_answers:
                        # Only do research on initial generation, not follow-ups
                        research_prompt = build_research_prompt(notes)
                        
                        # Use unified retry logic
                        research_response, research_conv_id = self._run_stage_with_retry(
                            project,
                            openai_client,
                            self.researcher_agent_name,
                            PipelineStage.RESEARCH,
                            research_prompt,
                        )
                        
                        research_report = extract_research_block(research_response)
                        if not research_report:
                            research_report = research_response
                        
                        result.research_report = research_report
                        result.stages_completed.append(PipelineStage.RESEARCH)
                        
                        # Test mode: capture raw research output
                        if self.test_mode:
                            result.stage_outputs["research"] = {
                                "raw_response": research_response,
                                "extracted_report": research_report,
                            }
                        
                        self._send_stage_event(PipelineStage.RESEARCH, "stage_complete", {
                            "message": "✅ Research: Found documentation and references",
                            "icon": "✅",
                            "has_content": bool(research_report),
                        })
                    else:
                        # Follow-up: use prior research if provided, otherwise note it's unavailable
                        if prior_research:
                            research_report = prior_research
                            result.research_report = prior_research
                        else:
                            research_report = "(Prior research not available for this follow-up)"
                        self._send_stage_event(PipelineStage.RESEARCH, "stage_complete", {
                            "message": "⏭️ Research: Using previous research (follow-up)",
                            "icon": "⏭️",
                        })
                    
                    # --- Stage 2: Write ---
                    self._check_cancelled()  # Check before write stage
                    self._send_stage_event(PipelineStage.WRITE, "stage_start", {
                        "message": "✏️ Write: Drafting TSG from notes and research...",
                        "icon": "✏️",
                    })
                    
                    writer_prompt = build_writer_prompt(
                        notes=notes,
                        research=research_report,
                        prior_tsg=prior_tsg,
                        user_answers=user_answers,
                    )
                    
                    # Use unified retry logic
                    write_response, write_conv_id = self._run_stage_with_retry(
                        project,
                        openai_client,
                        self.writer_agent_name,
                        PipelineStage.WRITE,
                        writer_prompt,
                    )
                    result.thread_id = write_conv_id  # Store conversation ID
                    result.stages_completed.append(PipelineStage.WRITE)
                    
                    # Test mode: capture raw writer output
                    if self.test_mode:
                        result.stage_outputs["write"] = {
                            "raw_response": write_response,
                            "prompt": writer_prompt,
                        }
                    
                    self._send_stage_event(PipelineStage.WRITE, "stage_complete", {
                        "message": "✅ Write: TSG draft complete",
                        "icon": "✅",
                    })
                    
                    # --- Stage 3: Review (with retry loop) ---
                    self._check_cancelled()  # Check before review stage
                    self._send_stage_event(PipelineStage.REVIEW, "stage_start", {
                        "message": "🔎 Review: Validating structure and accuracy...",
                        "icon": "🔎",
                    })
                    
                    draft_tsg = write_response
                    final_tsg = None
                    review_result = None
                    review_response = None  # Track for test mode
                    
                    for retry in range(self.REVIEW_STRUCTURE_MAX_RETRIES + 1):
                        self._check_cancelled()  # Check before each review retry
                        result.retry_count = retry
                        
                        validation = validate_tsg_output(draft_tsg)
                        
                        if validation["valid"]:
                            review_prompt = build_review_prompt(
                                draft_tsg=draft_tsg,
                                research=research_report,
                                notes=notes,
                            )
                            
                            # Use retry logic for transient failures
                            review_response, _ = self._run_stage_with_retry(
                                project,
                                openai_client,
                                self.reviewer_agent_name,
                                PipelineStage.REVIEW,
                                review_prompt,
                            )
                            
                            review_result = extract_review_block(review_response)
                            result.review_result = review_result
                            
                            if review_result:
                                if review_result.get("approved", False):
                                    final_tsg = draft_tsg
                                    break
                                elif review_result.get("corrected_tsg"):
                                    # Use the corrected TSG as the new draft
                                    draft_tsg = review_result["corrected_tsg"]
                                    self._send_stage_event(PipelineStage.REVIEW, "status", {
                                        "message": f"🔧 Review: Auto-correcting issues (attempt {retry + 1})...",
                                        "icon": "🔧",
                                        "issues": review_result.get("accuracy_issues", []) + review_result.get("structure_issues", []),
                                    })
                                    # If this is the last retry, accept corrected TSG as final
                                    if retry >= self.REVIEW_STRUCTURE_MAX_RETRIES:
                                        final_tsg = draft_tsg
                                        self._send_stage_event(PipelineStage.REVIEW, "status", {
                                            "message": "⚠️ Review: Accepted corrected TSG with warnings",
                                            "icon": "⚠️",
                                            "issues": review_result.get("accuracy_issues", []),
                                        })
                                        break
                                    # Otherwise continue loop to re-validate the corrected TSG
                                else:
                                    final_tsg = draft_tsg
                                    self._send_stage_event(PipelineStage.REVIEW, "status", {
                                        "message": "⚠️ Review: Found issues (included as warnings)",
                                        "icon": "⚠️",
                                        "issues": review_result.get("accuracy_issues", []),
                                    })
                                    break
                            else:
                                final_tsg = draft_tsg
                                break
                        else:
                            if retry < self.REVIEW_STRUCTURE_MAX_RETRIES:
                                self._send_stage_event(PipelineStage.REVIEW, "status", {
                                    "message": f"🔧 Review: Fixing structure issues (attempt {retry + 1})...",
                                    "icon": "🔧",
                                    "issues": validation["issues"],
                                })
                                
                                # Include full context so Writer can properly fix the TSG
                                fix_prompt = f"""Your TSG had structure issues:
{chr(10).join(f'- {issue}' for issue in validation['issues'])}

Please fix these issues and regenerate the TSG with correct format.

<template>
{TSG_TEMPLATE}
</template>

<notes>
{notes}
</notes>

<research>
{research_report}
</research>

<prior_tsg>
{draft_tsg}
</prior_tsg>
"""
                                # Use retry logic for transient failures
                                draft_tsg, _ = self._run_stage_with_retry(
                                    project,
                                    openai_client,
                                    self.writer_agent_name,
                                    PipelineStage.WRITE,
                                    fix_prompt,
                                    write_conv_id,
                                )
                            else:
                                final_tsg = draft_tsg
                                break
                    
                    result.stages_completed.append(PipelineStage.REVIEW)
                    
                    # Test mode: capture review output
                    if self.test_mode:
                        result.stage_outputs["review"] = {
                            "raw_response": review_response,
                            "parsed_result": review_result,
                            "final_draft": draft_tsg,
                        }
                    
                    if final_tsg:
                        tsg_content = ""
                        questions_content = ""
                        
                        if TSG_BEGIN in final_tsg and TSG_END in final_tsg:
                            start = final_tsg.find(TSG_BEGIN) + len(TSG_BEGIN)
                            end = final_tsg.find(TSG_END)
                            tsg_content = final_tsg[start:end].strip()
                        
                        if QUESTIONS_BEGIN in final_tsg and QUESTIONS_END in final_tsg:
                            start = final_tsg.find(QUESTIONS_BEGIN) + len(QUESTIONS_BEGIN)
                            end = final_tsg.find(QUESTIONS_END)
                            questions_content = final_tsg[start:end].strip()
                        
                        result.tsg_content = tsg_content
                        result.questions_content = questions_content
                        result.success = bool(tsg_content)
                    
                    self._send_stage_event(PipelineStage.REVIEW, "stage_complete", {
                        "message": "Review complete",
                        "approved": review_result.get("approved", False) if review_result else False,
                    })
                    
                    self._send_stage_event(PipelineStage.COMPLETE, "pipeline_complete", {
                        "success": result.success,
                        "stages": [s.value for s in result.stages_completed],
                        "retries": result.retry_count,
                    })
                
        except Exception as e:
            result.error = str(e)
            self._send_stage_event(PipelineStage.FAILED, "error", {
                "message": str(e),
                "fatal": True,  # All retries exhausted
            })
        
        return result


def run_pipeline(
    notes: str,
    images: list[dict] | None = None,
    event_queue: queue.Queue | None = None,
    thread_id: str | None = None,
    prior_tsg: str | None = None,
    user_answers: str | None = None,
    prior_research: str | None = None,
    test_mode: bool = False,
    cancel_event: threading.Event | None = None,
) -> PipelineResult:
    """
    Convenience function to run the TSG pipeline.
    
    Loads configuration from environment variables and agent info from storage.
    If test_mode=True, captures raw outputs from each stage and writes to a JSON file.
    If cancel_event is provided and set, the pipeline will stop at the next checkpoint.
    """
    import json
    from datetime import datetime
    from dotenv import load_dotenv
    load_dotenv()
    
    endpoint = os.getenv("PROJECT_ENDPOINT")
    if not endpoint:
        raise ValueError("PROJECT_ENDPOINT environment variable required")
    
    # Determine app directory (supports PyInstaller executable mode)
    if getattr(sys, 'frozen', False):
        app_dir = Path(sys.executable).parent
    else:
        app_dir = Path.cwd()
    
    # Load agent info from storage
    agent_ids_file = app_dir / ".agent_ids.json"
    if not agent_ids_file.exists():
        raise ValueError("No agents configured. Use the web UI Setup wizard first.")
    
    try:
        agent_data = json.loads(agent_ids_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError) as e:
        raise ValueError(f"Failed to load agent info: {e}") from e
    
    # Helper to extract agent name from v1 (string ID) or v2 (dict with 'name') format
    def get_agent_name(agent_info):
        if isinstance(agent_info, dict):
            return agent_info.get("name")
        # v1 format: return None, caller must handle
        return None
    
    researcher_name = get_agent_name(agent_data.get("researcher"))
    writer_name = get_agent_name(agent_data.get("writer"))
    reviewer_name = get_agent_name(agent_data.get("reviewer"))
    
    if not all([researcher_name, writer_name, reviewer_name]):
        raise ValueError("Incomplete agent configuration (v2 format with names required). Re-run Setup wizard.")
    
    bing_connection_id = os.getenv("BING_CONNECTION_NAME")
    model_name = os.getenv("MODEL_DEPLOYMENT_NAME")
    
    pipeline = TSGPipeline(
        project_endpoint=endpoint,
        researcher_agent_name=researcher_name,
        writer_agent_name=writer_name,
        reviewer_agent_name=reviewer_name,
        bing_connection_id=bing_connection_id,
        model_name=model_name,
        test_mode=test_mode,
        cancel_event=cancel_event,
    )
    
    if event_queue:
        pipeline.set_event_queue(event_queue)
    
    result = pipeline.run(
        notes=notes,
        images=images,
        conversation_id=thread_id,  # v2: conversation_id instead of thread_id
        prior_tsg=prior_tsg,
        user_answers=user_answers,
        prior_research=prior_research,
    )
    
    # Write test output file if in test mode
    if test_mode and result.stage_outputs:
        # Create logs directory if needed
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        test_output_file = logs_dir / f"test_output_{timestamp}.json"
        test_data = {
            "timestamp": timestamp,
            "success": result.success,
            "thread_id": result.thread_id,  # Include for debugging session issues
            "input_notes": notes,
            "stages_completed": [s.value for s in result.stages_completed],
            "stage_outputs": result.stage_outputs,
            "final_tsg": result.tsg_content,
            "questions": result.questions_content,
            "error": result.error,
        }
        test_output_file.write_text(json.dumps(test_data, indent=2), encoding="utf-8")
        print(f"Test output written to: {test_output_file}")
    
    return result
