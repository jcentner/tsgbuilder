---
name: release-packaging
description: "Use when: changing TSG Builder release workflow, PyInstaller build, Windows installer, artifact names, versioning, checksums, or release docs."
---

# Release Packaging Skill

Use this workflow for release, packaging, and versioning changes.

## Release Truth

- `version.py` owns `APP_VERSION`.
- Tag format is `v{APP_VERSION}`.
- Release artifacts are four zips plus `SHA256SUMS.txt`.
- Windows installer is published as `tsg-builder-windows-setup.zip` containing `tsg-builder-windows-setup.exe`.
- Release notes should tell users to recreate agents when prompts, tools, model policy, or agent-definition signature inputs change.

## Workflow

1. Compare `.github/workflows/build.yml`, `build_exe.py`, `installer.iss`, `docs/releasing.md`, and `GETTING_STARTED.md`.
2. Avoid broad packaging rewrites unless a build or release contract requires it.
3. Keep executable naming and zip naming aligned across workflow, docs, and release body.
4. Treat manual release dispatch carefully; prefer tag-based release creation or reading `APP_VERSION`.

## Validation

Run `make test`, `make lint`, and `git diff --check`. Use `make build` when packaging logic changes.
