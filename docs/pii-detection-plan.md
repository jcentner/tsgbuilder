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
| Endpoint config | Hardcoded constant in `version.py` | Not user-configurable — centralized resource, not per-user (unlike `PROJECT_ENDPOINT` which is per-user) |
| Failure mode | Fail-closed with error message | If Language resource unreachable, block generation and show actionable error — input cannot be sent to external services without PII clearance |
| Confidence threshold | ≥ 0.8 | Reduce false positives; configurable as a constant in `pii_check.py` |

### PII Categories to Detect

| Category | Why |
|----------|-----|
| `Email` | Direct customer identifier |
| `PhoneNumber` | Direct customer identifier |
| `IPAddress` | Can identify customer infrastructure |
| `Person` | Customer/contact names |
| `AzureDocumentDBAuthKey` | Credential leak |
| `AzureStorageAccountKey` | Credential leak |
| `AzureSAS` | Credential leak |
| `AzureIoTConnectionString` | Credential leak |
| `SQLServerConnectionString` | Credential leak |
| `Password` | Credential leak |
| `CreditCardNumber` | Financial PII |
| `USSocialSecurityNumber` | Government PII |

> **Not flagged**: Bare GUIDs (too common in Azure error messages). Only GUIDs in credential/connection string context are caught via the Azure-specific categories above.

> **SDK mapping**: These category names must be mapped to `PiiEntityCategory` enum constants from the SDK (e.g., `AzureDocumentDBAuthKey` → `PiiEntityCategory.AZURE_DOCUMENT_DB_AUTH_KEY`). Verify each constant exists in `azure-ai-textanalytics>=5.3.0` during implementation.

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

- [ ] Create Azure Language resource (Free F0 or Standard S tier)
- [ ] Record the endpoint URL
- [ ] Assign `Cognitive Services Language Reader` role at resource scope — either:
  - [ ] Tenant-wide (`All Users` principal), **or**
  - [ ] Dynamic security group with membership rule (e.g., `user.department -eq "Azure Support"`)
- [ ] Enable Diagnostic Settings → send to Log Analytics workspace
  - [ ] Category: `Audit` (captures caller identity per request)
- [ ] Verify access: `az login` as a target user, call the PII endpoint, confirm 200

---

## Phase 2: Backend — `pii_check.py` + Constants

- [ ] Add `LANGUAGE_ENDPOINT` constant to `version.py` (hardcoded, not user-configurable)
- [ ] Add `azure-ai-textanalytics>=5.3.0` to `requirements.txt`
- [ ] Create `pii_check.py` with:
  - [ ] `PII_CATEGORIES` — list of `PiiEntityCategory` enum constants to detect (map from table above)
  - [ ] `PII_CONFIDENCE_THRESHOLD = 0.8`
  - [ ] `PII_CHUNK_SIZE = 5120` — max characters per document (synchronous API limit)
  - [ ] `PII_MAX_DOCS_PER_REQUEST = 5` — max documents per synchronous API call
  - [ ] `get_language_client()` — creates `TextAnalyticsClient` with `DefaultAzureCredential` + `LANGUAGE_ENDPOINT` (endpoint is hardcoded constant, always available)
  - [ ] `check_for_pii(text: str) -> dict` — calls `recognize_pii_entities()` with `disable_service_logs=True` and `categories_filter=PII_CATEGORIES`, filters by confidence threshold, returns:
    ```python
    {
        "pii_detected": bool,
        "findings": [{"category": str, "text": str, "confidence": float, "offset": int, "length": int}, ...],
        "redacted_text": str,        # from API's native doc.redacted_text
        "error": str | None,         # error message on failure, None on success
        "hint": str | None,          # actionable user hint on failure, None on success
    }
    ```
  - [ ] **Chunking for large inputs**:
    - Split input into chunks of ≤ `PII_CHUNK_SIZE` characters, breaking at whitespace boundaries to avoid splitting words/entities
    - Batch chunks in groups of `PII_MAX_DOCS_PER_REQUEST` (5) per API call
    - **Reassemble `redacted_text`**: concatenate each chunk's `redacted_text` in order to produce the full redacted document
    - **Adjust offsets**: shift each chunk's entity offsets by the cumulative character count of preceding chunks so findings reference positions in the original input
    - If any individual chunk returns `is_error=True`, log warning, treat that chunk as unchecked (use original text for its redacted portion), and continue with remaining chunks
  - [ ] **Error handling** — catch `ClientAuthenticationError`, `ServiceRequestError`, `HttpResponseError`, and generic `Exception`; on any error, log warning with error type (not input text) and return result with `error` + `hint` fields set (caller blocks generation)
  - [ ] **Logging** — print warnings on errors (e.g., `"⚠️ PII check failed (ErrorType): message"`) without logging any input text or PII content

---

## Phase 3: Backend — Web Endpoints

- [ ] Add `POST /api/pii-check` endpoint to `web_app.py`:
  - [ ] Accepts `{"notes": "..."}`
  - [ ] Validates notes is non-empty — return `400` with `{"error": "No notes provided"}` if empty/missing
  - [ ] Calls `check_for_pii()`
  - [ ] Returns `{"pii_detected", "findings", "redacted_text", "error", "hint"}`
  - [ ] Returns 200 when check succeeds (PII detected is not an HTTP error — it's a data response)
  - [ ] Returns 500 with `{"error": "...", "hint": "..."}` when the Language service is unreachable or errors
- [ ] Add server-side PII gate at top of `POST /api/generate/stream`:
  - [ ] Call `check_for_pii()` before starting the SSE stream
  - [ ] If PII detected, return `400` with `{"error": "PII detected in notes", "findings": [...]}`
  - [ ] If PII check returned an error, return `500` with `{"error": "...", "hint": "..."}` — do NOT proceed
  - [ ] Defense-in-depth — frontend already blocks, this prevents bypass
- [ ] Add server-side PII gate at top of `POST /api/answer/stream`:
  - [ ] Call `check_for_pii()` on the answers text before starting the SSE stream
  - [ ] Same behavior as generate/stream gate — block if PII found, block on errors
  - [ ] Rationale: follow-up answers can also contain PII (e.g., "the customer's email is...")

---

## Phase 4: Frontend — PII Modal

- [ ] Add `#piiModal` to `templates/index.html`:
  - [ ] Follows existing `.modal-overlay > .modal` pattern (from `#setupModal`)
  - [ ] Error-themed header (`--error` / `--error-bg` CSS variables, already defined in styles.css)
  - [ ] Body: scrollable list of findings (category badge + masked text snippet)
  - [ ] Footer: two buttons:
    - [ ] **"Go Back & Edit"** — closes modal, focuses textarea
    - [ ] **"Redact & Continue"** — replaces textarea value with `redacted_text`, closes modal (does NOT auto-generate — user reviews first)
- [ ] Add PII modal styles to `static/css/styles.css`:
  - [ ] `.pii-finding` — finding row layout
  - [ ] `.pii-category-badge` — category label styling
  - [ ] `.pii-text-snippet` — matched text display (monospace, subtle background)

---

## Phase 5: Frontend — Generate Flow Integration

- [ ] Modify `generateTSG()` in `static/js/main.js`:
  - [ ] After existing "notes empty" check, `POST` to `/api/pii-check`
  - [ ] If `pii_detected === true`: populate `#piiModal` with findings, stash `redacted_text`, show modal, `return` early
  - [ ] If `pii_detected === false` and no `error`: proceed to `generateTSGWithStreaming()` as normal
  - [ ] If `error` is set (Language service unreachable, auth failed, etc.): show error message with hint using `showError()`, `return` early — do NOT proceed with generation
  - [ ] If PII check request fails entirely (network error, non-200 status): show error "Could not reach PII check service", `return` early — do NOT proceed
- [ ] Modify `submitAnswers()` in `static/js/main.js`:
  - [ ] Before submitting, `POST` to `/api/pii-check` with answers text
  - [ ] Same PII modal / block-on-error behavior as `generateTSG()`
- [ ] Add `openPiiModal(findings, redactedText, targetTextarea)` function
  - [ ] `targetTextarea` param: `'notesInput'` for generate flow, `'answersInput'` for answer flow — determines which textarea "Go Back & Edit" focuses and "Redact & Continue" updates
- [ ] Add `closePiiModal()` function (matches `closeSetup()` pattern)
- [ ] Add `redactAndContinue()` function — sets target textarea value, closes modal

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
    - [ ] **Error handling tests**:
      - [ ] `ServiceRequestError` (network unreachable) → `error` + `hint` set, `pii_detected` false
      - [ ] `ClientAuthenticationError` → `error` + `hint` set
      - [ ] `HttpResponseError` with 403 (permission denied) → `error` + `hint` set
      - [ ] `HttpResponseError` with 429 (rate limit) → `error` + `hint` set
      - [ ] `HttpResponseError` with 500 (service error) → `error` + `hint` set
      - [ ] Generic `Exception` → `error` + `hint` set
      - [ ] Document-level `is_error=True` in one chunk → `error` + `hint` set (blocks generation)
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

- [ ] Add `pii_check.py` to file reference table in `.github/copilot-instructions.md`
- [ ] Add `pii_check.py` to file structure table in `docs/architecture.md`
- [ ] Add RBAC / Language resource setup notes to `README.md` (for project maintainers, not end users)
- [ ] Document the PII content filter on the Foundry model deployment as a complementary (optional) measure
- [ ] **Build impact**: Adding `azure-ai-textanalytics` increases the PyInstaller exe size. No hidden imports or data bundling should be needed (pure Python Azure SDK). Verify with `make build` after implementation.

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

3. **Endpoint naming**: The constant is `LANGUAGE_ENDPOINT` in `version.py` (hardcoded, always present). This is distinct from the `AZURE_LANGUAGE_ENDPOINT` environment variable convention used in SDK samples — intentional, since ours is not user-configurable. Unlike `PROJECT_ENDPOINT` (per-user, in `.env`), the Language endpoint is centralized and owned by the project author.

4. **Existing error patterns**: Follow `_classify_azure_sdk_error()` in `web_app.py` and `classify_error()` in `pipeline.py` for error classification conventions. Import shared Azure exception types from `azure.core.exceptions`.

5. **CSS variables**: `--error` and `--error-bg` already exist in `styles.css` for both light and dark themes. No new CSS variables needed for the PII modal.

6. **`openPiiModal` reuse**: The modal needs to work for both the notes textarea and the answers textarea. Parameterize with the target textarea ID.
