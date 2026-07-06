"""
test_agent_staleness.py — Tests for agent staleness detection.

Tests that:
- save_agent_ids() persists agent metadata in .agent_ids.json
- /api/status reports agents_stale when model metadata mismatches
- /api/validate reports agents_stale and blocks generation readiness
- Pre-existing files without model metadata are treated as stale

Run with: pytest tests/test_agent_staleness.py -v
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from web_app import app, save_agent_ids, get_agent_ids, get_agent_definition_signature
from version import APP_VERSION


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def tmp_agent_ids(tmp_path, monkeypatch):
    """Redirect .agent_ids.json to a temp directory."""
    monkeypatch.setattr("web_app._get_app_dir", lambda: tmp_path)
    (tmp_path / ".env").write_text(
        "PROJECT_ENDPOINT=test\nMODEL_DEPLOYMENT_NAME=gpt-5.2\n",
        encoding="utf-8",
    )
    return tmp_path / ".agent_ids.json"


@pytest.fixture
def sample_agents():
    """Return sample agent dicts (v2 format)."""
    return {
        "researcher": {"name": "TSG-Builder-Researcher", "version": "1", "id": "agent-r-123"},
        "writer": {"name": "TSG-Builder-Writer", "version": "1", "id": "agent-w-456"},
        "reviewer": {"name": "TSG-Builder-Reviewer", "version": "1", "id": "agent-rv-789"},
    }


def agent_metadata(model_deployment_name="gpt-5.2", underlying_model_name="gpt-5.2"):
    """Return current v2 metadata for sample agent files."""
    return {
        "app_version": APP_VERSION,
        "model_deployment_name": model_deployment_name,
        "underlying_model_name": underlying_model_name,
        "agent_definition_signature": get_agent_definition_signature(
            model_deployment_name,
            underlying_model_name,
        ),
    }


# =============================================================================
# TESTS: save_agent_ids() persists app_version
# =============================================================================

class TestSaveAgentIdsVersion:
    """Tests that save_agent_ids writes app and agent metadata."""

    @pytest.mark.unit
    def test_save_includes_app_version(self, tmp_agent_ids, sample_agents):
        """save_agent_ids should include app_version in the JSON file."""
        save_agent_ids(
            researcher=sample_agents["researcher"],
            writer=sample_agents["writer"],
            reviewer=sample_agents["reviewer"],
            name_prefix="TSG-Builder",
        )

        data = json.loads(tmp_agent_ids.read_text(encoding="utf-8"))
        assert "app_version" in data
        assert data["app_version"] == APP_VERSION

    @pytest.mark.unit
    def test_save_includes_agent_metadata(self, tmp_agent_ids, sample_agents):
        """save_agent_ids should include model and signature metadata."""
        save_agent_ids(
            researcher=sample_agents["researcher"],
            writer=sample_agents["writer"],
            reviewer=sample_agents["reviewer"],
            name_prefix="TSG-Builder",
            model_deployment_name="gpt-5.4",
            underlying_model_name="gpt-5.4",
        )

        data = json.loads(tmp_agent_ids.read_text(encoding="utf-8"))
        assert data["model_deployment_name"] == "gpt-5.4"
        assert data["underlying_model_name"] == "gpt-5.4"
        assert data["agent_definition_signature"] == get_agent_definition_signature("gpt-5.4", "gpt-5.4")

    @pytest.mark.unit
    def test_save_preserves_existing_fields(self, tmp_agent_ids, sample_agents):
        """save_agent_ids should still save all other fields correctly."""
        save_agent_ids(
            researcher=sample_agents["researcher"],
            writer=sample_agents["writer"],
            reviewer=sample_agents["reviewer"],
            name_prefix="MyPrefix",
        )

        data = json.loads(tmp_agent_ids.read_text(encoding="utf-8"))
        assert data["researcher"] == sample_agents["researcher"]
        assert data["writer"] == sample_agents["writer"]
        assert data["reviewer"] == sample_agents["reviewer"]
        assert data["name_prefix"] == "MyPrefix"
        assert data["app_version"] == APP_VERSION


# =============================================================================
# TESTS: /api/status staleness
# =============================================================================

class TestStatusStaleness:
    """Tests for agent staleness detection in /api/status."""

    @pytest.mark.unit
    def test_status_not_stale_when_metadata_matches(self, client, tmp_agent_ids, sample_agents, monkeypatch):
        """Agents with matching model metadata should not be stale."""
        monkeypatch.setenv("MODEL_DEPLOYMENT_NAME", "gpt-5.2")
        data = {
            **sample_agents,
            "name_prefix": "TSG-Builder",
            **agent_metadata("gpt-5.2", "gpt-5.2"),
        }
        tmp_agent_ids.write_text(json.dumps(data), encoding="utf-8")

        response = client.get("/api/status")
        result = json.loads(response.data)

        assert result["agents"]["configured"] is True
        assert result["agents"]["agents_stale"] is False
        assert result["ready"] is True

    @pytest.mark.unit
    def test_status_not_stale_when_only_version_differs(self, client, tmp_agent_ids, sample_agents, monkeypatch):
        """App version alone should not make agents stale."""
        monkeypatch.setenv("MODEL_DEPLOYMENT_NAME", "gpt-5.2")
        data = {
            **sample_agents,
            "name_prefix": "TSG-Builder",
            **agent_metadata("gpt-5.2", "gpt-5.2"),
            "app_version": "0.9.0",
        }
        tmp_agent_ids.write_text(json.dumps(data), encoding="utf-8")

        response = client.get("/api/status")
        result = json.loads(response.data)

        assert result["agents"]["configured"] is True
        assert result["agents"]["agents_stale"] is False
        assert result["ready"] is True

    @pytest.mark.unit
    def test_status_stale_when_metadata_missing(self, client, tmp_agent_ids, sample_agents, monkeypatch):
        """Pre-existing .agent_ids.json without model metadata should be stale."""
        monkeypatch.setenv("MODEL_DEPLOYMENT_NAME", "gpt-5.2")
        data = {
            **sample_agents,
            "name_prefix": "TSG-Builder",
            "app_version": APP_VERSION,
        }
        tmp_agent_ids.write_text(json.dumps(data), encoding="utf-8")

        response = client.get("/api/status")
        result = json.loads(response.data)

        assert result["agents"]["configured"] is True
        assert result["agents"]["agents_stale"] is True
        assert result["agents"]["agents_ready"] is False
        assert result["ready"] is False
        assert "agent metadata is missing" in result["agents"]["agents_stale_reasons"]

    @pytest.mark.unit
    def test_status_stale_when_model_differs(self, client, tmp_agent_ids, sample_agents, monkeypatch):
        """Agents created for another deployment should be stale."""
        monkeypatch.setenv("MODEL_DEPLOYMENT_NAME", "gpt-5.4")
        data = {
            **sample_agents,
            "name_prefix": "TSG-Builder",
            **agent_metadata("gpt-5.2", "gpt-5.2"),
        }
        tmp_agent_ids.write_text(json.dumps(data), encoding="utf-8")

        response = client.get("/api/status")
        result = json.loads(response.data)

        assert result["agents"]["agents_stale"] is True
        assert result["ready"] is False
        assert "model changed from gpt-5.2 to gpt-5.4" in result["agents"]["agents_stale_reasons"]

    @pytest.mark.unit
    def test_status_no_staleness_fields_when_no_agents(self, client, tmp_agent_ids):
        """When agents are not configured, staleness fields should not appear."""
        # No .agent_ids.json exists
        response = client.get("/api/status")
        result = json.loads(response.data)

        assert result["agents"]["configured"] is False
        # staleness fields should not be set
        assert "agents_stale" not in result["agents"]

    @pytest.mark.unit
    def test_status_rejects_legacy_string_agents(self, client, tmp_agent_ids):
        """Legacy string-only agent IDs should fail fast."""
        data = {
            "researcher": "agent-r-123",
            "writer": "agent-w-456",
            "reviewer": "agent-rv-789",
            "name_prefix": "TSG-Builder",
        }
        tmp_agent_ids.write_text(json.dumps(data), encoding="utf-8")

        response = client.get("/api/status")
        result = json.loads(response.data)

        assert result["agents"]["configured"] is False
        assert "Legacy agent configuration" in result["agents"]["error"]


# =============================================================================
# TESTS: /api/validate staleness
# =============================================================================

@pytest.fixture(autouse=True)
def _mock_azure_for_validate(monkeypatch):
    """Stub out Azure credential / project calls so /api/validate doesn't hang.

    The staleness tests only care about check #6 (Pipeline Agents).  Checks 3-5
    need Azure auth + a live project connection which are irrelevant here and
    would block indefinitely in offline / CI environments.
    """
    monkeypatch.setenv("PROJECT_ENDPOINT", "https://test.services.ai.azure.com/api/projects/test-project")
    monkeypatch.setenv("MODEL_DEPLOYMENT_NAME", "gpt-5.2")

    # Make DefaultAzureCredential.get_token succeed instantly
    fake_token = MagicMock()
    fake_token.token = "fake"
    fake_cred = MagicMock()
    fake_cred.get_token.return_value = fake_token
    monkeypatch.setattr(
        "azure.identity.DefaultAzureCredential",
        lambda *a, **kw: fake_cred,
    )

    # Make AIProjectClient a no-op context manager whose agents.list returns []
    fake_project = MagicMock()
    fake_project.__enter__ = lambda s: s
    fake_project.__exit__ = MagicMock(return_value=False)
    fake_project.agents.list.return_value = iter([])
    fake_project.deployments.get.side_effect = lambda name: MagicMock(
        model_name=name, name=name,
    )
    monkeypatch.setattr(
        "azure.ai.projects.AIProjectClient",
        lambda *a, **kw: fake_project,
    )


class TestValidateStaleness:
    """Tests for agent staleness detection in /api/validate."""

    @pytest.mark.unit
    def test_validate_not_stale_when_metadata_matches(self, client, tmp_agent_ids, sample_agents, monkeypatch):
        """Agents with matching metadata should not trigger staleness warning."""
        monkeypatch.setenv("MODEL_DEPLOYMENT_NAME", "gpt-5.2")
        data = {
            **sample_agents,
            "name_prefix": "TSG-Builder",
            **agent_metadata("gpt-5.2", "gpt-5.2"),
        }
        tmp_agent_ids.write_text(json.dumps(data), encoding="utf-8")

        response = client.get("/api/validate")
        result = json.loads(response.data)

        assert result["agents_stale"] is False
        assert result["agents_created_version"] is None
        assert result["ready_for_generation"] is True

        # Pipeline Agents check should pass without warning
        agent_check = next(c for c in result["checks"] if c["name"] == "Pipeline Agents")
        assert agent_check["passed"] is True
        assert agent_check.get("warning") is not True

    @pytest.mark.unit
    def test_validate_not_stale_when_only_version_differs(self, client, tmp_agent_ids, sample_agents, monkeypatch):
        """App version alone should not block generation readiness."""
        monkeypatch.setenv("MODEL_DEPLOYMENT_NAME", "gpt-5.2")
        data = {
            **sample_agents,
            "name_prefix": "TSG-Builder",
            **agent_metadata("gpt-5.2", "gpt-5.2"),
            "app_version": "1.0.5",
        }
        tmp_agent_ids.write_text(json.dumps(data), encoding="utf-8")

        response = client.get("/api/validate")
        result = json.loads(response.data)

        assert result["agents_stale"] is False
        assert result["ready_for_generation"] is True

        agent_check = next(c for c in result["checks"] if c["name"] == "Pipeline Agents")
        assert agent_check["passed"] is True
        assert agent_check.get("warning") is not True

    @pytest.mark.unit
    def test_validate_stale_when_metadata_missing(self, client, tmp_agent_ids, sample_agents, monkeypatch):
        """Pre-existing file without model metadata should be stale."""
        monkeypatch.setenv("MODEL_DEPLOYMENT_NAME", "gpt-5.2")
        data = {
            **sample_agents,
            "name_prefix": "TSG-Builder",
            "app_version": APP_VERSION,
        }
        tmp_agent_ids.write_text(json.dumps(data), encoding="utf-8")

        response = client.get("/api/validate")
        result = json.loads(response.data)

        assert result["agents_stale"] is True
        assert result["ready_for_generation"] is False
        assert "agent metadata is missing" in result["agent_stale_reasons"]

        agent_check = next(c for c in result["checks"] if c["name"] == "Pipeline Agents")
        assert agent_check["passed"] is False
        assert agent_check["warning"] is True

    @pytest.mark.unit
    def test_validate_stale_when_metadata_blank(self, client, tmp_agent_ids, sample_agents, monkeypatch):
        """Blank model metadata should be treated as missing."""
        monkeypatch.setenv("MODEL_DEPLOYMENT_NAME", "gpt-5.2")
        data = {
            **sample_agents,
            "name_prefix": "TSG-Builder",
            "app_version": APP_VERSION,
            "model_deployment_name": "",
            "underlying_model_name": "   ",
            "agent_definition_signature": "",
        }
        tmp_agent_ids.write_text(json.dumps(data), encoding="utf-8")

        response = client.get("/api/validate")
        result = json.loads(response.data)

        assert result["agents_stale"] is True
        assert result["ready_for_generation"] is False
        assert "agent metadata is missing" in result["agent_stale_reasons"]

    @pytest.mark.unit
    def test_validate_stale_when_model_differs(self, client, tmp_agent_ids, sample_agents, monkeypatch):
        """Changed MODEL_DEPLOYMENT_NAME should block generation readiness."""
        monkeypatch.setenv("MODEL_DEPLOYMENT_NAME", "gpt-5.4")
        data = {
            **sample_agents,
            "name_prefix": "TSG-Builder",
            **agent_metadata("gpt-5.2", "gpt-5.2"),
        }
        tmp_agent_ids.write_text(json.dumps(data), encoding="utf-8")

        response = client.get("/api/validate")
        result = json.loads(response.data)

        assert result["agents_stale"] is True
        assert result["ready_for_generation"] is False
        assert "model changed from gpt-5.2 to gpt-5.4" in result["agent_stale_reasons"]

        agent_check = next(c for c in result["checks"] if c["name"] == "Pipeline Agents")
        assert agent_check["passed"] is False
        assert agent_check["warning"] is True

    @pytest.mark.unit
    def test_validate_no_staleness_when_agents_missing(self, client, tmp_agent_ids):
        """When no agents configured, staleness should be false/None."""
        # No .agent_ids.json file
        response = client.get("/api/validate")
        result = json.loads(response.data)

        assert result["agents_stale"] is False
        assert result["agents_created_version"] is None
        assert result["ready_for_generation"] is False

        # Pipeline Agents check should fail
        agent_check = next(c for c in result["checks"] if c["name"] == "Pipeline Agents")
        assert agent_check["passed"] is False

    @pytest.mark.unit
    def test_validate_rejects_legacy_string_agents(self, client, tmp_agent_ids):
        """Legacy string-only agent IDs should block generation readiness."""
        data = {
            "researcher": "agent-r-123",
            "writer": "agent-w-456",
            "reviewer": "agent-rv-789",
            "name_prefix": "TSG-Builder",
        }
        tmp_agent_ids.write_text(json.dumps(data), encoding="utf-8")

        response = client.get("/api/validate")
        result = json.loads(response.data)

        assert result["ready_for_generation"] is False
        agent_check = next(c for c in result["checks"] if c["name"] == "Pipeline Agents")
        assert agent_check["passed"] is False
        assert "Legacy agent configuration" in agent_check["message"]

    @pytest.mark.unit
    @patch("web_app.check_for_pii")
    @patch("web_app.run_pipeline")
    def test_generate_blocks_when_agent_metadata_missing(self, mock_run_pipeline, mock_check_for_pii, client, tmp_agent_ids, sample_agents, monkeypatch):
        """Generation should not start when persisted agents lack model metadata."""
        monkeypatch.setenv("MODEL_DEPLOYMENT_NAME", "gpt-5.2")
        mock_check_for_pii.return_value = {
            "pii_detected": False,
            "findings": [],
            "redacted_text": "test notes",
            "error": None,
            "hint": None,
        }
        data = {
            **sample_agents,
            "name_prefix": "TSG-Builder",
            "app_version": APP_VERSION,
        }
        tmp_agent_ids.write_text(json.dumps(data), encoding="utf-8")

        response = client.post(
            "/api/generate/stream",
            data=json.dumps({"notes": "test notes"}),
            content_type="application/json",
        )

        assert response.status_code == 400
        result = json.loads(response.data)
        assert "Recreate agents" in result["error"]
        mock_run_pipeline.assert_not_called()

    @pytest.mark.unit
    @patch("web_app.check_for_pii")
    @patch("web_app.run_pipeline")
    def test_generate_blocks_when_underlying_model_changes(self, mock_run_pipeline, mock_check_for_pii, client, tmp_agent_ids, sample_agents, monkeypatch):
        """Generation should verify the current deployment's underlying model."""
        monkeypatch.setenv("MODEL_DEPLOYMENT_NAME", "gpt-prod")
        mock_check_for_pii.return_value = {
            "pii_detected": False,
            "findings": [],
            "redacted_text": "test notes",
            "error": None,
            "hint": None,
        }
        data = {
            **sample_agents,
            "name_prefix": "TSG-Builder",
            **agent_metadata("gpt-prod", "gpt-5.2"),
        }
        tmp_agent_ids.write_text(json.dumps(data), encoding="utf-8")

        fake_project = MagicMock()
        fake_project.__enter__ = lambda s: s
        fake_project.__exit__ = MagicMock(return_value=False)
        fake_deployment = MagicMock()
        fake_deployment.name = "gpt-prod"
        fake_deployment.model_name = "gpt-5.4"
        fake_project.deployments.get.return_value = fake_deployment

        with patch("web_app.get_project_client", return_value=fake_project):
            response = client.post(
                "/api/generate/stream",
                data=json.dumps({"notes": "test notes"}),
                content_type="application/json",
            )

        assert response.status_code == 400
        result = json.loads(response.data)
        assert "agent definition changed" in result["error"]
        mock_run_pipeline.assert_not_called()
