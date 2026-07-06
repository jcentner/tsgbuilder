---
description: "Review or implement a TSG Builder frontend/setup/SSE flow change"
---

# Frontend Flow Change

Use this prompt when changing the setup wizard, PII modal, image handling, warning display, streaming progress, copy/download, or follow-up flows.

## Task

Make the requested UI change while keeping the vanilla JS structure and backend contracts intact.

## Steps

1. Read `.github/instructions/frontend.instructions.md`.
2. Inspect the matching Flask endpoint in `web_app.py` before editing JS.
3. Preserve backend PII re-checks and frontend PII modal behavior.
4. Keep review warnings outside rendered TSG content and non-blocking.
5. Keep setup status tied to `/api/status` and validation tied to `/api/validate`.
6. Avoid adding a build step or framework.

## Validate

Run targeted endpoint tests when backend behavior changes, then:

```bash
.venv/bin/pytest tests/test_web_endpoints.py tests/test_pii_check.py -q
make test-quick
```

For visual changes, manually check setup, generation, PII block/redaction, follow-up answers, review-warning handling in the feedback panel, copy/download, and cancellation.
