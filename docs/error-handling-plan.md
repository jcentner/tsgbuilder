# Error Handling & Timeout Improvements Plan

> **Created**: January 23, 2026  
> **Status**: In Progress  
> **Priority**: High/Medium  

This document outlines the implementation plan for improving error handling and timeout management in TSG Builder, with a focus on surfacing Azure service issues with user-readable messages.

## Executive Summary

The application has a solid foundation for error handling with centralized classification (`classify_error`) and retry logic. However, there are gaps where Azure service errors could be surfaced more specifically to users, and some edge cases that aren't explicitly handled.

---

## Phase 1: Enhanced Error Classification (High Priority) ✅ COMPLETED

> **Completed**: January 27, 2026

**Goal**: Improve `classify_error()` to detect Azure-specific HTTP status codes and provide actionable user messages.

### 1.1 Update `ErrorClassification` dataclass ✅
**File**: `pipeline.py`  
**Changes**:
- Add `http_status_code: int | None` field to track detected status code
- Add `error_code: str | None` field for API-specific error codes (e.g., `rate_limit_exceeded`)
- Add `is_auth_error: bool` field for authentication-specific handling

### 1.2 Expand `classify_error()` function ✅
**File**: `pipeline.py`  
**Changes**:
- Add detection patterns for HTTP status codes:

| Status Code | User Message |
|-------------|--------------|
| 401 | "Azure authentication failed. Run `az login` and try again." |
| 403 | "Permission denied. Check your Azure role assignments." |
| 404 | "Resource not found. Try re-creating agents in Setup." |
| 500 | "Azure service error. Please try again." |
| 502 | "Azure gateway error. Please try again." |
| 503 | "Azure AI service temporarily unavailable. Try again in a few minutes." |
| 504 | "Azure gateway timed out. Try again with shorter input." |

- Add detection for common error phrases:
  - "unauthorized" / "authentication" → auth error
  - "forbidden" / "permission" → permission error
  - "not found" / "does not exist" → resource not found
  - "service unavailable" → service outage
  - "quota" / "exceeded" → quota exhaustion
- Set `is_retryable` appropriately (401/403 are NOT retryable; 500/502/503 ARE retryable)

### 1.3 Create error code constants ✅
**File**: `pipeline.py`  
**Changes**:
- Define constants for user-friendly messages to ensure consistency
- Create mapping: `HTTP_STATUS_MESSAGES = {401: "...", 403: "...", ...}`
- Create `ERROR_PHRASE_PATTERNS` list for pattern-based error detection
- Add helper functions `_extract_http_status_code()` and `_extract_api_error_code()`

---

## Phase 2: Streaming Event Error Parsing (Medium Priority) ✅ COMPLETED

> **Completed**: January 28, 2026

**Goal**: Extract structured error information from Azure API `ResponseErrorEvent` and `ResponseFailedEvent`.

### 2.1 Update `process_pipeline_v2_stream()` for `response.failed` events ✅
**File**: `pipeline.py`  
**Location**: Lines 839-874 (after Phase 2 edits)  
**Changes**:
- Parse `event.response.error` for structured fields:
  - `error.code` (e.g., `server_error`, `rate_limit_exceeded`)
  - `error.message`
  - `error.param` (if available)
- Pass structured info to `_send_classified_error()` for better classification
- Added verbose logging for debugging structured error info

### 2.2 Update `_send_classified_error()` for structured errors ✅
**File**: `pipeline.py`  
**Location**: Lines 478-568 (after Phase 2 edits)  
**Changes**:
- Accept optional `error_code` and `http_status_code` parameters
- Use `_extract_http_status_code()` and `_extract_api_error_code()` from Phase 1 for string-based extraction
- Use `HTTP_STATUS_MESSAGES` lookup for HTTP status codes
- Added `API_ERROR_CODES` mapping for API-specific error codes
- Include structured error info in event data for debugging

| API Error Code | User Message |
|----------------|--------------|
| `rate_limit_exceeded` | Rate limit message |
| `server_error` | Service error message |
| `invalid_prompt` | "Input could not be processed. Try simplifying." |
| `vector_store_timeout` | "Search timed out. Retrying..." |
| `context_length_exceeded` | "Input too long. Try shorter notes." |
| `content_filter` | "Content was filtered. Review input for policy violations." |

### 2.3 Handle `error` event type with structured data ✅
**File**: `pipeline.py`  
**Location**: Lines 875-906 (after Phase 2 edits)  
**Changes**:
- Parse `event.code`, `event.message`, `event.param` when available
- Include error code in the classified error for better debugging
- Added verbose logging for debugging structured error info

---

## Phase 3: Agent Creation Error Handling (Medium Priority) ✅ COMPLETED

> **Completed**: January 28, 2026

**Goal**: Provide specific, actionable error messages when agent creation fails.

### 3.1 Create helper function for Azure SDK exceptions ✅
**File**: `web_app.py`  
**Location**: Lines 521-604 (new function before api_create_agent)  
**Changes**:
- Added `_classify_azure_sdk_error(error: Exception) -> tuple[str, str | None, int]` function
- Returns (user_message, hint, http_status_code)
- Handles specific Azure exception types:
  - `ClientAuthenticationError` → auth guidance with hint to run `az login`
  - `ServiceRequestError` → connectivity guidance with endpoint check hint
  - `ResourceNotFoundError` → resource missing guidance
  - `HttpResponseError` → parses status code (401, 403, 404, 429, 5xx) with appropriate hints

### 3.2 Update `api_create_agent()` endpoint ✅
**File**: `web_app.py`  
**Location**: Lines 713-732 (exception handlers)  
**Changes**:
- Catches specific exception types before generic `Exception`
- Uses `_classify_azure_sdk_error()` for user-friendly messages
- Returns structured error response with hint field:
  ```json
  {
    "success": false,
    "error": "User-friendly message",
    "error_type": "HttpResponseError",
    "hint": "Run 'az login' to refresh credentials."
  }
  ```

### 3.3 Update frontend to display hints ✅
**File**: `templates/index.html`  
**Location**: `createAgent()` function  
**Changes**:
- Parses `hint` field from error responses
- Displays hints with 💡 icon in secondary text style below error message

---

## Phase 4: Web App Error Handler Enhancement (Medium Priority) ✅ COMPLETED

> **Completed**: January 28, 2026

**Goal**: Improve `_get_user_friendly_error()` to handle Azure-specific errors.

### 4.1 Create `PipelineError` exception class ✅
**File**: `pipeline.py`  
**Location**: After `ResponseFailedError` class  
**Changes**:
- Created `PipelineError` exception that carries:
  - `stage: PipelineStage`
  - `original_error: Exception`
  - `http_status: int | None`
  - `error_code: str | None`
- Updated `classify_error()` to handle `PipelineError` by unwrapping and using pre-computed info

### 4.2 Update `_run_stage()` to raise `PipelineError` ✅
**File**: `pipeline.py`  
**Location**: Exception handler in `_run_stage()`  
**Changes**:
- Replaced `RuntimeError` with `PipelineError` that carries structured context
- Pre-classifies the error to extract HTTP status and error code

### 4.3 Refactor `_get_user_friendly_error()` ✅
**File**: `web_app.py`  
**Location**: Lines 120-218  
**Changes**:
- Changed return type from `str` to `tuple[str, str | None]` (message, hint)
- Added handling for `PipelineError` (uses stage info directly, no string parsing)
- Added handling for Azure SDK exceptions:
  - `ClientAuthenticationError` → auth guidance with hint
  - `ServiceRequestError` → connectivity guidance with hint
  - `ResourceNotFoundError` → resource missing guidance with hint
  - `HttpResponseError` → parses status code (401, 403, 404, 429, 5xx) with hints
- Falls back to string-based stage detection for unknown exceptions
- Generates appropriate hints based on error classification

### 4.4 Update call site and frontend ✅
**File**: `web_app.py` and `templates/index.html`  
**Changes**:
- Updated exception handler in `/api/generate` to unpack tuple return
- Includes `hint` field in error event data when available
- Frontend displays hints with 💡 icon in activity feed and error messages

---

## Phase 5: Timeout Tuning (Medium Priority) ✅ COMPLETED

> **Completed**: January 28, 2026

**Goal**: Optimize timeout values for better responsiveness without false positives.

### 5.1 Reduce tool call timeout ✅
**File**: `pipeline.py`  
**Location**: Line 200  
**Changes**:
- Changed `TOOL_CALL_TIMEOUT = 120` to `TOOL_CALL_TIMEOUT = 90`
- Updated comment explaining rationale (Bing typically <30s, MCP <60s)

### 5.2 Add secondary stream stall detection ✅ (Already Implemented)
**File**: `pipeline.py`  
**Status**: Already covered by existing `_iterate_with_timeout()` implementation.
- Each event has a per-event timeout via `STREAM_IDLE_TIMEOUT`
- Tool timeouts checked on every event iteration
- No additional implementation needed

### 5.3 Make timeouts configurable ⏭️ SKIPPED
**Status**: Deferred - not needed for current use case.
- Single-user application doesn't require runtime timeout tuning
- Can be added later if operators need flexibility

---

## Phase 6: Retry Logic Improvements (Low Priority) ✅ COMPLETED

> **Completed**: January 28, 2026

**Goal**: Add jitter and improve retry messaging.

### 6.1 Add jitter to backoff ⏭️ SKIPPED
**Status**: Not needed - single-user application has no thundering herd problem.
- Jitter prevents synchronized retries across multiple clients
- TSG Builder is single-user, so no benefit from jitter

### 6.2 Improve retry status messages ✅ (Already Implemented)
**File**: `pipeline.py`  
**Status**: Already implemented in `_run_stage_with_retry()`:
- ✅ Shows wait time: `"Waiting {wait_time}s before retry..."`
- ✅ Shows specific error: `classification.user_message`
- ⏭️ Countdown skipped (optional, noted as "may be noisy" in plan)

---

## Phase 7: Documentation & Testing (Low Priority) ✅ COMPLETED

> **Completed**: January 28, 2026

### 7.1 Update copilot-instructions.md ⏭️ SKIPPED
**Status**: Existing documentation sufficient.
- Error handling code is self-documenting via `HTTP_STATUS_MESSAGES` and `API_ERROR_CODES` in `pipeline.py`
- File table already references `pipeline.py` for error classification

### 7.2 Add error handling test cases ✅ (Already Implemented)
**File**: `tests/test_error_handling.py`  
**Status**: Comprehensive test suite already exists:
- ✅ `TestPipelineError` - PipelineError class tests
- ✅ `TestGetUserFriendlyErrorWithPipelineError` - HTTP status code handling
- ✅ `TestGetUserFriendlyErrorWithAzureSDK` - Azure SDK exception tests
- ✅ `TestClassifyError` - Error classification logic
- ✅ `TestResponseFailedError` - Structured error info tests

### 7.3 Update README troubleshooting section ✅ (Already Implemented)
**File**: `README.md`  
**Status**: Troubleshooting section covers common user-facing issues:
- ✅ Authentication failures
- ✅ Connection problems
- ✅ Agent not found
- ✅ Tool/research issues

---

## Implementation Order & Dependencies

```
Phase 1 ─────┐
             │
Phase 2 ─────┼──▶ Phase 4 ──▶ Phase 7
             │
Phase 3 ─────┘

Phase 5 ─────────▶ Phase 6 ──▶ Phase 7
```

| Phase | Depends On | Estimated Effort | Risk |
|-------|------------|------------------|------|
| 1 | None | Medium | Low |
| 2 | Phase 1 (uses same patterns) | Medium | Low |
| 3 | None | Medium | Low |
| 4 | Phase 1 | Small | Low |
| 5 | None | Small | Medium (may affect timing) |
| 6 | Phase 5 | Small | Low |
| 7 | All above | Medium | None |

---

## Rollout Strategy

1. **Phase 1+2+4 together** - Core error classification improvements (biggest user impact)
2. **Phase 3** - Agent creation errors (independent, can be done in parallel)
3. **Phase 5** - Timeout tuning (test carefully, may need adjustment)
4. **Phase 6** - Retry improvements (low risk, quality of life)
5. **Phase 7** - Documentation and tests (finalization)

---

## Current State Analysis

### Strengths (Already Implemented)
- Centralized `classify_error()` function in `pipeline.py`
- Retry logic with stage-specific retry counts
- Rate limit backoff with increasing delays
- User-friendly status messages during streaming
- Frontend distinguishes retryable vs fatal errors
- Activity feed shows error progression

### Gaps Identified
| Gap | Current Behavior | Desired Behavior |
|-----|------------------|------------------|
| HTTP 401 | Generic timeout/error | "Authentication failed. Run `az login`." |
| HTTP 403 | Generic error | "Permission denied. Check role assignments." |
| HTTP 503 | May show as timeout | "Azure service temporarily unavailable." |
| Agent deleted | "Agent not found" | "Agent removed. Re-create in Setup." |
| Bing connection invalid | Tool error | "Bing connection invalid. Check Setup." |
| Model deployment removed | 404 or generic | "Model not found. Check configuration." |
| Network loss | "peer closed" | "Network connection lost." |

---

## Azure API Error Reference

### HTTP Status Codes
| Code | Type | Retryable? |
|------|------|------------|
| 400 | Bad Request | No |
| 401 | Authentication Error | No |
| 403 | Permission Denied | No |
| 404 | Not Found | No |
| 422 | Unprocessable Entity | No |
| 429 | Rate Limit | Yes (with backoff) |
| 500 | Internal Server Error | Yes |
| 502 | Bad Gateway | Yes |
| 503 | Service Unavailable | Yes |
| 504 | Gateway Timeout | Yes |

### API Error Codes (from ResponseErrorEvent)
- `server_error`
- `rate_limit_exceeded`
- `invalid_prompt`
- `vector_store_timeout`
- `invalid_image`
- `invalid_image_format`
- `image_too_large`
- `image_content_policy_violation`

---

## Notes

- All phases should maintain backward compatibility
- Test each phase in isolation before combining
- Monitor logs after deployment to catch edge cases
- Consider adding telemetry for error frequency analysis
