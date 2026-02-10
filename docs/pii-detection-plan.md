# PII Detection — Implementation Plan

Adds a pre-flight PII check to prevent customer-identifiable information from being sent to external Foundry Agents and Bing search. Uses the **Azure AI Language PII API** via a centralized, author-owned Language resource.

> **Issue**: [logs/issue-pii-detection.md](../logs/issue-pii-detection.md)

---

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Detection service | Azure AI Language PII API (`azure-ai-textanalytics>=5.3.0`) | Purpose-built for input scanning, native redaction, GA SDK, deterministic |
| Resource model | Centralized, author-owned Language resource | Zero user setup, central metrics, single cost center |
| Auth | `DefaultAzureCredential` (Entra ID) | Matches existing Foundry auth, no API keys, policy-compliant (local auth disabled) |
| RBAC | `Cognitive Services Language Reader` on Language resource, granted tenant-wide or via dynamic security group | All users are same tenant; they already have Entra identities from Foundry access |
| Endpoint config | Hardcoded default in `version.py`, silently overridable via `LANGUAGE_ENDPOINT` env var | Not user-configurable by design — centralized resource, not per-user. Env var override exists as an undocumented escape hatch for emergencies (not surfaced in UI, setup, or docs) |
| Failure mode | Fail-closed with error message | If Language resource unreachable, block generation and show actionable error — input cannot be sent to external services without PII clearance |
| Confidence threshold | ≥ 0.8 | Reduce false positives; configurable as a constant in `pii_check.py` |

### PII Categories to Detect

| SDK Enum Constant | Category | Why |
|-------------------|----------|-----|
| `EMAIL` | Email | Direct customer identifier |
| `PHONE_NUMBER` | PhoneNumber | Direct customer identifier |
| `IP_ADDRESS` | IPAddress | Can identify customer infrastructure |
| `PERSON` | Person | Customer/contact names |
| `AZURE_DOCUMENT_DB_AUTH_KEY` | AzureDocumentDBAuthKey | Credential leak |
| `AZURE_STORAGE_ACCOUNT_KEY` | AzureStorageAccountKey | Credential leak |
| `AZURE_SAS` | AzureSAS | Credential leak |
| `AZURE_IO_T_CONNECTION_STRING` | AzureIoTConnectionString | Credential leak (note: SDK splits IoT as `IO_T`) |
| `SQL_SERVER_CONNECTION_STRING` | SQLServerConnectionString | Credential leak |
| `CREDIT_CARD_NUMBER` | CreditCardNumber | Financial PII |
| `US_SOCIAL_SECURITY_NUMBER` | USSocialSecurityNumber | Government PII |

> **Not flagged**: Bare GUIDs (too common in Azure error messages). Only GUIDs in credential/connection string context are caught via the Azure-specific categories above.

> **Intentionally excluded**: `Organization` — too noisy for Azure troubleshooting notes that routinely mention "Microsoft", service names, and partner companies. `Password` — does not exist as a `PiiEntityCategory` enum constant in the SDK; Azure-specific credential categories above already cover connection strings, keys, and SAS tokens.

> **SDK mapping**: The table above lists the exact `PiiEntityCategory` enum constant names. Use `PiiEntityCategory.<CONSTANT>` directly in `PII_CATEGORIES` (e.g., `PiiEntityCategory.AZURE_DOCUMENT_DB_AUTH_KEY`). All constants verified against `azure-ai-textanalytics>=5.3.0`.

### Metrics & Tracking

All metrics come from Azure Monitor + Diagnostic Logs on the centralized Language resource (the only shared component — the app runs locally as an exe).

| Signal | Source |
|--------|--------|
| Total PII check calls (volume) | Azure Monitor Metrics → `Total Calls` |
| Unique users (adoption) | Diagnostic Logs → distinct `CallerObjectId` |
| Calls per user | Diagnostic Logs → group by `CallerObjectId` |
| Usage trend | Diagnostic Logs → count by `bin(TimeGenerated, 1d)` |
| Error rate | Metrics → `Client Errors` / `Server Errors` |
| Latency | Metrics → `Response Latency` |
| Cost | Cost Management → filter by Language resource |

### Error Handling Strategy

The PII check is a **hard gate** — if it can't confirm the input is clean, generation is blocked. The user gets a clear, actionable error message explaining what went wrong and how to fix it. Follow the same error UX patterns as the existing pipeline (user-friendly message + hint).

| Scenario | Backend Behavior | Frontend Behavior |
|----------|-----------------|-------------------|
| Language resource unreachable (network) | Return `{"error": "PII check failed: cannot reach Language service", "hint": "Check your network connection and try again."}` | Show error message with hint, block generation |
| Authentication failure (`ClientAuthenticationError`) | Return `{"error": "PII check failed: authentication error", "hint": "Run 'az login' to refresh your credentials."}` | Show error message with hint, block generation |
| Permission denied (403 on Language resource) | Return `{"error": "PII check failed: access denied", "hint": "Your account may not have Cognitive Services Language Reader role."}` | Show error message with hint, block generation |
| Service error (5xx from Language API) | Return `{"error": "PII check failed: Language service error (5xx)", "hint": "The Azure Language service is experiencing issues. Try again in a few minutes."}` | Show error message with hint, block generation |
| Rate limited (429) | Return `{"error": "PII check failed: rate limited", "hint": "Too many requests. Wait a moment and try again."}` | Show error message with hint, block generation |
| Document-level error from API (`is_error=True`) | Return `{"error": "PII check failed: could not scan all content", "hint": "The Language service could not process part of the input."}` | Show error message with hint, block generation |
| Frontend `POST /api/pii-check` network failure | N/A | Show error: "Could not reach PII check service", block generation |
| Frontend `POST /api/pii-check` returns non-200 | N/A | Show error from response body, block generation |

**Logging**: When any error occurs, `pii_check.py` logs the error type and message to the console (e.g., `"⚠️ PII check failed (ServiceRequestError): Connection refused"`) **without logging the input text or any detected PII content**.

**Return shape**: The `check_for_pii()` function always returns the same dict shape:
```python
{
    "pii_detected": bool,       # False on error (but error field blocks generation)
    "findings": list,            # [] on error
    "redacted_text": str,        # original text on error (unused since generation is blocked)
    "error": str | None,         # error message, or None on success
    "hint": str | None,          # actionable hint for user, or None on success
}
```

---

## Phase 1: Azure Setup (One-Time, Manual)

Owner: project author (not end users).

- [x] Create Azure Language resource (Free F0 or Standard S tier)
- [x] Record the endpoint URL
- [x] Assign `Cognitive Services Language Reader` role at resource scope — either:
  - [x] Tenant-wide (`All Users` principal), **or**
  - [ ] Dynamic security group with membership rule (e.g., `user.department -eq "Azure Support"`)
- [x] Enable Diagnostic Settings → send to Log Analytics workspace
  - [x] Category: `Audit` (captures caller identity per request)
- [x] Verify access: `az login` as a target user, call the PII endpoint, confirm 200

---

## Phase 2: Backend — `pii_check.py` + Constants

- [x] Add `LANGUAGE_ENDPOINT` to `version.py` — hardcoded default with silent `os.getenv()` override: `LANGUAGE_ENDPOINT = os.getenv("LANGUAGE_ENDPOINT", "https://tsgbuilder-pii-language.cognitiveservices.azure.com/")`  (undocumented escape hatch, not surfaced in UI or docs)
- [x] Add `azure-ai-textanalytics>=5.3.0` to `requirements.txt`
- [x] Create `pii_check.py` with:
  - [x] `PII_CATEGORIES` — list of `PiiEntityCategory` enum constants to detect (map from table above)
  - [x] `PII_CONFIDENCE_THRESHOLD = 0.8`
  - [x] `PII_CHUNK_SIZE = 5120` — max characters per document (synchronous API limit)
  - [x] `PII_MAX_DOCS_PER_REQUEST = 5` — max documents per synchronous API call
  - [x] `get_language_client()` — creates `TextAnalyticsClient` with `DefaultAzureCredential` + `LANGUAGE_ENDPOINT` (endpoint is hardcoded constant, always available)
  - [x] `check_for_pii(text: str) -> dict` — calls `recognize_pii_entities()` with `disable_service_logs=True` and `categories_filter=PII_CATEGORIES`, filters by confidence threshold, returns:
    ```python
    {
        "pii_detected": bool,
        "findings": [{"category": str, "text": str, "confidence": float, "offset": int, "length": int}, ...],
        "redacted_text": str,        # from API's native doc.redacted_text
        "error": str | None,         # error message on failure, None on success
        "hint": str | None,          # actionable user hint on failure, None on success
    }
    ```
  - [x] **Chunking for large inputs**:
    - Split input into chunks of ≤ `PII_CHUNK_SIZE` characters, breaking at whitespace boundaries to avoid splitting words/entities
    - Batch chunks in groups of `PII_MAX_DOCS_PER_REQUEST` (5) per API call
    - **Reassemble `redacted_text`**: concatenate each chunk's `redacted_text` in order to produce the full redacted document
    - **Adjust offsets**: shift each chunk's entity offsets by the cumulative character count of preceding chunks so findings reference positions in the original input
    - If any individual chunk returns `is_error=True`, **fail-closed**: log warning (without input text), stop processing, and return result with `error` + `hint` fields set — do NOT continue with remaining chunks or allow generation to proceed
  - [x] **Error handling** — reuse the existing `_classify_azure_sdk_error()` from `web_app.py`. Refactored into `error_utils.py` so both `web_app.py` and `pii_check.py` import the same classifier (`classify_azure_sdk_error()`). Catches `ClientAuthenticationError`, `ServiceRequestError`, `HttpResponseError`, and generic `Exception`; classifies via shared utility; on any error, returns result with `error` + `hint` fields set (caller blocks generation)
  - [x] **Logging** — print warnings on errors (e.g., `"⚠️ PII check failed (ErrorType): message"`) without logging any input text or PII content

---

## Phase 3: Backend — Web Endpoints

- [x] Add `POST /api/pii-check` endpoint to `web_app.py`:
  - [x] Accepts `{"notes": "..."}`
  - [x] Validates notes is non-empty — return `400` with `{"error": "No notes provided"}` if empty/missing
  - [x] Calls `check_for_pii()`
  - [x] Returns `{"pii_detected", "findings", "redacted_text", "error", "hint"}`
  - [x] Returns 200 when check succeeds (PII detected is not an HTTP error — it's a data response)
  - [x] Returns 500 with `{"error": "...", "hint": "..."}` when the Language service is unreachable or errors
- [x] Add server-side PII gate at top of `POST /api/generate/stream`:
  - [x] Call `check_for_pii()` before starting the SSE stream
  - [x] If PII detected, return `400` with `{"error": "PII detected in notes", "findings": [...]}`
  - [x] If PII check returned an error, return `500` with `{"error": "...", "hint": "..."}` — do NOT proceed
  - [x] Defense-in-depth — frontend already blocks, this prevents bypass
- [x] Add server-side PII gate at top of `POST /api/answer/stream`:
  - [x] Call `check_for_pii()` on the answers text before starting the SSE stream
  - [x] Same behavior as generate/stream gate — block if PII found, block on errors
  - [x] Rationale: follow-up answers can also contain PII (e.g., "the customer's email is...")

---

## Phase 4: Frontend — PII Modal

- [x] Add `#piiModal` to `templates/index.html`:
  - [x] Follows existing `.modal-overlay > .modal` pattern (from `#setupModal`)
  - [x] Error-themed header (`--error` / `--error-bg` CSS variables, already defined in styles.css)
  - [x] Body: scrollable list of findings (category badge + masked text snippet)
  - [x] Footer: two buttons:
    - [x] **"Go Back & Edit"** — closes modal, focuses textarea
    - [x] **"Redact & Continue"** — replaces textarea value with `redacted_text`, closes modal (does NOT auto-generate — user reviews first)
- [x] Add PII modal styles to `static/css/styles.css`:
  - [x] `.pii-finding` — finding row layout
  - [x] `.pii-category-badge` — category label styling
  - [x] `.pii-text-snippet` — matched text display (monospace, subtle background)

---

## Phase 5: Frontend — Generate Flow Integration

- [x] Modify `generateTSG()` in `static/js/main.js`:
  - [x] Disable the Generate button and show brief loading state (e.g., button text → "Checking...") during the PII check request to prevent double-clicks and signal activity during the ~100-300ms call
  - [x] After existing "notes empty" check, `POST` to `/api/pii-check`
  - [x] If `pii_detected === true`: populate `#piiModal` with findings, stash `redacted_text`, show modal, `return` early
  - [x] If `pii_detected === false` and no `error`: proceed to `generateTSGWithStreaming()` as normal
  - [x] If `error` is set (Language service unreachable, auth failed, etc.): show error message with hint using `showError()`, `return` early — do NOT proceed with generation
  - [x] If PII check request fails entirely (network error, fetch exception) or returns 4xx/5xx: parse error/hint from response body if available, otherwise show "Could not reach PII check service", `return` early — do NOT proceed
- [x] Modify `submitAnswers()` in `static/js/main.js`:
  - [x] Before submitting, `POST` to `/api/pii-check` with answers text
  - [x] Same PII modal / block-on-error behavior as `generateTSG()`
- [x] Add `openPiiModal(findings, redactedText, targetTextarea)` function
  - [x] `targetTextarea` param: `'notesInput'` for generate flow, `'answersInput'` for answer flow — determines which textarea "Go Back & Edit" focuses and "Redact & Continue" updates
- [x] Add `closePiiModal()` function (matches `closeSetup()` pattern)
- [x] Add `redactAndContinue()` function — sets target textarea value, closes modal

---

## Phase 6: Tests

- [ ] Create `tests/test_pii_check.py`:
  - [ ] **Unit tests** (mock `TextAnalyticsClient`):
    - [ ] Detects email addresses
    - [ ] Detects phone numbers
    - [ ] Detects IP addresses
    - [ ] Detects Azure storage keys / SAS tokens / connection strings
    - [ ] Does not flag bare GUIDs
    - [ ] Filters below confidence threshold
    - [ ] Returns `redacted_text` from API response
    - [ ] Passes `disable_service_logs=True` and `categories_filter` to API
    - [ ] **Chunking tests**:
      - [ ] Input under 5,120 chars → single API call, no chunking
      - [ ] Input over 5,120 chars → split into chunks, results merged
      - [ ] Offsets adjusted correctly for multi-chunk input
      - [ ] Redacted text reassembled correctly across chunks
      - [ ] Chunks split at whitespace boundaries (no mid-word splits)
      - [ ] Input requiring >5 chunks → multiple batched API calls
    - [ ] **Error handling tests** (reuse existing Azure SDK error fixtures from `conftest.py`):
      - [ ] `ServiceRequestError` (network unreachable) → `error` + `hint` set, `pii_detected` false
      - [ ] `ClientAuthenticationError` → `error` + `hint` set
      - [ ] `HttpResponseError` with 403 (permission denied) → `error` + `hint` set
      - [ ] `HttpResponseError` with 429 (rate limit) → `error` + `hint` set
      - [ ] `HttpResponseError` with 500 (service error) → `error` + `hint` set
      - [ ] Generic `Exception` → `error` + `hint` set
      - [ ] Document-level `is_error=True` in one chunk → `error` + `hint` set (blocks generation, does NOT continue to remaining chunks)
      - [ ] Multi-chunk partial success (first chunk OK, second chunk `is_error=True`) → blocks generation, findings from successful chunks are NOT returned
  - [ ] **Endpoint tests** (Flask test client):
    - [ ] `POST /api/pii-check` with clean text → `pii_detected: false`
    - [ ] `POST /api/pii-check` with PII text → `pii_detected: true` + findings
    - [ ] `POST /api/pii-check` with empty notes → 400
    - [ ] `POST /api/pii-check` when Language API errors → 500 with `error` + `hint`
    - [ ] `POST /api/generate/stream` with PII text → 400 with findings
    - [ ] `POST /api/generate/stream` when PII check errors → 500, does NOT proceed
    - [ ] `POST /api/answer/stream` with PII text → 400 with findings
    - [ ] `POST /api/answer/stream` when PII check errors → 500, does NOT proceed
- [ ] Verify existing tests still pass

---

## Phase 7: Documentation & Build

### Documentation Updates

- [ ] **`.github/copilot-instructions.md`**:
  - [ ] Add `pii_check.py` to file reference table (purpose: "PII detection via Azure AI Language API")
  - [ ] Add shared error utility file (if refactored) to file reference table
  - [ ] Add row to "Warning System" table for PII-related errors (source: PII check, type: blocks generation, not a soft warning)
  - [ ] Add entry to "Common Issues" section: "PII false positives" — explain that Azure names, service names etc. may trigger `Person`/`Organization` detection; fixed category list is intentional, adjust based on feedback
- [ ] **`docs/architecture.md`**:
  - [ ] Add `pii_check.py` to file structure table
  - [ ] Add shared error utility file (if refactored) to file structure table
  - [ ] Update pipeline diagram to show PII check as a pre-flight gate before Stage 1 (Research)
  - [ ] Add "PII Pre-Flight Check" subsection to Design Decisions explaining: why fail-closed, why centralized resource, why no bypass
- [ ] **`README.md`**:
  - [ ] Add RBAC / Language resource setup notes (for project maintainers, not end users)
  - [ ] Document the PII content filter on the Foundry model deployment as a complementary (optional) measure
- [ ] **`docs/releasing.md`**:
  - [ ] Note that `azure-ai-textanalytics` dependency increases exe build size

### Build Verification

- [ ] **Hidden imports**: `azure-ai-textanalytics` depends on `azure.core`, `isodate`, and other sub-packages that may require PyInstaller hidden imports (e.g., `azure.ai.textanalytics._version`). Run `make build` after implementation, test the resulting exe, and add any required `--hidden-import` flags to `build_exe.py`
- [ ] **Exe smoke test**: Verify the built exe can successfully call the Language API PII endpoint (not just that it launches)

---

## User Experience Summary

```
User pastes notes → clicks Generate
         │
         ▼
    POST /api/pii-check (~100-300ms)
         │
    ┌────┴──────────────────┬─────────────────────┐
    │                       │                     │
No PII                  PII found            Error / Unreachable
    │                       │                     │
    ▼                       ▼                     ▼
Start pipeline          Show #piiModal        Show error message
as normal               ┌──────────────────┐  with actionable hint
                        │ ⚠ PII Detected   │  (BLOCKED — user must
                        │                  │   fix and retry)
                        │ • Email: j***@.. │
                        │ • Phone: ***-*** │
                        │                  │
                        │ [Go Back & Edit] │
                        │ [Redact & Cont.] │
                        └──────────────────┘
                             │         │
                        Go Back    Redact
                             │         │
                             ▼         ▼
                        Focus      Replace textarea
                        textarea   with redacted text,
                                   user reviews &
                                   clicks Generate again

Same flow applies to submitAnswers() with the answers textarea.
```

### End-user setup required: **None**

If they can `az login` and use TSG Builder today, PII check works automatically.

---

## Out of Scope

| Item | Why |
|------|-----|
| AI-based name/company detection beyond Language API | Language API already detects `Person` and `Organization` categories |
| Per-user Language resource setup | Centralized resource eliminates this |
| App-level telemetry (App Insights, etc.) | App runs locally as exe, no shared backend to pipe logs to |
| PII content filter on Foundry deployment | Complementary output filter — manual portal config, not a code change |
| Configurable PII categories in UI | Premature — start with fixed list, adjust based on false positive feedback |
| User-facing on/off toggle for PII check | PII check is always active — it's a security requirement, not optional |
| "Proceed anyway" button in PII modal | User must edit or redact; no bypass to prevent accidental PII leakage |

---

## Implementation Notes

These are technical details to keep in mind during implementation:

1. **`disable_service_logs=True`**: Always pass this to `recognize_pii_entities()`. This prevents the Language service from logging input text server-side. It defaults to `True` in recent SDK versions, but set it explicitly for clarity.

2. **`categories_filter`**: Pass `PII_CATEGORIES` to `recognize_pii_entities()` to avoid detecting categories we don't care about (reduces noise and false positives).

3. **Endpoint naming**: `LANGUAGE_ENDPOINT` in `version.py` uses a hardcoded default with a silent `os.getenv()` override. The env var is intentionally undocumented — it exists only as an emergency escape hatch (e.g., resource re-creation or region move) and is not surfaced in the setup UI, validation, config modal, or any user-facing documentation. Unlike `PROJECT_ENDPOINT` (per-user, in `.env`), the Language endpoint is centralized and owned by the project author.

4. **Reuse existing error classification**: Refactor `_classify_azure_sdk_error()` out of `web_app.py` into a shared utility so both `web_app.py` and `pii_check.py` import the same function. This keeps Azure SDK error-to-message mapping in one place. The shared utility should also use the existing hint constants (`HINT_AUTH`, `HINT_CONNECTION`, etc.) from `pipeline.py`.

5. **CSS variables**: `--error` and `--error-bg` already exist in `styles.css` for both light and dark themes. No new CSS variables needed for the PII modal.

6. **`openPiiModal` reuse**: The modal needs to work for both the notes textarea and the answers textarea. Parameterize with the target textarea ID.
