---
applyTo: "web_app.py,validate_setup.py,delete_agents.py,model_policy.py,telemetry.py,docs/telemetry.md,tests/test_agent_staleness.py,tests/test_telemetry*.py,tests/test_pipeline_telemetry.py,tests/test_model_policy.py"
---

# Setup, Model Policy & Telemetry — Copilot Instructions

These instructions apply when editing setup validation, model policy, agent metadata, or telemetry.

## Setup And Model Policy

- Keep model policy in the shared `model_policy.py` / `error_utils.py` path; do not duplicate allow/block logic in routes or CLI validation.
- Supported models are non-chat `gpt-5.1`, `gpt-5.2`, `gpt-5.4`, and `gpt-5.5` deployments.
- Block `chat`, `mini`, `nano`, `pro`, and `codex` variants, including versioned siblings.
- Unknown underlying model names remain non-blocking only when Azure cannot report `model_name` for an existing deployment.
- `.agent_ids.json` is v2-only and must include role dictionaries with `name`, `version`, and `id`.
- Persist and compare `model_deployment_name`, `underlying_model_name`, and `agent_definition_signature`.
- Missing, blank, mismatched, or stale agent metadata must block generation readiness until agents are recreated.
- Generation endpoints must re-check agent readiness before calling `run_pipeline()`.

## Telemetry

- Telemetry is anonymous and fail-silent.
- Never collect note content, generated TSG content, follow-up answers, file paths, resource names, project endpoints, agent names, secrets, or raw exception text.
- For user-submitted signals (e.g. the `tsg_feedback` event), validate enum fields server-side against a closed vocabulary and reject out-of-enum values; clamp or drop numeric buckets to prevent high-cardinality dimensions — this is the PII boundary. Shared feedback/eval enums live in `quality_taxonomy.py`.
- Document any event or property changes in `docs/telemetry.md` and test them.
