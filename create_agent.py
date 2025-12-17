#!/usr/bin/env python3
"""
create_agent.py — create a classic Azure AI Foundry Agent that formats notes into TSGs.

Steps:
- Connects to your Azure AI Foundry project using DefaultAzureCredential
- Creates an agent with Bing Search and Microsoft Learn MCP attached (classic Agents API)
- Saves the agent id for ask_agent.py to use
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import BingGroundingTool, McpTool

from tsg_constants import AGENT_INSTRUCTIONS

LEARN_MCP_URL = "https://learn.microsoft.com/api/mcp"  # public, no auth required


def require_env(var_name: str) -> str:
  value = os.getenv(var_name)
  if not value:
    print(f"ERROR: Missing required environment variable {var_name}.", file=sys.stderr)
    sys.exit(1)
  return value


def main():
  load_dotenv()

  endpoint = require_env("PROJECT_ENDPOINT")
  model = require_env("MODEL_DEPLOYMENT_NAME")
  conn_id = require_env("BING_CONNECTION_NAME")
  agent_name = os.getenv("AGENT_NAME", "tsg-agent")

  project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())

  # Build tools list: Bing grounding + Microsoft Learn MCP
  tools = []
  
  # Bing grounding for web/doc lookup
  bing_tool = BingGroundingTool(connection_id=conn_id)
  tools.extend(bing_tool.definitions)
  
  # Microsoft Learn MCP for official documentation
  mcp_tool = McpTool(server_label="learn", server_url=LEARN_MCP_URL)
  tools.extend(mcp_tool.definitions)

  with project:
    agent = project.agents.create_agent(
      model=model,
      name=agent_name,
      instructions=AGENT_INSTRUCTIONS,
      tools=tools,
    )

  # Persist agent id for inference.
  Path(".agent_id").write_text(agent.id + "\n", encoding="utf-8")
  print(f"Created agent: id={agent.id} name={agent_name}")


if __name__ == "__main__":
  main()
