#!/usr/bin/env python3
"""
pipeline.py — Multi-stage TSG generation pipeline.

Orchestrates the Research → Write → Review stages for high-quality TSG generation.
"""

from __future__ import annotations

import os
import queue
import time
import threading
import httpx
from dataclasses import dataclass, field
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


class CancelledError(Exception):
    """Raised when a pipeline run is cancelled by the user."""
    pass


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
        print(f"[VERBOSE][{stage_name}][{elapsed:6.1f}s] {event_type}")
    
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
                print(f"[VERBOSE][{stage_name}] output_item.added: type={item_type}, item={item}")
            
            # Track tool start time (include bing_grounding_call which is the actual Bing tool type)
            if timing_context is not None and item_type in ('mcp_call', 'web_search_call', 'bing_grounding_call', 'function_call'):
                timing_context['tool_start'] = time.time()
            
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
            
            # Calculate tool elapsed time
            tool_elapsed = ""
            if timing_context and 'tool_start' in timing_context:
                elapsed_sec = time.time() - timing_context['tool_start']
                tool_elapsed = f" ({elapsed_sec:.1f}s)"
                timing_context['tool_end'] = time.time()  # Track when tool finished for model thinking time
            
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
                error_text = str(item.error)
                # Provide user-friendly messages for common errors
                if '429' in error_text or 'Too Many Requests' in error_text:
                    if 'mcp' in error_text.lower() or 'learn.microsoft.com' in error_text.lower():
                        send_event("error", {
                            "message": f"⏳ Microsoft Learn rate limited (429) - will retry",
                            "icon": "⏳",
                            "error_type": "rate_limit",
                        })
                    else:
                        send_event("error", {
                            "message": f"⏳ Rate limited (429) - will retry",
                            "icon": "⏳",
                            "error_type": "rate_limit",
                        })
                elif 'mcp' in error_text.lower() or 'learn.microsoft.com' in error_text.lower():
                    send_event("error", {
                        "message": f"⚠️ Microsoft Learn error: {error_text[:150]}",
                        "icon": "⚠️",
                        "error_type": "mcp_error",
                    })
                elif any(x in error_text.lower() for x in ['timeout', 'timed out', 'connection', 'httpx']):
                    send_event("error", {
                        "message": f"⚠️ Tool timeout - will retry: {error_text[:100]}",
                        "icon": "⚠️",
                        "error_type": "timeout",
                    })
                else:
                    send_event("error", {
                        "message": f"⚠️ Tool error: {item.error}",
                        "icon": "⚠️",
                        "error_type": "tool_error",
                    })
            if hasattr(item, 'status') and item.status == 'failed':
                error_detail = str(getattr(item, 'error', 'unknown'))
                # Same user-friendly handling for failed status
                if '429' in error_detail or 'Too Many Requests' in error_detail:
                    send_event("error", {
                        "message": f"⏳ Tool rate limited - will retry",
                        "icon": "⏳",
                        "error_type": "rate_limit",
                    })
                elif any(x in error_detail.lower() for x in ['timeout', 'timed out', 'connection', 'httpx']):
                    send_event("error", {
                        "message": f"⚠️ Tool timeout - will retry: {error_detail[:100]}",
                        "icon": "⚠️",
                        "error_type": "timeout",
                    })
                else:
                    send_event("error", {
                        "message": f"⚠️ Tool failed: {error_detail[:150]}",
                        "icon": "⚠️",
                        "error_type": "tool_error",
                    })
    
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
        # Categorize the error for UI handling
        error_lower = error_msg.lower()
        if any(x in error_lower for x in ['timeout', 'timed out', 'connection', 'httpx']):
            send_event("error", {
                "message": f"⚠️ {stage_name} timeout - will retry: {error_msg[:100]}",
                "icon": "⚠️",
                "error_type": "timeout",
            })
        elif '429' in error_msg or 'rate limit' in error_lower:
            send_event("error", {
                "message": f"⏳ {stage_name} rate limited - will retry",
                "icon": "⏳",
                "error_type": "rate_limit",
            })
        else:
            send_event("error", {
                "message": f"❌ {stage_name} failed: {error_msg}",
                "icon": "❌",
            })
    
    elif event_type == "error":
        # Handle error events that may occur during tool processing
        error_msg = getattr(event, 'message', None) or getattr(event, 'error', None) or str(event)
        # Categorize the error for UI handling
        error_lower = str(error_msg).lower()
        if any(x in error_lower for x in ['timeout', 'timed out', 'connection', 'httpx']):
            send_event("error", {
                "message": f"⚠️ {stage_name} timeout - will retry: {str(error_msg)[:100]}",
                "icon": "⚠️",
                "error_type": "timeout",
            })
        elif '429' in str(error_msg) or 'rate limit' in error_lower:
            send_event("error", {
                "message": f"⏳ {stage_name} rate limited - will retry",
                "icon": "⏳",
                "error_type": "rate_limit",
            })
        else:
            send_event("error", {
                "message": f"❌ {stage_name} error: {error_msg}",
                "icon": "❌",
            })
    
    elif event_type and event_type.startswith("error"):
        # Catch any other error-type events - treat as potentially retryable
        error_str = str(event)
        error_lower = error_str.lower()
        if any(x in error_lower for x in ['timeout', 'timed out', 'connection', 'httpx']):
            send_event("error", {
                "message": f"⚠️ {stage_name}: {event_type} - timeout, will retry",
                "icon": "⚠️",
                "error_type": "timeout",
            })
        else:
            send_event("error", {
                "message": f"❌ {stage_name}: {event_type} - {event}",
                "icon": "❌",
            })


class TSGPipeline:
    """
    Multi-stage TSG generation pipeline.
    
    Stages:
    1. Research: Gather docs and information using tools
    2. Write: Create TSG from notes + research (no tools)
    3. Review: Validate structure and accuracy, auto-fix if possible
    
    Agents are created once during setup and reused across runs.
    """
    
    MAX_RETRIES = 2
    RESEARCH_MAX_RETRIES = 3  # Extra retries for research stage due to tool timeouts and rate limits
    
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
                
                # Log when we've been waiting a long time for an event
                if verbose and wait_time > 5:
                    print(f"[VERBOSE][{stage.value}] ⚠️ Long wait: {wait_time:.1f}s after event #{event_count-1} ({last_event_type})")
                
                if verbose:
                    print(f"[VERBOSE][{stage.value}] Event #{event_count}: {event_type} (waited {wait_time:.1f}s)")
                
                last_event_time = now
                last_event_type = event_type
                
                process_pipeline_v2_stream(
                    event, 
                    self._event_queue, 
                    stage, 
                    response_text_parts,
                    timing_context,
                )
                
                # Capture conversation ID from response if not already set
                if not conversation_id and event_type == "response.created":
                    if hasattr(event, 'response'):
                        conv_id = getattr(event.response, 'conversation_id', None)
                        if conv_id:
                            conversation_id = conv_id
            
            if verbose:
                print(f"[VERBOSE][{stage.value}] ✅ Stream complete: {event_count} events")
            
            return "".join(response_text_parts), conversation_id or ""
            
        except Exception as e:
            # Don't send error event here - let the caller's retry logic decide
            # whether this is a retryable error or a fatal error
            raise RuntimeError(f"Stage {stage.value} failed: {e}") from e
    
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
            import threading
            print(f"[VERBOSE] Pipeline.run() starting on thread {threading.current_thread().name}")
            print(f"[VERBOSE]   Notes length: {len(notes)}, Has images: {bool(images)}")
        
        try:
            # Check for cancellation before starting
            self._check_cancelled()
            
            with project:
                # Get OpenAI client for v2 responses API with extended timeout
                openai_client = project.get_openai_client()
                
                if verbose:
                    print(f"[VERBOSE]   OpenAI client created: {id(openai_client)}")
                    # Log HTTP client details
                    if hasattr(openai_client, '_client'):
                        client = openai_client._client
                        print(f"[VERBOSE]   httpx client: {type(client).__name__}, id={id(client)}")
                        if hasattr(client, '_transport'):
                            print(f"[VERBOSE]   transport: {type(client._transport).__name__}")
                
                # Timeout config:
                #   - connect: 30s to establish connection
                #   - read: 30s between data chunks (catches Bing hangs that go 60+s)
                #   - write: 30s to send request data
                #   - pool: 60s to acquire connection from pool
                openai_client.timeout = httpx.Timeout(
                    timeout=300.0,  # 5 min default for all operations
                    connect=30.0,
                    read=30.0,
                    write=30.0,
                    pool=60.0,
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
                        
                        # Research stage has its own retry loop due to frequent Bing timeouts
                        research_response = ""
                        research_conv_id = ""
                        last_research_error = None
                        
                        for research_attempt in range(self.RESEARCH_MAX_RETRIES + 1):
                            self._check_cancelled()  # Check before each retry attempt
                            try:
                                if research_attempt > 0:
                                    self._send_stage_event(PipelineStage.RESEARCH, "status", {
                                        "message": f"🔄 Research: Retrying after timeout (attempt {research_attempt + 1})...",
                                        "icon": "🔄",
                                    })
                                
                                research_response, research_conv_id = self._run_stage(
                                    project,
                                    openai_client,
                                    self.researcher_agent_name,
                                    PipelineStage.RESEARCH,
                                    research_prompt,
                                )
                                last_research_error = None
                                break  # Success, exit retry loop
                                
                            except Exception as e:
                                last_research_error = e
                                error_str = str(e).lower()
                                
                                # Categorize the error for appropriate handling
                                is_rate_limit = any(x in error_str for x in ['429', 'rate limit', 'too many requests'])
                                is_mcp_error = 'mcp' in error_str or 'learn.microsoft.com' in error_str
                                is_timeout = any(x in error_str for x in ['timeout', 'timed out', 'connection', 'httpx'])
                                is_retryable = is_rate_limit or is_timeout
                                
                                # Send user-friendly error status
                                if is_rate_limit and is_mcp_error:
                                    self._send_stage_event(PipelineStage.RESEARCH, "status", {
                                        "message": f"⚠️ Research: Microsoft Learn rate limited (429), waiting to retry...",
                                        "icon": "⏳",
                                    })
                                elif is_mcp_error:
                                    self._send_stage_event(PipelineStage.RESEARCH, "status", {
                                        "message": f"⚠️ Research: Microsoft Learn error, will retry...",
                                        "icon": "⚠️",
                                    })
                                elif is_rate_limit:
                                    self._send_stage_event(PipelineStage.RESEARCH, "status", {
                                        "message": f"⚠️ Research: Rate limited (429), waiting to retry...",
                                        "icon": "⏳",
                                    })
                                elif is_timeout:
                                    self._send_stage_event(PipelineStage.RESEARCH, "status", {
                                        "message": f"⚠️ Research: Tool call timed out, will retry...",
                                        "icon": "⚠️",
                                    })
                                
                                if is_retryable and research_attempt < self.RESEARCH_MAX_RETRIES:
                                    # Backoff: wait longer for rate limits
                                    if is_rate_limit:
                                        import time as time_module
                                        wait_time = 30 * (research_attempt + 1)  # 30s, 60s, 90s
                                        self._send_stage_event(PipelineStage.RESEARCH, "status", {
                                            "message": f"⏳ Research: Waiting {wait_time}s before retry...",
                                            "icon": "⏳",
                                        })
                                        time_module.sleep(wait_time)
                                    continue
                                else:
                                    # Non-retryable error or out of retries - send descriptive error
                                    if is_mcp_error:
                                        self._send_stage_event(PipelineStage.RESEARCH, "error", {
                                            "message": f"❌ Microsoft Learn MCP error: {str(e)[:200]}",
                                            "icon": "❌",
                                            "fatal": True,  # Retries exhausted
                                        })
                                    raise
                        
                        if last_research_error:
                            raise last_research_error
                        
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
                    
                    write_response, write_conv_id = self._run_stage(
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
                    
                    for retry in range(self.MAX_RETRIES + 1):
                        self._check_cancelled()  # Check before each review retry
                        result.retry_count = retry
                        
                        validation = validate_tsg_output(draft_tsg)
                        
                        if validation["valid"]:
                            review_prompt = build_review_prompt(
                                draft_tsg=draft_tsg,
                                research=research_report,
                                notes=notes,
                            )
                            
                            review_response, _ = self._run_stage(
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
                                    if retry >= self.MAX_RETRIES:
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
                            if retry < self.MAX_RETRIES:
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
                                draft_tsg, _ = self._run_stage(
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
    
    # Load agent info from storage
    agent_ids_file = Path(".agent_ids.json")
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
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        test_output_file = Path(f"test_output_{timestamp}.json")
        test_data = {
            "timestamp": timestamp,
            "success": result.success,
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
