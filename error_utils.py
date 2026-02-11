"""
error_utils.py — Shared Azure SDK error classification utilities.

Provides user-friendly error messages and hints for Azure SDK exceptions.
Used by web_app.py (agent creation) and pii_check.py (Language API errors).
"""

from __future__ import annotations

from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ResourceNotFoundError,
    ServiceRequestError,
)

from pipeline import (
    HINT_AUTH,
    HINT_CONNECTION,
    HINT_NOT_FOUND,
    HINT_SERVICE_ERROR,
    HTTP_STATUS_MESSAGES,
)


def classify_azure_sdk_error(error: Exception) -> tuple[str, str | None, int]:
    """Classify Azure SDK exceptions into user-friendly messages with hints.

    Uses shared constants from pipeline.py for consistent messaging across
    the codebase. Returns (user_message, hint, http_status_code).
    """
    # ClientAuthenticationError - credentials/auth issues
    if isinstance(error, ClientAuthenticationError):
        return ("Azure authentication failed.", HINT_AUTH, 401)

    # ServiceRequestError - network/connectivity issues
    if isinstance(error, ServiceRequestError):
        return ("Could not connect to Azure service.", HINT_CONNECTION, 0)

    # ResourceNotFoundError - resource doesn't exist
    if isinstance(error, ResourceNotFoundError):
        return ("Azure resource not found.", HINT_NOT_FOUND, 404)

    # HttpResponseError - general HTTP errors with status codes
    if isinstance(error, HttpResponseError):
        status_code = getattr(error, "status_code", 500) or 500

        # Use shared HTTP_STATUS_MESSAGES for consistent messaging
        if status_code in HTTP_STATUS_MESSAGES:
            msg, _, hint = HTTP_STATUS_MESSAGES[status_code]
            return (f"{msg} ({status_code}).", hint, status_code)
        elif status_code >= 500:
            reason = getattr(error, "reason", "") or ""
            return (
                f"Azure service error ({status_code} {reason}).",
                HINT_SERVICE_ERROR,
                status_code,
            )
        else:
            # Other 4xx errors - use error message
            error_msg = str(error)
            if hasattr(error, "message") and error.message:
                error_msg = error.message
            return (f"Request failed ({status_code}): {error_msg[:200]}", None, status_code)

    # Generic fallback for unknown exceptions
    return (f"Unexpected error: {str(error)[:200]}", None, 500)
