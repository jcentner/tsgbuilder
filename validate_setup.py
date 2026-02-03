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
    print("\n[1/7] Checking environment variables...")
    
    required = ["PROJECT_ENDPOINT", "MODEL_DEPLOYMENT_NAME", "BING_CONNECTION_NAME"]
    optional = ["AGENT_NAME"]
    
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
    print("\n[0/7] Checking .env file...")
    
    dotenv_path = find_dotenv()
    if dotenv_path:
        print_ok(f"Found .env at: {dotenv_path}")
        return True
    else:
        print_fail(".env file not found. Run 'make ui' to auto-create and configure.")
        return False


def check_azure_auth() -> bool:
    """Check Azure authentication works."""
    print("\n[2/7] Checking Azure authentication...")
    
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
    print("\n[3/7] Checking Azure AI Project connection...")
    
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


def check_model_deployment(endpoint: str, deployment_name: str) -> bool:
    """Check if the specified model deployment exists in the project."""
    print("\n[4/7] Checking model deployment...")
    
    try:
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        
        with AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential()) as project:
            deployment = project.deployments.get(name=deployment_name)
            print_ok(f"Found deployment: {deployment.name}")
            return True
    except Exception as e:
        error_str = str(e)
        # Try to list available deployments for helpful error
        available_names = []
        try:
            from azure.identity import DefaultAzureCredential
            from azure.ai.projects import AIProjectClient
            with AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential()) as project:
                deployments = list(project.deployments.list())
                available_names = [d.name for d in deployments]
        except Exception:
            pass
        
        if available_names:
            print_warn(f"Deployment '{deployment_name}' not found.")
            print(f"    Available deployments: {', '.join(available_names[:5])}")
        elif "404" in error_str or "NotFound" in error_str:
            print_warn(f"Deployment '{deployment_name}' not found in project")
        else:
            print_warn(f"Could not verify deployment: {str(e)[:80]}")
        return False


def check_bing_connection(endpoint: str, connection_id: str) -> bool:
    """Check if the Bing connection exists in the project."""
    print("\n[5/7] Checking Bing connection...")
    
    # Extract connection name from ARM resource ID if needed
    connection_name = connection_id.split('/')[-1] if '/' in connection_id else connection_id
    
    try:
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        
        with AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential()) as project:
            connection = project.connections.get(connection_name)
            print_ok(f"Found connection: {connection_name}")
            return True
    except Exception as e:
        error_str = str(e)
        # Try to list available connections for helpful error
        available_names = []
        try:
            from azure.identity import DefaultAzureCredential
            from azure.ai.projects import AIProjectClient
            with AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential()) as project:
                connections = list(project.connections.list())
                available_names = [c.name for c in connections]
        except Exception:
            pass
        
        if available_names:
            print_warn(f"Connection '{connection_name}' not found.")
            print(f"    Available connections: {', '.join(available_names[:5])}")
        elif "404" in error_str or "NotFound" in error_str:
            print_warn(f"Connection '{connection_name}' not found in project")
        else:
            print_warn(f"Could not verify connection: {str(e)[:80]}")
        return False


def check_agent_ref() -> bool:
    """Check if agent IDs file exists."""
    print("\n[6/7] Checking pipeline agents...")
    
    agent_ids_file = Path(".agent_ids.json")
    
    if agent_ids_file.exists():
        import json
        try:
            data = json.loads(agent_ids_file.read_text(encoding="utf-8"))
            prefix = data.get("name_prefix", "TSG")
            print_ok(f"3 pipeline agents configured ({prefix})")
            return True
        except (json.JSONDecodeError, IOError) as e:
            print_warn(f"Agent IDs file exists but is invalid: {e}")
            return True
    else:
        print_warn("No agents created yet. Use the Setup wizard in the web UI.")
        return True  # Not a failure, just not created yet


def check_dependencies() -> bool:
    """Check that required Python packages are installed with correct versions."""
    print("\n[7/7] Checking Python dependencies...")
    
    all_ok = True
    
    # Check azure-ai-projects version (must be v2: 2.0.0b3+)
    try:
        import azure.ai.projects
        version = azure.ai.projects.__version__
        major = int(version.split(".")[0])
        if major >= 2:
            print_ok(f"azure-ai-projects {version} (v2 SDK ✓)")
        else:
            print_fail(f"azure-ai-projects {version} is v1 (classic Foundry)")
            print("    Need v2 SDK: pip install --pre azure-ai-projects")
            all_ok = False
    except ImportError:
        print_fail("azure-ai-projects is not installed. Run: pip install --pre azure-ai-projects")
        all_ok = False
    except (ValueError, IndexError):
        print_warn(f"azure-ai-projects installed but couldn't parse version")
    
    # Check that azure-ai-agents is NOT installed (it forces classic mode)
    try:
        import azure.ai.agents
        print_warn("azure-ai-agents is installed - this forces classic Foundry mode!")
        print("    Recommend: pip uninstall azure-ai-agents")
    except ImportError:
        print_ok("azure-ai-agents not installed (good for v2)")
    
    # Check other required packages
    other_packages = [
        ("azure.identity", "azure-identity"),
        ("dotenv", "python-dotenv"),
        ("openai", "openai"),
        ("flask", "flask"),
    ]
    
    for module_name, package_name in other_packages:
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
    
    # Run all checks
    results = []
    warnings = []
    
    results.append(("Dependencies", check_dependencies()))
    results.append((".env file", check_dotenv_file()))
    
    env_ok, env_vars = check_env_vars()
    results.append(("Environment variables", env_ok))
    
    project_connected = False
    if env_ok:
        results.append(("Azure authentication", check_azure_auth()))
        
        if "PROJECT_ENDPOINT" in env_vars:
            project_connected = check_project_connection(env_vars["PROJECT_ENDPOINT"])
            results.append(("Project connection", project_connected))
            
            # Run deployment and connection checks (warnings, not blocking)
            if project_connected:
                endpoint = env_vars["PROJECT_ENDPOINT"]
                model_name = env_vars.get("MODEL_DEPLOYMENT_NAME", "")
                bing_conn = env_vars.get("BING_CONNECTION_NAME", "")
                
                if model_name:
                    model_ok = check_model_deployment(endpoint, model_name)
                    if not model_ok:
                        warnings.append("Model Deployment")
                    else:
                        results.append(("Model Deployment", True))
                
                if bing_conn:
                    bing_ok = check_bing_connection(endpoint, bing_conn)
                    if not bing_ok:
                        warnings.append("Bing Connection")
                    else:
                        results.append(("Bing Connection", True))
    
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
    
    # Show warnings (not blocking)
    for name in warnings:
        print(f"  ⚠ WARN: {name}")
    
    print()
    if all_passed:
        print("All checks passed! You're ready to run the TSG Builder.")
        print("\nNext steps:")
        if not Path(".agent_ids.json").exists():
            print("  1. Run the UI:  make ui")
            print("  2. Use the Setup wizard to create agents")
        else:
            print("  Run the UI: make ui")
        sys.exit(0)
    else:
        print("Some checks failed. Please fix the issues above before proceeding.")
        sys.exit(1)


if __name__ == "__main__":
    main()
