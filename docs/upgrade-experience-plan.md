# Implementation Plan: Upgrade Experience (v1.0.7)

Tracking issue: [`issues/issue-upgrade-experience.md`](../issues/issue-upgrade-experience.md)

This document breaks the four deliverables into concrete, ordered implementation checklists vetted against the existing codebase. Each checkbox is a discrete commit-sized unit of work.

---

## Deliverable 1: Version Check + About Pane Upgrade Banner

### 1A. Backend — version check background thread (`web_app.py`)

Current state: `main()` already spawns a background thread for telemetry init. `/api/about` returns `version`, `github_url`, and agent info.

- [ ] Add `import urllib.request` and `import re` (both stdlib — no new dependency)
- [ ] Add module-level cache variables:
  - `_latest_version: str | None = None`
  - `_update_url: str | None = None`
  - `_update_check_done: bool = False`
- [ ] Add `_check_for_updates()` function:
  - Read `TSG_UPDATE_CHECK` from env; return immediately if `"0"` / `"false"` / `"no"`
  - `GET https://api.github.com/repos/jcentner/tsgbuilder/releases/latest` with `Accept: application/vnd.github+json` header and a 5-second timeout
  - Parse JSON → `tag_name` (strip leading `v`) → store in `_latest_version`
  - Store `html_url` in `_update_url`
  - Entire function wrapped in bare `except Exception: pass` (fail-silent)
- [ ] Add `_is_newer(latest: str, current: str) -> bool` semver comparison helper:
  - Split on `.`, compare integer tuples — handle pre-release suffixes by treating them as older than the same version without suffix
  - Return `True` only when `latest` is strictly newer
- [ ] In `main()`, spawn `_check_for_updates` in a daemon thread (alongside or after the telemetry thread):
  ```python
  threading.Thread(target=_check_for_updates, daemon=True).start()
  ```
- [ ] In `api_about()`, add three new fields to the response dict:
  - `"latest_version": _latest_version` (string or `None`)
  - `"update_url": _update_url` (string or `None`)
  - `"update_check_enabled": os.getenv("TSG_UPDATE_CHECK", "1").strip().lower() not in ("0", "false", "no")`

**Vetting notes:**
- `api_about()` is at line ~390 of `web_app.py`; it returns a flat `jsonify({...})` dict — easy to extend.
- `main()` already uses `threading.Thread(..., daemon=True).start()` for telemetry — same pattern.
- No external HTTP library is used today; `urllib.request` avoids adding a dependency. `requests` is not in `requirements.txt`.

### 1B. Telemetry — `update_available` event (`web_app.py`, `docs/telemetry.md`)

- [ ] At the end of `_check_for_updates()`, after caching values, if `_is_newer(latest, APP_VERSION)`:
  - Call `telemetry.track_event("update_available", properties={"current_version": APP_VERSION, "latest_version": _latest_version})`
  - This fires at most once per app launch (function runs once)
- [ ] Add `update_available` event to `docs/telemetry.md`:
  - Document fields: `current_version`, `latest_version`
  - Trigger: background version check in `main()` detects newer release
  - Add to the "Events" section between `app_started` and `setup_completed`
- [ ] Add entry to "File Reference" table if not already covering `web_app.py` (it does — no change needed)

### 1C. Frontend — upgrade banner in About modal (`main.js`)

Current state: `loadAboutInfo()` (line ~1117) fetches `/api/about` and builds the About modal HTML. Version is shown as `Version ${data.version}` in a centered header.

- [ ] In `loadAboutInfo()`, after building the version header div, add a conditional block:
  - If `data.latest_version && data.latest_version !== data.version` and `_isNewer(data.latest_version, data.version)`:
    - Render upgrade banner div at top of content (green/info-colored box):
      ```
      📦 Version X.Y.Z is available (you have A.B.C)
      
      To upgrade: download the new release and extract into this same folder,
      overwriting the executable and _internal/ directory. Your .env configuration
      and agent setup will be preserved automatically.
      
      [Download Latest →]  (link to data.update_url or data.github_url + "/releases")
      ```
  - If `data.latest_version && data.latest_version === data.version`:
    - Show `✓ Up to date` next to the version text
  - If `!data.latest_version` (check failed / disabled):
    - Show nothing extra (no error state)
- [ ] Add `_isNewer(a, b)` JS helper function (mirrors backend logic):
  - Split on `.`, compare integer parts left-to-right
  - Returns `true` if `a` > `b`

**Vetting notes:**
- The About modal HTML lives in `templates/index.html` (line ~271) and is populated entirely by JS — no template changes needed.
- CSS for banners can reuse existing `.warning-banner` styles or inline styles (the About modal already uses inline styles extensively).

### 1D. Opt-out mechanism

- [ ] In `DEFAULT_ENV_CONTENT` (line ~100 of `web_app.py`), add a commented-out entry:
  ```
  # Set to 0 to disable update checks
  # TSG_UPDATE_CHECK=0
  ```
- [ ] Document `TSG_UPDATE_CHECK=0` in the GETTING_STARTED.md telemetry section (it's adjacent to `TSG_TELEMETRY=0`)

### 1E. Tests

- [ ] Unit test `_is_newer()` with cases: equal versions, newer patch, newer minor, newer major, pre-release vs stable, malformed input
- [ ] Unit test `_check_for_updates()` with mocked `urllib.request.urlopen`:
  - Success case: sets `_latest_version` and `_update_url`
  - Network failure: silently fails, variables remain `None`
  - Disabled via env (`TSG_UPDATE_CHECK=0`): returns early
- [ ] Unit test `api_about()` includes `latest_version`, `update_url`, `update_check_enabled` fields
- [ ] Unit test or integration test: `update_available` telemetry event fired when newer version detected

---

## Deliverable 2: Agent Staleness Detection

### 2A. Persist app version in agent IDs (`web_app.py`)

Current state: `save_agent_ids()` (line ~271) writes `{"researcher": {...}, "writer": {...}, "reviewer": {...}, "name_prefix": "..."}` to `.agent_ids.json`.

- [ ] In `save_agent_ids()`, add `"app_version": APP_VERSION` to the `data` dict:
  ```python
  data = {
      "researcher": researcher,
      "writer": writer,
      "reviewer": reviewer,
      "name_prefix": name_prefix,
      "app_version": APP_VERSION,
  }
  ```

### 2B. Staleness detection in `/api/validate` (`web_app.py`)

Current state: `/api/validate` (line ~412) runs 6 checks. Check #6 is "Pipeline Agents" — reads `.agent_ids.json` and reports pass/fail.

- [ ] In the Pipeline Agents check block (check #6), after loading `agent_ids`:
  - Read `agent_ids.get("app_version")` — may be `None` for pre-upgrade files
  - Compare to `APP_VERSION`:
    - Match → no change (existing pass/fail logic)
    - Mismatch or missing → add `"agents_stale": True` and `"agents_created_version": stored_version or "unknown"` to the check dict
    - Update the message to include: `"3 agents configured ({prefix}) — created with v{stored_version}, current is v{APP_VERSION}"`
  - The check still **passes** (staleness is a warning, not a blocker)
- [ ] Add `agents_stale` and `agents_created_version` to the top-level `/api/validate` response for easy frontend access:
  ```python
  "agents_stale": agents_stale,
  "agents_created_version": agents_created_version,
  ```

### 2C. Staleness detection in `/api/status` (`web_app.py`)

Current state: `/api/status` (line ~315) loads agent IDs and reports `configured: true/false`.

- [ ] After loading agent IDs, check `data.get("app_version")` vs `APP_VERSION`
- [ ] Add `"agents_stale": True/False` to the `result["agents"]` dict
- [ ] Add `"agents_created_version": stored_version` to the response

### 2D. Frontend — staleness warning in setup wizard (`setup.js`)

Current state: `updateSetupOverallStatus()` (line ~228) fetches `/api/status` and updates the agent status display. `runValidation()` (line ~113) renders validation check results.

- [ ] In `updateSetupOverallStatus()`, after the agents-configured block:
  - If `data.agents.agents_stale === true`:
    - Show warning text below the agent info div:
      ```
      ⚠️ Agents were created with vX.Y.Z — recreate them to get the latest improvements.
      ```
    - Optionally highlight the "Recreate Agents" button (it already exists and is enabled)
- [ ] In `runValidation()`, the check rendering already handles a `warning` field — the backend just needs to set it. Verify the staleness check renders correctly with the existing `warning` CSS class.

### 2E. Tests

- [ ] Unit test `save_agent_ids()` includes `app_version` in written JSON
- [ ] Unit test `/api/validate`: agents created with older version → `agents_stale: true`
- [ ] Unit test `/api/validate`: agents created with current version → `agents_stale: false` (or absent)
- [ ] Unit test `/api/validate`: pre-existing `.agent_ids.json` without `app_version` → treated as stale
- [ ] Unit test `/api/status`: same staleness cases

---

## Deliverable 3: Inno Setup Installer for Windows

### 3A. Create installer script (`installer.iss`)

- [ ] Create `installer.iss` in repo root with Inno Setup directives:
  - `AppName=TSG Builder`
  - `AppVersion={#AppVersion}` (parameterized — CI passes version via `/D`)
  - `DefaultDirName={localappdata}\TSGBuilder` (per-user, no admin)
  - `PrivilegesRequired=lowest`
  - `OutputBaseFilename=tsg-builder-windows-setup`
  - `AppPublisher=`, `AppPublisherURL=https://github.com/jcentner/tsgbuilder`
  - `SetupIconFile=` (optional — skip if no icon available)
  - `UninstallDisplayName=TSG Builder`
- [ ] `[Files]` section:
  - `Source: "dist\tsg-builder-windows\tsg-builder-windows.exe"; DestDir: "{app}"; Flags: ignoreversion`
  - `Source: "dist\tsg-builder-windows\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs`
  - `Source: "dist\tsg-builder-windows\GETTING_STARTED.md"; DestDir: "{app}"; Flags: ignoreversion`
  - Explicitly do NOT include `.env` or `.agent_ids.json` (user config preserved by omission)
- [ ] `[Icons]` section:
  - `Name: "{userprograms}\TSG Builder"; Filename: "{app}\tsg-builder-windows.exe"`
- [ ] `[UninstallDelete]` section:
  - Clean up `_internal\` directory on uninstall
  - Do NOT delete `.env` (preserve user config)
- [ ] `[Code]` section (optional):
  - Consider a `InitializeSetup` function to close existing TSG Builder instances before upgrade

### 3B. CI — build installer (`build.yml`)

Current state: Windows build creates `dist/tsg-builder-windows/` folder, zips it.

- [ ] Add a step after the Windows `Build executable` step (inside the `build` job, conditional on `matrix.platform == 'windows'`):
  ```yaml
  - name: Build Windows installer
    if: matrix.platform == 'windows'
    run: |
      choco install innosetup -y --no-progress
      & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss /DAppVersion=${{ github.ref_name }}
    shell: pwsh
  ```
- [ ] Upload the installer as a separate artifact:
  ```yaml
  - name: Upload installer
    if: matrix.platform == 'windows'
    uses: actions/upload-artifact@v4
    with:
      name: tsg-builder-windows-installer
      path: Output/tsg-builder-windows-setup.exe
      if-no-files-found: error
  ```
  (Inno Setup default output dir is `Output/`)

### 3C. CI — attach installer to release (`build.yml`)

Current state: The `release` job downloads all artifacts and zips them.

- [ ] In the `release` job, download the installer artifact alongside the existing ones
- [ ] Copy the installer `.exe` into the `release/` directory
- [ ] Add to SHA256 checksums generation
- [ ] Add `release/tsg-builder-windows-setup.exe` to the `files:` list in the `Create draft release` step
- [ ] Update the release body template to include installer row:
  ```markdown
  | Windows (installer) | `tsg-builder-windows-setup.exe` |
  | Windows (zip) | `tsg-builder-windows.zip` |
  ```

### 3D. Tests

- [ ] Validate `installer.iss` syntax (this is a manual/CI step — Inno Setup's `ISCC` will fail on syntax errors)
- [ ] Manual test: build installer locally, run on Windows, verify install path, Start Menu shortcut, uninstall
- [ ] Verify `.env` and `.agent_ids.json` are preserved across installer upgrade

---

## Deliverable 4: Upgrade Documentation

### 4A. GETTING_STARTED.md — Upgrading section

Current state: Sections are: Prerequisites → Setting Up Azure AI Foundry → Quick Start → Finding Your Configuration Values → Usage Tips → Troubleshooting → Telemetry → More Information. No upgrade section exists.

- [ ] Add `## Upgrading` section between **Quick Start** (ends ~line 82) and **Finding Your Configuration Values** (starts ~line 99):
  ```markdown
  ## Upgrading

  ### Windows (installer)
  Run the new installer — it automatically replaces app files while
  preserving your configuration.

  ### All platforms (zip)
  1. Download the new release zip from [Releases](https://github.com/jcentner/tsgbuilder/releases)
  2. Extract into **the same folder** as your current installation, overwriting existing files
  3. Your `.env` configuration and settings are preserved automatically
  4. Open TSG Builder — if prompted, recreate agents to pick up the latest improvements
  ```

### 4B. docs/releasing.md — upgrade mention in release notes

Current state: The release body template in `build.yml` has "First Run" instructions but no upgrade guidance.

- [ ] In `docs/releasing.md`, add a note in the "Review and Publish" section (step 4, ~line 68):
  ```
  - Add upgrade instructions if agent prompts changed (users should recreate agents)
  ```
- [ ] Update the release body template in `build.yml` to add an "Upgrading" section after "First Run":
  ```markdown
  ### Upgrading
  - **Installer (Windows)**: Run `tsg-builder-windows-setup.exe` — your configuration is preserved
  - **Zip (all platforms)**: Extract into the same folder, overwriting existing files
  - If you see an "agents stale" warning, click **Recreate Agents** in Setup
  ```

### 4C. `TSG_UPDATE_CHECK` documentation

- [ ] Add `TSG_UPDATE_CHECK=0` to the Telemetry section of GETTING_STARTED.md alongside `TSG_TELEMETRY=0`
  (covered in 1D above — just confirming it lands in this deliverable's scope)

---

## Implementation Order

> Recommended sequence for PRs (or commit groups within a single PR):

| Order | Deliverable | Dependencies | Est. Complexity |
|-------|-------------|--------------|-----------------|
| 1 | **2: Agent staleness** | None | Small — 2 files modified |
| 2 | **1: Version check + banner** | None (independent) | Medium — backend thread + frontend |
| 3 | **4: Upgrade docs** | After 1 & 2 (docs should reflect reality) | Small — docs only |
| 4 | **3: Inno Setup installer** | After 4 (docs reference installer) | Medium — new file + CI changes |

Deliverables 1 and 2 can be developed in parallel. Deliverable 4 (docs) should be written after 1 & 2 are implemented so the documentation matches the actual behavior. Deliverable 3 is independent but benefits from having the docs finalized first.

---

## Risk Notes

- **GitHub API rate limit**: Unauthenticated requests are limited to 60/hour per IP. For a desktop app that checks once per launch, this is fine. The 5-second timeout and fail-silent behavior prevent any user impact.
- **Pre-existing `.agent_ids.json`**: Files from v1.0.6 and earlier won't have `app_version`. Treating missing as stale is the safe default — users get a one-time "recreate agents" prompt after upgrading.
- **Inno Setup on CI**: `choco install innosetup` is well-established in GitHub Actions Windows runners. The step adds ~30 seconds to the build.
- **No `requests` library**: Using `urllib.request` avoids adding a dependency. The GitHub API response is small JSON — no need for a full HTTP client.
