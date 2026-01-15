#!/usr/bin/env python3
"""
Minimal test to reproduce hanging behavior with MCP + Bing tools.

Usage:
    python test_tools.py [--mcp-only | --bing-only | --both] [--prompt "custom prompt"]
    python test_tools.py --sse-mode  # Mirrors Flask SSE + threading pattern

This creates a temporary agent, runs a test query, and cleans up.
"""

import os
import sys
import time
import queue
import threading
import argparse
import httpx
from datetime import datetime
from pathlib import Path
from typing import Generator, Any

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    PromptAgentDefinition,
    MCPTool,
    BingGroundingAgentTool,
    BingGroundingSearchToolParameters,
    BingGroundingSearchConfiguration,
)

# Load environment from parent directory
load_dotenv(Path(__file__).parent.parent / ".env")

# Microsoft Learn MCP URL
LEARN_MCP_URL = "https://learn.microsoft.com/api/mcp"

# Default test prompts
DEFAULT_PROMPTS = {
    "mcp_only": "What is a capability host in Azure AI Foundry? Give a brief summary.",
    "bing_only": "Search for recent Azure AI Foundry announcements. Give a brief summary.",
    "both": "What is a capability host in Azure AI Foundry? Also search for any recent announcements about it.",
    # Realistic pipeline-style research prompt
    "research": """You are researching an Azure AI Foundry issue. Search for and gather information about:

1. Azure AI Agents capability hosts - what they are, how model deployments work
2. Cross-resource model deployment limitations in Azure AI Foundry
3. Any GitHub issues or community discussions about model deployment access errors
4. Official Microsoft documentation about connecting Azure OpenAI resources to AI Foundry projects

For each finding, provide:
- The source URL
- A brief summary of the relevant information
- Any workarounds or solutions mentioned

Focus on recent (2025-2026) information. Search both official docs and community sources.""",
}

# Import the real research instructions from the main pipeline
# This allows --prod-instructions mode to use exact prod settings
try:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from tsg_constants import RESEARCH_STAGE_INSTRUCTIONS, build_research_prompt
    HAS_PROD_CONSTANTS = True
except ImportError:
    HAS_PROD_CONSTANTS = False
    RESEARCH_STAGE_INSTRUCTIONS = None
    build_research_prompt = None


def create_test_agent(
    project: AIProjectClient,
    model: str,
    use_mcp: bool = True,
    use_bing: bool = True,
    bing_connection_id: str | None = None,
    instructions: str | None = None,
) -> str:
    """Create a test agent with specified tools."""
    tools = []
    tool_names = []
    
    if use_mcp:
        tools.append(MCPTool(
            server_label="learn",
            server_url=LEARN_MCP_URL,
            require_approval="never",
        ))
        tool_names.append("MCP")
    
    if use_bing and bing_connection_id:
        tools.append(BingGroundingAgentTool(
            bing_grounding=BingGroundingSearchToolParameters(
                search_configurations=[
                    BingGroundingSearchConfiguration(
                        project_connection_id=bing_connection_id,
                        count=5,
                    )
                ]
            )
        ))
        tool_names.append("Bing")
    
    timestamp = datetime.now().strftime("%H%M%S")
    agent_name = f"hang-test-{'-'.join(tool_names).lower()}-{timestamp}"
    
    # Use provided instructions or default
    agent_instructions = instructions or "You are a helpful assistant. Be concise in your responses."
    
    print(f"Creating agent: {agent_name}")
    print(f"  Tools: {', '.join(tool_names) if tool_names else 'None'}")
    print(f"  Instructions: {'[PROD]' if instructions else '[DEFAULT]'} ({len(agent_instructions)} chars)")
    
    agent = project.agents.create_version(
        agent_name=agent_name,
        definition=PromptAgentDefinition(
            model=model,
            instructions=agent_instructions,
            tools=tools if tools else None,
            temperature=0,
        ),
    )
    
    print(f"  Agent ID: {agent.id}")
    print(f"  Agent Name: {agent.name}")
    return agent.name


def get_prod_agent_name() -> str | None:
    """Get the production researcher agent name from .agent_ids.json."""
    import json
    agent_ids_path = Path(__file__).parent.parent / ".agent_ids.json"
    if agent_ids_path.exists():
        with open(agent_ids_path) as f:
            data = json.load(f)
            researcher = data.get("researcher", {})
            return researcher.get("name")
    return None


def run_test(
    project: AIProjectClient,
    agent_name: str,
    prompt: str,
    timeout: int = 300,
    verbose: bool = False,
) -> None:
    """Run a test query against the agent and measure timing."""
    print(f"\n{'='*60}")
    print(f"Running test with prompt:")
    print(f"  {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
    print(f"{'='*60}\n")
    
    openai_client = project.get_openai_client()
    
    # Match pipeline.py timeout configuration
    openai_client.timeout = httpx.Timeout(
        timeout=600.0,
        connect=60.0,
        read=600.0,
        write=60.0,
        pool=120.0,
    )
    
    # Track timing
    start_time = time.time()
    last_event_time = start_time
    tool_calls = []
    event_count = 0
    
    try:
        print("Starting streaming response...\n")
        
        # Use extra_body pattern from pipeline.py
        stream_kwargs = {
            "stream": True,
            "input": prompt,
            "extra_body": {
                "agent": {
                    "name": agent_name,
                    "type": "agent_reference"
                }
            }
        }
        
        # Mirror pipeline: use with openai_client context manager
        with openai_client:
            stream_response = openai_client.responses.create(**stream_kwargs)
            
            for event in stream_response:
                event_count += 1
                now = time.time()
                elapsed = now - start_time
                since_last = now - last_event_time
                
                event_type = getattr(event, 'type', 'unknown')
                
                # Verbose mode: log all events
                if verbose:
                    print(f"[{elapsed:6.1f}s] #{event_count:3d} {event_type}")
                
                # Match the actual item types from Azure AI Foundry:
                #   - mcp_call: Microsoft Learn MCP tool
                #   - bing_grounding_call / web_search_call: Bing search
                #   - function_call: generic tool calls
                tool_types = ('mcp_call', 'web_search_call', 'bing_grounding_call', 'function_call')
                
                # Log significant events
                if event_type == 'response.output_item.added':
                    item = getattr(event, 'item', None)
                    if item:
                        item_type = getattr(item, 'type', 'unknown')
                        if item_type in tool_types:
                            if item_type == 'mcp_call':
                                tool_name = getattr(item, 'name', None) or 'Microsoft Learn MCP'
                            elif item_type in ('bing_grounding_call', 'web_search_call'):
                                tool_name = 'Bing Search'
                            else:
                                tool_name = getattr(item, 'name', 'unknown')
                            print(f"[{elapsed:6.1f}s] 🔧 Tool call started: {tool_name} ({item_type})")
                            tool_calls.append({
                                'name': tool_name,
                                'item_type': item_type,
                                'start': elapsed,
                                'end': None,
                            })
                
                elif event_type == 'response.output_item.done':
                    item = getattr(event, 'item', None)
                    if item:
                        item_type = getattr(item, 'type', 'unknown')
                        if item_type in tool_types:
                            # Find matching tool call by item_type and mark end
                            for tc in reversed(tool_calls):
                                if tc['item_type'] == item_type and tc['end'] is None:
                                    tc['end'] = elapsed
                                    duration = tc['end'] - tc['start']
                                    print(f"[{elapsed:6.1f}s] ✅ Tool call complete: {tc['name']} ({duration:.1f}s)")
                                    break
                
                elif event_type == 'response.completed':
                    print(f"[{elapsed:6.1f}s] 🏁 Response completed")
                
                elif event_type == 'response.failed':
                    error = getattr(event, 'response', None)
                    error_msg = getattr(error, 'error', None) if error else 'Unknown error'
                    print(f"[{elapsed:6.1f}s] ❌ Response failed: {error_msg}")
                
                # Warn if long gap between events
                if since_last > 30:
                    print(f"[{elapsed:6.1f}s] ⚠️  Long gap: {since_last:.1f}s since last event")
                
                last_event_time = now
                
                # Timeout check
                if elapsed > timeout:
                    print(f"\n⏰ TIMEOUT: {timeout}s exceeded")
                    break
        
        total_time = time.time() - start_time
        print(f"\n{'='*60}")
        print(f"Test completed in {total_time:.1f}s")
        print(f"{'='*60}")
        
        # Summary of tool calls
        if tool_calls:
            print("\nTool call summary:")
            for tc in tool_calls:
                duration = (tc['end'] - tc['start']) if tc['end'] else 'INCOMPLETE'
                print(f"  - {tc['name']}: {duration}s" if isinstance(duration, str) else f"  - {tc['name']}: {duration:.1f}s")
        
    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        print(f"\n\n⚠️  Interrupted after {elapsed:.1f}s")
        if tool_calls:
            print("\nTool calls at interruption:")
            for tc in tool_calls:
                status = "completed" if tc['end'] else "IN PROGRESS"
                print(f"  - {tc['name']}: {status}")
        raise


def run_test_sse_mode(
    project: AIProjectClient,
    agent_name: str,
    prompt: str,
    timeout: int = 300,
    verbose: bool = False,
) -> None:
    """
    Run test mirroring the Flask SSE + threading pattern from web_app.py.
    
    This mirrors how the real pipeline works:
    1. Main thread yields SSE events (simulated with prints)
    2. Background thread runs the actual API call
    3. queue.Queue passes events between threads
    4. 30s keepalive timeout on queue.get()
    """
    print(f"\n{'='*60}")
    print(f"SSE MODE: Mirroring Flask pipeline pattern")
    print(f"Running test with prompt:")
    print(f"  {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
    print(f"{'='*60}\n")
    
    # Shared state (mirrors web_app.py pattern)
    event_queue: queue.Queue = queue.Queue()
    result_holder: dict[str, Any] = {"result": None, "error": None}
    
    # Track timing
    start_time = time.time()
    tool_calls: list[dict] = []
    
    def pipeline_thread():
        """Background thread that runs the API call (mirrors run_pipeline_thread in web_app.py)."""
        nonlocal tool_calls
        last_event_time = time.time()
        
        try:
            openai_client = project.get_openai_client()
            
            # Match pipeline.py timeout configuration
            openai_client.timeout = httpx.Timeout(
                timeout=600.0,
                connect=60.0,
                read=600.0,
                write=60.0,
                pool=120.0,
            )
            
            stream_kwargs = {
                "stream": True,
                "input": prompt,
                "extra_body": {
                    "agent": {
                        "name": agent_name,
                        "type": "agent_reference"
                    }
                }
            }
            
            event_queue.put({"type": "status", "message": "Starting streaming response..."})
            
            with openai_client:
                stream_response = openai_client.responses.create(**stream_kwargs)
                
                event_count = 0
                for event in stream_response:
                    event_count += 1
                    now = time.time()
                    elapsed = now - start_time
                    since_last = now - last_event_time
                    
                    event_type = getattr(event, 'type', 'unknown')
                    
                    # Verbose mode: send raw events to main thread for logging
                    if verbose:
                        event_queue.put({
                            "type": "verbose", 
                            "elapsed": elapsed,
                            "event_num": event_count,
                            "event_type": event_type,
                        })
                    
                    # Process events and put them on the queue (like process_pipeline_v2_stream)
                    # Match the actual item types from Azure AI Foundry:
                    #   - mcp_call: Microsoft Learn MCP tool
                    #   - bing_grounding_call / web_search_call: Bing search
                    #   - function_call: generic tool calls
                    tool_types = ('mcp_call', 'web_search_call', 'bing_grounding_call', 'function_call')
                    
                    if event_type == 'response.output_item.added':
                        item = getattr(event, 'item', None)
                        if item:
                            item_type = getattr(item, 'type', 'unknown')
                            if item_type in tool_types:
                                # Get tool name based on type
                                if item_type == 'mcp_call':
                                    tool_name = getattr(item, 'name', None) or 'Microsoft Learn MCP'
                                elif item_type in ('bing_grounding_call', 'web_search_call'):
                                    tool_name = 'Bing Search'
                                else:
                                    tool_name = getattr(item, 'name', 'unknown')
                                
                                tool_calls.append({
                                    'name': tool_name,
                                    'item_type': item_type,
                                    'start': elapsed,
                                    'end': None,
                                })
                                event_queue.put({
                                    "type": "tool_start",
                                    "elapsed": elapsed,
                                    "tool": tool_name,
                                    "item_type": item_type,
                                })
                    
                    elif event_type == 'response.output_item.done':
                        item = getattr(event, 'item', None)
                        if item:
                            item_type = getattr(item, 'type', 'unknown')
                            if item_type in tool_types:
                                # Match by item_type to find the right tool call
                                for tc in reversed(tool_calls):
                                    if tc['item_type'] == item_type and tc['end'] is None:
                                        tc['end'] = elapsed
                                        event_queue.put({
                                            "type": "tool_done",
                                            "elapsed": elapsed,
                                            "tool": tc['name'],
                                            "item_type": item_type,
                                            "duration": tc['end'] - tc['start'],
                                        })
                                        break
                    
                    elif event_type == 'response.completed':
                        event_queue.put({"type": "completed", "elapsed": elapsed, "event_count": event_count})
                    
                    elif event_type == 'response.failed':
                        error = getattr(event, 'response', None)
                        error_msg = getattr(error, 'error', None) if error else 'Unknown error'
                        event_queue.put({"type": "failed", "elapsed": elapsed, "error": str(error_msg)})
                    
                    # Warn if long gap
                    if since_last > 30:
                        event_queue.put({
                            "type": "long_gap",
                            "elapsed": elapsed,
                            "gap": since_last,
                        })
                    
                    last_event_time = now
                    
                    # Timeout check
                    if elapsed > timeout:
                        event_queue.put({"type": "timeout", "elapsed": elapsed})
                        break
            
            result_holder["result"] = {"success": True, "tool_calls": tool_calls}
            
        except Exception as e:
            result_holder["error"] = str(e)
            event_queue.put({"type": "error", "message": str(e)})
        finally:
            event_queue.put(None)  # Signal end
    
    # Start background thread (mirrors web_app.py)
    thread = threading.Thread(target=pipeline_thread)
    thread.start()
    
    print("[SSE] Background thread started")
    print("[SSE] Main thread consuming events (30s keepalive timeout)...\n")
    
    # Main thread consumes events (mirrors the SSE generator in web_app.py)
    try:
        while True:
            try:
                # 30s timeout matches web_app.py keepalive interval
                event = event_queue.get(timeout=30)
                
                if event is None:
                    print("\n[SSE] Stream ended (received None sentinel)")
                    break
                
                elapsed = time.time() - start_time
                event_type = event.get("type", "unknown")
                
                if event_type == "status":
                    print(f"[{elapsed:6.1f}s] 📡 {event.get('message')}")
                elif event_type == "tool_start":
                    print(f"[{event.get('elapsed', elapsed):6.1f}s] 🔧 Tool call started: {event.get('tool')}")
                elif event_type == "tool_done":
                    print(f"[{event.get('elapsed', elapsed):6.1f}s] ✅ Tool call complete: {event.get('tool')} ({event.get('duration', 0):.1f}s)")
                elif event_type == "completed":
                    print(f"[{event.get('elapsed', elapsed):6.1f}s] 🏁 Response completed")
                elif event_type == "failed":
                    print(f"[{event.get('elapsed', elapsed):6.1f}s] ❌ Response failed: {event.get('error')}")
                elif event_type == "long_gap":
                    print(f"[{event.get('elapsed', elapsed):6.1f}s] ⚠️  Long gap: {event.get('gap', 0):.1f}s since last event")
                elif event_type == "timeout":
                    print(f"[{event.get('elapsed', elapsed):6.1f}s] ⏰ TIMEOUT exceeded")
                elif event_type == "error":
                    print(f"[{elapsed:6.1f}s] ❌ Error: {event.get('message')}")
                elif event_type == "verbose":
                    print(f"[{event.get('elapsed', elapsed):6.1f}s] #{event.get('event_num', '?'):3} {event.get('event_type', '?')}")
                else:
                    print(f"[{elapsed:6.1f}s] 📨 Event: {event_type}")
                    
            except queue.Empty:
                # This is the keepalive path - matches web_app.py behavior
                elapsed = time.time() - start_time
                print(f"[{elapsed:6.1f}s] 💓 Keepalive (no events for 30s) - would send SSE keepalive")
                
                # Check if we've exceeded timeout during a gap
                if elapsed > timeout:
                    print(f"[{elapsed:6.1f}s] ⏰ TIMEOUT during keepalive gap")
                    break
                    
    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        print(f"\n\n⚠️  Interrupted after {elapsed:.1f}s")
    
    # Wait for thread to finish
    thread.join(timeout=5)
    if thread.is_alive():
        print("[SSE] Warning: Background thread still running after 5s wait")
    
    total_time = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"SSE MODE Test completed in {total_time:.1f}s")
    print(f"{'='*60}")
    
    # Summary
    if result_holder["error"]:
        print(f"\n❌ Error: {result_holder['error']}")
    elif result_holder["result"]:
        tc_list = result_holder["result"].get("tool_calls", [])
        if tc_list:
            print("\nTool call summary:")
            for tc in tc_list:
                duration = (tc['end'] - tc['start']) if tc['end'] else 'INCOMPLETE'
                print(f"  - {tc['name']}: {duration}s" if isinstance(duration, str) else f"  - {tc['name']}: {duration:.1f}s")


def cleanup_agent(project: AIProjectClient, agent_name: str) -> None:
    """Delete the test agent."""
    print(f"\nCleaning up agent: {agent_name}")
    try:
        # In v2 API, we archive the agent by name
        # Note: This may vary depending on your SDK version
        project.agents.archive_version(agent_name=agent_name, version="1")
        print("  Agent archived")
    except Exception as e:
        print(f"  Warning: Could not archive agent: {e}")


def main():
    parser = argparse.ArgumentParser(description="Test MCP + Bing tool hanging behavior")
    parser.add_argument("--mcp-only", action="store_true", help="Test with MCP tool only")
    parser.add_argument("--bing-only", action="store_true", help="Test with Bing tool only")
    parser.add_argument("--both", action="store_true", help="Test with both tools (default)")
    parser.add_argument("--sse-mode", action="store_true", help="Use SSE + threading pattern (mirrors Flask pipeline)")
    parser.add_argument("--prod-instructions", action="store_true", help="Use exact production agent instructions")
    parser.add_argument("--prod-prompt", type=str, help="User notes to wrap in prod research prompt format")
    parser.add_argument("--use-prod-agent", action="store_true", help="Use the existing production researcher agent")
    parser.add_argument("--prompt", type=str, help="Custom test prompt")
    parser.add_argument("--research", action="store_true", help="Use realistic research-style prompt")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds (default: 300)")
    parser.add_argument("--no-cleanup", action="store_true", help="Don't delete agent after test")
    parser.add_argument("--verbose", "-v", action="store_true", help="Log all stream events for debugging")
    args = parser.parse_args()
    
    # Determine tool configuration
    if args.mcp_only:
        use_mcp, use_bing = True, False
        mode = "mcp_only"
    elif args.bing_only:
        use_mcp, use_bing = False, True
        mode = "bing_only"
    else:
        use_mcp, use_bing = True, True
        mode = "both"
    
    # Determine instructions
    instructions = None
    if args.prod_instructions:
        if not HAS_PROD_CONSTANTS:
            print("Error: Could not import production constants from tsg_constants.py")
            sys.exit(1)
        instructions = RESEARCH_STAGE_INSTRUCTIONS
        print(f"Using PRODUCTION research instructions ({len(instructions)} chars)")
    
    # Get prompt
    if args.prod_prompt:
        if not HAS_PROD_CONSTANTS or not build_research_prompt:
            print("Error: Could not import build_research_prompt from tsg_constants.py")
            sys.exit(1)
        prompt = build_research_prompt(args.prod_prompt)
        print(f"Using PRODUCTION research prompt format with user notes")
    elif args.prompt:
        prompt = args.prompt
    elif args.research:
        prompt = DEFAULT_PROMPTS["research"]
    else:
        prompt = DEFAULT_PROMPTS[mode]
    
    # Load config
    endpoint = os.getenv("PROJECT_ENDPOINT")
    model = os.getenv("MODEL_DEPLOYMENT_NAME")
    bing_conn = os.getenv("BING_CONNECTION_NAME")
    
    if not endpoint:
        print("Error: PROJECT_ENDPOINT not set in .env")
        sys.exit(1)
    if not model:
        print("Error: MODEL_DEPLOYMENT_NAME not set in .env")
        sys.exit(1)
    if use_bing and not bing_conn:
        print("Error: BING_CONNECTION_NAME not set in .env (required for Bing tool)")
        sys.exit(1)
    
    print(f"Configuration:")
    print(f"  Endpoint: {endpoint}")
    print(f"  Model: {model}")
    print(f"  Bing Connection: {bing_conn or 'N/A'}")
    print(f"  Mode: {mode}")
    print(f"  SSE Mode: {args.sse_mode}")
    print(f"  Prod Instructions: {args.prod_instructions}")
    print(f"  Use Prod Agent: {args.use_prod_agent}")
    print(f"  Verbose: {args.verbose}")
    print(f"  Timeout: {args.timeout}s")
    print()
    
    # Run test
    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
    agent_name = None
    created_agent = False  # Track if we created the agent (for cleanup)
    
    try:
        with project:
            if args.use_prod_agent:
                # Use the existing production researcher agent
                agent_name = get_prod_agent_name()
                if not agent_name:
                    print("Error: Could not find production agent in .agent_ids.json")
                    sys.exit(1)
                print(f"Using PRODUCTION agent: {agent_name}")
                created_agent = False
            else:
                agent_name = create_test_agent(
                    project,
                    model,
                    use_mcp=use_mcp,
                    use_bing=use_bing,
                    bing_connection_id=bing_conn,
                    instructions=instructions,
                )
                created_agent = True
            
            if args.sse_mode:
                run_test_sse_mode(project, agent_name, prompt, timeout=args.timeout, verbose=args.verbose)
            else:
                run_test(project, agent_name, prompt, timeout=args.timeout, verbose=args.verbose)
            
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if agent_name and created_agent and not args.no_cleanup:
            try:
                with project:
                    cleanup_agent(project, agent_name)
            except Exception as e:
                print(f"Cleanup failed: {e}")


if __name__ == "__main__":
    main()
