---
description: "Audit TSG Builder docs for stale product, model, setup, and release wording"
---

# Docs Consistency Audit

Use this prompt to review docs after behavior, setup, model policy, packaging, or telemetry changes.

## Task

Find docs that no longer match implementation or tests. Report exact files and minimal fixes.

## Search Targets

- Stale model wording: `gpt-5.2 only`, `Only gpt-5.2`, warning-only `gpt-5.1`, unsupported `gpt-5.4` or `gpt-5.5`.
- Stale agent setup wording: v1 agent IDs, missing model metadata, app-version-only staleness.
- Stale release wording: three zips, bare installer exe as release attachment, missing `SHA256SUMS.txt`.
- Local-only links to `tmp/` or `issues/` from tracked docs.
- Telemetry docs that miss changed event names or properties.

## Validate

Run:

```bash
git diff --check
make test-quick
```
