#!/usr/bin/env python3
"""
pipeline.py — Multi-stage TSG generation pipeline.

Orchestrates the Research → Write → Review stages for high-quality TSG generation.
"""

from __future__ import annotations

import os
import queue
import time
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
    """
    event_type = getattr(event, 'type', None)
    stage_name = stage.value.capitalize()
    
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
            
            # Track tool start time
            if timing_context is not None and item_type in ('mcp_call', 'web_search_call', 'function_call'):
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
            elif item_type == "web_search_call":
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
            elif item_type == "web_search_call":
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
        send_event("error", {
            "message": f"❌ {stage_name} failed: {error_msg}",
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
    RESEARCH_MAX_RETRIES = 2  # Extra retries for research due to Bing timeouts
    
    def __init__(
        self,
        project_endpoint: str,
        researcher_agent_name: str,
        writer_agent_name: str,
        reviewer_agent_name: str,
        bing_connection_id: str | None = None,
        model_name: str | None = None,
        test_mode: bool = False,
    ):
        self.project_endpoint = project_endpoint
        # v2: store agent names instead of IDs
        self.researcher_agent_name = researcher_agent_name
        self.writer_agent_name = writer_agent_name
        self.reviewer_agent_name = reviewer_agent_name
        self.bing_connection_id = bing_connection_id
        self.model_name = model_name or os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-5.2")
        self.test_mode = test_mode
        
        self._event_queue: queue.Queue | None = None
    
    def set_event_queue(self, event_queue: queue.Queue):
        """Set the event queue for SSE streaming."""
        self._event_queue = event_queue
    
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
            
            # Stream the response
            stream_response = openai_client.responses.create(**stream_kwargs)
            
            for event in stream_response:
                process_pipeline_v2_stream(
                    event, 
                    self._event_queue, 
                    stage, 
                    response_text_parts,
                    timing_context,
                )
                
                # Capture conversation ID from response if not already set
                if not conversation_id and getattr(event, 'type', None) == "response.created":
                    if hasattr(event, 'response'):
                        conv_id = getattr(event.response, 'conversation_id', None)
                        if conv_id:
                            conversation_id = conv_id
            
            return "".join(response_text_parts), conversation_id or ""
            
        except Exception as e:
            self._send_stage_event(stage, "error", {"message": str(e)})
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
        
        try:
            with project:
                # Get OpenAI client for v2 responses API with extended timeout
                # Bing Search calls can take several minutes; extend to 15 min for long research phases
                openai_client = project.get_openai_client()
                openai_client.timeout = httpx.Timeout(900.0, connect=60.0)  # 15 min read, 1 min connect
                with openai_client:
                    # --- Stage 1: Research ---
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
                                # Retry on timeout or connection errors
                                is_retryable = any(x in error_str for x in ['timeout', 'timed out', 'connection', 'httpx'])
                                
                                if is_retryable and research_attempt < self.RESEARCH_MAX_RETRIES:
                                    self._send_stage_event(PipelineStage.RESEARCH, "status", {
                                        "message": f"⚠️ Research: Tool call timed out, will retry...",
                                        "icon": "⚠️",
                                    })
                                    continue
                                else:
                                    # Non-retryable error or out of retries
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
                    self._send_stage_event(PipelineStage.REVIEW, "stage_start", {
                        "message": "🔎 Review: Validating structure and accuracy...",
                        "icon": "🔎",
                    })
                    
                    draft_tsg = write_response
                    final_tsg = None
                    review_result = None
                    review_response = None  # Track for test mode
                    
                    for retry in range(self.MAX_RETRIES + 1):
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
                                    draft_tsg = review_result["corrected_tsg"]
                                    self._send_stage_event(PipelineStage.REVIEW, "status", {
                                        "message": f"🔧 Review: Auto-correcting issues (attempt {retry + 1})...",
                                        "icon": "🔧",
                                        "issues": review_result.get("accuracy_issues", []) + review_result.get("structure_issues", []),
                                    })
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
) -> PipelineResult:
    """
    Convenience function to run the TSG pipeline.
    
    Loads configuration from environment variables and agent info from storage.
    If test_mode=True, captures raw outputs from each stage and writes to a JSON file.
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
