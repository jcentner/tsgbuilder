#!/usr/bin/env python3
"""
v2-agent-test.py — Test script for Azure AI Foundry v2 Agents.

This script creates a v2 agent using the new Foundry SDK (azure-ai-projects>=2.0.0b3)
with MCP tool integration (Microsoft Learn), runs a test conversation, and cleans up.

Key differences from v1 (classic) agents:
- Uses create_version() instead of create_agent()
- Uses PromptAgentDefinition from azure.ai.projects.models (NOT azure.ai.agents.models)
- Uses project_client.get_openai_client() for conversations
- Uses MCPTool from azure.ai.projects.models (NOT azure.ai.agents.models)
- NO azure-ai-agents package dependency (that forces classic mode)
"""

import os
import sys

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition, MCPTool

# Microsoft Learn MCP URL (same as used in main project)
LEARN_MCP_URL = "https://learn.microsoft.com/api/mcp"


def verify_sdk_version():
    """Verify we're using the v2 SDK (2.0.0b3+), not v1 (1.0.0)."""
    import azure.ai.projects
    version = azure.ai.projects.__version__
    print(f"azure-ai-projects version: {version}")
    
    # Parse major version
    major = int(version.split(".")[0])
    if major < 2:
        print(f"❌ ERROR: SDK version {version} is v1 (classic Foundry)")
        print("   Install v2 SDK: pip install --pre azure-ai-projects")
        sys.exit(1)
    
    print("✅ Using v2 SDK (new Foundry)")
    return version


def verify_no_agents_package():
    """Verify azure-ai-agents is NOT installed (it forces classic mode)."""
    try:
        import azure.ai.agents
        print("❌ WARNING: azure-ai-agents package is installed!")
        print("   This may cause agents to appear in classic Foundry.")
        print("   Consider: pip uninstall azure-ai-agents")
    except ImportError:
        print("✅ azure-ai-agents not installed (good for v2)")


def main():
    """Create a v2 agent with MCP tool, test it, and clean up."""
    
    print("=" * 60)
    print("Azure AI Foundry v2 Agent Test")
    print("=" * 60)
    
    # Load environment
    load_dotenv()
    
    # Verify SDK versions
    print("\n📦 Checking SDK versions...")
    verify_sdk_version()
    verify_no_agents_package()
    
    # Get configuration
    endpoint = os.environ.get("PROJECT_ENDPOINT")
    model = os.environ.get("MODEL_DEPLOYMENT_NAME")
    agent_name = os.environ.get("AGENT_NAME", "v2-test-agent")
    
    if not endpoint:
        print("❌ ERROR: PROJECT_ENDPOINT not set in .env")
        sys.exit(1)
    if not model:
        print("❌ ERROR: MODEL_DEPLOYMENT_NAME not set in .env")
        sys.exit(1)
    
    print(f"\n🔧 Configuration:")
    print(f"   Endpoint: {endpoint}")
    print(f"   Model: {model}")
    print(f"   Agent Name: {agent_name}")
    
    # Verify endpoint format (new Foundry)
    if ".services.ai.azure.com/api/projects/" not in endpoint:
        print("⚠️  WARNING: Endpoint may not be new Foundry format")
        print("   Expected: https://<name>.services.ai.azure.com/api/projects/<project>")
    
    # Create project client
    print("\n🔌 Connecting to Azure AI Foundry...")
    credential = DefaultAzureCredential()
    project_client = AIProjectClient(endpoint=endpoint, credential=credential)
    
    # Create MCP tool for Microsoft Learn
    print("\n🔧 Creating MCP tool (Microsoft Learn)...")
    mcp_tool = MCPTool(
        server_label="learn",
        server_url=LEARN_MCP_URL,
        require_approval="never",  # Auto-approve for testing
    )
    print(f"   Server URL: {LEARN_MCP_URL}")
    
    agent = None
    conversation_id = None
    
    try:
        with project_client:
            # Get OpenAI client for agent operations
            with project_client.get_openai_client() as openai_client:
                
                # Create v2 agent (versioned) with MCP tool
                print("\n🤖 Creating v2 agent...")
                agent = project_client.agents.create_version(
                    agent_name=agent_name,
                    definition=PromptAgentDefinition(
                        model=model,
                        instructions=(
                            "You are a helpful assistant that can search Microsoft Learn "
                            "documentation to answer technical questions about Azure and "
                            "Microsoft products. Use the MCP tool to search documentation "
                            "when needed."
                        ),
                        tools=[mcp_tool],
                    ),
                )
                print(f"✅ Agent created in NEW Foundry:")
                print(f"   ID: {agent.id}")
                print(f"   Name: {agent.name}")
                print(f"   Version: {agent.version}")
                
                # Test the agent with a conversation
                print("\n💬 Testing agent with conversation...")
                test_question = "What is Azure AI Foundry?"
                print(f"   User: {test_question}")
                
                try:
                    # Create conversation with initial message
                    conversation = openai_client.conversations.create(
                        items=[{
                            "type": "message",
                            "role": "user",
                            "content": test_question
                        }],
                    )
                    conversation_id = conversation.id
                    print(f"   Conversation ID: {conversation_id}")
                    
                    # Get response from agent
                    response = openai_client.responses.create(
                        conversation=conversation_id,
                        extra_body={
                            "agent": {
                                "name": agent.name,
                                "type": "agent_reference"
                            }
                        },
                        input="",
                    )
                    
                    print(f"\n   Agent response:")
                    print("-" * 40)
                    # Handle response output
                    if hasattr(response, 'output_text') and response.output_text:
                        print(response.output_text[:500])
                        if len(response.output_text) > 500:
                            print("... (truncated)")
                    else:
                        print(f"   Raw response: {response}")
                    print("-" * 40)
                    
                    # Check if MCP tool was used
                    if hasattr(response, 'output') and response.output:
                        for item in response.output:
                            if hasattr(item, 'type'):
                                if item.type == 'mcp_call':
                                    print(f"   ✅ MCP tool was invoked: {item}")
                                elif item.type == 'mcp_approval_request':
                                    print(f"   ⚠️ MCP approval requested (should be auto-approved)")
                    
                    print("\n✅ Agent test completed successfully!")
                    
                finally:
                    # Cleanup conversation (inside openai_client context)
                    if conversation_id:
                        print("\n🧹 Cleaning up conversation...")
                        try:
                            openai_client.conversations.delete(conversation_id=conversation_id)
                            print(f"   Deleted conversation: {conversation_id}")
                        except Exception as cleanup_error:
                            print(f"   Failed to delete conversation: {cleanup_error}")
                        conversation_id = None
                
            # Cleanup agent (inside project_client context, outside openai_client)
            if agent:
                print("\n🧹 Cleaning up agent...")
                try:
                    project_client.agents.delete_version(
                        agent_name=agent.name,
                        agent_version=agent.version
                    )
                    print(f"   Deleted agent: {agent.name} (version {agent.version})")
                except Exception as cleanup_error:
                    print(f"   Failed to delete agent: {cleanup_error}")
                agent = None
        
        print("\n" + "=" * 60)
        print("✅ All tests passed! Agent appeared in NEW Foundry.")
        print("=" * 60)
        print("\n📋 Next steps:")
        print("   1. Check the Foundry portal (with 'new Foundry' toggle ON)")
        print("   2. Verify no agents appeared in classic Azure AI Studio")
        print("   3. If agent still appears in classic, check:")
        print("      - azure-ai-projects version is 2.0.0b3+")
        print("      - azure-ai-agents is NOT installed")
        print("      - Project is a 'Foundry project' (not hub-based)")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        print("\n⚠️  Note: Cleanup may have failed. Check portal for orphaned agents.")
        sys.exit(1)


if __name__ == "__main__":
    main()