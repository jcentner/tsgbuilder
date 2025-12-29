#!/usr/bin/env python3
"""
pipeline.py — Multi-stage TSG generation pipeline.

Orchestrates the Research → Write → Review stages for high-quality TSG generation.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Generator, Optional

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import (
    AgentEventHandler,
    MessageDeltaChunk,
    ThreadMessage,
    ThreadRun,
    RunStep,
    McpTool,
)

from tsg_constants import (
    # Markers
    TSG_BEGIN,
    TSG_END,
    QUESTIONS_BEGIN,
    QUESTIONS_END,
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


# Microsoft Learn MCP URL
LEARN_MCP_URL = "https://learn.microsoft.com/api/mcp"


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


class PipelineEventHandler(AgentEventHandler):
    """Event handler that queues events for pipeline stage execution."""
    
    def __init__(self, event_queue: queue.Queue, stage: PipelineStage):
        super().__init__()
        self.event_queue = event_queue
        self.stage = stage
        self.response_text = ""
        self._current_status = ""
        self._run_id = None
        self._last_error = None
    
    def _send_event(self, event_type: str, data: dict):
        data["stage"] = self.stage.value
        self.event_queue.put({"type": event_type, "data": data})
    
    def on_thread_run(self, run: ThreadRun) -> None:
        self._run_id = run.id
        if run.status != self._current_status:
            self._current_status = run.status
            self._send_event("status", {
                "status": run.status,
                "message": self._get_status_message(run.status)
            })
        
        if run.status == "failed":
            error_info = {"message": "Agent run failed"}
            if hasattr(run, "last_error") and run.last_error:
                error_info["code"] = getattr(run.last_error, "code", None)
                error_info["message"] = getattr(run.last_error, "message", str(run.last_error))
            self._last_error = error_info
    
    def _get_status_message(self, status: str) -> str:
        stage_name = self.stage.value.capitalize()
        messages = {
            "queued": f"{stage_name}: Queued...",
            "in_progress": f"{stage_name}: Processing...",
            "requires_action": f"{stage_name}: Executing tools...",
            "completed": f"{stage_name}: Complete",
            "failed": f"{stage_name}: Failed",
        }
        return messages.get(status, f"{stage_name}: {status}")
    
    def on_run_step(self, step: RunStep) -> None:
        if step.type == "tool_calls" and hasattr(step, "step_details"):
            self._handle_tool_calls(step)
    
    def _handle_tool_calls(self, step: RunStep) -> None:
        if not hasattr(step.step_details, "tool_calls"):
            return
        for tool_call in step.step_details.tool_calls:
            tool_type = getattr(tool_call, "type", "unknown")
            tool_info = {"type": tool_type}
            
            # Extract tool-specific info
            if hasattr(tool_call, "bing_grounding"):
                queries = []
                if hasattr(tool_call.bing_grounding, "requesturl"):
                    queries.append(tool_call.bing_grounding.requesturl)
                tool_info["queries"] = queries
                tool_info["name"] = "Bing Search"
            elif hasattr(tool_call, "mcp"):
                mcp = tool_call.mcp
                tool_info["server"] = getattr(mcp, "server_label", "unknown")
                tool_info["tool"] = getattr(mcp, "tool_name", "unknown")
                tool_info["name"] = f"MCP: {tool_info['tool']}"
            
            self._send_event("tool_call", tool_info)
    
    def on_message_delta(self, delta: MessageDeltaChunk) -> None:
        if delta.text:
            self.response_text += delta.text
    
    def on_thread_message(self, message: ThreadMessage) -> None:
        if message.role == "assistant" and message.content:
            for content_part in message.content:
                if hasattr(content_part, "text") and content_part.text:
                    if hasattr(content_part.text, "value"):
                        self.response_text = content_part.text.value
    
    def on_error(self, data: str) -> None:
        self._last_error = {"message": data}
    
    def on_done(self) -> None:
        pass
    
    def on_unhandled_event(self, event_type: str, event_data: Any) -> None:
        pass


class TSGPipeline:
    """
    Multi-stage TSG generation pipeline.
    
    Stages:
    1. Research: Gather docs and information using tools
    2. Write: Create TSG from notes + research (no tools)
    3. Review: Validate structure and accuracy, auto-fix if possible
    """
    
    MAX_RETRIES = 2
    
    def __init__(
        self,
        project_endpoint: str,
        agent_id: str,
        bing_connection_id: str | None = None,
        model_name: str | None = None,
    ):
        self.project_endpoint = project_endpoint
        self.agent_id = agent_id
        self.bing_connection_id = bing_connection_id
        self.model_name = model_name or os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-4.1")
        
        self._event_queue: queue.Queue | None = None
        self._research_agent_id: str | None = None
        self._writer_agent_id: str | None = None
        self._review_agent_id: str | None = None
    
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
    
    def _create_stage_agent(
        self,
        project: AIProjectClient,
        name: str,
        instructions: str,
        with_tools: bool = False,
    ) -> str:
        """Create an agent for a specific stage."""
        from azure.ai.agents.models import BingGroundingTool, McpTool
        
        tools = []
        tool_resources = None
        
        if with_tools:
            # Add Bing Search if connection available
            if self.bing_connection_id:
                bing_tool = BingGroundingTool(connection_id=self.bing_connection_id)
                tools.extend(bing_tool.definitions)
            
            # Add Microsoft Learn MCP
            mcp_tool = McpTool(server_label="learn", server_url=LEARN_MCP_URL)
            mcp_tool.set_approval_mode("never")
            tools.extend(mcp_tool.definitions)
            tool_resources = mcp_tool.resources
        
        agent = project.agents.create_agent(
            model=self.model_name,
            name=name,
            instructions=instructions,
            tools=tools if tools else None,
            tool_resources=tool_resources,
            temperature=0,
        )
        return agent.id
    
    def _run_stage(
        self,
        project: AIProjectClient,
        agent_id: str,
        stage: PipelineStage,
        user_message: str,
        thread_id: str | None = None,
    ) -> tuple[str, str]:
        """
        Run a single pipeline stage.
        
        Returns: (response_text, thread_id)
        """
        # Create thread if needed
        if thread_id is None:
            thread = project.agents.threads.create()
            thread_id = thread.id
        
        # Send user message
        project.agents.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_message,
        )
        
        # Create MCP tool resources for automatic execution
        mcp_tool = McpTool(server_label="learn", server_url=LEARN_MCP_URL)
        mcp_tool.set_approval_mode("never")
        
        # Run with streaming
        if self._event_queue:
            handler = PipelineEventHandler(self._event_queue, stage)
            with project.agents.runs.stream(
                thread_id=thread_id,
                agent_id=agent_id,
                event_handler=handler,
                tool_resources=mcp_tool.resources,
            ) as stream:
                stream.until_done()
            return handler.response_text, thread_id
        else:
            # Non-streaming fallback
            run = project.agents.runs.create(
                thread_id=thread_id,
                agent_id=agent_id,
            )
            while run.status in ("queued", "in_progress", "requires_action"):
                time.sleep(0.5)
                run = project.agents.runs.retrieve(thread_id=thread_id, run_id=run.id)
            
            if run.status == "failed":
                raise RuntimeError(f"Stage {stage.value} failed: {run.last_error}")
            
            # Get response
            messages = project.agents.messages.list(thread_id=thread_id)
            for msg in messages:
                if msg.role == "assistant" and msg.content:
                    for part in msg.content:
                        if hasattr(part, "text") and part.text:
                            return part.text.value, thread_id
            return "", thread_id
    
    def run(
        self,
        notes: str,
        images: list[dict] | None = None,
        thread_id: str | None = None,
        prior_tsg: str | None = None,
        user_answers: str | None = None,
    ) -> PipelineResult:
        """
        Run the complete TSG generation pipeline.
        
        Args:
            notes: Raw troubleshooting notes
            images: Optional images (base64 encoded) - used in research stage
            thread_id: Optional existing thread for follow-up
            prior_tsg: Optional prior TSG for iteration
            user_answers: Optional answers to follow-up questions
            
        Returns:
            PipelineResult with TSG content and metadata
        """
        result = PipelineResult(success=False, thread_id=thread_id or "")
        project = self._get_project_client()
        
        try:
            with project:
                # --- Stage 1: Research ---
                self._send_stage_event(PipelineStage.RESEARCH, "stage_start", {
                    "message": "Starting research phase..."
                })
                
                research_report = ""
                if not user_answers:
                    # Only do research on initial generation, not follow-ups
                    # Create research agent (with tools)
                    research_agent_id = self._create_stage_agent(
                        project,
                        name="TSG-Researcher",
                        instructions=RESEARCH_STAGE_INSTRUCTIONS,
                        with_tools=True,
                    )
                    
                    research_prompt = build_research_prompt(notes)
                    # TODO: Add image support to research stage
                    
                    research_response, research_thread_id = self._run_stage(
                        project,
                        research_agent_id,
                        PipelineStage.RESEARCH,
                        research_prompt,
                    )
                    
                    research_report = extract_research_block(research_response)
                    if not research_report:
                        # Use full response if markers missing
                        research_report = research_response
                    
                    result.research_report = research_report
                    result.stages_completed.append(PipelineStage.RESEARCH)
                    
                    self._send_stage_event(PipelineStage.RESEARCH, "stage_complete", {
                        "message": "Research complete",
                        "has_content": bool(research_report),
                    })
                    
                    # Clean up research agent
                    try:
                        project.agents.delete_agent(research_agent_id)
                    except Exception:
                        pass
                else:
                    # For follow-ups, skip research and use a placeholder
                    research_report = "(Follow-up - using prior research context)"
                    self._send_stage_event(PipelineStage.RESEARCH, "stage_complete", {
                        "message": "Skipped (follow-up)",
                    })
                
                # --- Stage 2: Write ---
                self._send_stage_event(PipelineStage.WRITE, "stage_start", {
                    "message": "Writing TSG draft..."
                })
                
                # Create writer agent (no tools)
                writer_agent_id = self._create_stage_agent(
                    project,
                    name="TSG-Writer",
                    instructions=WRITER_STAGE_INSTRUCTIONS,
                    with_tools=False,
                )
                
                writer_prompt = build_writer_prompt(
                    notes=notes,
                    research=research_report,
                    prior_tsg=prior_tsg,
                    user_answers=user_answers,
                )
                
                write_response, write_thread_id = self._run_stage(
                    project,
                    writer_agent_id,
                    PipelineStage.WRITE,
                    writer_prompt,
                )
                result.thread_id = write_thread_id
                result.stages_completed.append(PipelineStage.WRITE)
                
                self._send_stage_event(PipelineStage.WRITE, "stage_complete", {
                    "message": "Draft complete",
                })
                
                # Clean up writer agent
                try:
                    project.agents.delete_agent(writer_agent_id)
                except Exception:
                    pass
                
                # --- Stage 3: Review (with retry loop) ---
                self._send_stage_event(PipelineStage.REVIEW, "stage_start", {
                    "message": "Reviewing TSG quality..."
                })
                
                # Create review agent (no tools)
                review_agent_id = self._create_stage_agent(
                    project,
                    name="TSG-Reviewer",
                    instructions=REVIEW_STAGE_INSTRUCTIONS,
                    with_tools=False,
                )
                
                draft_tsg = write_response
                final_tsg = None
                review_result = None
                
                for retry in range(self.MAX_RETRIES + 1):
                    result.retry_count = retry
                    
                    # First validate structure programmatically
                    validation = validate_tsg_output(draft_tsg)
                    
                    if validation["valid"]:
                        # Structure OK - now do LLM review for accuracy
                        review_prompt = build_review_prompt(
                            draft_tsg=draft_tsg,
                            research=research_report,
                            notes=notes,
                        )
                        
                        review_response, _ = self._run_stage(
                            project,
                            review_agent_id,
                            PipelineStage.REVIEW,
                            review_prompt,
                        )
                        
                        review_result = extract_review_block(review_response)
                        result.review_result = review_result
                        
                        if review_result:
                            if review_result.get("approved", False):
                                # Approved!
                                final_tsg = draft_tsg
                                break
                            elif review_result.get("corrected_tsg"):
                                # Auto-corrected
                                draft_tsg = review_result["corrected_tsg"]
                                self._send_stage_event(PipelineStage.REVIEW, "status", {
                                    "message": f"Auto-correcting issues (attempt {retry + 1})...",
                                    "issues": review_result.get("accuracy_issues", []) + review_result.get("structure_issues", []),
                                })
                            else:
                                # Issues but no auto-fix - use as-is with warnings
                                final_tsg = draft_tsg
                                self._send_stage_event(PipelineStage.REVIEW, "status", {
                                    "message": "Review found issues (included as warnings)",
                                    "issues": review_result.get("accuracy_issues", []),
                                })
                                break
                        else:
                            # Couldn't parse review - accept draft
                            final_tsg = draft_tsg
                            break
                    else:
                        # Structure invalid - try to fix with writer
                        if retry < self.MAX_RETRIES:
                            self._send_stage_event(PipelineStage.REVIEW, "status", {
                                "message": f"Fixing structure issues (attempt {retry + 1})...",
                                "issues": validation["issues"],
                            })
                            
                            # Send fix request to writer
                            fix_prompt = f"""Your TSG had structure issues:
{chr(10).join(f'- {issue}' for issue in validation['issues'])}

Please fix these issues and regenerate the TSG with correct format.

<prior_tsg>
{draft_tsg}
</prior_tsg>
"""
                            draft_tsg, _ = self._run_stage(
                                project,
                                writer_agent_id,
                                PipelineStage.WRITE,
                                fix_prompt,
                                write_thread_id,
                            )
                        else:
                            # Max retries - use last draft
                            final_tsg = draft_tsg
                            break
                
                result.stages_completed.append(PipelineStage.REVIEW)
                
                # Clean up review agent
                try:
                    project.agents.delete_agent(review_agent_id)
                except Exception:
                    pass
                
                # Extract final blocks
                if final_tsg:
                    # Extract TSG and questions from the final output
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
) -> PipelineResult:
    """
    Convenience function to run the TSG pipeline.
    
    Loads configuration from environment variables.
    """
    from dotenv import load_dotenv
    load_dotenv()
    
    endpoint = os.getenv("PROJECT_ENDPOINT")
    if not endpoint:
        raise ValueError("PROJECT_ENDPOINT environment variable required")
    
    agent_id = os.getenv("AGENT_ID")
    if not agent_id:
        agent_id_file = Path(".agent_id")
        if agent_id_file.exists():
            agent_id = agent_id_file.read_text(encoding="utf-8").strip()
    
    if not agent_id:
        raise ValueError("No agent ID found. Run 'make create-agent' first.")
    
    bing_connection_id = os.getenv("BING_CONNECTION_NAME")
    model_name = os.getenv("MODEL_DEPLOYMENT_NAME")
    
    pipeline = TSGPipeline(
        project_endpoint=endpoint,
        agent_id=agent_id,
        bing_connection_id=bing_connection_id,
        model_name=model_name,
    )
    
    if event_queue:
        pipeline.set_event_queue(event_queue)
    
    return pipeline.run(
        notes=notes,
        images=images,
        thread_id=thread_id,
        prior_tsg=prior_tsg,
        user_answers=user_answers,
    )
