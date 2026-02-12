"""
test_telemetry.py — Unit tests for the telemetry module.

Tests cover:
- track_event calls exporter with correct args (mocked)
- Opt-out via TSG_TELEMETRY=0 suppresses all emission
- install_id generated on first call, reused on subsequent calls
- Silent failure when exporter raises (no crash, no log spam)
- No install_id generated or persisted when opted out
- Connection string cascade (_build_config → env var → disabled)
"""

import importlib
import logging
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def _reset_telemetry():
    """Reset telemetry module state between tests."""
    import telemetry
    telemetry._initialized = False
    telemetry._logger = None
    telemetry._install_id = None


# =============================================================================
# CONNECTION STRING CASCADE
# =============================================================================

class TestConnectionStringCascade:
    """Connection string resolution: _build_config → env var → None."""

    def setup_method(self):
        _reset_telemetry()

    def test_build_config_takes_priority(self, monkeypatch):
        """_build_config.py connection string takes priority over env var."""
        import telemetry

        # Create a mock _build_config module
        mock_config = MagicMock()
        mock_config.APPINSIGHTS_CONNECTION_STRING = "InstrumentationKey=from-build-config"
        monkeypatch.setitem(sys.modules, "_build_config", mock_config)
        monkeypatch.setenv("APPINSIGHTS_CONNECTION_STRING", "InstrumentationKey=from-env")

        result = telemetry._get_connection_string()
        assert result == "InstrumentationKey=from-build-config"

    def test_env_var_used_when_no_build_config(self, monkeypatch):
        """Environment variable used when _build_config is not available."""
        import telemetry

        # Ensure _build_config is not importable
        monkeypatch.delitem(sys.modules, "_build_config", raising=False)
        monkeypatch.setenv("APPINSIGHTS_CONNECTION_STRING", "InstrumentationKey=from-env")

        # Temporarily break the import
        with patch.dict(sys.modules, {"_build_config": None}):
            result = telemetry._get_connection_string()

        assert result == "InstrumentationKey=from-env"

    def test_returns_none_when_no_config(self, monkeypatch):
        """Returns None when neither _build_config nor env var exists."""
        import telemetry

        monkeypatch.delenv("APPINSIGHTS_CONNECTION_STRING", raising=False)
        with patch.dict(sys.modules, {"_build_config": None}):
            result = telemetry._get_connection_string()

        assert result is None

    def test_empty_build_config_falls_through(self, monkeypatch):
        """Empty string in _build_config falls through to env var."""
        import telemetry

        mock_config = MagicMock()
        mock_config.APPINSIGHTS_CONNECTION_STRING = ""
        monkeypatch.setitem(sys.modules, "_build_config", mock_config)
        monkeypatch.setenv("APPINSIGHTS_CONNECTION_STRING", "InstrumentationKey=from-env")

        result = telemetry._get_connection_string()
        assert result == "InstrumentationKey=from-env"


# =============================================================================
# OPT-OUT
# =============================================================================

class TestOptOut:
    """TSG_TELEMETRY=0/false/no disables all telemetry."""

    def setup_method(self):
        _reset_telemetry()

    @pytest.mark.parametrize("value", ["0", "false", "False", "FALSE", "no", "No"])
    def test_opt_out_values(self, monkeypatch, value):
        """Various opt-out values all disable telemetry."""
        import telemetry
        monkeypatch.setenv("TSG_TELEMETRY", value)
        assert telemetry.is_telemetry_enabled() is False

    @pytest.mark.parametrize("value", ["1", "true", "yes", "anything", ""])
    def test_opt_in_values(self, monkeypatch, value):
        """Non-opt-out values keep telemetry enabled."""
        import telemetry
        monkeypatch.setenv("TSG_TELEMETRY", value)
        assert telemetry.is_telemetry_enabled() is True

    def test_default_is_enabled(self, monkeypatch):
        """Telemetry is enabled by default when TSG_TELEMETRY is unset."""
        import telemetry
        monkeypatch.delenv("TSG_TELEMETRY", raising=False)
        assert telemetry.is_telemetry_enabled() is True

    def test_opt_out_suppresses_track_event(self, monkeypatch):
        """track_event does nothing when opted out."""
        import telemetry
        monkeypatch.setenv("TSG_TELEMETRY", "0")
        _reset_telemetry()

        # Set up a mock logger to verify it's NOT called
        mock_logger = MagicMock(spec=logging.Logger)
        telemetry._logger = mock_logger

        telemetry.track_event("test_event", {"key": "val"})
        mock_logger.info.assert_not_called()


# =============================================================================
# INSTALL ID
# =============================================================================

class TestInstallId:
    """install_id generation, persistence, and opt-out behavior."""

    def setup_method(self):
        _reset_telemetry()

    def test_generates_uuid4(self, monkeypatch, tmp_path):
        """Generated install_id is a valid UUID4."""
        import telemetry

        monkeypatch.delenv("TSG_TELEMETRY", raising=False)
        monkeypatch.delenv("TSG_INSTALL_ID", raising=False)

        # Point to a temp .env so we don't pollute the real one
        env_file = tmp_path / ".env"
        env_file.write_text("")
        monkeypatch.setattr(telemetry, "_get_env_path", lambda: env_file)

        install_id = telemetry._get_or_create_install_id()
        assert install_id is not None

        # Validate it's a proper UUID
        import uuid
        parsed = uuid.UUID(install_id)
        assert parsed.version == 4

    def test_reuses_existing_id(self, monkeypatch):
        """Returns cached install_id on subsequent calls."""
        import telemetry

        monkeypatch.delenv("TSG_TELEMETRY", raising=False)
        monkeypatch.setenv("TSG_INSTALL_ID", "existing-id-123")

        id1 = telemetry._get_or_create_install_id()
        id2 = telemetry._get_or_create_install_id()
        assert id1 == id2 == "existing-id-123"

    def test_persists_to_env_file(self, monkeypatch, tmp_path):
        """New install_id is persisted to .env file."""
        import telemetry

        monkeypatch.delenv("TSG_TELEMETRY", raising=False)
        monkeypatch.delenv("TSG_INSTALL_ID", raising=False)

        env_file = tmp_path / ".env"
        env_file.write_text("")
        monkeypatch.setattr(telemetry, "_get_env_path", lambda: env_file)

        install_id = telemetry._get_or_create_install_id()

        # Verify it was written to the file
        content = env_file.read_text()
        assert "TSG_INSTALL_ID" in content
        assert install_id in content

    def test_no_id_when_opted_out(self, monkeypatch):
        """No install_id generated or persisted when telemetry is opted out."""
        import telemetry

        monkeypatch.setenv("TSG_TELEMETRY", "0")

        result = telemetry._get_or_create_install_id()
        assert result is None

    def test_no_persist_when_opted_out(self, monkeypatch, tmp_path):
        """No install_id written to .env when opted out."""
        import telemetry

        monkeypatch.setenv("TSG_TELEMETRY", "0")

        env_file = tmp_path / ".env"
        env_file.write_text("")
        monkeypatch.setattr(telemetry, "_get_env_path", lambda: env_file)

        telemetry._get_or_create_install_id()

        content = env_file.read_text()
        assert "TSG_INSTALL_ID" not in content

    def test_survives_missing_env_file(self, monkeypatch, tmp_path):
        """install_id generated even if .env file doesn't exist."""
        import telemetry

        monkeypatch.delenv("TSG_TELEMETRY", raising=False)
        monkeypatch.delenv("TSG_INSTALL_ID", raising=False)

        # Point to a non-existent file
        env_file = tmp_path / "nonexistent" / ".env"
        monkeypatch.setattr(telemetry, "_get_env_path", lambda: env_file)

        install_id = telemetry._get_or_create_install_id()
        assert install_id is not None


# =============================================================================
# TRACK EVENT
# =============================================================================

class TestTrackEvent:
    """track_event emits events with correct structure."""

    def setup_method(self):
        _reset_telemetry()

    def test_calls_logger_with_event_name(self, monkeypatch):
        """track_event calls logger.info with event name and custom_event.name."""
        import telemetry

        monkeypatch.delenv("TSG_TELEMETRY", raising=False)
        mock_logger = MagicMock(spec=logging.Logger)
        telemetry._logger = mock_logger
        telemetry._install_id = "test-install-id"

        telemetry.track_event("app_started", {"version": "1.0.0"})

        mock_logger.info.assert_called_once()
        args, kwargs = mock_logger.info.call_args
        assert args[0] == "app_started"
        extra = kwargs["extra"]
        assert extra["microsoft.custom_event.name"] == "app_started"
        assert extra["version"] == "1.0.0"
        assert extra["install_id"] == "test-install-id"

    def test_includes_properties_and_measurements(self, monkeypatch):
        """Both properties and measurements are included in the extra dict."""
        import telemetry

        monkeypatch.delenv("TSG_TELEMETRY", raising=False)
        mock_logger = MagicMock(spec=logging.Logger)
        telemetry._logger = mock_logger
        telemetry._install_id = "test-id"

        telemetry.track_event(
            "tsg_generated",
            properties={"version": "1.0.0", "had_missing": "true"},
            measurements={"duration_seconds": 42.5, "total_tokens": 1500},
        )

        extra = mock_logger.info.call_args[1]["extra"]
        assert extra["microsoft.custom_event.name"] == "tsg_generated"
        assert extra["version"] == "1.0.0"
        assert extra["had_missing"] == "true"
        assert extra["duration_seconds"] == 42.5
        assert extra["total_tokens"] == 1500

    def test_no_op_when_logger_is_none(self, monkeypatch):
        """track_event is a no-op when logger is not initialized."""
        import telemetry

        monkeypatch.delenv("TSG_TELEMETRY", raising=False)
        telemetry._logger = None

        # Should not raise
        telemetry.track_event("test_event", {"key": "val"})

    def test_auto_attaches_install_id(self, monkeypatch):
        """install_id is automatically attached if not already in properties."""
        import telemetry

        monkeypatch.delenv("TSG_TELEMETRY", raising=False)
        mock_logger = MagicMock(spec=logging.Logger)
        telemetry._logger = mock_logger
        telemetry._install_id = "auto-id"

        telemetry.track_event("test", {})

        extra = mock_logger.info.call_args[1]["extra"]
        assert extra["install_id"] == "auto-id"

    def test_does_not_override_explicit_install_id(self, monkeypatch):
        """Explicit install_id in properties is not overwritten."""
        import telemetry

        monkeypatch.delenv("TSG_TELEMETRY", raising=False)
        mock_logger = MagicMock(spec=logging.Logger)
        telemetry._logger = mock_logger
        telemetry._install_id = "auto-id"

        telemetry.track_event("test", {"install_id": "explicit-id"})

        extra = mock_logger.info.call_args[1]["extra"]
        assert extra["install_id"] == "explicit-id"


# =============================================================================
# SILENT FAILURE
# =============================================================================

class TestSilentFailure:
    """Telemetry never crashes the application."""

    def setup_method(self):
        _reset_telemetry()

    def test_track_event_swallows_exceptions(self, monkeypatch):
        """track_event silently swallows any exception from the logger."""
        import telemetry

        monkeypatch.delenv("TSG_TELEMETRY", raising=False)
        mock_logger = MagicMock(spec=logging.Logger)
        mock_logger.info.side_effect = RuntimeError("Exporter exploded")
        telemetry._logger = mock_logger
        telemetry._install_id = "test-id"

        # Must not raise
        telemetry.track_event("test_event", {"key": "val"})

    def test_init_telemetry_swallows_import_error(self, monkeypatch):
        """init_telemetry silently handles missing OpenTelemetry packages."""
        import telemetry

        monkeypatch.delenv("TSG_TELEMETRY", raising=False)
        monkeypatch.setenv("APPINSIGHTS_CONNECTION_STRING", "InstrumentationKey=test")

        # Make the OpenTelemetry import fail
        with patch.dict(sys.modules, {"opentelemetry._logs": None}):
            telemetry.init_telemetry()

        # Should be marked as initialized (to avoid retrying) but logger stays None
        assert telemetry._initialized is True
        assert telemetry._logger is None

    def test_init_telemetry_no_op_when_disabled(self, monkeypatch):
        """init_telemetry is a no-op when telemetry is disabled."""
        import telemetry

        monkeypatch.setenv("TSG_TELEMETRY", "0")
        telemetry.init_telemetry()

        assert telemetry._initialized is True
        assert telemetry._logger is None

    def test_init_telemetry_no_op_when_no_connection_string(self, monkeypatch):
        """init_telemetry is a no-op when no connection string is available."""
        import telemetry

        monkeypatch.delenv("TSG_TELEMETRY", raising=False)
        monkeypatch.delenv("APPINSIGHTS_CONNECTION_STRING", raising=False)

        with patch.dict(sys.modules, {"_build_config": None}):
            telemetry.init_telemetry()

        assert telemetry._initialized is True
        assert telemetry._logger is None

    def test_init_telemetry_idempotent(self, monkeypatch):
        """Calling init_telemetry multiple times is safe."""
        import telemetry

        monkeypatch.setenv("TSG_TELEMETRY", "0")

        telemetry.init_telemetry()
        telemetry.init_telemetry()
        telemetry.init_telemetry()

        assert telemetry._initialized is True


# =============================================================================
# INIT WITH REAL EXPORTER (mocked)
# =============================================================================

class TestInitWithExporter:
    """init_telemetry sets up the logging pipeline when properly configured."""

    def setup_method(self):
        _reset_telemetry()

    def test_sets_up_logger_when_configured(self, monkeypatch):
        """init_telemetry creates a logger when connection string is available."""
        import telemetry

        monkeypatch.delenv("TSG_TELEMETRY", raising=False)
        monkeypatch.setenv("APPINSIGHTS_CONNECTION_STRING", "InstrumentationKey=test-key")

        # Mock all OTel components that get imported inside init_telemetry
        mock_logs_module = MagicMock()
        mock_sdk_logs_module = MagicMock()
        mock_export_module = MagicMock()
        mock_exporter_module = MagicMock()

        mock_logger_provider_instance = MagicMock()
        mock_sdk_logs_module.LoggerProvider.return_value = mock_logger_provider_instance
        mock_handler_instance = MagicMock()
        mock_sdk_logs_module.LoggingHandler.return_value = mock_handler_instance
        mock_exporter_instance = MagicMock()
        mock_exporter_module.AzureMonitorLogExporter.return_value = mock_exporter_instance
        mock_processor_instance = MagicMock()
        mock_export_module.BatchLogRecordProcessor.return_value = mock_processor_instance

        with patch.dict(sys.modules, {
            "_build_config": None,
            "opentelemetry._logs": mock_logs_module,
            "opentelemetry.sdk._logs": mock_sdk_logs_module,
            "opentelemetry.sdk._logs.export": mock_export_module,
            "azure.monitor.opentelemetry.exporter": mock_exporter_module,
        }):
            # Re-import to pick up the mocked modules
            importlib.reload(telemetry)
            _reset_telemetry()
            telemetry.init_telemetry()

        assert telemetry._initialized is True
        assert telemetry._logger is not None
        assert telemetry._logger.name == "tsgbuilder.telemetry"
