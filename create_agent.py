#!/usr/bin/env python3
"""
create_agent.py — create an Azure AI Foundry Agent that formats notes into TSGs.

Steps:
- Connects to your Azure AI Foundry project using DefaultAzureCredential
- Creates an agent with Bing Search (and optionally the Learn MCP server) attached
- Saves the new agent's id to ./.agent_id for ask_agent.py to use
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import McpTool, BingGroundingTool

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
  agent_name = os.getenv("AGENT_NAME", "TSG-Builder")
  enable_learn = os.getenv("ENABLE_LEARN_MCP", "false").lower() in {"1", "true", "yes"}

  project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())

  tools = []
  # Always attach Bing grounding for doc lookup.
  tools.extend(BingGroundingTool(connection_id=conn_id).definitions)

  # Optionally attach Learn MCP (no auth required).
  if enable_learn:
    tools.extend(
      McpTool(server_label="learn", server_url=LEARN_MCP_URL).definitions
    )

  with project:
    agent = project.agents.create_agent(
      model=model,
      name=agent_name,
      instructions=AGENT_INSTRUCTIONS,
      tools=tools,
    )

  Path(".agent_id").write_text(agent.id + "\n", encoding="utf-8")
  print(f"Created agent: {agent.id} (name='{agent_name}'). Wrote .agent_id")


if __name__ == "__main__":
  main()
