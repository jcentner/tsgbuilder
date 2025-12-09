#!/usr/bin/env python3
"""
create_agent.py — create a new-style Azure AI Foundry Agent that formats notes into TSGs.

Steps:
- Connects to your Azure AI Foundry project using DefaultAzureCredential
- Creates a versioned agent with Bing Search and the Learn MCP server attached
- Saves the agent reference (name:version) and id for ask_agent.py to use
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import McpTool, BingGroundingTool

from tsg_constants import AGENT_INSTRUCTIONS, AGENT_VERSION

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

  tools = []
  # Always attach Bing grounding for doc lookup and Learn MCP for Microsoft docs.
  tools.extend(BingGroundingTool(connection_id=conn_id).definitions)
  tools.extend(McpTool(server_label="learn", server_url=LEARN_MCP_URL).definitions)

  with project:
    agent = project.agents.create(
      model=model,
      name=agent_name,
      instructions=AGENT_INSTRUCTIONS,
      tools=tools,
      version=AGENT_VERSION,
    )

  # Persist both id and name:version reference for inference.
  Path(".agent_id").write_text(agent.id + "\n", encoding="utf-8")
  Path(".agent_ref").write_text(f"{agent_name}:{AGENT_VERSION}\n", encoding="utf-8")
  print(f"Created agent: id={agent.id} ref={agent_name}:{AGENT_VERSION}")


if __name__ == "__main__":
  main()
