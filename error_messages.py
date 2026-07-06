"""Shared user-facing Azure error messages and hints."""

from __future__ import annotations


HINT_AUTH = "Run 'az login' to refresh your credentials."
HINT_TENANT_MISMATCH = "Run 'az login' and select the correct subscription, or use 'az account set -s <subscription>'."
HINT_PERMISSION = "Check your Azure role assignments on the AI project."
HINT_NOT_FOUND = "Try re-creating agents in Setup."
HINT_RATE_LIMIT = "Wait a few minutes and try again."
HINT_TIMEOUT = "Try again with shorter input, or check your network connection."
HINT_CONNECTION = "Check your network connection and verify PROJECT_ENDPOINT is correct."
HINT_SERVICE_ERROR = "This is usually temporary. Try again in a moment."


HTTP_STATUS_MESSAGES: dict[int, tuple[str, bool, str | None]] = {
    401: ("Azure authentication failed.", False, HINT_AUTH),
    403: ("Permission denied.", False, HINT_PERMISSION),
    404: ("Resource not found.", False, HINT_NOT_FOUND),
    429: ("Rate limit exceeded.", True, HINT_RATE_LIMIT),
    500: ("Azure service error.", True, HINT_SERVICE_ERROR),
    502: ("Azure gateway error.", True, HINT_SERVICE_ERROR),
    503: ("Azure AI service temporarily unavailable.", True, HINT_RATE_LIMIT),
    504: ("Azure gateway timed out.", True, HINT_TIMEOUT),
}
