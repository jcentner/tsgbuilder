"""
test_version_check.py — Tests for the version check + About banner feature.

Tests:
- _is_newer() semver comparison logic
- _check_for_updates() with mocked HTTP responses
- /api/about includes version check fields
- update_available telemetry event

Run with: pytest tests/test_version_check.py -v
"""

import json
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from io import BytesIO

from web_app import app, _is_newer


# =============================================================================
# TESTS: _is_newer() semver comparison
# =============================================================================

class TestIsNewer:
    """Tests for the _is_newer() semver comparison helper."""

    @pytest.mark.unit
    def test_equal_versions_not_newer(self):
        assert _is_newer("1.0.7", "1.0.7") is False

    @pytest.mark.unit
    def test_newer_patch(self):
        assert _is_newer("1.0.8", "1.0.7") is True

    @pytest.mark.unit
    def test_older_patch(self):
        assert _is_newer("1.0.6", "1.0.7") is False

    @pytest.mark.unit
    def test_newer_minor(self):
        assert _is_newer("1.1.0", "1.0.7") is True

    @pytest.mark.unit
    def test_older_minor(self):
        assert _is_newer("1.0.0", "1.1.0") is False

    @pytest.mark.unit
    def test_newer_major(self):
        assert _is_newer("2.0.0", "1.9.9") is True

    @pytest.mark.unit
    def test_older_major(self):
        assert _is_newer("1.0.0", "2.0.0") is False

    @pytest.mark.unit
    def test_prerelease_older_than_stable(self):
        """1.0.8 stable is newer than 1.0.8-beta.1."""
        assert _is_newer("1.0.8", "1.0.8-beta.1") is True

    @pytest.mark.unit
    def test_stable_not_newer_than_same_stable(self):
        assert _is_newer("1.0.7", "1.0.7") is False

    @pytest.mark.unit
    def test_prerelease_not_newer_than_same_stable(self):
        """1.0.7-beta.1 is NOT newer than 1.0.7 stable."""
        assert _is_newer("1.0.7-beta.1", "1.0.7") is False

    @pytest.mark.unit
    def test_malformed_latest_returns_false(self):
        assert _is_newer("not-a-version", "1.0.7") is False

    @pytest.mark.unit
    def test_malformed_current_returns_false(self):
        assert _is_newer("1.0.8", "bad") is False

    @pytest.mark.unit
    def test_both_malformed_returns_false(self):
        assert _is_newer("abc", "xyz") is False

    @pytest.mark.unit
    def test_empty_strings_return_false(self):
        assert _is_newer("", "") is False

    @pytest.mark.unit
    def test_whitespace_trimmed(self):
        assert _is_newer("  1.0.8  ", "  1.0.7  ") is True

    @pytest.mark.unit
    def test_both_prerelease_same_numeric_not_newer(self):
        """Two pre-releases of the same numeric version — not newer."""
        assert _is_newer("1.0.8-beta.2", "1.0.8-beta.1") is False

    @pytest.mark.unit
    def test_higher_numeric_prerelease_is_newer(self):
        """1.1.0-beta.1 is newer than 1.0.7."""
        assert _is_newer("1.1.0-beta.1", "1.0.7") is True


# =============================================================================
# TESTS: _check_for_updates()
# =============================================================================

class TestCheckForUpdates:
    """Tests for the _check_for_updates() background function."""

    def _reset_update_state(self):
        """Reset module-level cache variables."""
        import web_app
        web_app._latest_version = None
        web_app._update_url = None
        web_app._update_check_done = False

    @pytest.mark.unit
    def test_success_sets_latest_version(self, monkeypatch):
        """When GitHub API returns a newer version, cache is populated."""
        import web_app
        self._reset_update_state()

        # Mock APP_VERSION to be older than the "latest"
        monkeypatch.setattr("web_app.APP_VERSION", "1.0.6")
        monkeypatch.delenv("TSG_UPDATE_CHECK", raising=False)

        fake_response = BytesIO(json.dumps({
            "tag_name": "v1.0.8",
            "html_url": "https://github.com/jcentner/tsgbuilder/releases/tag/v1.0.8",
        }).encode())
        fake_response.status = 200

        mock_urlopen = MagicMock(return_value=fake_response)
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", mock_urlopen), \
             patch.object(web_app.telemetry, "track_event") as mock_track:
            web_app._check_for_updates()

        assert web_app._latest_version == "1.0.8"
        assert web_app._update_url == "https://github.com/jcentner/tsgbuilder/releases/tag/v1.0.8"
        assert web_app._update_check_done is True

        # Verify telemetry event
        mock_track.assert_called_once_with(
            "update_available",
            properties={
                "current_version": "1.0.6",
                "latest_version": "1.0.8",
            },
        )

        self._reset_update_state()

    @pytest.mark.unit
    def test_no_update_when_current_is_latest(self, monkeypatch):
        """When GitHub returns the same version, cache stays None."""
        import web_app
        self._reset_update_state()

        monkeypatch.setattr("web_app.APP_VERSION", "1.0.7")
        monkeypatch.delenv("TSG_UPDATE_CHECK", raising=False)

        fake_response = BytesIO(json.dumps({
            "tag_name": "v1.0.7",
            "html_url": "https://github.com/jcentner/tsgbuilder/releases/tag/v1.0.7",
        }).encode())
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", MagicMock(return_value=fake_response)), \
             patch.object(web_app.telemetry, "track_event") as mock_track:
            web_app._check_for_updates()

        assert web_app._latest_version is None
        assert web_app._update_check_done is True
        mock_track.assert_not_called()

        self._reset_update_state()

    @pytest.mark.unit
    def test_network_failure_silently_ignored(self, monkeypatch):
        """Network errors should be swallowed, cache stays None."""
        import web_app
        self._reset_update_state()

        monkeypatch.delenv("TSG_UPDATE_CHECK", raising=False)

        with patch("urllib.request.urlopen", side_effect=OSError("Connection refused")):
            web_app._check_for_updates()

        assert web_app._latest_version is None
        assert web_app._update_check_done is True

        self._reset_update_state()

    @pytest.mark.unit
    def test_opt_out_skips_check(self, monkeypatch):
        """TSG_UPDATE_CHECK=0 should skip the HTTP request entirely."""
        import web_app
        self._reset_update_state()

        monkeypatch.setenv("TSG_UPDATE_CHECK", "0")

        with patch("urllib.request.urlopen") as mock_urlopen:
            web_app._check_for_updates()

        mock_urlopen.assert_not_called()
        assert web_app._latest_version is None
        assert web_app._update_check_done is True

        self._reset_update_state()

    @pytest.mark.unit
    def test_opt_out_false_skips_check(self, monkeypatch):
        """TSG_UPDATE_CHECK=false should also skip."""
        import web_app
        self._reset_update_state()

        monkeypatch.setenv("TSG_UPDATE_CHECK", "false")

        with patch("urllib.request.urlopen") as mock_urlopen:
            web_app._check_for_updates()

        mock_urlopen.assert_not_called()
        assert web_app._update_check_done is True

        self._reset_update_state()


# =============================================================================
# TESTS: /api/about version check fields
# =============================================================================

class TestAboutVersionFields:
    """Tests that /api/about includes version check fields."""

    @pytest.mark.unit
    def test_about_includes_update_fields(self, client):
        """About response should include latest_version, update_url, update_check_enabled."""
        response = client.get("/api/about")
        data = json.loads(response.data)

        assert "latest_version" in data
        assert "update_url" in data
        assert "update_check_enabled" in data

    @pytest.mark.unit
    def test_about_shows_latest_when_available(self, client, monkeypatch):
        """When a newer version is cached, /api/about should return it."""
        import web_app
        monkeypatch.setattr(web_app, "_latest_version", "2.0.0")
        monkeypatch.setattr(web_app, "_update_url", "https://example.com/release")

        response = client.get("/api/about")
        data = json.loads(response.data)

        assert data["latest_version"] == "2.0.0"
        assert data["update_url"] == "https://example.com/release"

    @pytest.mark.unit
    def test_about_shows_none_when_no_update(self, client, monkeypatch):
        """When no newer version, fields should be None."""
        import web_app
        monkeypatch.setattr(web_app, "_latest_version", None)
        monkeypatch.setattr(web_app, "_update_url", None)

        response = client.get("/api/about")
        data = json.loads(response.data)

        assert data["latest_version"] is None
        assert data["update_url"] is None

    @pytest.mark.unit
    def test_about_update_check_enabled_default(self, client, monkeypatch):
        """Update check should be enabled by default."""
        monkeypatch.delenv("TSG_UPDATE_CHECK", raising=False)

        response = client.get("/api/about")
        data = json.loads(response.data)

        assert data["update_check_enabled"] is True

    @pytest.mark.unit
    def test_about_update_check_disabled(self, client, monkeypatch):
        """TSG_UPDATE_CHECK=0 should report disabled."""
        monkeypatch.setenv("TSG_UPDATE_CHECK", "0")

        response = client.get("/api/about")
        data = json.loads(response.data)

        assert data["update_check_enabled"] is False
