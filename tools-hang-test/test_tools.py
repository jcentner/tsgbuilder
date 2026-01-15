#!/usr/bin/env python3
"""
Minimal test to reproduce hanging behavior with MCP + Bing tools.

Usage:
    python test_tools.py [--mcp-only | --bing-only | --both] [--prompt "custom prompt"]

This creates a temporary agent, runs a test query, and cleans up.
"""

import os
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path

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
}


def create_test_agent(
    project: AIProjectClient,
    model: str,
    use_mcp: bool = True,
    use_bing: bool = True,
    bing_connection_id: str | None = None,
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
    
    print(f"Creating agent: {agent_name}")
    print(f"  Tools: {', '.join(tool_names) if tool_names else 'None'}")
    
    agent = project.agents.create_version(
        agent_name=agent_name,
        definition=PromptAgentDefinition(
            model=model,
            instructions="You are a helpful assistant. Be concise in your responses.",
            tools=tools if tools else None,
            temperature=0,
        ),
    )
    
    print(f"  Agent ID: {agent.id}")
    print(f"  Agent Name: {agent.name}")
    return agent.name


def run_test(
    project: AIProjectClient,
    agent_name: str,
    prompt: str,
    timeout: int = 300,
) -> None:
    """Run a test query against the agent and measure timing."""
    print(f"\n{'='*60}")
    print(f"Running test with prompt:")
    print(f"  {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
    print(f"{'='*60}\n")
    
    openai_client = project.get_openai_client()
    
    # Track timing
    start_time = time.time()
    last_event_time = start_time
    tool_calls = []
    
    try:
        print("Starting streaming response...\n")
        
        with openai_client.responses.create(
            agent=agent_name,
            input=prompt,
            stream=True,
        ) as stream:
            for event in stream:
                now = time.time()
                elapsed = now - start_time
                since_last = now - last_event_time
                
                event_type = getattr(event, 'type', 'unknown')
                
                # Log significant events
                if event_type == 'response.output_item.added':
                    item = getattr(event, 'item', None)
                    if item:
                        item_type = getattr(item, 'type', 'unknown')
                        if item_type == 'function_call':
                            func_name = getattr(item, 'name', 'unknown')
                            print(f"[{elapsed:6.1f}s] 🔧 Tool call started: {func_name}")
                            tool_calls.append({
                                'name': func_name,
                                'start': elapsed,
                                'end': None,
                            })
                
                elif event_type == 'response.output_item.done':
                    item = getattr(event, 'item', None)
                    if item:
                        item_type = getattr(item, 'type', 'unknown')
                        if item_type == 'function_call':
                            func_name = getattr(item, 'name', 'unknown')
                            # Find matching tool call and mark end
                            for tc in reversed(tool_calls):
                                if tc['name'] == func_name and tc['end'] is None:
                                    tc['end'] = elapsed
                                    duration = tc['end'] - tc['start']
                                    print(f"[{elapsed:6.1f}s] ✅ Tool call complete: {func_name} ({duration:.1f}s)")
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
    parser.add_argument("--prompt", type=str, help="Custom test prompt")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds (default: 300)")
    parser.add_argument("--no-cleanup", action="store_true", help="Don't delete agent after test")
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
    
    # Get prompt
    prompt = args.prompt or DEFAULT_PROMPTS[mode]
    
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
    print(f"  Timeout: {args.timeout}s")
    print()
    
    # Run test
    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
    agent_name = None
    
    try:
        with project:
            agent_name = create_test_agent(
                project,
                model,
                use_mcp=use_mcp,
                use_bing=use_bing,
                bing_connection_id=bing_conn,
            )
            
            run_test(project, agent_name, prompt, timeout=args.timeout)
            
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if agent_name and not args.no_cleanup:
            try:
                with project:
                    cleanup_agent(project, agent_name)
            except Exception as e:
                print(f"Cleanup failed: {e}")


if __name__ == "__main__":
    main()
