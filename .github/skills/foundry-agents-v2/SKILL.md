---
name: foundry-agents-v2
description: "Use when: working with the Azure AI Foundry v2 SDK — AIProjectClient, agent creation (create_version / PromptAgentDefinition), the Responses API (responses.create), agent_reference vs agent, MCP/Web Search tools, streaming events, or azure-ai-projects version breakage."
---

# Foundry Agents v2 SDK Skill

Reference for the Azure AI Foundry **v2** (non-hub, GA) agent stack that TSG Builder is built on. Use this to avoid rediscovering the SDK contract from `pipeline.py` and `web_app.py` each time. Ground any change against those files; they are source-of-truth.

## Package Pins (`requirements.txt`)

- `azure-ai-projects==2.0.0` — the v2 SDK (`AIProjectClient`, `project.agents`, `project.get_openai_client()`).
- `openai==2.24.0` — the client used for the Responses API (`responses.create`).
- `azure-identity==1.25.2` — `DefaultAzureCredential` (typically `az login`).
- **Never add `azure-ai-agents`.** It forces classic/hub Foundry mode and breaks the v2 path. This is called out in `requirements.txt` on purpose.
- Version bumps of `azure-ai-projects` have introduced breaking changes before (e.g. the `agent` → `agent_reference` migration). Treat any bump as a contract change: run `tests/test_pipeline_sdk_contract.py`.

## Client + Auth

```python
from azure.ai.projects import AIProjectClient
project = AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=DefaultAzureCredential())
openai_client = project.get_openai_client()
```

- `PROJECT_ENDPOINT` is a Foundry **project** endpoint (`https://<res>.services.ai.azure.com/api/projects/<name>`), not a hub.
- Use `with project:` as a context manager. Once it closes you must recreate the client before reuse (see `web_app.py` agent-creation flow).

## Agent Creation (v2)

```python
from azure.ai.projects.models import PromptAgentDefinition, MCPTool, WebSearchPreviewTool

researcher = project.agents.create_version(
    agent_name=f"{prefix}-Researcher",
    definition=PromptAgentDefinition(
        model=model,                 # deployment name, non-chat GPT-5 family
        instructions=RESEARCH_STAGE_INSTRUCTIONS,
        tools=[mcp_tool, web_search_tool],
    ),
)
# returns an object with .name, .version, .id  → persisted in .agent_ids.json
```

- `create_version` (not a `create_agent`/assistant call) is the v2 pattern; each call produces a versioned agent definition.
- **Researcher gets tools; Writer and Reviewer get none** (mirrors the pipeline contract).
- Tools:
  - `MCPTool(server_label="learn", server_url="https://learn.microsoft.com/api/mcp", require_approval="never")`
  - `WebSearchPreviewTool(search_context_size="high")` — Microsoft-managed Bing, **no connection ID required**.

## Running a Stage (Responses API)

```python
stream_kwargs = {
    "stream": True,
    "input": user_message,
    "extra_body": {
        "agent_reference": {"name": agent_name, "type": "agent_reference"},
    },
}
stream_response = openai_client.responses.create(**stream_kwargs)
```

- **CRITICAL:** the agent goes under `extra_body["agent_reference"]` with `type="agent_reference"`. The old `agent` key is dead (removed in SDK ≥ 2.0.0b4). `tests/test_pipeline_sdk_contract.py` guards this.
- Session continuity is ID-prefix driven:
  - `conv_*` → `extra_body["conversation"] = conversation_id`
  - `resp_*` → `previous_response_id = conversation_id` (top-level kwarg, not in `extra_body`)

## Streaming Events

- Terminal/success: `response.completed` — read `response.output_text`, `response.conversation_id`, `response.id`, and `response.usage.input_tokens` / `.output_tokens`.
- Failure: `error` events and `response.failed` (parsed by `_extract_stream_error`).
- Tool activity: `web_search_call` (current) — `bing_grounding_call` is the legacy name still handled for back-compat.
- Timeouts (`pipeline.py`): per-tool ~90s (`TOOL_TIMEOUT`; Bing <30s, MCP <60s typical) and `STREAM_IDLE_TIMEOUT = 120s` for a hung stream.

## Model Policy

Supported deployments are the non-chat GPT-5 family (`gpt-5.1`, `gpt-5.2`, `gpt-5.4`, `gpt-5.5`); `chat`/`mini`/`nano`/`pro`/`codex` variants are blocked. See the `foundry-agent-setup` skill and `model_policy.py` for the authoritative allow/block logic.

## Validation

```bash
.venv/bin/pytest tests/test_pipeline_sdk_contract.py -q
make test-quick
```

Run the SDK contract tests after any `azure-ai-projects` / `openai` bump or change to agent creation, `responses.create` kwargs, or streaming event handling.
