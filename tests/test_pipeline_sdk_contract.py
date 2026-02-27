"""
test_pipeline_sdk_contract.py — Tests that validate the SDK API contract.

These tests verify that the pipeline passes the correct parameters to the
Azure AI Foundry SDK (openai_client.responses.create). They catch breaking
changes like the agent → agent_reference migration (SDK 2.0.0b4).

These are unit tests that mock the OpenAI client — no Azure credentials needed.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from pipeline import TSGPipeline, PipelineStage


# =============================================================================
# Helpers
# =============================================================================

def _make_pipeline(**overrides) -> TSGPipeline:
    """Create a TSGPipeline with sensible test defaults."""
    defaults = dict(
        project_endpoint="https://fake.services.ai.azure.com/api/projects/test",
        researcher_agent_name="TSG-Builder-Researcher",
        writer_agent_name="TSG-Builder-Writer",
        reviewer_agent_name="TSG-Builder-Reviewer",
        model_name="gpt-5.2",
        test_mode=True,
    )
    defaults.update(overrides)
    return TSGPipeline(**defaults)


def _mock_stream_with_completed_event(text: str = "done"):
    """Return a mock stream that yields a single response.completed event.

    This is the minimal stream the pipeline needs to produce a result.
    """
    event = Mock()
    event.type = "response.completed"
    event.response = Mock()
    event.response.conversation_id = "conv_test123"
    event.response.id = "resp_test456"

    # The process_pipeline_v2_stream function looks for output items
    output_item = Mock()
    output_item.type = "message"
    content_part = Mock()
    content_part.type = "output_text"
    content_part.text = text
    output_item.content = [content_part]
    event.response.output = [output_item]

    return iter([event])


# =============================================================================
# Tests: extra_body contract
# =============================================================================

@pytest.mark.unit
class TestAgentReferenceContract:
    """Verify the extra_body shape passed to responses.create().

    The Azure AI Foundry API (SDK ≥ 2.0.0b4) requires the agent reference
    to be sent under the 'agent_reference' key, NOT 'agent'.
    See: https://learn.microsoft.com/azure/ai-foundry/agents/how-to/migrate
    """

    def test_extra_body_uses_agent_reference_key(self):
        """extra_body must use 'agent_reference', not 'agent'."""
        pipeline = _make_pipeline()
        mock_project = Mock()
        mock_openai = Mock()

        # responses.create returns an iterable stream
        mock_openai.responses.create.return_value = _mock_stream_with_completed_event()

        with patch("pipeline._iterate_with_timeout", side_effect=lambda stream, *a, **kw: stream):
            pipeline._run_stage(
                project=mock_project,
                openai_client=mock_openai,
                agent_name="TSG-Builder-Researcher",
                stage=PipelineStage.RESEARCH,
                user_message="test prompt",
            )

        # Extract the kwargs passed to responses.create
        call_kwargs = mock_openai.responses.create.call_args
        extra_body = call_kwargs.kwargs.get("extra_body") or call_kwargs[1].get("extra_body")

        # CRITICAL: must be 'agent_reference', not 'agent'
        assert "agent_reference" in extra_body, (
            f"extra_body must contain 'agent_reference' key (got keys: {list(extra_body.keys())}). "
            "See SDK 2.0.0b4 migration: https://learn.microsoft.com/azure/ai-foundry/agents/how-to/migrate"
        )
        assert "agent" not in extra_body, (
            "extra_body must NOT contain deprecated 'agent' key — "
            "use 'agent_reference' instead (SDK ≥ 2.0.0b4)"
        )

    def test_agent_reference_has_name_and_type(self):
        """agent_reference must include 'name' and 'type' fields."""
        pipeline = _make_pipeline()
        mock_project = Mock()
        mock_openai = Mock()
        mock_openai.responses.create.return_value = _mock_stream_with_completed_event()

        with patch("pipeline._iterate_with_timeout", side_effect=lambda stream, *a, **kw: stream):
            pipeline._run_stage(
                project=mock_project,
                openai_client=mock_openai,
                agent_name="TSG-Builder-Writer",
                stage=PipelineStage.WRITE,
                user_message="test prompt",
            )

        extra_body = mock_openai.responses.create.call_args.kwargs["extra_body"]
        agent_ref = extra_body["agent_reference"]

        assert agent_ref["name"] == "TSG-Builder-Writer"
        assert agent_ref["type"] == "agent_reference"

    def test_agent_name_propagated_correctly(self):
        """The agent name passed to _run_stage should appear in extra_body."""
        pipeline = _make_pipeline()
        mock_project = Mock()
        mock_openai = Mock()
        mock_openai.responses.create.return_value = _mock_stream_with_completed_event()

        with patch("pipeline._iterate_with_timeout", side_effect=lambda stream, *a, **kw: stream):
            pipeline._run_stage(
                project=mock_project,
                openai_client=mock_openai,
                agent_name="Custom-Agent-Name",
                stage=PipelineStage.REVIEW,
                user_message="review this",
            )

        extra_body = mock_openai.responses.create.call_args.kwargs["extra_body"]
        assert extra_body["agent_reference"]["name"] == "Custom-Agent-Name"


# =============================================================================
# Tests: conversation/session continuity contract
# =============================================================================

@pytest.mark.unit
class TestSessionContinuityContract:
    """Verify conversation and response ID handling in responses.create()."""

    def test_no_conversation_when_fresh(self):
        """First call (no conversation_id) should not include conversation param."""
        pipeline = _make_pipeline()
        mock_project = Mock()
        mock_openai = Mock()
        mock_openai.responses.create.return_value = _mock_stream_with_completed_event()

        with patch("pipeline._iterate_with_timeout", side_effect=lambda stream, *a, **kw: stream):
            pipeline._run_stage(
                project=mock_project,
                openai_client=mock_openai,
                agent_name="TSG-Builder-Researcher",
                stage=PipelineStage.RESEARCH,
                user_message="test",
                conversation_id=None,
            )

        call_kwargs = mock_openai.responses.create.call_args.kwargs
        extra_body = call_kwargs["extra_body"]
        # No conversation key when starting fresh
        assert "conversation" not in extra_body
        assert "previous_response_id" not in call_kwargs

    def test_conversation_id_passed_in_extra_body(self):
        """conv_* IDs go into extra_body['conversation']."""
        pipeline = _make_pipeline()
        mock_project = Mock()
        mock_openai = Mock()
        mock_openai.responses.create.return_value = _mock_stream_with_completed_event()

        with patch("pipeline._iterate_with_timeout", side_effect=lambda stream, *a, **kw: stream):
            pipeline._run_stage(
                project=mock_project,
                openai_client=mock_openai,
                agent_name="TSG-Builder-Writer",
                stage=PipelineStage.WRITE,
                user_message="write",
                conversation_id="conv_abc123",
            )

        call_kwargs = mock_openai.responses.create.call_args.kwargs
        assert call_kwargs["extra_body"]["conversation"] == "conv_abc123"

    def test_response_id_passed_as_previous_response_id(self):
        """resp_* IDs go into top-level previous_response_id."""
        pipeline = _make_pipeline()
        mock_project = Mock()
        mock_openai = Mock()
        mock_openai.responses.create.return_value = _mock_stream_with_completed_event()

        with patch("pipeline._iterate_with_timeout", side_effect=lambda stream, *a, **kw: stream):
            pipeline._run_stage(
                project=mock_project,
                openai_client=mock_openai,
                agent_name="TSG-Builder-Reviewer",
                stage=PipelineStage.REVIEW,
                user_message="review",
                conversation_id="resp_xyz789",
            )

        call_kwargs = mock_openai.responses.create.call_args.kwargs
        assert call_kwargs["previous_response_id"] == "resp_xyz789"
        # resp_* should NOT go into extra_body
        assert "conversation" not in call_kwargs["extra_body"]

    def test_stream_kwarg_always_true(self):
        """responses.create must always be called with stream=True."""
        pipeline = _make_pipeline()
        mock_project = Mock()
        mock_openai = Mock()
        mock_openai.responses.create.return_value = _mock_stream_with_completed_event()

        with patch("pipeline._iterate_with_timeout", side_effect=lambda stream, *a, **kw: stream):
            pipeline._run_stage(
                project=mock_project,
                openai_client=mock_openai,
                agent_name="TSG-Builder-Researcher",
                stage=PipelineStage.RESEARCH,
                user_message="test",
            )

        call_kwargs = mock_openai.responses.create.call_args.kwargs
        assert call_kwargs["stream"] is True

    def test_input_message_passed_through(self):
        """The user_message must appear as 'input' in the API call."""
        pipeline = _make_pipeline()
        mock_project = Mock()
        mock_openai = Mock()
        mock_openai.responses.create.return_value = _mock_stream_with_completed_event()

        with patch("pipeline._iterate_with_timeout", side_effect=lambda stream, *a, **kw: stream):
            pipeline._run_stage(
                project=mock_project,
                openai_client=mock_openai,
                agent_name="TSG-Builder-Writer",
                stage=PipelineStage.WRITE,
                user_message="Generate TSG for topic X",
            )

        call_kwargs = mock_openai.responses.create.call_args.kwargs
        assert call_kwargs["input"] == "Generate TSG for topic X"
