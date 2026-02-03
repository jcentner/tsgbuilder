"""
test_error_handling.py — Tests for error handling in TSG Builder.

Tests the Phase 4 error handling enhancements:
- PipelineError exception class
- _get_user_friendly_error() function
- classify_error() with various error types

Run with: pytest tests/test_error_handling.py -v
"""

import pytest
from pipeline import (
    PipelineError,
    PipelineStage,
    classify_error,
    ResponseFailedError,
)
from web_app import _get_user_friendly_error


# =============================================================================
# TESTS: PipelineError Class
# =============================================================================

class TestPipelineError:
    """Tests for the PipelineError exception class."""
    
    @pytest.mark.unit
    def test_creation_with_all_fields(self, pipeline_error_factory):
        """PipelineError should carry all structured context."""
        original = ValueError("Something went wrong")
        pe = PipelineError(
            stage=PipelineStage.RESEARCH,
            original_error=original,
            http_status=401,
            error_code="unauthorized",
        )
        
        assert pe.stage == PipelineStage.RESEARCH
        assert pe.original_error is original
        assert pe.http_status == 401
        assert pe.error_code == "unauthorized"
    
    @pytest.mark.unit
    def test_string_representation_includes_stage(self):
        """PipelineError string should include stage name."""
        pe = PipelineError(
            stage=PipelineStage.WRITE,
            original_error=ValueError("test"),
        )
        error_str = str(pe).lower()
        assert "write" in error_str
    
    @pytest.mark.unit
    def test_optional_fields_default_to_none(self):
        """http_status and error_code should default to None."""
        pe = PipelineError(
            stage=PipelineStage.REVIEW,
            original_error=ValueError("test"),
        )
        assert pe.http_status is None
        assert pe.error_code is None


# =============================================================================
# TESTS: _get_user_friendly_error with PipelineError
# =============================================================================

class TestGetUserFriendlyErrorWithPipelineError:
    """Tests for _get_user_friendly_error with PipelineError input."""
    
    @pytest.mark.unit
    def test_401_error_includes_auth_hint(self, error_helper):
        """401 errors should include az login hint."""
        pe = PipelineError(
            stage=PipelineStage.RESEARCH,
            original_error=ValueError("401 unauthorized"),
            http_status=401,
        )
        msg, hint = _get_user_friendly_error(pe)
        
        error_helper.assert_user_friendly_error(
            msg, hint,
            expected_msg_contains=["auth"],
            expected_hint_contains=["az login"],
        )
    
    @pytest.mark.unit
    def test_404_error_includes_setup_hint(self, error_helper):
        """404 errors should include re-create in Setup hint."""
        pe = PipelineError(
            stage=PipelineStage.WRITE,
            original_error=ValueError("404 not found"),
            http_status=404,
        )
        msg, hint = _get_user_friendly_error(pe)
        
        error_helper.assert_user_friendly_error(
            msg, hint,
            expected_msg_contains=["not found"],
            expected_hint_contains=["setup"],
        )
    
    @pytest.mark.unit
    def test_retrying_message_replaced_with_try_again(self):
        """Messages with 'Retrying...' should be replaced with 'Please try again.'"""
        pe = PipelineError(
            stage=PipelineStage.RESEARCH,
            original_error=ValueError("Some error"),
        )
        msg, _ = _get_user_friendly_error(pe)
        
        assert "Retrying" not in msg
        assert "Will retry" not in msg


# =============================================================================
# TESTS: _get_user_friendly_error with Azure SDK Errors
# =============================================================================

class TestGetUserFriendlyErrorWithAzureSDK:
    """Tests for _get_user_friendly_error with Azure SDK exceptions."""
    
    @pytest.mark.unit
    def test_client_authentication_error(self, auth_error, error_helper):
        """ClientAuthenticationError should return auth message with hint."""
        msg, hint = _get_user_friendly_error(auth_error)
        
        error_helper.assert_user_friendly_error(
            msg, hint,
            expected_msg_contains=["auth"],
            expected_hint_contains=["az login"],
        )
    
    @pytest.mark.unit
    def test_service_request_error(self, connection_error, error_helper):
        """ServiceRequestError should return connection message with hint."""
        msg, hint = _get_user_friendly_error(connection_error)
        
        error_helper.assert_user_friendly_error(
            msg, hint,
            expected_msg_contains=["connect"],
            expected_hint_contains=["network", "endpoint"],
        )
    
    @pytest.mark.unit
    def test_resource_not_found_error(self, not_found_error, error_helper):
        """ResourceNotFoundError should return not found message with hint."""
        msg, hint = _get_user_friendly_error(not_found_error)
        
        error_helper.assert_user_friendly_error(
            msg, hint,
            expected_msg_contains=["not found"],
        )
    
    @pytest.mark.unit
    @pytest.mark.parametrize("status_code,expected_msg,expected_hint", [
        (401, "401", "az login"),
        (403, "403", "role"),
        (429, "429", "wait"),
        (500, "500", "temporary"),
    ])
    def test_http_response_error_status_codes(
        self, mock_http_error, error_helper, status_code, expected_msg, expected_hint
    ):
        """HttpResponseError should map status codes to appropriate messages."""
        err = mock_http_error(status_code)
        msg, hint = _get_user_friendly_error(err)
        
        error_helper.assert_user_friendly_error(
            msg, hint,
            expected_msg_contains=[expected_msg],
            expected_hint_contains=[expected_hint],
        )


# =============================================================================
# TESTS: _get_user_friendly_error Fallback Path
# =============================================================================

class TestGetUserFriendlyErrorFallback:
    """Tests for _get_user_friendly_error fallback behavior."""
    
    @pytest.mark.unit
    def test_generic_error_returns_message(self):
        """Generic errors should still return a user-friendly message."""
        err = ValueError("Something unexpected happened")
        msg, hint = _get_user_friendly_error(err)
        
        assert msg is not None
        assert len(msg) > 0
    
    @pytest.mark.unit
    def test_timeout_error_includes_hint(self, error_helper):
        """Timeout errors should include a hint about shorter input."""
        err = TimeoutError("Connection timed out")
        msg, hint = _get_user_friendly_error(err)
        
        # Hint should be provided for timeout errors
        assert hint is not None
    
    @pytest.mark.unit
    @pytest.mark.parametrize("stage_keyword,expected_stage", [
        ("research", "Research"),
        ("write", "Write"),
        ("review", "Review"),
    ])
    def test_stage_detection_from_error_message(self, stage_keyword, expected_stage):
        """Stage should be detected from error message content."""
        err = ValueError(f"Error in {stage_keyword} stage: something failed")
        msg, _ = _get_user_friendly_error(err)
        
        # The message should reference the detected stage
        assert expected_stage in msg or stage_keyword in msg.lower()


# =============================================================================
# TESTS: classify_error Function
# =============================================================================

class TestClassifyError:
    """Tests for the classify_error function."""
    
    @pytest.mark.unit
    def test_pipeline_error_unwrapping(self, error_helper):
        """classify_error should unwrap PipelineError and use pre-computed info."""
        inner = ResponseFailedError(
            stage="research",
            error_msg="Rate limit exceeded",
            error_code="rate_limit_exceeded",
            http_status_code=429,
        )
        pe = PipelineError(
            stage=PipelineStage.RESEARCH,
            original_error=inner,
            http_status=429,
            error_code="rate_limit_exceeded",
        )
        
        classification = classify_error(pe, PipelineStage.RESEARCH)
        
        error_helper.assert_classification(
            classification,
            http_status_code=429,
            error_code="rate_limit_exceeded",
        )
    
    @pytest.mark.unit
    @pytest.mark.parametrize("error_msg,expected_code", [
        ("status code: 401", 401),
        ("HTTP 403 Forbidden", 403),
        ("returned 500 error", 500),
        ("Error 429: Too many requests", 429),
        ("Got a 502 bad gateway", 502),
    ])
    def test_http_status_detection_from_string(self, error_msg, expected_code, error_helper):
        """classify_error should detect HTTP status codes from error strings."""
        err = ValueError(error_msg)
        classification = classify_error(err, PipelineStage.RESEARCH)
        
        error_helper.assert_classification(
            classification,
            http_status_code=expected_code,
        )
    
    @pytest.mark.unit
    def test_rate_limit_detection(self, error_helper):
        """Rate limit errors should be marked as retryable."""
        err = ValueError("429 rate limit exceeded")
        classification = classify_error(err, PipelineStage.RESEARCH)
        
        error_helper.assert_classification(
            classification,
            is_rate_limit=True,
            is_retryable=True,
        )
    
    @pytest.mark.unit
    def test_auth_error_not_retryable(self, error_helper):
        """Auth errors (401, 403) should not be retryable."""
        err = ValueError("401 unauthorized")
        classification = classify_error(err, PipelineStage.RESEARCH)
        
        error_helper.assert_classification(
            classification,
            is_auth_error=True,
            is_retryable=False,
        )
    
    @pytest.mark.unit
    def test_timeout_detection(self, tool_timeout_error, error_helper):
        """Timeout errors should be detected and marked retryable."""
        classification = classify_error(tool_timeout_error, PipelineStage.RESEARCH)
        
        error_helper.assert_classification(
            classification,
            is_timeout=True,
            is_retryable=True,
        )
    
    @pytest.mark.unit
    def test_tool_error_detection(self, error_helper):
        """Tool errors (MCP, Bing) should be detected."""
        err = ValueError("Microsoft Learn MCP server error")
        classification = classify_error(err, PipelineStage.RESEARCH)
        
        error_helper.assert_classification(
            classification,
            is_tool_error=True,
            is_retryable=True,
        )


# =============================================================================
# TESTS: ResponseFailedError
# =============================================================================

class TestResponseFailedError:
    """Tests for ResponseFailedError handling."""
    
    @pytest.mark.unit
    def test_creation_with_all_fields(self, response_failed_error_factory):
        """ResponseFailedError should carry all structured context."""
        err = response_failed_error_factory(
            stage="research",
            error_msg="Server error",
            error_code="server_error",
            http_status_code=500,
        )
        
        assert err.stage == "research"
        assert err.error_msg == "Server error"
        assert err.error_code == "server_error"
        assert err.http_status_code == 500
    
    @pytest.mark.unit
    def test_classify_error_uses_structured_info(self, response_failed_error_factory, error_helper):
        """classify_error should use pre-parsed info from ResponseFailedError."""
        err = response_failed_error_factory(
            stage="research",
            error_msg="Rate limited",
            error_code="rate_limit_exceeded",
            http_status_code=429,
        )
        
        classification = classify_error(err, PipelineStage.RESEARCH)
        
        error_helper.assert_classification(
            classification,
            http_status_code=429,
            error_code="rate_limit_exceeded",
        )


# =============================================================================
# STANDALONE RUNNER (for running without pytest)
# =============================================================================

if __name__ == "__main__":
    # Support running directly with python for quick checks
    pytest.main([__file__, "-v"])
