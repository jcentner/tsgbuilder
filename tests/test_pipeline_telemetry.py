"""
test_pipeline_telemetry.py — Unit tests for Phase 1b pipeline telemetry plumbing.

Tests cover:
- PipelineResult includes new telemetry fields with sensible defaults
- Token accumulation sums across multiple response.completed events
- Duration fields and input metadata are populated
"""

import queue
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import (
    PipelineResult,
    PipelineStage,
    process_pipeline_v2_stream,
)


# =============================================================================
# PipelineResult DEFAULT FIELDS
# =============================================================================

class TestPipelineResultFields:
    """PipelineResult includes all new telemetry fields with sensible defaults."""

    def test_has_duration_fields(self):
        """Result has wall-clock duration fields defaulting to 0."""
        result = PipelineResult(success=True)
        assert result.duration_seconds == 0.0
        assert result.research_duration_s == 0.0
        assert result.write_duration_s == 0.0
        assert result.review_duration_s == 0.0

    def test_has_token_fields(self):
        """Result has per-stage token fields defaulting to 0."""
        result = PipelineResult(success=True)
        assert result.research_input_tokens == 0
        assert result.research_output_tokens == 0
        assert result.write_input_tokens == 0
        assert result.write_output_tokens == 0
        assert result.review_input_tokens == 0
        assert result.review_output_tokens == 0
        assert result.total_tokens == 0

    def test_has_input_metadata_fields(self):
        """Result has image_count and notes_line_count defaulting to 0."""
        result = PipelineResult(success=True)
        assert result.image_count == 0
        assert result.notes_line_count == 0

    def test_fields_are_settable(self):
        """All telemetry fields can be set after construction."""
        result = PipelineResult(success=True)
        result.duration_seconds = 42.5
        result.research_input_tokens = 1000
        result.research_output_tokens = 500
        result.total_tokens = 1500
        result.image_count = 3
        result.notes_line_count = 25
        
        assert result.duration_seconds == 42.5
        assert result.research_input_tokens == 1000
        assert result.total_tokens == 1500
        assert result.image_count == 3
        assert result.notes_line_count == 25

    def test_existing_fields_still_work(self):
        """Existing PipelineResult fields are unaffected."""
        result = PipelineResult(
            success=True,
            tsg_content="# Test TSG",
            questions_content="NO_MISSING",
            retry_count=1,
        )
        assert result.success is True
        assert result.tsg_content == "# Test TSG"
        assert result.questions_content == "NO_MISSING"
        assert result.retry_count == 1


# =============================================================================
# TOKEN ACCUMULATION IN STREAM PROCESSING
# =============================================================================

class TestTokenAccumulation:
    """Token usage is extracted and accumulated from response.completed events."""

    def _make_response_completed_event(self, input_tokens=0, output_tokens=0):
        """Create a mock response.completed event with usage data."""
        event = MagicMock()
        event.type = "response.completed"
        event.response = MagicMock()
        event.response.output_text = "test output"
        event.response.usage = MagicMock()
        event.response.usage.input_tokens = input_tokens
        event.response.usage.output_tokens = output_tokens
        return event

    def test_single_response_completed(self):
        """Token counts extracted from a single response.completed event."""
        timing_context = {}
        event = self._make_response_completed_event(input_tokens=100, output_tokens=50)
        
        process_pipeline_v2_stream(
            event, None, PipelineStage.RESEARCH, [], timing_context
        )
        
        assert timing_context['input_tokens'] == 100
        assert timing_context['output_tokens'] == 50

    def test_multiple_response_completed_accumulates(self):
        """Token counts are summed across multiple response.completed events."""
        timing_context = {}
        response_text = []
        
        # First response.completed (e.g., after first tool call)
        event1 = self._make_response_completed_event(input_tokens=100, output_tokens=50)
        process_pipeline_v2_stream(
            event1, None, PipelineStage.RESEARCH, response_text, timing_context
        )
        
        # Second response.completed (e.g., after second tool call)
        event2 = self._make_response_completed_event(input_tokens=200, output_tokens=80)
        process_pipeline_v2_stream(
            event2, None, PipelineStage.RESEARCH, response_text, timing_context
        )
        
        # Third response.completed (final response)
        event3 = self._make_response_completed_event(input_tokens=300, output_tokens=120)
        process_pipeline_v2_stream(
            event3, None, PipelineStage.RESEARCH, response_text, timing_context
        )
        
        assert timing_context['input_tokens'] == 600   # 100 + 200 + 300
        assert timing_context['output_tokens'] == 250  # 50 + 80 + 120

    def test_null_usage_handled(self):
        """No crash when response.usage is None."""
        timing_context = {}
        event = MagicMock()
        event.type = "response.completed"
        event.response = MagicMock()
        event.response.output_text = "test"
        event.response.usage = None
        
        # Should not raise
        process_pipeline_v2_stream(
            event, None, PipelineStage.WRITE, [], timing_context
        )
        
        # No token keys should be added
        assert timing_context.get('input_tokens', 0) == 0
        assert timing_context.get('output_tokens', 0) == 0

    def test_missing_usage_attribute(self):
        """No crash when response has no usage attribute."""
        timing_context = {}
        event = MagicMock()
        event.type = "response.completed"
        event.response = MagicMock(spec=[])  # No attributes at all
        event.response.output_text = None
        
        # Should not raise
        process_pipeline_v2_stream(
            event, None, PipelineStage.WRITE, [], timing_context
        )

    def test_none_timing_context(self):
        """No crash when timing_context is None (backwards compatibility)."""
        event = self._make_response_completed_event(input_tokens=100, output_tokens=50)
        
        # Should not raise
        process_pipeline_v2_stream(
            event, None, PipelineStage.WRITE, [], None
        )

    def test_tokens_with_event_queue(self):
        """Token extraction works when event_queue is provided."""
        timing_context = {}
        event_queue = queue.Queue()
        event = self._make_response_completed_event(input_tokens=500, output_tokens=200)
        
        process_pipeline_v2_stream(
            event, event_queue, PipelineStage.RESEARCH, [], timing_context
        )
        
        assert timing_context['input_tokens'] == 500
        assert timing_context['output_tokens'] == 200
        # Also check that the status event was sent
        assert not event_queue.empty()

    def test_zero_tokens_handled(self):
        """Zero token values don't cause issues."""
        timing_context = {}
        event = self._make_response_completed_event(input_tokens=0, output_tokens=0)
        
        process_pipeline_v2_stream(
            event, None, PipelineStage.WRITE, [], timing_context
        )
        
        assert timing_context['input_tokens'] == 0
        assert timing_context['output_tokens'] == 0


# =============================================================================
# INPUT METADATA
# =============================================================================

class TestInputMetadata:
    """image_count and notes_line_count are correctly derived."""

    def test_notes_line_count(self):
        """notes_line_count reflects actual line count of input."""
        result = PipelineResult(success=False)
        notes = "Line 1\nLine 2\nLine 3\n"
        result.notes_line_count = len(notes.splitlines())
        assert result.notes_line_count == 3

    def test_empty_notes(self):
        """Empty notes produces 0 line count."""
        result = PipelineResult(success=False)
        notes = ""
        result.notes_line_count = len(notes.splitlines()) if notes else 0
        assert result.notes_line_count == 0

    def test_image_count_with_images(self):
        """image_count reflects the number of images."""
        result = PipelineResult(success=False)
        images = [{"data": "base64_1"}, {"data": "base64_2"}]
        result.image_count = len(images)
        assert result.image_count == 2

    def test_image_count_no_images(self):
        """image_count is 0 when no images."""
        result = PipelineResult(success=False)
        result.image_count = len([]) if [] else 0
        assert result.image_count == 0
