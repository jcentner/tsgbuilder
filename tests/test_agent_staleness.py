"""
test_agent_staleness.py — Tests for agent staleness detection.

Tests that:
- save_agent_ids() persists app_version in .agent_ids.json
- /api/status reports agents_stale when version mismatches
- /api/validate reports agents_stale and surfaces a warning
- Pre-existing files without app_version are treated as stale

Run with: pytest tests/test_agent_staleness.py -v
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from web_app import app, save_agent_ids, get_agent_ids
from version import APP_VERSION


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def tmp_agent_ids(tmp_path, monkeypatch):
    """Redirect .agent_ids.json to a temp directory."""
    monkeypatch.setattr("web_app._get_app_dir", lambda: tmp_path)
    return tmp_path / ".agent_ids.json"


@pytest.fixture
def sample_agents():
    """Return sample agent dicts (v2 format)."""
    return {
        "researcher": {"name": "TSG-Builder-Researcher", "version": "1", "id": "agent-r-123"},
        "writer": {"name": "TSG-Builder-Writer", "version": "1", "id": "agent-w-456"},
        "reviewer": {"name": "TSG-Builder-Reviewer", "version": "1", "id": "agent-rv-789"},
    }


# =============================================================================
# TESTS: save_agent_ids() persists app_version
# =============================================================================

class TestSaveAgentIdsVersion:
    """Tests that save_agent_ids writes app_version."""

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
    def test_status_not_stale_when_version_matches(self, client, tmp_agent_ids, sample_agents):
        """Agents with current app_version should not be stale."""
        data = {
            **sample_agents,
            "name_prefix": "TSG-Builder",
            "app_version": APP_VERSION,
        }
        tmp_agent_ids.write_text(json.dumps(data), encoding="utf-8")

        response = client.get("/api/status")
        result = json.loads(response.data)

        assert result["agents"]["configured"] is True
        assert result["agents"]["agents_stale"] is False

    @pytest.mark.unit
    def test_status_stale_when_version_differs(self, client, tmp_agent_ids, sample_agents):
        """Agents with a different app_version should be stale."""
        data = {
            **sample_agents,
            "name_prefix": "TSG-Builder",
            "app_version": "0.9.0",
        }
        tmp_agent_ids.write_text(json.dumps(data), encoding="utf-8")

        response = client.get("/api/status")
        result = json.loads(response.data)

        assert result["agents"]["configured"] is True
        assert result["agents"]["agents_stale"] is True
        assert result["agents"]["agents_created_version"] == "0.9.0"

    @pytest.mark.unit
    def test_status_stale_when_version_missing(self, client, tmp_agent_ids, sample_agents):
        """Pre-existing .agent_ids.json without app_version should be treated as stale."""
        data = {
            **sample_agents,
            "name_prefix": "TSG-Builder",
            # no app_version key
        }
        tmp_agent_ids.write_text(json.dumps(data), encoding="utf-8")

        response = client.get("/api/status")
        result = json.loads(response.data)

        assert result["agents"]["configured"] is True
        assert result["agents"]["agents_stale"] is True
        assert result["agents"]["agents_created_version"] == "unknown"

    @pytest.mark.unit
    def test_status_no_staleness_fields_when_no_agents(self, client, tmp_agent_ids):
        """When agents are not configured, staleness fields should not appear."""
        # No .agent_ids.json exists
        response = client.get("/api/status")
        result = json.loads(response.data)

        assert result["agents"]["configured"] is False
        # staleness fields should not be set
        assert "agents_stale" not in result["agents"]


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
    fake_project.deployments.get.return_value = MagicMock(
        model_name="gpt-5.2", name="gpt-5.2",
    )
    monkeypatch.setattr(
        "azure.ai.projects.AIProjectClient",
        lambda *a, **kw: fake_project,
    )


class TestValidateStaleness:
    """Tests for agent staleness detection in /api/validate."""

    @pytest.mark.unit
    def test_validate_not_stale_when_version_matches(self, client, tmp_agent_ids, sample_agents):
        """Agents with current version should not trigger staleness warning."""
        data = {
            **sample_agents,
            "name_prefix": "TSG-Builder",
            "app_version": APP_VERSION,
        }
        tmp_agent_ids.write_text(json.dumps(data), encoding="utf-8")

        response = client.get("/api/validate")
        result = json.loads(response.data)

        assert result["agents_stale"] is False
        assert result["agents_created_version"] is None

        # Pipeline Agents check should pass without warning
        agent_check = next(c for c in result["checks"] if c["name"] == "Pipeline Agents")
        assert agent_check["passed"] is True
        assert agent_check.get("warning") is not True

    @pytest.mark.unit
    def test_validate_stale_when_version_differs(self, client, tmp_agent_ids, sample_agents):
        """Agents with old version should trigger staleness in validate response."""
        data = {
            **sample_agents,
            "name_prefix": "TSG-Builder",
            "app_version": "1.0.5",
        }
        tmp_agent_ids.write_text(json.dumps(data), encoding="utf-8")

        response = client.get("/api/validate")
        result = json.loads(response.data)

        assert result["agents_stale"] is True
        assert result["agents_created_version"] == "1.0.5"

        # Pipeline Agents check should still pass but with warning
        agent_check = next(c for c in result["checks"] if c["name"] == "Pipeline Agents")
        assert agent_check["passed"] is True
        assert agent_check["warning"] is True
        assert "v1.0.5" in agent_check["message"]
        assert f"v{APP_VERSION}" in agent_check["message"]

    @pytest.mark.unit
    def test_validate_stale_when_version_missing(self, client, tmp_agent_ids, sample_agents):
        """Pre-existing file without app_version should be treated as stale."""
        data = {
            **sample_agents,
            "name_prefix": "TSG-Builder",
        }
        tmp_agent_ids.write_text(json.dumps(data), encoding="utf-8")

        response = client.get("/api/validate")
        result = json.loads(response.data)

        assert result["agents_stale"] is True
        assert result["agents_created_version"] == "unknown"

        agent_check = next(c for c in result["checks"] if c["name"] == "Pipeline Agents")
        assert agent_check["passed"] is True
        assert agent_check["warning"] is True

    @pytest.mark.unit
    def test_validate_no_staleness_when_agents_missing(self, client, tmp_agent_ids):
        """When no agents configured, staleness should be false/None."""
        # No .agent_ids.json file
        response = client.get("/api/validate")
        result = json.loads(response.data)

        assert result["agents_stale"] is False
        assert result["agents_created_version"] is None

        # Pipeline Agents check should fail
        agent_check = next(c for c in result["checks"] if c["name"] == "Pipeline Agents")
        assert agent_check["passed"] is False
