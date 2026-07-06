---
applyTo: ".github/workflows/*.yml,.github/workflows/*.yaml,installer.iss,build_exe.py,docs/releasing.md,GETTING_STARTED.md,version.py,requirements.txt,Makefile"
---

# Release & Packaging — Copilot Instructions

These instructions apply when editing release, build, packaging, or version files.

## Release Contract

- `version.py` is the only source of truth for `APP_VERSION`.
- CI is pinned to Python 3.11; keep local code compatible with that runtime.
- Release attachments are four zip files plus `SHA256SUMS.txt`:
  - `tsg-builder-linux.zip`
  - `tsg-builder-macos.zip`
  - `tsg-builder-windows.zip`
  - `tsg-builder-windows-setup.zip`
  - `SHA256SUMS.txt`
- The Windows installer zip contains `tsg-builder-windows-setup.exe`; public download docs should name the zip first.
- If agent prompts, tools, model policy, or signature inputs change, release notes should tell users to recreate agents.

## Validation

- Prefer lightweight tests or syntax checks for build scripts before full packaging.
- Run `make test` before release.
- Compare `docs/releasing.md` with `.github/workflows/build.yml` whenever workflow artifact names change.
- Avoid manual release behavior that derives installer version from a branch name; release creation should be tag-based or read `APP_VERSION`.
