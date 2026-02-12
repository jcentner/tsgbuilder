# Telemetry Implementation Plan

**Issue:** [issue-usage-telemetry.md](../issues/issue-usage-telemetry.md)  
**Status:** Phase 1a + 1b + 2 + 3 complete (code changes merged; Azure resource + release tag are manual)  
**PR scope:** All phases ship in a single PR, implemented phase-by-phase.

---

## Phase 1a — Telemetry Module Foundation

Create the core `telemetry.py` module and supporting infrastructure. No existing files modified beyond `.gitignore` and `requirements.txt`.

- [x] Create `telemetry.py` with:
  - `init_telemetry()` — initialize `azure-monitor-opentelemetry-exporter`, check opt-out
  - `track_event(name, properties, measurements)` — fire-and-forget event emission, all calls wrapped in silent `try/except`
  - `is_telemetry_enabled()` — check `TSG_TELEMETRY` env var (`0`/`false` = disabled)
  - `_get_connection_string()` — cascade: `_build_config` → `APPINSIGHTS_CONNECTION_STRING` env var → `None` (disabled)
  - `_get_or_create_install_id()` — generate `uuid4`, persist to `.env` via `set_key()`, skip when telemetry opted out
- [x] Add `_build_config.py` to `.gitignore`
- [x] Add `azure-monitor-opentelemetry-exporter` to `requirements.txt`
- [x] Write unit tests (34 tests in `tests/test_telemetry.py`):
  - `track_event` calls exporter with correct args (mocked)
  - Opt-out via `TSG_TELEMETRY=0` suppresses all emission
  - `install_id` generated on first call, reused on subsequent calls
  - Silent failure when exporter raises (no crash, no log spam)
  - No `install_id` generated or persisted when opted out
  - Connection string cascade works (`_build_config` → env var → disabled)

## Phase 1b — Pipeline Plumbing

Enrich `PipelineResult` with duration and token fields. Capture them during pipeline execution. No telemetry emission yet — just making the data available.

- [x] Add fields to `PipelineResult` in `pipeline.py`:
  - `duration_seconds` (total wall-clock)
  - `research_duration_s`, `write_duration_s`, `review_duration_s`
  - `research_input_tokens`, `research_output_tokens`
  - `write_input_tokens`, `write_output_tokens`
  - `review_input_tokens`, `review_output_tokens`
  - `total_tokens`
  - `image_count`, `notes_line_count`
- [x] Extract token usage from `response.completed` events in `process_pipeline_v2_stream()`:
  - Read `event.response.usage` (null-check required)
  - **Accumulate** across multiple `response.completed` events per stage (multi-turn agent interactions)
  - Store in `timing_context` dict
- [x] Capture per-stage wall-clock durations in `_run_stage()` / `run()`:
  - Record `time.time()` before/after each stage call
  - `_run_stage()` returns 3-tuple `(text, conversation_id, timing_context)` to propagate token data
  - Propagate to `PipelineResult`; fix-round tokens accumulated into write/review totals
- [x] Surface `image_count` and `notes_line_count` (available from notes input) in `PipelineResult`
- [x] Write unit tests (16 tests in `tests/test_pipeline_telemetry.py`):
  - `PipelineResult` includes new fields with sensible defaults
  - Token accumulation sums across multiple `response.completed` events
  - Null/missing usage handled gracefully
  - Input metadata (notes lines, images) correctly derived

## Phase 2 — Instrumentation

Emit telemetry events from application code using the module from Phase 1a and the enriched data from Phase 1b.

### Server-side events

- [x] `app_started` — in `web_app.py` `main()`:
  - Properties: `version`, `platform` (linux/macos/windows/wsl2), `python_version`, `run_mode` (source/executable), `install_id`
  - Call `init_telemetry()` here
  - Log opt-out status: "📊 Telemetry: enabled" / "📊 Telemetry: disabled"
- [x] `tsg_generated` — in `web_app.py` `generate_pipeline_sse_events()` success path:
  - Properties: `version`, `had_missing`, `missing_sections` (csv), `follow_up_round` (0 for initial), `model`, `install_id`
  - Measurements: `duration_seconds`, `research_duration_s`, `write_duration_s`, `review_duration_s`, `missing_count`, `notes_line_count`, `image_count`, per-stage token counts, `total_tokens`
- [x] `pipeline_error` — in `web_app.py` `generate_pipeline_sse_events()` error path:
  - Properties: `version`, `stage`, `error_class` (from `classify_error()`), `install_id`
  - Measurements: `retry_count`
- [x] `pii_blocked` — in `web_app.py` PII gates (`api_generate_stream()` and `api_answer_stream()`):
  - Properties: `version`, `action` (edit/redact), `input_type` (notes/followup), `install_id`
  - Measurements: `entity_count`
- [x] `setup_completed` — in `web_app.py` `api_create_agents()` success path:
  - Properties: `version`, `model_deployment`, `install_id`
- [x] `tsg_generated` with `follow_up_round > 0` — in `web_app.py` `api_answer_stream()`

### Client-side event

- [x] Add `POST /api/telemetry/copied` endpoint in `web_app.py` (lightweight, returns 204)
- [x] `tsg_copied` — fire-and-forget `fetch()` in `copyTSG()` in `static/js/main.js`:
  - Properties: `version`, `follow_up_round`, `install_id`

### Tests

- [x] Integration-style tests verifying each instrumentation point calls `track_event` with expected event name and property keys (mocked exporter)
- [x] Verify `pii_blocked` emitted on PII gate trigger
- [x] Verify `pipeline_error` emitted with correct `error_class` mapping
- [x] Verify `tsg_copied` endpoint returns 204 and emits event

## Phase 3 — Build & Release Integration

Wire up the connection string injection for release binaries and add user-facing documentation.

- [x] Update `build_exe.py`:
  - Generate `_build_config.py` from `APPINSIGHTS_CONNECTION_STRING` env var before PyInstaller runs
  - Add `_build_config` as a hidden import so it's bundled in the binary
- [x] Update `.github/workflows/build.yml`:
  - Pass `APPINSIGHTS_CONNECTION_STRING: ${{ secrets.APPINSIGHTS_CONNECTION_STRING }}` env var to the build step
- [ ] Create Application Insights resource in Azure, store connection string as GitHub Actions repo secret
- [x] Add telemetry disclosure and opt-out instructions to `README.md`:
  - What is collected (counts, enums, durations, version — never content or PII)
  - How to opt out (`TSG_TELEMETRY=0` in `.env`)
  - `install_id` explanation
- [ ] Tag a release and verify events appear in App Insights Live Metrics

---

## Notes

- **Sampling rate**: Configure 100% sampling on the App Insights resource initially (low expected volume). Drop to 50% if adoption grows significantly. This is an Azure Portal resource setting, not a code change.
- **Dependency**: Using `azure-monitor-opentelemetry-exporter` for automatic batching, retry, and standard App Insights integration. Acceptable size increase for the benefits.
- **All phases in one PR**: Phases are implementation order, not separate PRs. Each phase builds on the last and is tested before moving on.
