---
applyTo: "tests/**/*.py,tests/README.md,pytest.ini"
---

# Tests — Copilot Instructions

These instructions apply when editing the pytest suite.

## Test Style

- Prefer focused unit tests with mocked Azure SDK, network, browser, and filesystem dependencies.
- Use existing fixtures in `tests/conftest.py` before adding new helpers.
- Keep tests behavior-scoped: name the user-visible or contract behavior, not implementation mechanics.
- Add regression cases for edge inputs when changing parsing, validation, streaming, or persistence.

## Contracts To Preserve

- Model policy tests must cover supported non-chat `gpt-5.1`, `gpt-5.2`, `gpt-5.4`, `gpt-5.5`; blocked `chat`, `mini`, `nano`, `pro`, `codex` variants; version suffixes; near misses such as `gpt-5.10`; and unknown model names.
- Setup/staleness tests must treat missing or blank agent metadata as not ready for generation.
- PII tests must preserve fail-closed behavior for service/auth errors and detected PII.
- Telemetry tests must never assert or introduce collection of note content, TSG content, file paths, resource names, secrets, or raw exception text.
- Pipeline marker tests must preserve `<!-- TSG_BEGIN/END -->` and `<!-- QUESTIONS_BEGIN/END -->` contracts.

## Validation

- Run the narrow affected test first, for example `.venv/bin/pytest tests/test_agent_staleness.py -q`.
- Run `make test-quick` before committing broad behavior changes.
- Run `make test` before release or final submission.
