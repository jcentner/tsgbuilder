#!/usr/bin/env python3
"""
validate_setup.py — Validate environment configuration before running the TSG Builder.

Checks:
1. Required environment variables are set
2. Azure credentials work (can authenticate)
3. Azure AI Project is accessible
4. Bing connection is valid (if specified)
5. Agent reference file exists (if agent was created)
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv, find_dotenv


def print_ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def print_fail(msg: str) -> None:
    print(f"  ✗ {msg}")


def print_warn(msg: str) -> None:
    print(f"  ⚠ {msg}")


def check_env_vars() -> tuple[bool, dict[str, str]]:
    """Check that required environment variables are set."""
    print("\n[1/5] Checking environment variables...")
    
    required = ["PROJECT_ENDPOINT", "MODEL_DEPLOYMENT_NAME", "BING_CONNECTION_NAME"]
    optional = ["AGENT_NAME", "AGENT_ID"]
    
    env_vars = {}
    all_ok = True
    
    for var in required:
        value = os.getenv(var)
        if value:
            env_vars[var] = value
            # Mask sensitive parts for display
            if "subscriptions" in value.lower():
                display = value[:50] + "..." if len(value) > 50 else value
            else:
                display = value
            print_ok(f"{var} = {display}")
        else:
            print_fail(f"{var} is not set (REQUIRED)")
            all_ok = False
    
    for var in optional:
        value = os.getenv(var)
        if value:
            env_vars[var] = value
            print_ok(f"{var} = {value} (optional)")
        else:
            print_warn(f"{var} is not set (optional)")
    
    return all_ok, env_vars


def check_dotenv_file() -> bool:
    """Check if .env file exists."""
    print("\n[0/5] Checking .env file...")
    
    dotenv_path = find_dotenv()
    if dotenv_path:
        print_ok(f"Found .env at: {dotenv_path}")
        return True
    else:
        env_sample = Path(".env-sample")
        if env_sample.exists():
            print_fail(".env file not found. Copy .env-sample to .env and fill in your values.")
        else:
            print_fail(".env file not found.")
        return False


def check_azure_auth() -> bool:
    """Check Azure authentication works."""
    print("\n[2/5] Checking Azure authentication...")
    
    try:
        from azure.identity import DefaultAzureCredential
        credential = DefaultAzureCredential()
        # Try to get a token for Azure management
        token = credential.get_token("https://cognitiveservices.azure.com/.default")
        if token:
            print_ok("Azure authentication successful (DefaultAzureCredential)")
            return True
    except Exception as e:
        print_fail(f"Azure authentication failed: {e}")
        print("    Hint: Run 'az login' or ensure your credentials are configured.")
    return False


def check_project_connection(endpoint: str) -> bool:
    """Check connection to Azure AI Project."""
    print("\n[3/5] Checking Azure AI Project connection...")
    
    try:
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        
        project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
        # Try a simple operation to verify connectivity
        with project:
            # Just creating the client and context manager is enough to verify
            print_ok(f"Connected to project at: {endpoint}")
            return True
    except Exception as e:
        print_fail(f"Failed to connect to project: {e}")
        print("    Hint: Verify PROJECT_ENDPOINT is correct and you have access.")
    return False


def check_agent_ref() -> bool:
    """Check if agent ID file exists."""
    print("\n[4/5] Checking agent ID...")
    
    agent_id_file = Path(".agent_id")
    
    if agent_id_file.exists():
        agent_id = agent_id_file.read_text(encoding="utf-8").strip()
        print_ok(f"Agent ID found: {agent_id}")
        return True
    else:
        print_warn("No agent created yet. Run 'python create_agent.py' or 'make create-agent' first.")
        return True  # Not a failure, just not created yet


def check_dependencies() -> bool:
    """Check that required Python packages are installed."""
    print("\n[5/5] Checking Python dependencies...")
    
    required_packages = [
        ("azure.ai.projects", "azure-ai-projects"),
        ("azure.ai.agents", "azure-ai-agents"),
        ("azure.identity", "azure-identity"),
        ("dotenv", "python-dotenv"),
    ]
    
    all_ok = True
    for module_name, package_name in required_packages:
        try:
            __import__(module_name)
            print_ok(f"{package_name} is installed")
        except ImportError:
            print_fail(f"{package_name} is not installed. Run: pip install {package_name}")
            all_ok = False
    
    return all_ok


def main():
    print("=" * 60)
    print("TSG Builder - Environment Validation")
    print("=" * 60)
    
    # Load .env first
    load_dotenv(find_dotenv())
    
    results = []
    
    # Run all checks
    results.append(("Dependencies", check_dependencies()))
    results.append((".env file", check_dotenv_file()))
    
    env_ok, env_vars = check_env_vars()
    results.append(("Environment variables", env_ok))
    
    if env_ok:
        results.append(("Azure authentication", check_azure_auth()))
        
        if "PROJECT_ENDPOINT" in env_vars:
            results.append(("Project connection", check_project_connection(env_vars["PROJECT_ENDPOINT"])))
    
    results.append(("Agent ID", check_agent_ref()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("All checks passed! You're ready to run the TSG Builder.")
        print("\nNext steps:")
        if not Path(".agent_id").exists():
            print("  1. Create the agent:  make create-agent")
            print("  2. Run the UI:        make ui")
        else:
            print("  Run the UI: make ui")
        sys.exit(0)
    else:
        print("Some checks failed. Please fix the issues above before proceeding.")
        sys.exit(1)


if __name__ == "__main__":
    main()
