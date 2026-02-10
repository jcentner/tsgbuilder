"""
test_pii_check.py — Tests for PII detection in TSG Builder.

Tests the pii_check module (unit tests with mocked TextAnalyticsClient)
and the PII-related web endpoints (Flask test client).

Run with: pytest tests/test_pii_check.py -v
"""

import json
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

# Add parent directory to path so we can import from the main package
sys.path.insert(0, str(Path(__file__).parent.parent))

from pii_check import (
    check_for_pii,
    _split_into_chunks,
    PII_CATEGORIES,
    PII_CONFIDENCE_THRESHOLD,
    PII_CHUNK_SIZE,
    PII_MAX_DOCS_PER_REQUEST,
)
from web_app import app


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def reset_language_client():
    """Reset the cached Language client between tests."""
    import pii_check
    pii_check._client = None


def _make_entity(category, text, confidence, offset, length):
    """Create a mock PII entity."""
    entity = MagicMock()
    entity.category = category
    entity.text = text
    entity.confidence_score = confidence
    entity.offset = offset
    entity.length = length
    return entity


def _make_doc_result(entities, redacted_text, is_error=False, error=None):
    """Create a mock document result from the PII API."""
    doc = MagicMock()
    doc.is_error = is_error
    doc.entities = entities
    doc.redacted_text = redacted_text
    doc.error = error
    return doc


def _make_doc_error(message="Document processing failed"):
    """Create a mock document-level error result."""
    error_obj = MagicMock()
    error_obj.message = message
    doc = MagicMock()
    doc.is_error = True
    doc.error = error_obj
    return doc


# =============================================================================
# TESTS: _split_into_chunks helper
# =============================================================================

class TestSplitIntoChunks:
    """Tests for the text chunking helper."""

    @pytest.mark.unit
    def test_short_text_single_chunk(self):
        """Text under max_size should return a single chunk."""
        text = "Hello world"
        chunks = _split_into_chunks(text, max_size=5120)
        assert chunks == [text]

    @pytest.mark.unit
    def test_exact_size_single_chunk(self):
        """Text exactly at max_size should return a single chunk."""
        text = "a" * 5120
        chunks = _split_into_chunks(text, max_size=5120)
        assert chunks == [text]

    @pytest.mark.unit
    def test_splits_at_whitespace(self):
        """Chunks should split at whitespace boundaries."""
        # 10 chars each word + space, use small max_size
        text = "word1 word2 word3 word4"
        chunks = _split_into_chunks(text, max_size=12)
        # Should split at whitespace, not mid-word
        for chunk in chunks:
            # No chunk should start or end mid-word (except possibly the last)
            assert not chunk.startswith("ord")

    @pytest.mark.unit
    def test_concatenation_preserves_text(self):
        """Concatenating all chunks should reproduce the original text."""
        text = "The quick brown fox jumps over the lazy dog. " * 200
        chunks = _split_into_chunks(text, max_size=100)
        assert "".join(chunks) == text

    @pytest.mark.unit
    def test_no_empty_chunks(self):
        """No chunk should be empty."""
        text = "word " * 2000
        chunks = _split_into_chunks(text, max_size=100)
        for chunk in chunks:
            assert len(chunk) > 0

    @pytest.mark.unit
    def test_force_split_no_whitespace(self):
        """If no whitespace in window, force split at max_size."""
        text = "a" * 200  # No whitespace at all
        chunks = _split_into_chunks(text, max_size=50)
        assert "".join(chunks) == text
        assert all(len(c) <= 50 for c in chunks)


# =============================================================================
# TESTS: check_for_pii — Detection
# =============================================================================

class TestPiiDetection:
    """Tests for PII detection via mocked TextAnalyticsClient."""

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_detects_email(self, mock_get_client):
        """Should detect email addresses."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.recognize_pii_entities.return_value = [
            _make_doc_result(
                entities=[_make_entity("Email", "john@contoso.com", 0.95, 10, 16)],
                redacted_text="Contact *************** for help.",
            )
        ]

        result = check_for_pii("Contact john@contoso.com for help.")

        assert result["pii_detected"] is True
        assert len(result["findings"]) == 1
        assert result["findings"][0]["category"] == "Email"
        assert result["findings"][0]["text"] == "john@contoso.com"
        assert result["error"] is None

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_detects_phone_number(self, mock_get_client):
        """Should detect phone numbers."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.recognize_pii_entities.return_value = [
            _make_doc_result(
                entities=[_make_entity("PhoneNumber", "555-123-4567", 0.9, 5, 12)],
                redacted_text="Call ************ please.",
            )
        ]

        result = check_for_pii("Call 555-123-4567 please.")

        assert result["pii_detected"] is True
        assert result["findings"][0]["category"] == "PhoneNumber"

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_detects_ip_address(self, mock_get_client):
        """Should detect IP addresses."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.recognize_pii_entities.return_value = [
            _make_doc_result(
                entities=[_make_entity("IPAddress", "192.168.1.100", 0.92, 4, 13)],
                redacted_text="IP: ************* is blocked.",
            )
        ]

        result = check_for_pii("IP: 192.168.1.100 is blocked.")

        assert result["pii_detected"] is True
        assert result["findings"][0]["category"] == "IPAddress"

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_detects_azure_storage_key(self, mock_get_client):
        """Should detect Azure storage keys / SAS tokens / connection strings."""
        client = MagicMock()
        mock_get_client.return_value = client
        fake_key = "DefaultEndpointsProtocol=https;AccountName=test;AccountKey=abc123=="
        client.recognize_pii_entities.return_value = [
            _make_doc_result(
                entities=[
                    _make_entity("AzureStorageAccountKey", fake_key, 0.98, 0, len(fake_key)),
                ],
                redacted_text="*" * len(fake_key),
            )
        ]

        result = check_for_pii(fake_key)

        assert result["pii_detected"] is True
        assert result["findings"][0]["category"] == "AzureStorageAccountKey"

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_no_pii_in_clean_text(self, mock_get_client):
        """Clean text should return pii_detected=False."""
        client = MagicMock()
        mock_get_client.return_value = client
        clean = "The VM failed to start with error code 0x80070005."
        client.recognize_pii_entities.return_value = [
            _make_doc_result(entities=[], redacted_text=clean)
        ]

        result = check_for_pii(clean)

        assert result["pii_detected"] is False
        assert result["findings"] == []
        assert result["redacted_text"] == clean
        assert result["error"] is None

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_does_not_flag_bare_guids(self, mock_get_client):
        """Bare GUIDs should not trigger PII detection (no GUID category in filter)."""
        client = MagicMock()
        mock_get_client.return_value = client
        text = "Subscription ID: 12345678-1234-1234-1234-123456789abc"
        client.recognize_pii_entities.return_value = [
            _make_doc_result(entities=[], redacted_text=text)
        ]

        result = check_for_pii(text)

        assert result["pii_detected"] is False

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_filters_below_confidence_threshold(self, mock_get_client):
        """Entities below PII_CONFIDENCE_THRESHOLD should be excluded."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.recognize_pii_entities.return_value = [
            _make_doc_result(
                entities=[
                    _make_entity("Person", "Microsoft", 0.5, 0, 9),  # Below 0.8
                    _make_entity("Email", "test@test.com", 0.95, 20, 13),  # Above 0.8
                ],
                redacted_text="********* uses ************* for email.",
            )
        ]

        result = check_for_pii("Microsoft uses test@test.com for email.")

        assert result["pii_detected"] is True
        assert len(result["findings"]) == 1
        assert result["findings"][0]["category"] == "Email"

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_returns_redacted_text(self, mock_get_client):
        """Should return the API's redacted_text."""
        client = MagicMock()
        mock_get_client.return_value = client
        redacted = "Contact *************** for help."
        client.recognize_pii_entities.return_value = [
            _make_doc_result(
                entities=[_make_entity("Email", "john@contoso.com", 0.95, 8, 16)],
                redacted_text=redacted,
            )
        ]

        result = check_for_pii("Contact john@contoso.com for help.")

        assert result["redacted_text"] == redacted

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_passes_correct_api_parameters(self, mock_get_client):
        """Should pass disable_service_logs=True and categories_filter to API."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.recognize_pii_entities.return_value = [
            _make_doc_result(entities=[], redacted_text="test text")
        ]

        check_for_pii("test text")

        call_kwargs = client.recognize_pii_entities.call_args
        assert call_kwargs.kwargs["disable_service_logs"] is True
        assert call_kwargs.kwargs["categories_filter"] is PII_CATEGORIES
        assert call_kwargs.kwargs["language"] == "en"


# =============================================================================
# TESTS: check_for_pii — Chunking
# =============================================================================

class TestPiiChunking:
    """Tests for chunking behavior with large inputs."""

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_small_input_single_api_call(self, mock_get_client):
        """Input under 5120 chars should make a single API call."""
        client = MagicMock()
        mock_get_client.return_value = client
        text = "Short text."
        client.recognize_pii_entities.return_value = [
            _make_doc_result(entities=[], redacted_text=text)
        ]

        check_for_pii(text)

        assert client.recognize_pii_entities.call_count == 1
        # Should send single-element list
        docs = client.recognize_pii_entities.call_args[0][0]
        assert len(docs) == 1

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_large_input_splits_into_chunks(self, mock_get_client):
        """Input over 5120 chars should be split and results merged."""
        client = MagicMock()
        mock_get_client.return_value = client

        # Create text that's ~10K chars (needs 2 chunks)
        text = ("word " * 1200).strip()  # 5999 chars
        chunks = _split_into_chunks(text)
        assert len(chunks) == 2  # Sanity check

        # Mock API to return results for each chunk
        client.recognize_pii_entities.return_value = [
            _make_doc_result(
                entities=[_make_entity("Email", "a@b.com", 0.9, 10, 7)],
                redacted_text=chunks[0].replace("word", "****", 1),
            ),
            _make_doc_result(
                entities=[_make_entity("PhoneNumber", "555-1234", 0.85, 5, 8)],
                redacted_text=chunks[1].replace("word", "****", 1),
            ),
        ]

        result = check_for_pii(text)

        assert result["pii_detected"] is True
        assert len(result["findings"]) == 2

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_offsets_adjusted_for_chunks(self, mock_get_client):
        """Entity offsets should be adjusted by cumulative chunk length."""
        client = MagicMock()
        mock_get_client.return_value = client

        # Create two chunks of known size
        chunk1 = "a" * 100 + " "  # 101 chars
        chunk2 = "b" * 50
        text = chunk1 + chunk2

        # Mock chunking to produce these exact chunks
        with patch("pii_check._split_into_chunks", return_value=[chunk1, chunk2]):
            client.recognize_pii_entities.return_value = [
                _make_doc_result(
                    entities=[_make_entity("Email", "x@y.com", 0.9, 10, 7)],
                    redacted_text=chunk1,
                ),
                _make_doc_result(
                    entities=[_make_entity("Person", "Jane", 0.85, 5, 4)],
                    redacted_text=chunk2,
                ),
            ]

            result = check_for_pii(text)

        # First chunk entity: offset stays 10
        assert result["findings"][0]["offset"] == 10
        # Second chunk entity: offset 5 + chunk1 length (101) = 106
        assert result["findings"][1]["offset"] == 5 + len(chunk1)

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_redacted_text_reassembled(self, mock_get_client):
        """Redacted text should be concatenation of chunk redacted_texts."""
        client = MagicMock()
        mock_get_client.return_value = client

        chunk1 = "a" * 100 + " "
        chunk2 = "b" * 50
        text = chunk1 + chunk2

        redacted1 = "x" * 100 + " "
        redacted2 = "y" * 50

        with patch("pii_check._split_into_chunks", return_value=[chunk1, chunk2]):
            client.recognize_pii_entities.return_value = [
                _make_doc_result(entities=[], redacted_text=redacted1),
                _make_doc_result(entities=[], redacted_text=redacted2),
            ]

            result = check_for_pii(text)

        assert result["redacted_text"] == redacted1 + redacted2

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_chunks_split_at_whitespace(self, mock_get_client):
        """Chunks should not split mid-word."""
        client = MagicMock()
        mock_get_client.return_value = client

        # Words of 10 chars + space, chunk at 25 chars
        text = "abcdefghij " * 10  # 110 chars
        chunks = _split_into_chunks(text, max_size=25)

        for chunk in chunks:
            # No chunk should start with a partial word continuation
            # (unless it's the very first chunk)
            if chunk != chunks[0]:
                # Should start with a non-space character (start of word)
                # after the split point was at whitespace
                assert not chunk[0].isspace() or chunk.startswith(" ")

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_many_chunks_batched(self, mock_get_client):
        """Input requiring >5 chunks should use multiple batched API calls."""
        client = MagicMock()
        mock_get_client.return_value = client

        # Create 7 chunks worth of text
        chunks = [f"chunk{i} " * 500 for i in range(7)]
        text = "".join(chunks)

        with patch("pii_check._split_into_chunks", return_value=chunks):
            # First batch: 5 docs, second batch: 2 docs
            def side_effect(docs, **kwargs):
                return [
                    _make_doc_result(entities=[], redacted_text=d) for d in docs
                ]
            client.recognize_pii_entities.side_effect = side_effect

            result = check_for_pii(text)

        # Should have made 2 API calls (batch of 5 + batch of 2)
        assert client.recognize_pii_entities.call_count == 2
        first_call_docs = client.recognize_pii_entities.call_args_list[0][0][0]
        second_call_docs = client.recognize_pii_entities.call_args_list[1][0][0]
        assert len(first_call_docs) == 5
        assert len(second_call_docs) == 2
        assert result["error"] is None


# =============================================================================
# TESTS: check_for_pii — Error Handling
# =============================================================================

class TestPiiErrorHandling:
    """Tests for error handling in PII detection."""

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_service_request_error(self, mock_get_client, connection_error):
        """ServiceRequestError should return error + hint, pii_detected=False."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.recognize_pii_entities.side_effect = connection_error

        result = check_for_pii("test text")

        assert result["pii_detected"] is False
        assert result["findings"] == []
        assert result["error"] is not None
        assert "connect" in result["error"].lower()
        assert result["hint"] is not None

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_auth_error(self, mock_get_client, auth_error):
        """ClientAuthenticationError should return error + hint."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.recognize_pii_entities.side_effect = auth_error

        result = check_for_pii("test text")

        assert result["pii_detected"] is False
        assert result["error"] is not None
        assert "auth" in result["error"].lower()
        assert result["hint"] is not None
        assert "az login" in result["hint"].lower()

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_http_403_permission_denied(self, mock_get_client, mock_http_error):
        """HttpResponseError 403 should return error + hint."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.recognize_pii_entities.side_effect = mock_http_error(403, "Forbidden")

        result = check_for_pii("test text")

        assert result["pii_detected"] is False
        assert result["error"] is not None
        assert result["hint"] is not None

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_http_429_rate_limit(self, mock_get_client, mock_http_error):
        """HttpResponseError 429 should return error + hint."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.recognize_pii_entities.side_effect = mock_http_error(429, "Too Many Requests")

        result = check_for_pii("test text")

        assert result["pii_detected"] is False
        assert result["error"] is not None
        assert result["hint"] is not None

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_http_500_service_error(self, mock_get_client, mock_http_error):
        """HttpResponseError 500 should return error + hint."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.recognize_pii_entities.side_effect = mock_http_error(500, "Internal Server Error")

        result = check_for_pii("test text")

        assert result["pii_detected"] is False
        assert result["error"] is not None
        assert result["hint"] is not None

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_generic_exception(self, mock_get_client):
        """Generic Exception should return error + hint."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.recognize_pii_entities.side_effect = RuntimeError("Something broke")

        result = check_for_pii("test text")

        assert result["pii_detected"] is False
        assert result["error"] is not None
        assert "Something broke" in result["error"]
        assert result["hint"] is not None

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_document_level_error(self, mock_get_client):
        """Document-level is_error=True should block and return error."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.recognize_pii_entities.return_value = [_make_doc_error()]

        result = check_for_pii("test text")

        assert result["pii_detected"] is False
        assert result["error"] is not None
        assert "could not scan" in result["error"].lower()
        assert result["hint"] is not None

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_multi_chunk_partial_error_blocks(self, mock_get_client):
        """If second chunk has is_error, should block — no findings returned."""
        client = MagicMock()
        mock_get_client.return_value = client

        chunk1 = "a" * 100 + " "
        chunk2 = "b" * 50
        text = chunk1 + chunk2

        with patch("pii_check._split_into_chunks", return_value=[chunk1, chunk2]):
            client.recognize_pii_entities.return_value = [
                _make_doc_result(
                    entities=[_make_entity("Email", "x@y.com", 0.9, 10, 7)],
                    redacted_text=chunk1,
                ),
                _make_doc_error("Processing failed for chunk 2"),
            ]

            result = check_for_pii(text)

        # Should block — no partial results
        assert result["pii_detected"] is False
        assert result["findings"] == []
        assert result["error"] is not None
        assert result["hint"] is not None

    @pytest.mark.unit
    @patch("pii_check.get_language_client")
    def test_client_init_error(self, mock_get_client):
        """Error during client initialization should return error + hint."""
        from azure.core.exceptions import ClientAuthenticationError
        mock_get_client.side_effect = ClientAuthenticationError("No credentials")

        result = check_for_pii("test text")

        assert result["pii_detected"] is False
        assert result["error"] is not None
        assert result["hint"] is not None


# =============================================================================
# TESTS: Web Endpoints — /api/pii-check
# =============================================================================

class TestPiiCheckEndpoint:
    """Tests for POST /api/pii-check endpoint."""

    @pytest.mark.unit
    @patch("web_app.check_for_pii")
    def test_clean_text_returns_no_pii(self, mock_check, client):
        """Clean text should return pii_detected: false."""
        mock_check.return_value = {
            "pii_detected": False,
            "findings": [],
            "redacted_text": "clean text here",
            "error": None,
            "hint": None,
        }

        resp = client.post("/api/pii-check",
                           data=json.dumps({"notes": "clean text here"}),
                           content_type="application/json")

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["pii_detected"] is False
        assert data["findings"] == []

    @pytest.mark.unit
    @patch("web_app.check_for_pii")
    def test_pii_text_returns_findings(self, mock_check, client):
        """Text with PII should return pii_detected: true + findings."""
        mock_check.return_value = {
            "pii_detected": True,
            "findings": [{"category": "Email", "text": "john@test.com",
                          "confidence": 0.95, "offset": 0, "length": 13}],
            "redacted_text": "*************",
            "error": None,
            "hint": None,
        }

        resp = client.post("/api/pii-check",
                           data=json.dumps({"notes": "john@test.com"}),
                           content_type="application/json")

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["pii_detected"] is True
        assert len(data["findings"]) == 1
        assert data["findings"][0]["category"] == "Email"

    @pytest.mark.unit
    def test_empty_notes_returns_400(self, client):
        """Empty notes should return 400."""
        resp = client.post("/api/pii-check",
                           data=json.dumps({"notes": ""}),
                           content_type="application/json")
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "error" in data

    @pytest.mark.unit
    def test_missing_notes_returns_400(self, client):
        """Missing notes field should return 400."""
        resp = client.post("/api/pii-check",
                           data=json.dumps({}),
                           content_type="application/json")
        assert resp.status_code == 400

    @pytest.mark.unit
    @patch("web_app.check_for_pii")
    def test_language_api_error_returns_500(self, mock_check, client):
        """Language service error should return 500 with error + hint."""
        mock_check.return_value = {
            "pii_detected": False,
            "findings": [],
            "redacted_text": "test",
            "error": "PII check failed: authentication error",
            "hint": "Run 'az login' to refresh your credentials.",
        }

        resp = client.post("/api/pii-check",
                           data=json.dumps({"notes": "test"}),
                           content_type="application/json")

        assert resp.status_code == 500
        data = json.loads(resp.data)
        assert "error" in data
        assert "hint" in data


# =============================================================================
# TESTS: Web Endpoints — PII gates on generate/answer
# =============================================================================

class TestGenerateStreamPiiGate:
    """Tests for PII gate on POST /api/generate/stream."""

    @pytest.mark.unit
    @patch("web_app.check_for_pii")
    def test_pii_in_notes_returns_400(self, mock_check, client):
        """PII detected in notes should return 400 with findings."""
        mock_check.return_value = {
            "pii_detected": True,
            "findings": [{"category": "Email", "text": "a@b.com",
                          "confidence": 0.9, "offset": 0, "length": 7}],
            "redacted_text": "*******",
            "error": None,
            "hint": None,
        }

        resp = client.post("/api/generate/stream",
                           data=json.dumps({"notes": "a@b.com"}),
                           content_type="application/json")

        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "PII detected" in data["error"]
        assert len(data["findings"]) == 1

    @pytest.mark.unit
    @patch("web_app.check_for_pii")
    def test_pii_check_error_returns_500(self, mock_check, client):
        """PII check error should return 500, NOT proceed with generation."""
        mock_check.return_value = {
            "pii_detected": False,
            "findings": [],
            "redacted_text": "test notes",
            "error": "PII check failed: could not connect",
            "hint": "Check your network connection.",
        }

        resp = client.post("/api/generate/stream",
                           data=json.dumps({"notes": "test notes"}),
                           content_type="application/json")

        assert resp.status_code == 500
        data = json.loads(resp.data)
        assert "error" in data
        assert "hint" in data


class TestAnswerStreamPiiGate:
    """Tests for PII gate on POST /api/answer/stream."""

    @pytest.mark.unit
    @patch("web_app.check_for_pii")
    def test_pii_in_answers_returns_400(self, mock_check, client):
        """PII detected in answers should return 400 with findings."""
        # Need a valid session for this endpoint
        from web_app import sessions
        sessions["test-thread-00000000-0000-0000-0000-000000000000"] = {"notes": "original notes"}

        mock_check.return_value = {
            "pii_detected": True,
            "findings": [{"category": "PhoneNumber", "text": "555-1234",
                          "confidence": 0.88, "offset": 20, "length": 8}],
            "redacted_text": "The customer phone ********",
            "error": None,
            "hint": None,
        }

        resp = client.post("/api/answer/stream",
                           data=json.dumps({
                               "thread_id": "test-thread-00000000-0000-0000-0000-000000000000",
                               "answers": "The customer phone 555-1234",
                           }),
                           content_type="application/json")

        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "PII detected" in data["error"]
        assert len(data["findings"]) == 1

        # Cleanup
        sessions.pop("test-thread-00000000-0000-0000-0000-000000000000", None)

    @pytest.mark.unit
    @patch("web_app.check_for_pii")
    def test_pii_check_error_returns_500(self, mock_check, client):
        """PII check error on answers should return 500, NOT proceed."""
        from web_app import sessions
        sessions["test-thread-00000000-0000-0000-0000-000000000000"] = {"notes": "original notes"}

        mock_check.return_value = {
            "pii_detected": False,
            "findings": [],
            "redacted_text": "some answers",
            "error": "PII check failed: service unavailable",
            "hint": "Try again in a few minutes.",
        }

        resp = client.post("/api/answer/stream",
                           data=json.dumps({
                               "thread_id": "test-thread-00000000-0000-0000-0000-000000000000",
                               "answers": "some answers",
                           }),
                           content_type="application/json")

        assert resp.status_code == 500
        data = json.loads(resp.data)
        assert "error" in data
        assert "hint" in data

        # Cleanup
        sessions.pop("test-thread-00000000-0000-0000-0000-000000000000", None)
