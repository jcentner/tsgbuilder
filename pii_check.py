"""
pii_check.py — PII detection via Azure AI Language API.

Pre-flight check to prevent customer-identifiable information from being sent
to external Foundry Agents and Bing search. Uses a centralized, author-owned
Azure Language resource with Entra ID authentication.

Fail-closed: if the Language API is unreachable or errors, generation is blocked.
"""

from __future__ import annotations

from azure.ai.textanalytics import TextAnalyticsClient, PiiEntityCategory
from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ServiceRequestError,
)
from azure.identity import DefaultAzureCredential

from error_utils import classify_azure_sdk_error
from version import LANGUAGE_ENDPOINT


# =============================================================================
# CONSTANTS
# =============================================================================

# PII categories to detect — intentionally curated to reduce false positives.
# See docs/pii-detection-plan.md for rationale on each category.
PII_CATEGORIES: list[PiiEntityCategory] = [
    PiiEntityCategory.EMAIL,
    PiiEntityCategory.PHONE_NUMBER,
    PiiEntityCategory.IP_ADDRESS,
    PiiEntityCategory.PERSON,
    PiiEntityCategory.AZURE_DOCUMENT_DB_AUTH_KEY,
    PiiEntityCategory.AZURE_STORAGE_ACCOUNT_KEY,
    PiiEntityCategory.AZURE_SAS,
    PiiEntityCategory.AZURE_IO_T_CONNECTION_STRING,
    PiiEntityCategory.SQL_SERVER_CONNECTION_STRING,
    PiiEntityCategory.CREDIT_CARD_NUMBER,
    PiiEntityCategory.US_SOCIAL_SECURITY_NUMBER,
]

# Minimum confidence score to include a finding (0.0–1.0).
PII_CONFIDENCE_THRESHOLD: float = 0.8

# Max characters per document in the synchronous PII API.
PII_CHUNK_SIZE: int = 5120

# Max documents per synchronous API call.
PII_MAX_DOCS_PER_REQUEST: int = 5


# =============================================================================
# CLIENT
# =============================================================================

_client: TextAnalyticsClient | None = None


def get_language_client() -> TextAnalyticsClient:
    """Create or return a cached TextAnalyticsClient.

    Uses DefaultAzureCredential (Entra ID) and the centralized Language
    endpoint from version.py.
    """
    global _client
    if _client is None:
        _client = TextAnalyticsClient(
            endpoint=LANGUAGE_ENDPOINT,
            credential=DefaultAzureCredential(),
        )
    return _client


# =============================================================================
# CHUNKING HELPERS
# =============================================================================


def _split_into_chunks(text: str, max_size: int = PII_CHUNK_SIZE) -> list[str]:
    """Split text into chunks of ≤ max_size characters, breaking at whitespace.

    Returns a list of non-empty strings whose concatenation equals the original
    text (preserving all whitespace, including the split-point characters).
    """
    if len(text) <= max_size:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = start + max_size

        if end >= len(text):
            # Last chunk — take the rest
            chunks.append(text[start:])
            break

        # Walk backwards from 'end' to find a whitespace boundary
        split_at = end
        while split_at > start and not text[split_at].isspace():
            split_at -= 1

        if split_at == start:
            # No whitespace found in the window — force split at max_size
            split_at = end

        chunks.append(text[start:split_at])
        start = split_at

    return chunks


# =============================================================================
# RESULT HELPERS
# =============================================================================


def _empty_result(
    text: str,
    *,
    error: str | None = None,
    hint: str | None = None,
) -> dict:
    """Return the standard result dict shape."""
    return {
        "pii_detected": False,
        "findings": [],
        "redacted_text": text,
        "error": error,
        "hint": hint,
    }


def _error_result(text: str, error_msg: str, hint_msg: str) -> dict:
    """Return a result with error fields set (blocks generation)."""
    return _empty_result(text, error=error_msg, hint=hint_msg)


# =============================================================================
# MAIN FUNCTION
# =============================================================================


def check_for_pii(text: str) -> dict:
    """Scan text for personally identifiable information.

    Returns a dict with the following shape (always the same keys)::

        {
            "pii_detected": bool,
            "findings": [{"category": str, "text": str, "confidence": float,
                          "offset": int, "length": int}, ...],
            "redacted_text": str,
            "error": str | None,
            "hint": str | None,
        }

    On error, ``error`` and ``hint`` are set, ``pii_detected`` is False,
    and ``findings`` is empty. The caller must check ``error`` and block
    generation if it is set.
    """
    # ── 1. Get client ────────────────────────────────────────────────────
    try:
        client = get_language_client()
    except Exception as exc:
        print(f"⚠️ PII check failed (client init): {exc}")
        user_msg, hint, _ = classify_azure_sdk_error(exc)
        return _error_result(
            text,
            f"PII check failed: {user_msg}",
            hint or "Check your Azure credentials and network connection.",
        )

    # ── 2. Chunk the input ───────────────────────────────────────────────
    chunks = _split_into_chunks(text)

    # ── 3. Call the API in batches ───────────────────────────────────────
    all_findings: list[dict] = []
    redacted_parts: list[str] = []

    try:
        for batch_start in range(0, len(chunks), PII_MAX_DOCS_PER_REQUEST):
            batch = chunks[batch_start : batch_start + PII_MAX_DOCS_PER_REQUEST]

            results = client.recognize_pii_entities(
                batch,
                language="en",
                categories_filter=PII_CATEGORIES,
                disable_service_logs=True,
            )

            for i, doc in enumerate(results):
                # Fail-closed on document-level errors
                if doc.is_error:
                    error_msg = (
                        doc.error.message
                        if hasattr(doc, "error") and hasattr(doc.error, "message")
                        else "Unknown document error"
                    )
                    print(
                        f"⚠️ PII check failed (document error): {error_msg}"
                    )
                    return _error_result(
                        text,
                        "PII check failed: could not scan all content",
                        "The Language service could not process part of the input.",
                    )

                # Collect redacted text
                redacted_parts.append(doc.redacted_text)

                # Collect findings, adjusting offsets for chunk position
                chunk_index = batch_start + i
                chunk_offset = sum(len(chunks[j]) for j in range(chunk_index))

                for entity in doc.entities:
                    if entity.confidence_score >= PII_CONFIDENCE_THRESHOLD:
                        all_findings.append(
                            {
                                "category": entity.category,
                                "text": entity.text,
                                "confidence": entity.confidence_score,
                                "offset": entity.offset + chunk_offset,
                                "length": entity.length,
                            }
                        )

    except (
        ClientAuthenticationError,
        ServiceRequestError,
        HttpResponseError,
    ) as exc:
        print(f"⚠️ PII check failed ({type(exc).__name__}): {exc}")
        user_msg, hint, _ = classify_azure_sdk_error(exc)
        return _error_result(
            text,
            f"PII check failed: {user_msg}",
            hint or "Check your Azure credentials and network connection.",
        )
    except Exception as exc:
        print(f"⚠️ PII check failed ({type(exc).__name__}): {exc}")
        return _error_result(
            text,
            f"PII check failed: {str(exc)[:200]}",
            "An unexpected error occurred during PII scanning.",
        )

    # ── 4. Assemble result ───────────────────────────────────────────────
    full_redacted = "".join(redacted_parts)

    return {
        "pii_detected": len(all_findings) > 0,
        "findings": all_findings,
        "redacted_text": full_redacted,
        "error": None,
        "hint": None,
    }
