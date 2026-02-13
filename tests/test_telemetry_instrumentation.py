"""
test_telemetry_instrumentation.py — Phase 2 tests for telemetry instrumentation.

Tests verify that each instrumentation point calls track_event with the
expected event name and property/measurement keys. All telemetry calls are 
mocked — no actual App Insights traffic.

Tests cover:
- app_started event emitted in main()
- tsg_generated event emitted on successful pipeline result
- pipeline_error event emitted on pipeline failure (result-based and exception-based)
- pii_blocked event emitted when PII gate triggers
- setup_completed event emitted on successful agent creation
- tsg_copied endpoint returns 204 and emits event
- _get_platform() returns valid platform strings
- _get_run_mode() returns source or executable
- _extract_missing_sections() parses MISSING placeholders
- follow_up_round tracking in sessions
"""

import json
import sys
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

class TestGetPlatform:
    """_get_platform() returns correct platform string."""

    def test_linux(self, monkeypatch):
        from web_app import _get_platform
        monkeypatch.setattr(sys, "platform", "linux")
        # Mock /proc/version without "microsoft" to get plain linux
        mock_open = MagicMock(side_effect=FileNotFoundError)
        with patch("builtins.open", mock_open):
            assert _get_platform() == "linux"

    def test_macos(self, monkeypatch):
        from web_app import _get_platform
        monkeypatch.setattr(sys, "platform", "darwin")
        assert _get_platform() == "macos"

    def test_windows(self, monkeypatch):
        from web_app import _get_platform
        monkeypatch.setattr(sys, "platform", "win32")
        assert _get_platform() == "windows"

    def test_wsl2(self, monkeypatch):
        from web_app import _get_platform
        monkeypatch.setattr(sys, "platform", "linux")
        mock_content = "Linux version 5.15.0-1052-microsoft-standard-WSL2"
        with patch("builtins.open", MagicMock(return_value=MagicMock(
            __enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value=mock_content))),
            __exit__=MagicMock(return_value=False),
        ))):
            assert _get_platform() == "wsl2"

    def test_unknown_platform(self, monkeypatch):
        from web_app import _get_platform
        monkeypatch.setattr(sys, "platform", "freebsd")
        assert _get_platform() == "freebsd"


class TestGetRunMode:
    """_get_run_mode() returns source or executable."""

    def test_source_mode(self, monkeypatch):
        from web_app import _get_run_mode
        monkeypatch.delattr(sys, "frozen", raising=False)
        assert _get_run_mode() == "source"

    def test_executable_mode(self, monkeypatch):
        from web_app import _get_run_mode
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        assert _get_run_mode() == "executable"


class TestExtractMissingSections:
    """_extract_missing_sections() parses MISSING placeholders."""

    def test_no_missing(self):
        from web_app import _extract_missing_sections
        assert _extract_missing_sections("NO_MISSING") == []

    def test_empty_input(self):
        from web_app import _extract_missing_sections
        assert _extract_missing_sections("") == []
        assert _extract_missing_sections(None) == []

    def test_single_missing(self):
        from web_app import _extract_missing_sections
        content = "- {{MISSING::Cause::What caused the issue?}} -> What is the root cause?"
        assert _extract_missing_sections(content) == ["Cause"]

    def test_multiple_missing(self):
        from web_app import _extract_missing_sections
        content = (
            "- {{MISSING::Cause::hint}} -> question\n"
            "- {{MISSING::Diagnosis::hint}} -> question\n"
            "- {{MISSING::Mitigation or Resolution::hint}} -> question"
        )
        result = _extract_missing_sections(content)
        assert result == ["Cause", "Diagnosis", "Mitigation or Resolution"]


# =============================================================================
# APP_STARTED EVENT
# =============================================================================

class TestAppStartedEvent:
    """app_started emitted in main()."""

    @pytest.mark.unit
    def test_app_started_emitted(self, monkeypatch):
        """main() calls init_telemetry and emits app_started."""
        import web_app

        mock_init = MagicMock()
        mock_track = MagicMock()
        mock_enabled = MagicMock(return_value=True)
        mock_active = MagicMock(return_value=True)

        monkeypatch.setattr("telemetry.init_telemetry", mock_init)
        monkeypatch.setattr("telemetry.track_event", mock_track)
        monkeypatch.setattr("telemetry.is_telemetry_enabled", mock_enabled)
        monkeypatch.setattr("telemetry.is_active", mock_active)
        # Prevent Flask from actually starting
        monkeypatch.setattr(web_app.app, "run", MagicMock())
        # Prevent browser from opening
        monkeypatch.setattr("threading.Timer", MagicMock())

        # Capture the background thread so we can wait for it
        threads_started = []
        original_thread = threading.Thread
        def _capture_thread(*args, **kwargs):
            t = original_thread(*args, **kwargs)
            threads_started.append(t)
            return t
        monkeypatch.setattr("threading.Thread", _capture_thread)

        web_app.main()

        # Wait for the background telemetry thread to complete
        for t in threads_started:
            t.join(timeout=5)

        mock_init.assert_called_once()
        # Find the app_started call
        app_started_calls = [
            c for c in mock_track.call_args_list
            if c[0][0] == "app_started"
        ]
        assert len(app_started_calls) == 1
        props = app_started_calls[0][1]["properties"]
        assert "version" in props
        assert "platform" in props
        assert "python_version" in props
        assert "run_mode" in props

    @pytest.mark.unit
    def test_opt_out_logged(self, monkeypatch, capsys):
        """main() logs telemetry disabled status when opted out."""
        import web_app

        monkeypatch.setattr("telemetry.init_telemetry", MagicMock())
        monkeypatch.setattr("telemetry.track_event", MagicMock())
        monkeypatch.setattr("telemetry.is_telemetry_enabled", MagicMock(return_value=False))
        monkeypatch.setattr(web_app.app, "run", MagicMock())
        monkeypatch.setattr("threading.Timer", MagicMock())

        web_app.main()
        captured = capsys.readouterr()
        assert "disabled" in captured.out.lower()


# =============================================================================
# TSG_GENERATED EVENT
# =============================================================================

class TestTsgGeneratedEvent:
    """tsg_generated emitted on successful pipeline result."""

    @pytest.mark.unit
    def test_tsg_generated_emitted(self, monkeypatch):
        """Success path emits tsg_generated with all required fields."""
        from web_app import generate_pipeline_sse_events
        from pipeline import PipelineResult, PipelineStage

        mock_result = PipelineResult(
            success=True,
            tsg_content="# Test TSG",
            questions_content="NO_MISSING",
            research_report="Research report",
            thread_id="conv_123",
            stages_completed=[PipelineStage.RESEARCH, PipelineStage.WRITE, PipelineStage.REVIEW],
            duration_seconds=42.5,
            research_duration_s=10.0,
            write_duration_s=20.0,
            review_duration_s=12.5,
            research_input_tokens=1000,
            research_output_tokens=500,
            write_input_tokens=800,
            write_output_tokens=400,
            review_input_tokens=600,
            review_output_tokens=300,
            total_tokens=3600,
            notes_line_count=25,
            image_count=2,
        )

        mock_track = MagicMock()
        monkeypatch.setattr("telemetry.track_event", mock_track)

        with patch("web_app.run_pipeline", return_value=mock_result):
            list(generate_pipeline_sse_events("test notes"))  # drain generator for side effects

        # Find tsg_generated call
        tsg_calls = [c for c in mock_track.call_args_list if c[0][0] == "tsg_generated"]
        assert len(tsg_calls) == 1

        props = tsg_calls[0][1]["properties"]
        assert props["version"]
        assert props["had_missing"] == "False"
        assert props["follow_up_round"] == "0"
        assert "model" in props

        measurements = tsg_calls[0][1]["measurements"]
        assert measurements["duration_seconds"] == 42.5
        assert measurements["total_tokens"] == 3600
        assert measurements["notes_line_count"] == 25
        assert measurements["image_count"] == 2

    @pytest.mark.unit
    def test_tsg_generated_with_missing(self, monkeypatch):
        """tsg_generated event includes missing_sections when present."""
        from web_app import generate_pipeline_sse_events
        from pipeline import PipelineResult, PipelineStage

        mock_result = PipelineResult(
            success=True,
            tsg_content="# TSG with {{MISSING::Cause::hint}}",
            questions_content="- {{MISSING::Cause::hint}} -> What caused it?\n- {{MISSING::Diagnosis::hint}} -> How to diagnose?",
            research_report="Research",
            thread_id="conv_456",
            stages_completed=[PipelineStage.RESEARCH, PipelineStage.WRITE, PipelineStage.REVIEW],
        )

        mock_track = MagicMock()
        monkeypatch.setattr("telemetry.track_event", mock_track)

        with patch("web_app.run_pipeline", return_value=mock_result):
            list(generate_pipeline_sse_events("test notes"))

        tsg_calls = [c for c in mock_track.call_args_list if c[0][0] == "tsg_generated"]
        assert len(tsg_calls) == 1
        props = tsg_calls[0][1]["properties"]
        assert props["had_missing"] == "True"
        assert "Cause" in props["missing_sections"]
        assert "Diagnosis" in props["missing_sections"]
        measurements = tsg_calls[0][1]["measurements"]
        assert measurements["missing_count"] == 2


# =============================================================================
# PIPELINE_ERROR EVENT
# =============================================================================

class TestPipelineErrorEvent:
    """pipeline_error emitted on pipeline failure."""

    @pytest.mark.unit
    def test_pipeline_error_from_failed_result(self, monkeypatch):
        """pipeline_error emitted when result.success is False."""
        from web_app import generate_pipeline_sse_events
        from pipeline import PipelineResult, PipelineStage

        mock_result = PipelineResult(
            success=False,
            error="Pipeline research failed: rate limit",
            retry_count=2,
            stages_completed=[],
        )
        mock_result.metadata["error_stage"] = "research"
        mock_result.metadata["error_class"] = "rate_limit"

        mock_track = MagicMock()
        monkeypatch.setattr("telemetry.track_event", mock_track)

        with patch("web_app.run_pipeline", return_value=mock_result):
            list(generate_pipeline_sse_events("test notes"))

        error_calls = [c for c in mock_track.call_args_list if c[0][0] == "pipeline_error"]
        assert len(error_calls) == 1
        props = error_calls[0][1]["properties"]
        assert props["stage"] == "research"
        assert props["error_class"] == "rate_limit"
        measurements = error_calls[0][1]["measurements"]
        assert measurements["retry_count"] == 2

    @pytest.mark.unit
    def test_pipeline_error_from_exception(self, monkeypatch):
        """pipeline_error emitted when run_pipeline raises PipelineError."""
        from web_app import generate_pipeline_sse_events
        from pipeline import PipelineError, PipelineStage

        error = PipelineError(
            stage=PipelineStage.WRITE,
            original_error=RuntimeError("Connection timed out"),
        )

        mock_track = MagicMock()
        monkeypatch.setattr("telemetry.track_event", mock_track)

        with patch("web_app.run_pipeline", side_effect=error):
            list(generate_pipeline_sse_events("test notes"))

        error_calls = [c for c in mock_track.call_args_list if c[0][0] == "pipeline_error"]
        assert len(error_calls) == 1
        props = error_calls[0][1]["properties"]
        assert props["stage"] == "write"
        assert props["version"]

    @pytest.mark.unit
    def test_pipeline_error_unknown_for_non_pipeline_exception(self, monkeypatch):
        """pipeline_error uses 'unknown' stage for non-PipelineError exceptions."""
        from web_app import generate_pipeline_sse_events

        mock_track = MagicMock()
        monkeypatch.setattr("telemetry.track_event", mock_track)

        with patch("web_app.run_pipeline", side_effect=ValueError("config problem")):
            list(generate_pipeline_sse_events("test notes"))

        error_calls = [c for c in mock_track.call_args_list if c[0][0] == "pipeline_error"]
        assert len(error_calls) == 1
        props = error_calls[0][1]["properties"]
        assert props["stage"] == "unknown"
        assert props["error_class"] == "unknown"


# =============================================================================
# PII_BLOCKED EVENT
# =============================================================================

class TestPiiBlockedEvent:
    """pii_blocked emitted when PII gate triggers."""

    @pytest.mark.unit
    def test_pii_blocked_on_generate(self, client, monkeypatch):
        """PII in notes triggers pii_blocked with input_type=notes."""
        mock_track = MagicMock()
        monkeypatch.setattr("telemetry.track_event", mock_track)

        pii_result = {
            "pii_detected": True,
            "findings": [
                {"text": "test@email.com", "category": "Email", "confidence": 0.95, "offset": 0, "length": 14}
            ],
            "redacted_text": "***@email.com",
            "error": None,
            "hint": None,
        }
        with patch("web_app.check_for_pii", return_value=pii_result):
            response = client.post(
                "/api/generate/stream",
                json={"notes": "Contact test@email.com for help"},
            )

        assert response.status_code == 400

        pii_calls = [c for c in mock_track.call_args_list if c[0][0] == "pii_blocked"]
        assert len(pii_calls) == 1
        props = pii_calls[0][1]["properties"]
        assert props["input_type"] == "notes"
        assert props["action"] == "blocked"
        measurements = pii_calls[0][1]["measurements"]
        assert measurements["entity_count"] == 1

    @pytest.mark.unit
    def test_pii_blocked_on_answer(self, client, monkeypatch):
        """PII in follow-up answers triggers pii_blocked with input_type=followup."""
        import web_app
        mock_track = MagicMock()
        monkeypatch.setattr("telemetry.track_event", mock_track)

        # Set up a valid session
        web_app.sessions["test-thread-123"] = {
            "notes": "original notes",
            "current_tsg": "# TSG",
            "questions": "question",
            "research_report": "research",
        }

        pii_result = {
            "pii_detected": True,
            "findings": [
                {"text": "555-1234", "category": "PhoneNumber", "confidence": 0.9, "offset": 0, "length": 8},
                {"text": "john@example.com", "category": "Email", "confidence": 0.95, "offset": 10, "length": 16},
            ],
            "redacted_text": "*** and ***",
            "error": None,
            "hint": None,
        }
        with patch("web_app.check_for_pii", return_value=pii_result):
            response = client.post(
                "/api/answer/stream",
                json={"thread_id": "test-thread-123", "answers": "Call 555-1234 or john@example.com"},
            )

        assert response.status_code == 400

        pii_calls = [c for c in mock_track.call_args_list if c[0][0] == "pii_blocked"]
        assert len(pii_calls) == 1
        props = pii_calls[0][1]["properties"]
        assert props["input_type"] == "followup"
        measurements = pii_calls[0][1]["measurements"]
        assert measurements["entity_count"] == 2

        # Clean up
        web_app.sessions.pop("test-thread-123", None)


# =============================================================================
# SETUP_COMPLETED EVENT
# =============================================================================

class TestSetupCompletedEvent:
    """setup_completed emitted on successful agent creation."""

    @pytest.mark.unit
    def test_setup_completed_emitted(self, client, monkeypatch):
        """Successful agent creation emits setup_completed."""
        mock_track = MagicMock()
        monkeypatch.setattr("telemetry.track_event", mock_track)
        monkeypatch.setenv("PROJECT_ENDPOINT", "https://test.services.ai.azure.com/api/projects/test-project")
        monkeypatch.setenv("MODEL_DEPLOYMENT_NAME", "gpt-5.2")
        monkeypatch.setenv("AGENT_NAME", "TestTSG")

        # Mock agent creation
        mock_agent = MagicMock()
        mock_agent.name = "TestTSG-Researcher"
        mock_agent.version = "1.0"
        mock_agent.id = "agent-123"

        mock_project = MagicMock()
        mock_project.__enter__ = MagicMock(return_value=mock_project)
        mock_project.__exit__ = MagicMock(return_value=False)
        mock_project.agents.create_version.return_value = mock_agent

        with patch("azure.ai.projects.AIProjectClient", return_value=mock_project), \
             patch("web_app.save_agent_ids"):
            response = client.post("/api/create-agent")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True

        setup_calls = [c for c in mock_track.call_args_list if c[0][0] == "setup_completed"]
        assert len(setup_calls) == 1
        props = setup_calls[0][1]["properties"]
        assert props["model_deployment"] == "gpt-5.2"
        assert props["version"]


# =============================================================================
# TSG_COPIED EVENT
# =============================================================================

class TestTsgCopiedEvent:
    """tsg_copied endpoint works correctly."""

    @pytest.mark.unit
    def test_copied_returns_204(self, client, monkeypatch):
        """POST /api/telemetry/copied returns 204."""
        mock_track = MagicMock()
        monkeypatch.setattr("telemetry.track_event", mock_track)

        response = client.post(
            "/api/telemetry/copied",
            json={"follow_up_round": 2},
        )
        assert response.status_code == 204

    @pytest.mark.unit
    def test_copied_emits_event(self, client, monkeypatch):
        """POST /api/telemetry/copied emits tsg_copied event with action."""
        mock_track = MagicMock()
        monkeypatch.setattr("telemetry.track_event", mock_track)

        client.post(
            "/api/telemetry/copied",
            json={"follow_up_round": 3, "action": "copy"},
        )

        copied_calls = [c for c in mock_track.call_args_list if c[0][0] == "tsg_copied"]
        assert len(copied_calls) == 1
        props = copied_calls[0][1]["properties"]
        assert props["follow_up_round"] == "3"
        assert props["action"] == "copy"
        assert props["version"]

    @pytest.mark.unit
    def test_copied_no_body(self, client, monkeypatch):
        """POST /api/telemetry/copied works with no body (defaults action to copy)."""
        mock_track = MagicMock()
        monkeypatch.setattr("telemetry.track_event", mock_track)

        response = client.post("/api/telemetry/copied")
        assert response.status_code == 204

        copied_calls = [c for c in mock_track.call_args_list if c[0][0] == "tsg_copied"]
        assert len(copied_calls) == 1
        props = copied_calls[0][1]["properties"]
        assert props["follow_up_round"] == "0"
        assert props["action"] == "copy"

    @pytest.mark.unit
    def test_download_emits_event(self, client, monkeypatch):
        """POST /api/telemetry/copied with action=download emits correctly."""
        mock_track = MagicMock()
        monkeypatch.setattr("telemetry.track_event", mock_track)

        client.post(
            "/api/telemetry/copied",
            json={"follow_up_round": 1, "action": "download"},
        )

        copied_calls = [c for c in mock_track.call_args_list if c[0][0] == "tsg_copied"]
        assert len(copied_calls) == 1
        props = copied_calls[0][1]["properties"]
        assert props["action"] == "download"
        assert props["follow_up_round"] == "1"


# =============================================================================
# FOLLOW-UP ROUND TRACKING
# =============================================================================

class TestFollowUpRoundTracking:
    """follow_up_round is tracked correctly in sessions."""

    @pytest.mark.unit
    def test_initial_generation_round_zero(self, monkeypatch):
        """Initial generation uses follow_up_round=0."""
        from web_app import generate_pipeline_sse_events
        from pipeline import PipelineResult, PipelineStage

        mock_result = PipelineResult(
            success=True,
            tsg_content="# TSG",
            questions_content="NO_MISSING",
            thread_id="conv_100",
            stages_completed=[PipelineStage.RESEARCH, PipelineStage.WRITE, PipelineStage.REVIEW],
        )

        mock_track = MagicMock()
        monkeypatch.setattr("telemetry.track_event", mock_track)

        with patch("web_app.run_pipeline", return_value=mock_result):
            list(generate_pipeline_sse_events("test notes"))

        tsg_calls = [c for c in mock_track.call_args_list if c[0][0] == "tsg_generated"]
        assert tsg_calls[0][1]["properties"]["follow_up_round"] == "0"

    @pytest.mark.unit
    def test_follow_up_increments_round(self, monkeypatch):
        """Follow-up generation uses incremented round from session."""
        import web_app
        from web_app import generate_pipeline_sse_events
        from pipeline import PipelineResult, PipelineStage

        # Set up a session with round 0
        web_app.sessions["conv_200"] = {
            "notes": "notes",
            "current_tsg": "# TSG",
            "questions": "question",
            "research_report": "research",
            "follow_up_round": 0,
        }

        mock_result = PipelineResult(
            success=True,
            tsg_content="# Updated TSG",
            questions_content="NO_MISSING",
            thread_id="conv_200",
            stages_completed=[PipelineStage.WRITE, PipelineStage.REVIEW],
        )

        mock_track = MagicMock()
        monkeypatch.setattr("telemetry.track_event", mock_track)

        with patch("web_app.run_pipeline", return_value=mock_result):
            list(generate_pipeline_sse_events("notes", thread_id="conv_200", answers="answer"))

        tsg_calls = [c for c in mock_track.call_args_list if c[0][0] == "tsg_generated"]
        assert tsg_calls[0][1]["properties"]["follow_up_round"] == "1"

        # Clean up
        web_app.sessions.pop("conv_200", None)

    @pytest.mark.unit
    def test_follow_up_round_stored_in_session(self, monkeypatch):
        """follow_up_round is persisted in session data on success."""
        import web_app
        from web_app import generate_pipeline_sse_events
        from pipeline import PipelineResult, PipelineStage

        mock_result = PipelineResult(
            success=True,
            tsg_content="# TSG",
            questions_content="NO_MISSING",
            thread_id="conv_300",
            stages_completed=[PipelineStage.RESEARCH, PipelineStage.WRITE, PipelineStage.REVIEW],
        )

        mock_track = MagicMock()
        monkeypatch.setattr("telemetry.track_event", mock_track)

        with patch("web_app.run_pipeline", return_value=mock_result):
            list(generate_pipeline_sse_events("notes"))

        assert web_app.sessions["conv_300"]["follow_up_round"] == 0

        # Clean up
        web_app.sessions.pop("conv_300", None)


# =============================================================================
# ERROR METADATA IN PIPELINE RESULT
# =============================================================================

class TestPipelineErrorMetadata:
    """PipelineResult carries error classification in metadata."""

    @pytest.mark.unit
    def test_error_metadata_populated(self):
        """PipelineResult metadata stores error_stage and error_class."""
        from pipeline import PipelineResult
        result = PipelineResult(success=False, error="test error")
        result.metadata["error_stage"] = "research"
        result.metadata["error_class"] = "timeout"

        assert result.metadata["error_stage"] == "research"
        assert result.metadata["error_class"] == "timeout"

    @pytest.mark.unit
    def test_error_metadata_defaults_empty(self):
        """PipelineResult metadata defaults to empty dict."""
        from pipeline import PipelineResult
        result = PipelineResult(success=False)
        assert result.metadata == {}
        assert result.metadata.get("error_stage", "unknown") == "unknown"
        assert result.metadata.get("error_class", "unknown") == "unknown"
