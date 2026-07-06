---
applyTo: "README.md,GETTING_STARTED.md,docs/**/*.md,examples/README.md,.github/copilot-instructions.md,.github/instructions/*.instructions.md,.github/prompts/*.prompt.md,.github/skills/*/SKILL.md"
---

# Docs — Copilot Instructions

These instructions apply when editing tracked documentation.

## Source Of Truth

- Implementation and tests are source-of-truth. Do not document planned behavior as shipped behavior.
- If a doc is historical or plan-like, mark that status clearly near the top.
- Do not link tracked docs to gitignored local scratch paths such as `tmp/` or `issues/` unless the text explicitly says they are local-only.

## Current Product Truth

- Supported models are non-chat `gpt-5.1`, `gpt-5.2`, `gpt-5.4`, and `gpt-5.5` deployments.
- `chat`, `mini`, `nano`, `pro`, and `codex` variants are blocked until separately validated.
- Existing agents must be recreated when model metadata, the underlying model, or the agent-definition signature no longer matches current setup.
- Release artifacts are four zip files plus `SHA256SUMS.txt`: Linux, macOS, Windows portable, and Windows installer zip.

## Writing Rules

- Keep setup docs actionable; link changing Azure region/model availability to Microsoft Learn instead of hardcoding short region lists.
- Keep public docs free of internal audit notes, local planning scratch, and unsupported model claims.
- When changing telemetry events, update `docs/telemetry.md` in the same change.
- When changing release workflow or packaging, update `docs/releasing.md` in the same change.
