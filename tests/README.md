# TSG Builder Test Suite

This directory contains the test suite for TSG Builder.

## Quick Start

```bash
# Activate virtual environment
source .venv/bin/activate

# Run all tests with pytest
pytest tests/

# Run all tests with verbose output
pytest tests/ -v

# Run a specific test file
pytest tests/test_error_handling.py

# Run tests matching a pattern
pytest tests/ -k "error"

# Run with coverage
pytest tests/ --cov=. --cov-report=html
```

Or use the Makefile:

```bash
make test          # Run all tests
make test-verbose  # Run with verbose output
make test-cov      # Run with coverage report
```

## Test Structure

```
tests/
├── __init__.py              # Package marker
├── conftest.py              # Shared fixtures and utilities
├── README.md                # This file
├── test_error_handling.py   # Error handling tests (Phase 4)
└── test_pipeline.py         # Pipeline tests (future)
```

## Writing Tests

### Using Fixtures

The `conftest.py` file provides reusable fixtures for common test scenarios:

```python
def test_something(mock_http_error, pipeline_error_factory, error_helper):
    # Create a mock HTTP 401 error
    err = mock_http_error(401)
    
    # Create a pipeline error
    pe = pipeline_error_factory(
        stage=PipelineStage.RESEARCH,
        http_status=401,
    )
    
    # Use helper to assert error properties
    msg, hint = _get_user_friendly_error(pe)
    error_helper.assert_user_friendly_error(
        msg, hint,
        expected_msg_contains=["auth", "401"],
        expected_hint_contains=["az login"],
    )
```

### Available Fixtures

| Fixture | Description |
|---------|-------------|
| `mock_http_error` | Factory to create HttpResponseError with status codes |
| `auth_error` | Pre-built ClientAuthenticationError |
| `connection_error` | Pre-built ServiceRequestError |
| `not_found_error` | Pre-built ResourceNotFoundError |
| `pipeline_error_factory` | Factory to create PipelineError |
| `response_failed_error_factory` | Factory to create ResponseFailedError |
| `tool_timeout_error` | Pre-built ToolTimeoutError |
| `stream_idle_error` | Pre-built StreamIdleTimeoutError |
| `mock_event_queue` | Queue for capturing pipeline events |
| `mock_cancel_event` | Threading event for cancellation |
| `error_helper` | ErrorTestHelper with assertion methods |

### Test Markers

Use markers to categorize tests:

```python
import pytest

@pytest.mark.unit
def test_fast_unit_test():
    """Runs quickly, no external deps."""
    pass

@pytest.mark.integration
def test_azure_connection():
    """Requires Azure connection."""
    pass

@pytest.mark.slow
def test_full_pipeline():
    """Takes a long time to run."""
    pass
```

Run specific categories:

```bash
pytest tests/ -m unit           # Only unit tests
pytest tests/ -m "not slow"     # Skip slow tests
pytest tests/ -m integration    # Only integration tests
```

### Test Naming Conventions

- Test files: `test_<module>.py`
- Test functions: `test_<what>_<scenario>_<expected>`
- Test classes: `Test<Feature>`

Examples:
```python
def test_classify_error_with_401_returns_auth_error():
    pass

def test_get_user_friendly_error_with_pipeline_error_includes_hint():
    pass

class TestErrorClassification:
    def test_rate_limit_is_retryable(self):
        pass
```

## Adding New Tests

### 1. Create a new test file

```python
# tests/test_my_feature.py
"""Tests for my_feature module."""

import pytest
from my_module import my_function

class TestMyFeature:
    def test_basic_case(self):
        result = my_function("input")
        assert result == "expected"
    
    def test_edge_case(self, some_fixture):
        # Use fixtures from conftest.py
        pass
```

### 2. Add fixtures if needed

If your tests need shared setup, add fixtures to `conftest.py`:

```python
@pytest.fixture
def my_test_data():
    return {"key": "value"}
```

### 3. Run and verify

```bash
pytest tests/test_my_feature.py -v
```

## Test Categories

### Unit Tests (`test_*.py`)
- Test individual functions in isolation
- Mock external dependencies
- Should run quickly (<1s each)

### Integration Tests (future: `test_integration_*.py`)
- Test component interactions
- May require Azure connection
- Mark with `@pytest.mark.integration`

### End-to-End Tests (future: `test_e2e_*.py`)
- Test full pipeline flows
- Require Azure credentials
- Mark with `@pytest.mark.slow`

## Coverage

Generate coverage reports:

```bash
# Terminal report
pytest tests/ --cov=. --cov-report=term-missing

# HTML report (opens in browser)
pytest tests/ --cov=. --cov-report=html
open htmlcov/index.html
```

## Debugging Tests

```bash
# Stop on first failure
pytest tests/ -x

# Show print statements
pytest tests/ -s

# Enter debugger on failure
pytest tests/ --pdb

# Verbose with locals on failure
pytest tests/ -vvl
```

## CI/CD Integration

Tests are designed to run in CI pipelines:

```yaml
# Example GitHub Actions step
- name: Run tests
  run: |
    source .venv/bin/activate
    pytest tests/ -v --tb=short
```

For integration tests requiring Azure:
```yaml
- name: Run integration tests
  env:
    PROJECT_ENDPOINT: ${{ secrets.PROJECT_ENDPOINT }}
  run: |
    pytest tests/ -m integration -v
```
