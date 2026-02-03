#!/usr/bin/env python3
"""Delete TSG Builder agents from Azure AI Foundry.

This script reads agent info from .agent_ids.json and deletes them
from the configured Azure AI project using v2 API (delete_version).

Usage:
    python delete_agents.py         # Interactive confirmation
    python delete_agents.py --yes   # Skip confirmation
"""

import json
import os
import sys
from pathlib import Path

from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

AGENT_IDS_FILE = Path(".agent_ids.json")


def delete_agents(skip_confirm: bool = False) -> bool:
    """Delete all TSG Builder agents.
    
    Args:
        skip_confirm: If True, skip the confirmation prompt.
        
    Returns:
        True if agents were deleted successfully, False otherwise.
    """
    # Check if agent IDs file exists
    if not AGENT_IDS_FILE.exists():
        print("No .agent_ids.json file found. Nothing to delete.")
        return True
    
    # Load agent info
    try:
        data = json.loads(AGENT_IDS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"Error reading .agent_ids.json: {e}")
        return False
    
    agents = {
        "researcher": data.get("researcher"),
        "writer": data.get("writer"),
        "reviewer": data.get("reviewer"),
    }
    
    # Filter out empty entries
    agents = {k: v for k, v in agents.items() if v}
    
    if not agents:
        print("No agent info found in .agent_ids.json. Nothing to delete.")
        return True
    
    # Show what will be deleted
    name_prefix = data.get("name_prefix", "TSG")
    print(f"\nAgents to delete (prefix: {name_prefix}):")
    for role, agent_info in agents.items():
        # Handle both v1 (string ID) and v2 (dict with name/version) formats
        if isinstance(agent_info, dict):
            print(f"  - {role}: {agent_info.get('name')} (version {agent_info.get('version')})")
        else:
            print(f"  - {role}: {agent_info} (v1 format)")
    
    # Confirm unless --yes flag
    if not skip_confirm:
        response = input("\nDelete these agents from Azure? [y/N]: ").strip().lower()
        if response not in ("y", "yes"):
            print("Aborted.")
            return False
    
    # Check for PROJECT_ENDPOINT
    endpoint = os.environ.get("PROJECT_ENDPOINT")
    if not endpoint:
        print("Error: PROJECT_ENDPOINT environment variable is not set.")
        print("Please configure it in your .env file.")
        return False
    
    # Import Azure SDK (delayed to allow script to show help without deps)
    try:
        from azure.ai.projects import AIProjectClient
    except ImportError:
        print("Error: azure-ai-projects package not installed.")
        print("Run: pip install --pre azure-ai-projects")
        return False
    
    # Delete agents
    print("\nDeleting agents...")
    
    try:
        project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
        
        with project:
            for role, agent_info in agents.items():
                try:
                    # Handle v2 format (dict with name/version)
                    if isinstance(agent_info, dict):
                        agent_name = agent_info.get("name")
                        agent_version = agent_info.get("version")
                        project.agents.delete_version(
                            agent_name=agent_name,
                            agent_version=agent_version
                        )
                        print(f"  ✓ Deleted {role}: {agent_name} (version {agent_version})")
                    else:
                        # Fallback for v1 format (string ID) - try v1 delete
                        project.agents.delete_agent(agent_info)
                        print(f"  ✓ Deleted {role}: {agent_info}")
                except Exception as e:
                    # Agent may already be deleted or not exist
                    print(f"  ⚠ Could not delete {role}: {e}")
        
        print("\nAgent deletion complete.")
        return True
        
    except Exception as e:
        print(f"\nError connecting to Azure: {e}")
        return False


def main():
    skip_confirm = "--yes" in sys.argv or "-y" in sys.argv
    
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        sys.exit(0)
    
    success = delete_agents(skip_confirm=skip_confirm)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
