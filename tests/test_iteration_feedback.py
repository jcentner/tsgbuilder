"""
test_iteration_feedback.py — Tests for iteration feedback loop (prior review context).

Tests that:
- build_writer_prompt includes prior review feedback when provided
- build_writer_prompt is unchanged without prior review
- build_review_prompt includes prior review + suppression instructions when provided 
- build_review_prompt is unchanged without prior review

Run with: pytest tests/test_iteration_feedback.py -v
"""

import json
import pytest
from tsg_constants import build_writer_prompt, build_review_prompt


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_notes():
    return "Topic: ValueError when adding multiple tools to ToolSet."


@pytest.fixture
def sample_research():
    return "## Research Report\nToolSet allows only one instance per tool type."


@pytest.fixture
def sample_prior_tsg():
    return "<!-- TSG_BEGIN -->\n# **ToolSet ValueError**\n<!-- TSG_END -->"


@pytest.fixture
def sample_review_with_feedback():
    """A review result that has accuracy_issues and suggestions."""
    return {
        "approved": True,
        "structure_issues": [],
        "accuracy_issues": [
            "OpenAPI/MCP scoped too broadly to knowledge tools limitation."
        ],
        "completeness_issues": [],
        "format_issues": [],
        "suggestions": [
            "Add tool scope collision check to Diagnosis.",
            "Consider removing GitHub issue link from Related Information.",
        ],
        "corrected_tsg": None,
    }


@pytest.fixture
def sample_review_clean():
    """A review result with no feedback (clean approval)."""
    return {
        "approved": True,
        "structure_issues": [],
        "accuracy_issues": [],
        "completeness_issues": [],
        "format_issues": [],
        "suggestions": [],
        "corrected_tsg": None,
    }


@pytest.fixture
def sample_user_answers():
    return "No internal tooling for this issue. Apply other suggestions as you see fit."


# =============================================================================
# TESTS: build_writer_prompt — baseline (no prior review)
# =============================================================================

class TestWriterPromptBaseline:
    """Writer prompt without prior review should be unchanged from prior behavior."""

    def test_no_prior_tsg_no_answers(self, sample_notes, sample_research):
        prompt = build_writer_prompt(sample_notes, sample_research)
        assert "<prior_tsg>" not in prompt
        assert "<prior_review_feedback>" not in prompt
        assert "<answers>" not in prompt

    def test_with_prior_tsg_no_answers(self, sample_notes, sample_research, sample_prior_tsg):
        prompt = build_writer_prompt(sample_notes, sample_research, prior_tsg=sample_prior_tsg)
        assert "<prior_tsg>" in prompt
        assert sample_prior_tsg in prompt
        assert "<prior_review_feedback>" not in prompt
        assert "<answers>" not in prompt

    def test_with_answers_no_review(self, sample_notes, sample_research, sample_prior_tsg, sample_user_answers):
        """Answers without prior review should use original MISSING-replacement instruction."""
        prompt = build_writer_prompt(
            sample_notes, sample_research,
            prior_tsg=sample_prior_tsg,
            user_answers=sample_user_answers,
        )
        assert "<answers>" in prompt
        assert sample_user_answers in prompt
        assert "Replace {{MISSING::...}} placeholders with these answers." in prompt
        # Should NOT have the two-part instruction
        assert "reviewer's suggestions" not in prompt
        assert "<prior_review_feedback>" not in prompt


# =============================================================================
# TESTS: build_writer_prompt — with prior review
# =============================================================================

class TestWriterPromptWithReview:
    """Writer prompt with prior review should include feedback and two-part instruction."""

    def test_includes_review_feedback(
        self, sample_notes, sample_research, sample_prior_tsg,
        sample_review_with_feedback, sample_user_answers,
    ):
        prompt = build_writer_prompt(
            sample_notes, sample_research,
            prior_tsg=sample_prior_tsg,
            user_answers=sample_user_answers,
            prior_review=sample_review_with_feedback,
        )
        assert "<prior_review_feedback>" in prompt
        assert "accuracy_issues" in prompt
        assert "suggestions" in prompt
        assert "OpenAPI/MCP" in prompt

    def test_two_part_instruction(
        self, sample_notes, sample_research, sample_prior_tsg,
        sample_review_with_feedback, sample_user_answers,
    ):
        prompt = build_writer_prompt(
            sample_notes, sample_research,
            prior_tsg=sample_prior_tsg,
            user_answers=sample_user_answers,
            prior_review=sample_review_with_feedback,
        )
        # Should have the iteration-aware instruction, not the simple one
        assert "reviewer's suggestions" in prompt
        assert "apply suggestions the user accepted" in prompt
        assert "leave unchanged anything the user dismissed" in prompt
        # Should NOT have the old simple instruction
        assert "Replace {{MISSING::...}} placeholders with these answers.\n" not in prompt

    def test_review_without_answers_includes_feedback_only(
        self, sample_notes, sample_research, sample_prior_tsg,
        sample_review_with_feedback,
    ):
        """Prior review without answers should include feedback block but no answer instruction."""
        prompt = build_writer_prompt(
            sample_notes, sample_research,
            prior_tsg=sample_prior_tsg,
            prior_review=sample_review_with_feedback,
        )
        assert "<prior_review_feedback>" in prompt
        assert "<answers>" not in prompt

    def test_clean_review_no_feedback_block(
        self, sample_notes, sample_research, sample_prior_tsg,
        sample_review_clean, sample_user_answers,
    ):
        """Clean review (empty issues/suggestions) should NOT add prior_review_feedback."""
        prompt = build_writer_prompt(
            sample_notes, sample_research,
            prior_tsg=sample_prior_tsg,
            user_answers=sample_user_answers,
            prior_review=sample_review_clean,
        )
        assert "<prior_review_feedback>" not in prompt

    def test_empty_suggestions_not_included(
        self, sample_notes, sample_research, sample_prior_tsg,
        sample_user_answers,
    ):
        """Review with only empty arrays should not produce feedback block."""
        review = {
            "approved": True,
            "accuracy_issues": [],
            "suggestions": [],
            "completeness_issues": [],
        }
        prompt = build_writer_prompt(
            sample_notes, sample_research,
            prior_tsg=sample_prior_tsg,
            user_answers=sample_user_answers,
            prior_review=review,
        )
        assert "<prior_review_feedback>" not in prompt


# =============================================================================
# TESTS: build_review_prompt — baseline (no prior review)
# =============================================================================

class TestReviewPromptBaseline:
    """Review prompt without prior review should be unchanged from prior behavior."""

    def test_no_prior_review(self, sample_notes, sample_research, sample_prior_tsg):
        prompt = build_review_prompt(sample_prior_tsg, sample_research, sample_notes)
        assert "<prior_review>" not in prompt
        assert "<user_response_to_review>" not in prompt
        assert "Do NOT re-raise" not in prompt

    def test_prior_review_without_answers(
        self, sample_notes, sample_research, sample_prior_tsg,
        sample_review_with_feedback,
    ):
        """Prior review without user answers should not add suppression context."""
        prompt = build_review_prompt(
            sample_prior_tsg, sample_research, sample_notes,
            prior_review=sample_review_with_feedback,
        )
        assert "<prior_review>" not in prompt
        assert "Do NOT re-raise" not in prompt


# =============================================================================
# TESTS: build_review_prompt — with prior review + answers
# =============================================================================

class TestReviewPromptWithReview:
    """Review prompt with prior review + answers should include suppression instructions."""

    def test_includes_prior_review_and_response(
        self, sample_notes, sample_research, sample_prior_tsg,
        sample_review_with_feedback, sample_user_answers,
    ):
        prompt = build_review_prompt(
            sample_prior_tsg, sample_research, sample_notes,
            prior_review=sample_review_with_feedback,
            user_answers=sample_user_answers,
        )
        assert "<prior_review>" in prompt
        assert "<user_response_to_review>" in prompt
        assert sample_user_answers in prompt

    def test_suppression_instruction(
        self, sample_notes, sample_research, sample_prior_tsg,
        sample_review_with_feedback, sample_user_answers,
    ):
        prompt = build_review_prompt(
            sample_prior_tsg, sample_research, sample_notes,
            prior_review=sample_review_with_feedback,
            user_answers=sample_user_answers,
        )
        assert "Do NOT re-raise suggestions the user explicitly dismissed" in prompt
        assert "Only flag NEW issues" in prompt

    def test_review_feedback_json_is_valid(
        self, sample_notes, sample_research, sample_prior_tsg,
        sample_review_with_feedback, sample_user_answers,
    ):
        """The prior_review JSON embedded in the prompt should be parseable."""
        prompt = build_review_prompt(
            sample_prior_tsg, sample_research, sample_notes,
            prior_review=sample_review_with_feedback,
            user_answers=sample_user_answers,
        )
        # Extract JSON between <prior_review> markers
        start = prompt.find("<prior_review>") + len("<prior_review>")
        end = prompt.find("</prior_review>")
        json_str = prompt[start:end].strip()
        parsed = json.loads(json_str)
        assert "accuracy_issues" in parsed
        assert "suggestions" in parsed

    def test_clean_review_no_suppression(
        self, sample_notes, sample_research, sample_prior_tsg,
        sample_review_clean, sample_user_answers,
    ):
        """Clean review (empty issues) should not add suppression context."""
        prompt = build_review_prompt(
            sample_prior_tsg, sample_research, sample_notes,
            prior_review=sample_review_clean,
            user_answers=sample_user_answers,
        )
        assert "<prior_review>" not in prompt
        assert "Do NOT re-raise" not in prompt
