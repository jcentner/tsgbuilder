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

from error_messages import HINT_AUTH, HINT_CONNECTION, HINT_NOT_FOUND, HINT_SERVICE_ERROR, HTTP_STATUS_MESSAGES
from model_policy import SUPPORTED_MODELS_DISPLAY, evaluate_model_policy


# =============================================================================
# Model deployment classification
# =============================================================================

class ModelTier(Enum):
    """Classification tier for Azure AI model deployments."""
    SUPPORTED = "supported"
    BLOCKED = "blocked"


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

    policy = evaluate_model_policy(underlying_model)

    if policy.blocked_variant:
        return ModelClassification(
            tier=ModelTier.BLOCKED,
            message=(
                f"Deployment '{deployment_name}' uses {underlying_model}. "
                f"The {policy.blocked_variant} variant is not validated for TSG Builder. "
                f"Use one of these non-chat base models: {SUPPORTED_MODELS_DISPLAY}."
            ),
            critical=True,
        )

    if policy.supported:
        return ModelClassification(
            tier=ModelTier.SUPPORTED,
            message=f"Found deployment: {deployment_name} ({underlying_model})",
            critical=False,
        )

    # Everything else — unsupported
    return ModelClassification(
        tier=ModelTier.BLOCKED,
        message=(
            f"Deployment '{deployment_name}' uses {underlying_model}. "
            f"Supported models are non-chat deployments of: {SUPPORTED_MODELS_DISPLAY}. "
            f"Other models are not validated for this app's Agent Service tools, "
            f"image input, and review output requirements."
        ),
        critical=True,
    )


def classify_azure_sdk_error(error: Exception) -> tuple[str, str | None, int]:
    """Classify Azure SDK exceptions into user-friendly messages with hints.

    Uses shared constants from error_messages.py for consistent messaging across
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
