---
name: pii-telemetry
description: "Use when: changing PII checks, telemetry events, privacy boundaries, update checks, generated metrics, or docs/telemetry.md."
---

# PII And Telemetry Skill

Use this workflow for privacy, PII, and telemetry changes.

## PII Contract

- PII gate is fail-closed: detected PII or PII service/auth error blocks generation.
- Frontend checks help UX; backend checks at `/api/generate/stream` and `/api/answer/stream` are the authority.
- `Organization` is intentionally excluded from PII categories.

## Telemetry Contract

- Telemetry is anonymous, opt-out, and fail-silent.
- Do not collect note content, generated TSG content, follow-up answers, project endpoints, resource names, agent names, file paths, secrets, or raw exception text.
- Document every event/property change in `docs/telemetry.md`.

## Workflow

1. Inspect `pii_check.py`, `telemetry.py`, `web_app.py`, and related tests.
2. Add tests for fail-closed PII behavior or telemetry privacy shape.
3. Keep event properties low-cardinality and content-free.

## Validation

Run:

```bash
.venv/bin/pytest tests/test_pii_check.py tests/test_telemetry.py tests/test_telemetry_instrumentation.py -q
make test-quick
```
