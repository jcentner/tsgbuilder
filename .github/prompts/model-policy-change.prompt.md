---
description: "Review or implement a TSG Builder model policy change"
---

# Model Policy Change

Use this prompt when changing supported model names, blocked variants, deployment validation, or agent model metadata.

## Task

Implement or review the requested model policy change with the smallest safe diff.

## Steps

1. Inspect `model_policy.py`, `error_utils.py`, `web_app.py`, `validate_setup.py`, and `tests/test_model_policy.py`.
2. Keep allow/block rules centralized; do not duplicate policy logic in Flask routes or CLI validation.
3. Update tests for supported bases, blocked variants, version suffixes, near misses, and unknown model names.
4. If persisted agents are affected, update `tests/test_agent_staleness.py` and setup copy.
5. Update docs and `.github` instructions only after implementation and tests match.

## Validate

Run:

```bash
.venv/bin/pytest tests/test_model_policy.py tests/test_web_endpoints.py::TestModelDeploymentValidation tests/test_agent_staleness.py -q
make test-quick
```
