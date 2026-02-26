# TSG Builder — Copilot Instructions

Use this as authoritative guidance when making changes or answering questions about the codebase. Detailed pipeline stage contracts live in `.github/instructions/` as path-specific instruction files.

> **📝 Maintenance Note**: When discussing this codebase, if we identify undocumented intentions or expected behaviors, prompt the user to update this file or the relevant `.instructions.md` file.

## Prompt Sync Rule

When behavior changes in any stage prompt/constants, update the relevant instructions file in the same PR:
- Stage prompts live in `tsg_constants.py` → pipeline behavior in `.github/instructions/pipeline.instructions.md`
- UI changes → `.github/instructions/frontend.instructions.md`

If implementation and instructions disagree, implementation is source-of-truth. Update instructions immediately.

## Project Overview

TSG Builder transforms troubleshooting notes into structured Technical Support Guides (TSGs) through a three-stage AI pipeline (Research → Write → Review) for Azure Support teams. It runs as a Flask web app backed by Azure AI Foundry agents.

- **Language**: Python 3.11 (CI pinned)
- **Runtime**: Flask dev server or PyInstaller standalone executable
- **AI backend**: Azure AI Foundry v2 SDK, gpt-5.2 deployments only
- **Auth**: `DefaultAzureCredential` (typically `az login`)
- **PII gate**: Azure AI Language API (fail-closed pre-flight check)

## Build / Test / Run

```bash
make setup          # Create venv + install deps (first time)
make ui             # Start web UI at http://localhost:5000
make ui TEST=1      # Start with verbose logging + stage output capture
make test           # Run full pytest suite
make test-unit      # Fast: unit tests only (-m unit)
make test-quick     # Skip dep reinstall
make test-cov       # With coverage report
make lint           # py_compile syntax check
make build          # PyInstaller standalone executable
make clean          # Remove .venv, caches, agent IDs
make clean DELETE_AGENTS=1  # Also delete agents from Azure
```

Always run `make test` before submitting changes. Tests live in `tests/` with shared fixtures in `tests/conftest.py`.

## Folder Structure

```
├── pipeline.py          # Pipeline orchestration, error classification, retry logic
├── tsg_constants.py     # TSG template, stage prompts, REQUIRED_TSG_HEADINGS, validate_tsg_output()
├── web_app.py           # Flask server, SSE streaming, setup/iteration endpoints
├── pii_check.py         # PII detection gate (Azure AI Language)
├── error_utils.py       # Shared Azure SDK error classification
├── telemetry.py         # Anonymous usage telemetry
├── version.py           # Single source of truth: APP_VERSION, GITHUB_URL, TSG_SIGNATURE
├── validate_setup.py    # CLI environment validation
├── build_exe.py         # PyInstaller build (bundles templates/ + static/)
├── delete_agents.py     # Agent cleanup utility
├── templates/index.html # Web UI HTML
├── static/js/main.js    # Core UI logic (SSE, rendering, copy/download, PII modal)
├── static/js/setup.js   # Setup wizard client logic
├── static/css/styles.css# CSS custom properties + component styles
├── tests/               # Pytest suite (conftest.py has shared fixtures)
├── docs/                # architecture.md, telemetry.md, releasing.md
└── examples/            # Test inputs and expected outputs
```

## Core Design Principles

1. **TSGs are operations manuals** — authoritative, no source attributions, no meta-commentary. Production-ready.
2. **User notes are authoritative** — treat as trusted source material. Never reject output because notes differ from public docs.
3. **Warnings inform, never block** — doc discrepancies surface as UI warnings, never inside TSG content, never blocking generation.
4. **MISSING = absent, not unverified** — `{{MISSING::<Section>::<Hint>}}` only when required content is truly absent from notes AND research.
5. **Pipeline always produces output** — unless there's a real technical failure.

## Blocking vs Warning Matrix

| Condition | Outcome |
|---|---|
| PII detected in notes/follow-up answers | **Block** until edited/redacted |
| PII check service/auth error | **Block** (fail-closed) |
| Review `accuracy_issues` / `suggestions` | **Warn only** |
| Model is gpt-5.2 (non-chat) | **Pass** (fully compatible) |
| Model is gpt-5.1 (non-chat) | **Warn only** (`critical: false`) — may work but prompts optimized for 5.2 |
| Model is any `-chat` variant | **Block** (`critical: true`) — lacks image input, limited Agent Service tool support |
| Model is any other (gpt-5, gpt-4.1, etc.) | **Block** (`critical: true`) — unsupported Agent Service tools/capabilities |

## Code Conventions

- Use type hints on all function signatures
- All Python source files in the repo root (flat layout, no `src/` package)
- `version.py` is the sole source of truth for version — update only there
- PII categories defined in `PII_CATEGORIES` in `pii_check.py`; `Organization` intentionally excluded
- Error classification shared via `error_utils.py` — import from there, don't duplicate
- Telemetry events documented in `docs/telemetry.md` — update when adding events

## Version Management

Update `APP_VERSION` in `version.py`, tag `v{version}`, push tag to trigger the CI release workflow (`.github/workflows/build.yml`).

