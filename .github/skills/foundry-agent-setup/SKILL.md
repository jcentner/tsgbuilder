---
name: foundry-agent-setup
description: "Use when: changing Azure AI Foundry setup, model deployment validation, .agent_ids.json, agent staleness, create-agent, validate_setup.py, or supported GPT-5 model policy."
---

# Foundry Agent Setup Skill

Use this workflow for setup wizard, CLI validation, model policy, agent creation, and persisted agent metadata changes.

## Current Policy

- Supported non-chat base models: `gpt-5.1`, `gpt-5.2`, `gpt-5.4`, `gpt-5.5`.
- Block `chat`, `mini`, `nano`, `pro`, and `codex` variants, including versioned siblings.
- Unknown underlying model is non-blocking only when Azure cannot report `model_name` for an existing deployment.
- `.agent_ids.json` is v2-only and requires role objects with `name`, `version`, and `id`.
- Persist and compare `model_deployment_name`, `underlying_model_name`, and `agent_definition_signature`.
- Missing, blank, mismatched, or stale agent metadata blocks generation until agents are recreated.

## Workflow

1. Start with `model_policy.py`, `error_utils.py`, `web_app.py`, and `validate_setup.py`.
2. Keep policy centralized; do not duplicate allow/block logic in routes.
3. If agent definitions change, update the signature inputs and staleness tests.
4. Keep setup UI copy concise and accurate.

## Validation

Run:

```bash
.venv/bin/pytest tests/test_model_policy.py tests/test_agent_staleness.py tests/test_web_endpoints.py::TestModelDeploymentValidation -q
make test-quick
```
