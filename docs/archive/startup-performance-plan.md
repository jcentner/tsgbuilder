# Startup Performance Improvement Plan

> **Status**: Implemented  
> **Created**: 2026-02-13  
> **Problem**: On Windows, the compiled executable takes ~60 seconds from double-click to a usable web server. Most of that time shows nothing at all, then Powershell opens and things move quickly. 

---

## Root Cause Analysis

Four factors contribute to the slow startup, listed by impact:

| # | Cause | Est. Time | Details |
|---|-------|-----------|---------|
| 1 | `--onefile` extraction | ~30–45s | PyInstaller decompresses the entire 25 MB bundle into `%TEMP%` on every launch. Windows Defender scans each extracted file, compounding the delay. |
| 2 | Eager Azure SDK imports | ~10–15s | `web_app.py` imports `azure.identity`, `azure.ai.projects`, `azure.ai.textanalytics`, and `azure.core` at the top level, triggering hundreds of submodule loads before `main()` runs. |
| 3 | No early user feedback | — | Nothing prints until all imports complete and Flask starts. The user sees a blank console for the entire duration. |
| 4 | Synchronous telemetry init | ~2–3s | `telemetry.init_telemetry()` imports OpenTelemetry + Azure Monitor exporter synchronously before starting the server. |

---

## Fixes (A–D)

### Fix A: Switch `--onefile` → `--onedir` with `--contents-directory`

**Impact**: ~40s saved (eliminates per-launch extraction)  
**Effort**: Low  
**Risk**: Low — changes distribution shape from single file to folder  

#### What changes

**`build_exe.py` (line 88)**

Replace `"--onefile"` with `"--onedir"` and add `"--contents-directory", "_internal"`:

```python
"--onedir",                           # Folder-based (no per-launch extraction)
"--contents-directory", "_internal",  # Hide bundled files in _internal/
```

With `--onedir`, PyInstaller writes a **folder** (`dist/tsg-builder-{platform}/`) containing the executable alongside pre-extracted dependencies. There is no extraction step at launch — the OS loads DLLs/`.so` files in-place.

`--contents-directory _internal` (PyInstaller 6.0+, already in `requirements.txt`) moves all bundled dependencies into a `_internal/` subdirectory. This keeps the top-level distribution folder clean — users see only the executable (plus `.env` and `.agent_ids.json` after first run), not hundreds of `.dll`/`.so` files. This eliminates the UX regression that a naive `--onedir` switch would introduce.

Resulting folder structure:
```
tsg-builder-windows/
├── tsg-builder-windows.exe    ← user double-clicks this
├── _internal/                 ← bundled deps (hidden clutter)
│   ├── azure/
│   ├── flask/
│   ├── ...
│   └── base_library.zip
├── .env                       ← created on first run
└── .agent_ids.json            ← created during setup
```

**`build_exe.py` (lines 119–131)** — Update output path detection:

```python
# --onefile (current):
exe_path = Path("dist") / f"{exe_name}.exe"          # Windows
exe_path = Path("dist") / exe_name                    # Linux/macOS

# --onedir (new):
exe_path = Path("dist") / exe_name / (f"{exe_name}.exe" if platform_name == "windows" else exe_name)
```

Update the "To run" instructions to reference the exe inside the folder.

**`.github/workflows/build.yml`**

1. Add a `folder_name` matrix variable (without `.exe` suffix):
   ```yaml
   matrix:
     include:
       - os: ubuntu-latest
         platform: linux
         folder_name: tsg-builder-linux
       - os: macos-latest
         platform: macos
         folder_name: tsg-builder-macos
       - os: windows-latest
         platform: windows
         folder_name: tsg-builder-windows
   ```

2. **Upload artifact** step: change path from `dist/${{ matrix.exe_name }}` to `dist/${{ matrix.folder_name }}/` (upload entire folder).

3. **Release packaging** step: zip each platform **folder** instead of individual files:
   ```bash
   cd artifacts/tsg-builder-${{ matrix.platform }}
   zip -r ../../release/tsg-builder-${{ matrix.platform }}.zip .
   ```

4. **Release body**: update instructions from "Run the executable" to "Extract the zip and run the executable inside the folder."

**`web_app.py` (lines 146–155)** — Flask path resolution:

No code change strictly required. With `--contents-directory _internal`, `sys._MEIPASS` points to the `_internal/` subdirectory where templates and static files are bundled. The current `Path(sys._MEIPASS)` logic works correctly because it already resolves to wherever PyInstaller extracted/placed the bundled data files. Update the comment to clarify this.

#### Why this is safe

- `sys.executable` still points to the exe file in the top-level folder. `_get_app_dir()` (line 122) uses `Path(sys.executable).parent`, which resolves to the distribution folder — `.env` and `.agent_ids.json` are created there alongside the exe (not inside `_internal/`).
- `sys._MEIPASS` points to `_internal/` in `--onedir` + `--contents-directory` mode, which is where PyInstaller places bundled data files. The Flask template/static path resolution (`Path(sys._MEIPASS) / 'templates'`) works unchanged.
- Users already download a `.zip` — the only difference is extracting a folder. The top-level folder is clean (just the exe), so the experience is nearly identical to the current single-file approach.
- `--contents-directory` is supported in PyInstaller 6.0+ (`requirements.txt` already specifies `pyinstaller>=6.0.0`).

---

### Fix B: Immediate startup banner

**Impact**: Perceived latency eliminated  
**Effort**: Trivial  
**Risk**: None  

#### What changes

**`web_app.py`** — Insert between the docstring/`from __future__` line and the first library import:

```python
import sys

# --- Immediate startup feedback for compiled executable ---
# This MUST stay before all other imports. Users see a blank console for
# 30-60s while PyInstaller extracts files and Python loads Azure SDK
# modules. This print fires within ~1s of extraction completing.
if getattr(sys, 'frozen', False):
    print("TSG Builder is starting...", flush=True)
```

`flush=True` is critical — Python buffers stdout by default, and without it the message may not appear until much later.

After the block of Azure/pipeline imports (around line 57, after `import telemetry`), add a second progress message:

```python
if getattr(sys, 'frozen', False):
    print("Starting web server...", flush=True)
```

This gives users a three-phase indication:
1. `TSG Builder is starting...` (extraction done, imports beginning)
2. `Starting web server...` (imports done, Flask spinning up)
3. `🚀 TSG Builder UI starting at http://localhost:5000` (server ready)

#### Why this is safe

- Gated on `sys.frozen` — no output change when running from source or in tests.
- `sys` is a builtin; importing it has zero cost.
- No behavioral change whatsoever.

---

### Fix C: Defer heavy imports

**Impact**: ~10–15s saved on startup  
**Effort**: Medium  
**Risk**: Low-medium (import errors surface at runtime instead of startup)  

#### Strategy

Move **expensive** Azure SDK imports out of module-level scope so they load on first use (Setup, Validate, or Generate) rather than at startup.

**Keep at top level** (lightweight):
- `azure.core.exceptions` — just exception class definitions, fast to import, and needed in `except` clauses throughout the code
- `tsg_constants`, `version`, `error_utils` — pure Python, no SDK dependencies after this refactor
- `flask`, `dotenv`, and stdlib modules

**Defer** (heavy):
- `azure.identity` — triggers MSAL, credential chain discovery
- `azure.ai.projects` — large SDK with many submodules
- `azure.ai.textanalytics` — pulls in full Language SDK

#### File-by-file changes

**`pipeline.py` (lines 23–24)**

Move the two Azure imports inside `_get_project_client()` (line 1195):

```python
# Before (top-level):
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

# After (inside method):
def _get_project_client(self) -> "AIProjectClient":
    from azure.identity import DefaultAzureCredential
    from azure.ai.projects import AIProjectClient
    return AIProjectClient(
        endpoint=self.endpoint,
        credential=DefaultAzureCredential()
    )
```

Python caches imports in `sys.modules` after the first call, so subsequent invocations of `_get_project_client()` pay no cost.

This also breaks the import chain: `web_app.py` → `pipeline.py` → `azure.identity` + `azure.ai.projects`. After the change, importing `pipeline` no longer triggers Azure SDK loading.

**`pii_check.py` (lines 15–21)**

Move **all** `azure.ai.textanalytics` imports (including `PiiEntityCategory`) and `DefaultAzureCredential` inside the functions that use them:

```python
# REMOVE all top-level azure.ai.textanalytics imports.
# `from azure.ai.textanalytics import PiiEntityCategory` looks lightweight
# but actually triggers loading the entire azure.ai.textanalytics package,
# negating the deferred-import benefit for TextAnalyticsClient.

# Convert PII_CATEGORIES to use raw strings instead of the enum:
PII_CATEGORIES: list[str] = [
    "Email",
    "PhoneNumber",
    "IPAddress",
    "Person",
    "AzureDocumentDBAuthKey",
    "AzureStorageAccountKey",
    "AzureSAS",
    "AzureIoTConnectionString",
    "SQLServerConnectionString",
    "CreditCardNumber",
    "USSocialSecurityNumber",
]

# Move into get_language_client():
def get_language_client(endpoint: str) -> "TextAnalyticsClient":
    from azure.ai.textanalytics import TextAnalyticsClient
    from azure.identity import DefaultAzureCredential
    global _client, _client_endpoint
    if _client is None or _client_endpoint != endpoint:
        _client = TextAnalyticsClient(
            endpoint=endpoint,
            credential=DefaultAzureCredential(),
        )
        _client_endpoint = endpoint
    return _client
```

The `recognize_pii_entities()` API accepts category names as strings, so the `PiiEntityCategory` enum is not required at call sites. This avoids loading the entire `azure.ai.textanalytics` package at import time.

Keep the `azure.core.exceptions` imports at top level (used in `except` clauses in `check_for_pii()`).

**`web_app.py` (lines 23–35)**

Remove the heavy imports. Use **direct local imports** in each function that needs them — no helper or cache dict required. Python's `sys.modules` cache makes repeated `from azure.identity import ...` calls a zero-cost dict lookup after the first invocation.

```python
# REMOVE these top-level imports:
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    PromptAgentDefinition,
    MCPTool,
    WebSearchPreviewTool,
)

# KEEP this top-level import (lightweight, needed in except clauses):
from azure.core.exceptions import (
    HttpResponseError,
    ClientAuthenticationError,
    ServiceRequestError,
    ResourceNotFoundError,
)
```

**Functions in `web_app.py` that need updating:**

Add local imports at the top of each function body:

| Function | Line | Local imports needed |
|----------|------|---------------------|
| `get_project_client()` | 237–242 | `from azure.identity import DefaultAzureCredential` | 
||| `from azure.ai.projects import AIProjectClient` |
| `validate_endpoint()` route | ~448 | `from azure.identity import DefaultAzureCredential` |
| `validate_model()` route | ~470 | `from azure.identity import DefaultAzureCredential` |
||| `from azure.ai.projects import AIProjectClient` |
| `list_agents()` route | ~501 | `from azure.identity import DefaultAzureCredential` |
||| `from azure.ai.projects import AIProjectClient` |
| `delete_agents()` route | ~524 | `from azure.identity import DefaultAzureCredential` |
||| `from azure.ai.projects import AIProjectClient` |
| `create_agents()` route | ~640 | `from azure.identity import DefaultAzureCredential` |
||| `from azure.ai.projects import AIProjectClient` |
||| `from azure.ai.projects.models import PromptAgentDefinition, MCPTool, WebSearchPreviewTool` |

Example:
```python
def get_project_client() -> "AIProjectClient":
    """Create and return an AIProjectClient."""
    from azure.identity import DefaultAzureCredential
    from azure.ai.projects import AIProjectClient
    endpoint = os.getenv("PROJECT_ENDPOINT")
    if not endpoint:
        raise ValueError("PROJECT_ENDPOINT environment variable is required")
    return AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
```

This is simpler and more readable than a `_azure()` cache dict — call sites remain identical to the current code (just `AIProjectClient(...)`, not `_azure()['AIProjectClient'](...)`). The only visual change is two `from` lines at the top of each function.

The `except` clauses for `ClientAuthenticationError`, etc. remain unchanged — those classes are still imported at top level from `azure.core.exceptions`.

`_get_user_friendly_error()` (line 160) uses `isinstance()` checks against these same exception classes — no change needed since they come from `azure.core.exceptions`.

#### Import chain after all changes

```
web_app.py (at startup):
  ├── flask, dotenv, os, sys, json, etc.  ← fast (stdlib/near-stdlib)
  ├── azure.core.exceptions               ← fast (just exception classes)
  ├── tsg_constants                        ← fast (strings, functions)
  ├── pipeline                             ← fast (Azure SDK deferred in C2)
  ├── error_utils                          ← fast (only azure.core.exceptions + pipeline constants)
  ├── pii_check                            ← fast (TextAnalyticsClient deferred in C3)
  ├── version                              ← fast (just strings)
  └── telemetry                            ← fast (OpenTelemetry deferred to init_telemetry)

Azure SDK loaded on-demand:
  ├── azure.identity          → first Setup, Validate, or Generate action
  ├── azure.ai.projects       → first Setup or Generate action
  └── azure.ai.textanalytics  → first Generate action (PII check, fully deferred)
```

#### Why this is safe

- Python's `sys.modules` cache means deferred imports execute their module-level code only once — subsequent `from azure.identity import ...` calls are a no-op dict lookup.
- `from __future__ import annotations` is already present in all files, so type hints in function signatures are strings and don't trigger imports.
- First-use latency (~10s) is hidden behind the pipeline's own multi-second API call latency.
- **Risk**: An import error (e.g., missing package) would surface at first use instead of at startup. Mitigated by the test suite, which exercises all code paths.

---

### Fix D: Background telemetry initialization

**Impact**: ~2–3s saved  
**Effort**: Low  
**Risk**: None  

#### What changes

**`web_app.py` (lines 1165–1188 in `main()`):**

Currently telemetry init and the `app_started` event are synchronous:

```python
def main():
    telemetry.init_telemetry()                    # blocks ~2-3s
    if telemetry.is_active():
        print("📊 Telemetry: enabled")
    elif telemetry.is_telemetry_enabled():
        print("📊 Telemetry: disabled (no connection string)")
    else:
        print("📊 Telemetry: disabled (opted out)")

    import platform as _platform
    telemetry.track_event("app_started", properties={...})
```

Refactor to:

```python
def main():
    # Print telemetry status synchronously (instant — just reads env var)
    if not telemetry.is_telemetry_enabled():
        print("📊 Telemetry: disabled (opted out)")
    else:
        print("📊 Telemetry: initializing...")

        # Init + first event in background — non-blocking
        def _init_telemetry_background():
            telemetry.init_telemetry()

            # Report final status to match the 3 outcomes from
            # the previous synchronous flow
            if telemetry.is_active():
                print("📊 Telemetry: enabled", flush=True)
            else:
                print("📊 Telemetry: disabled (no connection string)", flush=True)

            import platform as _platform
            telemetry.track_event(
                "app_started",
                properties={
                    "version": APP_VERSION,
                    "platform": _get_platform(),
                    "python_version": _platform.python_version(),
                    "run_mode": _get_run_mode(),
                },
            )

        threading.Thread(
            target=_init_telemetry_background, daemon=True
        ).start()
```

This preserves the existing three distinct console messages:
1. `📊 Telemetry: disabled (opted out)` — synchronous, instant
2. `📊 Telemetry: enabled` — from background thread after init completes
3. `📊 Telemetry: disabled (no connection string)` — from background thread after init completes

The "initializing..." message appears immediately so users know telemetry setup is happening; the final status appears ~2–3s later (interleaved with other startup output, which is fine).

#### Why this is safe

- `track_event()` already guards with `if _logger is None: return` — any events emitted before `init_telemetry()` completes are silently dropped (by design for fire-and-forget telemetry).
- The `_initialized` flag in `telemetry.py` prevents double-init.
- `_install_id_lock` handles concurrent access to the install ID.
- The thread is a `daemon` thread — it won't prevent the process from exiting if the user hits Ctrl+C during init.
- The background `print()` calls use `flush=True` to ensure output appears promptly even with buffered stdout.
- Worst case: `app_started` event is emitted ~2–3s after server starts instead of before. Completely acceptable.

---

## Execution Order

| Step | Fix | Files Changed | Risk | Independently Testable |
|------|-----|---------------|------|------------------------|
| 1 | **B** — Startup banner | `web_app.py` | None | Yes — run exe, see banner |
| 2 | **D** — Background telemetry | `web_app.py` | None | Yes — run exe, verify events in App Insights |
| 3 | **C** — Deferred imports | `web_app.py`, `pipeline.py`, `pii_check.py` | Low-medium | Yes — `make test` + exe smoke test |
| 4 | **A** — `--onedir` + `--contents-directory` | `build_exe.py`, `.github/workflows/build.yml`, `web_app.py` (comment only) | Low | Yes — build exe, verify <5s startup, verify CI |

Fixes B and D are safe and fast — implement first. Fix C requires care and should be followed by the full test suite. Fix A changes distribution format and should be done last, with release notes.

## Measurement

Before and after each fix, measure actual import and startup times to validate the estimated savings:

```bash
# Measure import chain cost (Python 3.7+):
python -X importtime web_app.py 2> import_times.log
# Sort by cumulative time:
sort -t'|' -k2 -n import_times.log | tail -20

# Measure end-to-end startup (source mode):
time python -c "import web_app"

# Measure end-to-end startup (exe mode, Linux/macOS):
time ./dist/tsg-builder-linux/tsg-builder-linux &; sleep 5; kill %1
```

Capture baseline numbers before starting and after each fix to confirm savings match estimates.

## Testing Checklist

- [ ] **B**: Build exe → double-click → confirm `TSG Builder is starting...` appears within 1–2s of console window opening
- [ ] **D**: Build exe → run → generate a TSG → check App Insights for `app_started` event with correct properties
- [ ] **C**: Run `make test` (full suite) → build exe → complete Setup + Generate workflow → verify no import errors at any step
- [ ] **A**: Build exe → confirm `dist/tsg-builder-{platform}/` folder exists with exe at top level and `_internal/` subdirectory → double-click exe → confirm startup in <5s → push tag → verify CI workflow produces correct zip artifacts

## Expected Results

| Scenario | Before | After (all fixes) |
|----------|--------|-------------------|
| Double-click exe → first output | ~45–60s (blank window) | ~1s (`TSG Builder is starting...`) |
| Double-click exe → browser opens | ~60s | ~3–5s |
| Running from source (`python web_app.py`) | ~12–15s | ~2–3s |
