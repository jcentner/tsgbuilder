# Releasing TSG Builder

This document covers the release process and build infrastructure for TSG Builder.

## Quick Reference

```bash
# Create and push a release tag
git tag v1.0.0
git push origin v1.0.0

# Pre-release versions (marked as pre-release on GitHub)
git tag v1.0.0-beta.1
git push origin v1.0.0-beta.1
```

After pushing, go to [Actions](../../actions) to ensure the build workflow completes. 
Then go to [Releases](../../releases) to review and publish the draft (appears after build). 

---

## Version Scheme

| Tag Format | Release Type | Example |
|------------|--------------|---------|
| `v1.0.0` | Stable release | `v1.0.0`, `v1.2.3` |
| `v1.0.0-beta.N` | Beta pre-release | `v1.0.0-beta.1` |
| `v1.0.0-rc.N` | Release candidate | `v1.0.0-rc.1` |

Tags containing `-` are automatically marked as pre-releases.

---

## Release Process

### 1. Prepare the Release

1. Ensure all changes are committed and pushed to `main`
2. **Update `APP_VERSION` in `web_app.py`** to match the new version (e.g., `APP_VERSION = "1.1.0"`)
3. Verify tests pass: `make test`

### 2. Create and Push Tag

```bash
# For stable release
git tag v1.0.0
git push origin v1.0.0

# For pre-release
git tag v1.0.0-beta.1
git push origin v1.0.0-beta.1
```

### 3. Monitor the Build

1. Go to **Actions** tab in GitHub
2. Watch the "Build Executables" workflow
3. All three platforms (Linux, macOS, Windows) must succeed

Build takes approximately 3-5 minutes per platform.

### 4. Review and Publish

1. Go to [**Releases** page](https://github.com/jcentner/tsgbuilder/releases)
2. Find the new **draft** release
3. Review:
   - Release notes (auto-generated from commits)
   - All 4 files attached (3 executables + SHA256SUMS.txt)
   - Pre-release checkbox (should be checked for beta/rc)
4. Click **Publish release**

---

## Build Infrastructure

### Workflow File

`.github/workflows/build.yml`

### Triggers

| Trigger | When | Creates Release |
|---------|------|-----------------|
| Push tag `v*` | `git push origin v1.0.0` | Yes (draft) |
| Manual dispatch | Actions → Run workflow | Optional |

### Build Matrix

| Platform | Runner | Output |
|----------|--------|--------|
| Linux | `ubuntu-latest` | `tsg-builder-linux` |
| macOS | `macos-latest` | `tsg-builder-macos` |
| Windows | `windows-latest` | `tsg-builder-windows.exe` |

### Build Steps

1. **Checkout** — Clone repository
2. **Setup Python** — Python 3.11 with pip caching
3. **Install dependencies** — `pip install -r requirements.txt`
4. **Build executable** — `python build_exe.py`
5. **Upload artifact** — Store for release job

### Release Job

Runs after all builds succeed:

1. Downloads all 3 platform artifacts
2. Generates SHA256 checksums
3. Detects pre-release (tag contains `-`)
4. Creates draft release with auto-generated notes

---

## Local Build

Build an executable locally for testing:

```bash
make build
# Output: dist/tsg-builder-linux (or -macos, -windows.exe)
```

Or directly:

```bash
python build_exe.py --clean
```

### Build Output

| Platform | Size (approx) |
|----------|---------------|
| Linux | ~35 MB |
| macOS | ~35 MB |
| Windows | ~40 MB |

---

## Troubleshooting

### Build fails on Windows with Unicode error

Fixed in build_exe.py — all output uses ASCII-safe `[OK]`, `[FAILED]`, etc.

### Workflow canceled after one platform fails

GitHub Actions cancels remaining jobs when one fails. Fix the failing platform first.

### Draft release missing files

Check that all 3 build jobs succeeded. If one failed, fix and re-tag:

```bash
git tag -d v1.0.0           # Delete local tag
git push origin :v1.0.0     # Delete remote tag
# Fix the issue, commit, push
git tag v1.0.0
git push origin v1.0.0
```

### Manual workflow run

For testing without creating a tag:

1. Go to **Actions** → **Build Executables**
2. Click **Run workflow**
3. Optionally check "Create a draft release"

---

## Files

| File | Purpose |
|------|---------|
| `.github/workflows/build.yml` | GitHub Actions workflow |
| `build_exe.py` | PyInstaller build script |
| `requirements.txt` | Python dependencies (includes PyInstaller) |
