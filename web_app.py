#!/usr/bin/env python3
"""
web_app.py — Simple Flask web UI for TSG Builder.

Provides an easy-to-use web interface for generating TSGs from notes.
"""

from __future__ import annotations

import os
import sys
import time
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Generator

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from dotenv import load_dotenv, find_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

from tsg_constants import (
    TSG_BEGIN,
    TSG_END,
    QUESTIONS_BEGIN,
    QUESTIONS_END,
    build_user_prompt,
)

# Load environment variables
load_dotenv(find_dotenv())

app = Flask(__name__)

# Store active sessions (thread_id -> session data)
sessions: dict[str, dict] = {}


@dataclass
class SessionState:
    """Track state for a TSG generation session."""
    thread_id: str
    notes: str
    current_tsg: str | None = None
    questions: str | None = None
    status: str = "idle"  # idle, running, waiting_for_answers, complete, error
    error_message: str | None = None


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


def run_agent_and_get_response(project: AIProjectClient, thread_id: str, agent_id: str) -> str:
    """Create a run, poll until complete, and return the assistant's response text."""
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
    """Check if the agent is configured and ready."""
    try:
        endpoint = os.getenv("PROJECT_ENDPOINT")
        if not endpoint:
            return jsonify({
                "ready": False,
                "error": "PROJECT_ENDPOINT not configured. Please set up your .env file."
            })
        
        agent_id = get_agent_id()
        return jsonify({
            "ready": True,
            "agent_id": agent_id[:8] + "..." if agent_id else None
        })
    except Exception as e:
        return jsonify({
            "ready": False,
            "error": str(e)
        })


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
