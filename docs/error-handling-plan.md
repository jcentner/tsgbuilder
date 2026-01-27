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

## Phase 2: Streaming Event Error Parsing (Medium Priority)

**Goal**: Extract structured error information from Azure API `ResponseErrorEvent` and `ResponseFailedEvent`.

### 2.1 Update `process_pipeline_v2_stream()` for `response.failed` events
**File**: `pipeline.py`  
**Location**: Lines 535-542  
**Changes**:
- Parse `event.response.error` for structured fields:
  - `error.code` (e.g., `server_error`, `rate_limit_exceeded`)
  - `error.message`
  - `error.param` (if available)
- Pass structured info to `_send_classified_error()` for better classification

### 2.2 Update `_send_classified_error()` for structured errors
**File**: `pipeline.py`  
**Location**: Lines 260-307  
**Changes**:
- Accept optional `error_code` parameter
- Map API error codes to user-friendly messages:

| API Error Code | User Message |
|----------------|--------------|
| `rate_limit_exceeded` | Rate limit message |
| `server_error` | Service error message |
| `invalid_prompt` | "Input could not be processed. Try simplifying." |
| `vector_store_timeout` | "Search timed out. Retrying..." |

### 2.3 Handle `error` event type with structured data
**File**: `pipeline.py`  
**Location**: Lines 541-543  
**Changes**:
- Parse `event.code`, `event.message`, `event.param` when available
- Include error code in the classified error for better debugging

---

## Phase 3: Agent Creation Error Handling (Medium Priority)

**Goal**: Provide specific, actionable error messages when agent creation fails.

### 3.1 Create helper function for Azure SDK exceptions
**File**: `web_app.py`  
**Changes**:
- Add `_classify_azure_sdk_error(error: Exception) -> tuple[str, int]` function
- Return (user_message, http_status_code)
- Handle specific Azure exception types:
  - `HttpResponseError` → parse status code and message
  - `ClientAuthenticationError` → auth guidance
  - `ServiceRequestError` → connectivity guidance
  - `ResourceNotFoundError` → resource missing guidance

### 3.2 Update `api_create_agent()` endpoint
**File**: `web_app.py`  
**Location**: Lines 570-574  
**Changes**:
- Catch specific exception types before generic `Exception`
- Use `_classify_azure_sdk_error()` for user-friendly messages
- Include troubleshooting hints in error response:
  ```json
  {
    "success": false,
    "error": "User-friendly message",
    "error_type": "auth_error",
    "hint": "Run 'az login' to refresh credentials"
  }
  ```

### 3.3 Update frontend to display hints
**File**: `templates/index.html`  
**Changes**:
- Parse `hint` field from error responses
- Display hints in a distinct style below the error message

---

## Phase 4: Web App Error Handler Enhancement (Medium Priority)

**Goal**: Improve `_get_user_friendly_error()` to handle Azure-specific errors.

### 4.1 Refactor `_get_user_friendly_error()`
**File**: `web_app.py`  
**Location**: Lines 55-78  
**Changes**:
- Import and reuse `classify_error()` patterns from pipeline
- Add Azure-specific error detection:
  - Auth errors → "Authentication failed. Run `az login`."
  - Connection errors → "Cannot connect to Azure. Check network and endpoint."
  - Agent not found → "Agent was removed. Re-create in Setup."
- Preserve stage context when available

### 4.2 Add error context preservation
**File**: `pipeline.py`  
**Changes**:
- When raising `RuntimeError` in `_run_stage()`, include structured context
- Consider creating a custom `PipelineError` exception class that carries:
  - `stage: PipelineStage`
  - `original_error: Exception`
  - `http_status: int | None`
  - `error_code: str | None`

---

## Phase 5: Timeout Tuning (Medium Priority)

**Goal**: Optimize timeout values for better responsiveness without false positives.

### 5.1 Reduce tool call timeout
**File**: `pipeline.py`  
**Location**: Line 148  
**Changes**:
- Change `TOOL_CALL_TIMEOUT = 120` to `TOOL_CALL_TIMEOUT = 90`
- Add comment explaining rationale (Bing typically <30s, MCP <60s)

### 5.2 Add secondary stream stall detection
**File**: `pipeline.py`  
**Location**: `_run_stage()` method  
**Changes**:
- Track time since last event received
- If no events for 90s (outside of tool calls), log warning
- If no events for 180s, consider it a stall and raise timeout error
- This catches scenarios where the stream itself hangs (no tool active)

### 5.3 Make timeouts configurable
**File**: `pipeline.py`  
**Changes**:
- Read timeout values from environment variables with defaults:
  ```python
  TOOL_CALL_TIMEOUT = int(os.getenv("TSG_TOOL_TIMEOUT", "90"))
  STREAM_STALL_TIMEOUT = int(os.getenv("TSG_STREAM_TIMEOUT", "180"))
  ```
- Document in README.md

---

## Phase 6: Retry Logic Improvements (Low Priority)

**Goal**: Add jitter and improve retry messaging.

### 6.1 Add jitter to backoff
**File**: `pipeline.py`  
**Location**: `_run_stage_with_retry()` method  
**Changes**:
- Add random jitter (0-10%) to backoff delays:
  ```python
  import random
  jitter = random.uniform(0, 0.1) * wait_time
  wait_time += jitter
  ```

### 6.2 Improve retry status messages
**File**: `pipeline.py`  
**Changes**:
- Include estimated wait time in status: "Waiting 35s before retry..."
- Show which specific error triggered retry
- Count down during wait (optional, may be noisy)

---

## Phase 7: Documentation & Testing (Low Priority)

### 7.1 Update copilot-instructions.md
**File**: `.github/copilot-instructions.md`  
**Changes**:
- Document error handling philosophy
- List all error types and expected user messages
- Document timeout configuration options

### 7.2 Add error handling test cases
**File**: New file `tests/test_error_handling.py`  
**Changes**:
- Unit tests for `classify_error()` with various error strings
- Test HTTP status code detection
- Test Azure SDK exception handling
- Mock streaming events with error responses

### 7.3 Update README troubleshooting section
**File**: `README.md`  
**Changes**:
- Add section on common Azure errors and what they mean
- Include guidance for each error type
- Document timeout configuration

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
