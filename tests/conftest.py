"""
conftest.py — Shared pytest fixtures and test utilities for TSG Builder.

This file is automatically loaded by pytest and provides:
- Common fixtures for mocking Azure SDK errors
- Test utilities for creating pipeline errors
- Shared configuration for all tests
"""

import sys
from pathlib import Path
from unittest.mock import Mock
from typing import Any

import pytest

# Add parent directory to path so we can import from the main package
sys.path.insert(0, str(Path(__file__).parent.parent))

from web_app import app

# Import commonly used items
from azure.core.exceptions import (
    ClientAuthenticationError,
    ServiceRequestError,
    ResourceNotFoundError,
    HttpResponseError,
)

from pipeline import (
    PipelineError,
    PipelineStage,
    classify_error,
    ErrorClassification,
    ResponseFailedError,
    ToolTimeoutError,
    StreamIdleTimeoutError,
    CancelledError,
)


# =============================================================================
# FIXTURES: Azure SDK Errors
# =============================================================================

@pytest.fixture
def mock_http_error():
    """Factory fixture to create mock HttpResponseError with specific status codes."""
    def _create(status_code: int, reason: str = "Test") -> HttpResponseError:
        err = Mock(spec=HttpResponseError)
        err.status_code = status_code
        err.reason = reason
        err.__class__ = HttpResponseError
        return err
    return _create


@pytest.fixture
def auth_error():
    """Create a ClientAuthenticationError for testing."""
    return ClientAuthenticationError("Authentication failed")


@pytest.fixture
def connection_error():
    """Create a ServiceRequestError for testing."""
    return ServiceRequestError("Connection refused")


@pytest.fixture
def not_found_error():
    """Create a ResourceNotFoundError for testing."""
    return ResourceNotFoundError("Resource does not exist")


# =============================================================================
# FIXTURES: Pipeline Errors
# =============================================================================

@pytest.fixture
def pipeline_error_factory():
    """Factory fixture to create PipelineError with various configurations."""
    def _create(
        stage: PipelineStage = PipelineStage.RESEARCH,
        original_error: Exception = None,
        http_status: int | None = None,
        error_code: str | None = None,
    ) -> PipelineError:
        if original_error is None:
            original_error = ValueError("Test error")
        return PipelineError(
            stage=stage,
            original_error=original_error,
            http_status=http_status,
            error_code=error_code,
        )
    return _create


@pytest.fixture
def response_failed_error_factory():
    """Factory fixture to create ResponseFailedError."""
    def _create(
        stage: str = "research",
        error_msg: str = "Test error",
        error_code: str | None = None,
        http_status_code: int | None = None,
    ) -> ResponseFailedError:
        return ResponseFailedError(
            stage=stage,
            error_msg=error_msg,
            error_code=error_code,
            http_status_code=http_status_code,
        )
    return _create


@pytest.fixture
def tool_timeout_error():
    """Create a ToolTimeoutError for testing."""
    return ToolTimeoutError(tool_name="bing_search", elapsed=120.0, timeout=90.0)


@pytest.fixture
def stream_idle_error():
    """Create a StreamIdleTimeoutError for testing."""
    return StreamIdleTimeoutError(
        stage="research",
        idle_time=180.0,
        timeout=120.0,
        last_event="text_delta",
    )


# =============================================================================
# FIXTURES: Flask Test Client
# =============================================================================

@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


# =============================================================================
# TEST UTILITIES
# =============================================================================

class ErrorTestHelper:
    """Helper class for common error testing patterns."""
    
    @staticmethod
    def assert_user_friendly_error(
        msg: str,
        hint: str | None,
        expected_msg_contains: list[str] | None = None,
        expected_hint_contains: list[str] | None = None,
        hint_required: bool = True,
    ):
        """Assert that error message and hint contain expected content."""
        if expected_msg_contains:
            for term in expected_msg_contains:
                assert term.lower() in msg.lower(), \
                    f"Expected '{term}' in message '{msg}'"
        
        if hint_required:
            assert hint is not None, f"Expected hint but got None for message '{msg}'"
        
        if expected_hint_contains and hint:
            for term in expected_hint_contains:
                assert term.lower() in hint.lower(), \
                    f"Expected '{term}' in hint '{hint}'"
    
    @staticmethod
    def assert_classification(
        classification: ErrorClassification,
        is_retryable: bool | None = None,
        is_rate_limit: bool | None = None,
        is_timeout: bool | None = None,
        is_tool_error: bool | None = None,
        is_auth_error: bool | None = None,
        http_status_code: int | None = None,
        error_code: str | None = None,
    ):
        """Assert that error classification has expected properties."""
        if is_retryable is not None:
            assert classification.is_retryable == is_retryable, \
                f"Expected is_retryable={is_retryable}, got {classification.is_retryable}"
        
        if is_rate_limit is not None:
            assert classification.is_rate_limit == is_rate_limit, \
                f"Expected is_rate_limit={is_rate_limit}, got {classification.is_rate_limit}"
        
        if is_timeout is not None:
            assert classification.is_timeout == is_timeout, \
                f"Expected is_timeout={is_timeout}, got {classification.is_timeout}"
        
        if is_tool_error is not None:
            assert classification.is_tool_error == is_tool_error, \
                f"Expected is_tool_error={is_tool_error}, got {classification.is_tool_error}"
        
        if is_auth_error is not None:
            assert classification.is_auth_error == is_auth_error, \
                f"Expected is_auth_error={is_auth_error}, got {classification.is_auth_error}"
        
        if http_status_code is not None:
            assert classification.http_status_code == http_status_code, \
                f"Expected http_status_code={http_status_code}, got {classification.http_status_code}"
        
        if error_code is not None:
            assert classification.error_code == error_code, \
                f"Expected error_code={error_code}, got {classification.error_code}"


@pytest.fixture
def error_helper():
    """Provide ErrorTestHelper instance."""
    return ErrorTestHelper()


# =============================================================================
# PYTEST CONFIGURATION
# =============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests that require Azure connection"
    )
    config.addinivalue_line(
        "markers", "unit: marks unit tests (no external dependencies)"
    )
