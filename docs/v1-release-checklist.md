# TSG Builder v1 Release Checklist

Code review checklist for the v1 release merge.

## Code Quality & Cleanliness

- [x] Remove debug print statements from `web_app.py` (lines 836-840)
- [x] Remove or protect `/api/debug/threads` endpoint
- [x] No hardcoded secrets (uses `DefaultAzureCredential`)
- [x] Review console.log statements in `templates/index.html` — only 2 statements, both for legitimate debugging (status retry, cancel). Acceptable for local tool.

## Security

- [x] localhost-only binding (`app.run(host="127.0.0.1")`)
- [x] README security warning (documents "local use only")
- [x] Customer data guidance in README
- [x] Review input sanitization for notes/images — validates structure (list, has 'data' field). Content not sanitized but acceptable for local-only tool where user controls input.
- [x] Review CSRF protection for POST endpoints — not implemented, acceptable for local-only tool that doesn't handle sensitive state.

## Error Handling

- [x] All unit tests passing (30/30)
- [x] Structured error classification with `ErrorClassification` dataclass
- [x] User-friendly error messages with `HINT_*` constants
- [x] Error logging to `logs/errors.log`
- [x] Fix duplicate return statement in `web_app.py` (lines 200-201)

## Test Coverage

- [x] Error handling tests (`test_error_handling.py`)
- [x] TSG validation tests (`test_tsg_validation.py`)
- [x] Web endpoint tests (`test_web_endpoints.py`)
- [ ] Integration tests for full pipeline flow (future)

## Documentation

- [x] README comprehensive (installation, usage, troubleshooting)
- [x] Architecture documented (`docs/architecture.md`)
- [x] Copilot instructions (`.github/copilot-instructions.md`)
- [ ] API endpoint documentation (future)
- [ ] CHANGELOG.md for release notes (future)

## Dependencies & Versions

- [x] Verify `azure-ai-projects>=2.0.0b3` beta stability
- [x] Version pinning uses `>=` (flexibility over reproducibility, acceptable)
- [x] Python 3.12 compatibility verified

## Production Readiness

- [x] Flask dev server acceptable for local-only tool
- [x] Test output location — outputs to `logs/` directory (correct)
- [ ] Test executable on different platforms
- [ ] GitHub Actions build/release workflow verification

## Code Architecture

- [x] Pipeline stages well-separated
- [x] Constants centralized in `tsg_constants.py`
- [ ] Refactor JS/CSS out of `index.html` (future)
- [ ] Consider splitting large files (future refactor)

## Known TODOs (from project files)

From `todo.md`:
- [ ] Major cleanup before merge
- [ ] Test executable on different platforms
- [ ] Test build through GitHub Actions, tag, and releases
- [ ] Evaluate stop server/close button in UI
- [ ] Review Notes auto-apply improvements

---

## Priority Actions Completed

1. ✅ Removed debug print statements from `web_app.py`
2. ✅ Fixed duplicate return statement in `web_app.py`
3. ✅ Added tests for `validate_tsg_output()` and Flask endpoints (69 tests total)
4. ✅ Protected `/api/debug/threads` endpoint (only available in debug mode)
5. ✅ Reviewed console.log, input sanitization, CSRF — acceptable for local tool
6. ✅ Updated `.github/copilot-instructions.md` known gaps
