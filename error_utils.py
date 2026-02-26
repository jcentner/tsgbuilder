"""
error_utils.py — Shared Azure SDK error classification utilities.

Provides user-friendly error messages and hints for Azure SDK exceptions.
Used by web_app.py (agent creation) and pii_check.py (Language API errors).

Also provides model deployment classification (classify_model) used by
web_app.py (/api/validate, /api/create-agent) and validate_setup.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

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


# =============================================================================
# Model deployment classification
# =============================================================================

class ModelTier(Enum):
    """Classification tier for Azure AI model deployments."""
    SUPPORTED = "supported"   # gpt-5.2 — fully compatible
    WARN = "warn"             # gpt-5.1 — may work, prompts optimized for 5.2
    BLOCKED = "blocked"       # -chat variants, older models — unsupported


@dataclass
class ModelClassification:
    """Result of classifying a model deployment's underlying model."""
    tier: ModelTier
    message: str
    critical: bool  # True only for BLOCKED tier


def classify_model(underlying_model: str | None, deployment_name: str = "") -> ModelClassification:
    """Classify a model deployment's underlying model into support tiers.

    Args:
        underlying_model: The model_name from the deployment object (e.g. "gpt-5.2").
                          None or empty if the model could not be determined.
        deployment_name: The deployment name, used for display in messages.

    Returns:
        ModelClassification with tier, user-facing message, and critical flag.
    """
    if not underlying_model:
        return ModelClassification(
            tier=ModelTier.SUPPORTED,
            message=f"Found deployment: {deployment_name} (could not determine underlying model)",
            critical=False,
        )

    model_lower = underlying_model.lower()

    # -chat variants lack image input and full Agent Service tool support — block
    if model_lower.endswith("-chat"):
        return ModelClassification(
            tier=ModelTier.BLOCKED,
            message=(
                f"Deployment '{deployment_name}' uses {underlying_model}. "
                f"-chat models lack image input and full Agent Service tool support. "
                f"Use a gpt-5.2 (non-chat) deployment."
            ),
            critical=True,
        )

    # gpt-5.2 — fully compatible
    if "gpt-5.2" in model_lower:
        return ModelClassification(
            tier=ModelTier.SUPPORTED,
            message=f"Found deployment: {deployment_name} ({underlying_model})",
            critical=False,
        )

    # gpt-5.1 — may work but prompts are optimized for gpt-5.2
    if "gpt-5.1" in model_lower:
        return ModelClassification(
            tier=ModelTier.WARN,
            message=(
                f"Deployment '{deployment_name}' uses {underlying_model}. "
                f"Prompts are optimized for gpt-5.2; gpt-5.1 may work but is not fully tested."
            ),
            critical=False,
        )

    # Everything else — unsupported
    return ModelClassification(
        tier=ModelTier.BLOCKED,
        message=(
            f"Deployment '{deployment_name}' uses {underlying_model}. "
            f"Only gpt-5.2 is supported. Other models lack required Agent Service "
            f"tool support and image input capabilities."
        ),
        critical=True,
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
