"""
test_web_endpoints.py — Tests for Flask web endpoints.

Tests the REST API endpoints in web_app.py.

Run with: pytest tests/test_web_endpoints.py -v
"""

import json
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory to path so we can import from the main package
sys.path.insert(0, str(Path(__file__).parent.parent))

from web_app import app, extract_blocks


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up mock environment variables."""
    monkeypatch.setenv("PROJECT_ENDPOINT", "https://test.azure.com/api/projects/test")
    monkeypatch.setenv("MODEL_DEPLOYMENT_NAME", "gpt-5.2")
    monkeypatch.setenv("BING_CONNECTION_NAME", "/subscriptions/test/connections/bing")


# =============================================================================
# TESTS: Index Route
# =============================================================================

class TestIndexRoute:
    """Tests for the main index route."""
    
    @pytest.mark.unit
    def test_index_returns_html(self, client):
        """GET / should return HTML content."""
        response = client.get("/")
        assert response.status_code == 200
        assert b"<!DOCTYPE html>" in response.data or b"<html" in response.data


# =============================================================================
# TESTS: Status API
# =============================================================================

class TestStatusAPI:
    """Tests for /api/status endpoint."""
    
    @pytest.mark.unit
    def test_status_returns_json(self, client):
        """GET /api/status should return JSON."""
        response = client.get("/api/status")
        assert response.status_code == 200
        assert response.content_type == "application/json"
    
    @pytest.mark.unit
    def test_status_has_required_fields(self, client):
        """Status response should have required structure."""
        response = client.get("/api/status")
        data = json.loads(response.data)
        
        assert "ready" in data
        assert "needs_setup" in data
        assert "config" in data
        assert "agents" in data
    
    @pytest.mark.unit
    def test_status_config_fields(self, client):
        """Status config should have all expected fields."""
        response = client.get("/api/status")
        data = json.loads(response.data)
        
        config = data["config"]
        assert "has_env_file" in config
        assert "has_endpoint" in config
        assert "has_model" in config
        assert "has_bing" in config
    
    @pytest.mark.unit
    def test_status_agents_fields(self, client):
        """Status agents should have all expected fields."""
        response = client.get("/api/status")
        data = json.loads(response.data)
        
        agents = data["agents"]
        assert "configured" in agents
        assert "researcher" in agents
        assert "writer" in agents
        assert "reviewer" in agents


# =============================================================================
# TESTS: Config API
# =============================================================================

class TestConfigAPI:
    """Tests for /api/config endpoint."""
    
    @pytest.mark.unit
    def test_config_get_returns_json(self, client):
        """GET /api/config should return JSON."""
        response = client.get("/api/config")
        assert response.status_code == 200
        assert response.content_type == "application/json"
    
    @pytest.mark.unit
    def test_config_get_has_required_fields(self, client):
        """Config response should have expected fields."""
        response = client.get("/api/config")
        data = json.loads(response.data)
        
        assert "PROJECT_ENDPOINT" in data
        assert "MODEL_DEPLOYMENT_NAME" in data
        assert "BING_CONNECTION_NAME" in data
        assert "AGENT_NAME" in data


# =============================================================================
# TESTS: Validate API
# =============================================================================

class TestValidateAPI:
    """Tests for /api/validate endpoint."""
    
    @pytest.mark.unit
    def test_validate_returns_json(self, client):
        """GET /api/validate should return JSON."""
        response = client.get("/api/validate")
        assert response.status_code == 200
        assert response.content_type == "application/json"
    
    @pytest.mark.unit
    def test_validate_has_checks_array(self, client):
        """Validate response should have checks array."""
        response = client.get("/api/validate")
        data = json.loads(response.data)
        
        assert "checks" in data
        assert isinstance(data["checks"], list)
    
    @pytest.mark.unit
    def test_validate_has_status_fields(self, client):
        """Validate response should have status fields."""
        response = client.get("/api/validate")
        data = json.loads(response.data)
        
        assert "all_passed" in data
        assert "ready_for_agent" in data


# =============================================================================
# TESTS: Debug Endpoint Protection
# =============================================================================

class TestDebugEndpoint:
    """Tests for /api/debug/threads endpoint protection."""
    
    @pytest.mark.unit
    def test_debug_blocked_in_production(self, client):
        """Debug endpoint should return 403 when not in debug mode."""
        # Ensure debug mode is off
        app.debug = False
        response = client.get("/api/debug/threads")
        assert response.status_code == 403
        data = json.loads(response.data)
        assert "error" in data
        assert "not available" in data["error"].lower()
    
    @pytest.mark.unit
    def test_debug_allowed_in_debug_mode(self, client):
        """Debug endpoint should work when debug mode is on."""
        # Enable debug mode
        original_debug = app.debug
        app.debug = True
        try:
            response = client.get("/api/debug/threads")
            assert response.status_code == 200
            data = json.loads(response.data)
            assert "thread_count" in data
            assert "threads" in data
        finally:
            app.debug = original_debug


# =============================================================================
# TESTS: Generate API Input Validation
# =============================================================================

class TestGenerateAPIValidation:
    """Tests for /api/generate/stream input validation."""
    
    @pytest.mark.unit
    def test_generate_requires_notes(self, client):
        """POST /api/generate/stream without notes should return 400."""
        response = client.post(
            "/api/generate/stream",
            data=json.dumps({"notes": ""}),
            content_type="application/json"
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data
    
    @pytest.mark.unit
    def test_generate_rejects_invalid_images(self, client):
        """POST with invalid images format should return 400."""
        response = client.post(
            "/api/generate/stream",
            data=json.dumps({
                "notes": "Some test notes",
                "images": "not a list"
            }),
            content_type="application/json"
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data
        assert "list" in data["error"].lower()
    
    @pytest.mark.unit
    def test_generate_rejects_images_without_data(self, client):
        """POST with images missing 'data' field should return 400."""
        response = client.post(
            "/api/generate/stream",
            data=json.dumps({
                "notes": "Some test notes",
                "images": [{"type": "image/png"}]  # Missing 'data'
            }),
            content_type="application/json"
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data


# =============================================================================
# TESTS: Extract Blocks Utility
# =============================================================================

class TestExtractBlocks:
    """Tests for the extract_blocks utility function."""
    
    @pytest.mark.unit
    def test_extract_both_blocks(self):
        """Should extract both TSG and questions blocks."""
        content = """
<!-- TSG_BEGIN -->
TSG content here
<!-- TSG_END -->

<!-- QUESTIONS_BEGIN -->
NO_MISSING
<!-- QUESTIONS_END -->
"""
        tsg, questions = extract_blocks(content)
        assert "TSG content here" in tsg
        assert questions == "NO_MISSING"
    
    @pytest.mark.unit
    def test_extract_empty_when_missing_markers(self):
        """Should return empty strings when markers missing."""
        content = "Just some text without markers"
        tsg, questions = extract_blocks(content)
        assert tsg == ""
        assert questions == ""
    
    @pytest.mark.unit
    def test_extract_strips_whitespace(self):
        """Should strip whitespace from extracted content."""
        content = """
<!-- TSG_BEGIN -->
   Padded content   
<!-- TSG_END -->

<!-- QUESTIONS_BEGIN -->
   NO_MISSING   
<!-- QUESTIONS_END -->
"""
        tsg, questions = extract_blocks(content)
        assert tsg == "Padded content"
        assert questions == "NO_MISSING"


# =============================================================================
# TESTS: Cancel API
# =============================================================================

class TestCancelAPI:
    """Tests for /api/cancel/<run_id> endpoint."""
    
    @pytest.mark.unit
    def test_cancel_rejects_invalid_uuid(self, client):
        """POST /api/cancel/<run_id> with invalid UUID should return 400."""
        response = client.post("/api/cancel/not-a-valid-uuid")
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data
        assert "invalid" in data["error"].lower()
    
    @pytest.mark.unit
    def test_cancel_with_unknown_run_id(self, client):
        """POST /api/cancel/<run_id> with unknown (but valid) UUID should return 404."""
        # Use a valid UUID format that doesn't exist
        response = client.post("/api/cancel/12345678-1234-5678-1234-567812345678")
        assert response.status_code == 404
        data = json.loads(response.data)
        assert "error" in data
