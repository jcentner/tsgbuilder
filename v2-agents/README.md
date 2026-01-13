# Azure AI Foundry v2 Agent Test

This subfolder contains a test setup for **v2 Azure AI Foundry agents** using the new SDK (`azure-ai-projects>=2.0.0b3`).

## Why v2?

The main project uses v1 agents (`azure-ai-agents` package) which appear in **classic Azure AI Studio**. This test validates creating agents that appear in the **new Microsoft Foundry** portal.

## Key Differences: v1 (Classic) vs v2 (New Foundry)

| Aspect | v1 (Classic) | v2 (New Foundry) |
|--------|-------------|------------------|
| **SDK Package** | `azure-ai-projects==1.0.0` + `azure-ai-agents` | `azure-ai-projects>=2.0.0b3` (NO azure-ai-agents) |
| **Agent Creation** | `project.agents.create_agent()` | `project.agents.create_version()` |
| **Agent Definition** | Various model classes from `azure.ai.agents.models` | `PromptAgentDefinition` from `azure.ai.projects.models` |
| **Tools** | `McpTool` from `azure.ai.agents.models` | `MCPTool` from `azure.ai.projects.models` |
| **Conversations** | Threads + Messages API | `openai_client.conversations` + `responses` |
| **Portal** | Azure AI Studio (classic) | Microsoft Foundry (new) |

## Setup

### 1. Create Virtual Environment

```bash
cd v2-agents
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install --pre -r requirements.txt
```

**CRITICAL**: Do NOT install `azure-ai-agents` — it forces classic mode!

### 3. Verify SDK Version

```bash
python -c "import azure.ai.projects; print(azure.ai.projects.__version__)"
```

Should output `2.0.0b3` or higher.

### 4. Configure Environment

Edit `.env` with your values:

```bash
PROJECT_ENDPOINT=https://jacobcentner-3341-resource.services.ai.azure.com/api/projects/jacobcentner-3341
MODEL_DEPLOYMENT_NAME=gpt-5.2
AGENT_NAME=v2-test-agent
```

### 5. Azure Login

```bash
az login
```

### 6. Run Test

```bash
python v2-agent-test.py
```

## Expected Output

```
============================================================
Azure AI Foundry v2 Agent Test
============================================================

📦 Checking SDK versions...
azure-ai-projects version: 2.0.0b3
✅ Using v2 SDK (new Foundry)
✅ azure-ai-agents not installed (good for v2)

🔧 Configuration:
   Endpoint: https://jacobcentner-3341-resource.services.ai.azure.com/api/projects/jacobcentner-3341
   Model: gpt-4.1
   Agent Name: v2-test-agent

🔌 Connecting to Azure AI Foundry...

🔧 Creating MCP tool (Microsoft Learn)...
   Server URL: https://learn.microsoft.com/api/mcp

🤖 Creating v2 agent...
✅ Agent created in NEW Foundry:
   ID: ...
   Name: v2-test-agent
   Version: 1

💬 Testing agent with conversation...
   ...

✅ All tests passed! Agent appeared in NEW Foundry.
```

## Troubleshooting

### Agent appears in Classic Foundry instead of New Foundry

1. **Check SDK version**: Must be `azure-ai-projects>=2.0.0b3`
   ```bash
   pip show azure-ai-projects
   ```

2. **Uninstall azure-ai-agents**: This package forces classic mode
   ```bash
   pip uninstall azure-ai-agents
   ```

3. **Verify endpoint format**: Must be new Foundry format
   ```
   https://<name>.services.ai.azure.com/api/projects/<project>
   ```

4. **Check project type**: Must be a "Foundry project" (not hub-based)
   - In Azure portal, the project should be under a Foundry resource
   - Enable "Try the new Foundry" toggle in the portal

### Authentication Errors

1. Ensure you're logged in: `az login`
2. Check role assignment: Need "Contributor" or "Owner" on the project
3. Verify endpoint URL is correct

### MCP Tool Not Working

1. Microsoft Learn MCP URL: `https://learn.microsoft.com/api/mcp`
2. No authentication required for this public endpoint
3. Set `require_approval="never"` for auto-approval in tests

## Files

- `v2-agent-test.py` — Main test script with MCP tool integration
- `requirements.txt` — v2 SDK dependencies (no azure-ai-agents!)
- `.env` — Environment configuration (not committed)
- `.gitignore` — Excludes .env and venv/

## References

- [Azure AI Projects SDK v2 Documentation](https://learn.microsoft.com/en-us/python/api/overview/azure/ai-projects-readme?view=azure-python-preview)
- [Microsoft Foundry Samples](https://github.com/microsoft-foundry/foundry-samples)
- [What is Azure AI Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/what-is-foundry)
