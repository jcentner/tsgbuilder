---
description: "Run a release readiness review for TSG Builder"
---

# Release Readiness

Use this prompt before cutting a TSG Builder release.

## Checklist

1. Confirm `APP_VERSION` in `version.py` matches the planned tag.
2. Confirm `.github/workflows/build.yml` release artifacts match `docs/releasing.md`.
3. Confirm release notes mention agent recreation if prompts, tools, model policy, or agent-definition signature inputs changed.
4. Confirm `GETTING_STARTED.md` installer and zip upgrade instructions match current artifacts.
5. Confirm telemetry docs match any event/property changes.
6. Confirm `.env`, `.agent_ids.json`, `dist/`, `build/`, caches, `tmp/`, and `issues/` are not staged.

## Validate

Run:

```bash
make test
make lint
git diff --check
```

Optional packaging checks:

```bash
make build
```
