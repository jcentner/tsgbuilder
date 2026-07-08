"""
test_pipeline_contract_stability.py — Freeze the public pipeline output contract.

TSG Builder is now consumed both standalone and as a dependency by downstream
internal apps. Those consumers parse the pipeline's marker strings, the review
JSON shape, and the validation return shape. A change to any of these is a
multi-consumer breaking event.

This test intentionally pins the contract with literal, hard-coded expected
values (NOT by importing the same constant it is checking). If a change here is
deliberate, update the literals AND provide a deprecation path for consumers.

Run with: pytest tests/test_pipeline_contract_stability.py -v
"""

import inspect

import pytest

import tsg_constants
from tsg_constants import (
    validate_tsg_output,
    ensure_required_diagnosis_line,
    extract_review_block,
    extract_research_block,
)


# =============================================================================
# Marker strings — parsed byte-for-byte by downstream consumers
# =============================================================================

class TestMarkerContract:
    """Marker literals must not change without a deprecation path."""

    @pytest.mark.unit
    def test_marker_literals_frozen(self):
        expected = {
            "TSG_BEGIN": "<!-- TSG_BEGIN -->",
            "TSG_END": "<!-- TSG_END -->",
            "QUESTIONS_BEGIN": "<!-- QUESTIONS_BEGIN -->",
            "QUESTIONS_END": "<!-- QUESTIONS_END -->",
            "RESEARCH_BEGIN": "<!-- RESEARCH_BEGIN -->",
            "RESEARCH_END": "<!-- RESEARCH_END -->",
            "REVIEW_BEGIN": "<!-- REVIEW_BEGIN -->",
            "REVIEW_END": "<!-- REVIEW_END -->",
        }
        for name, literal in expected.items():
            assert getattr(tsg_constants, name) == literal, (
                f"{name} changed — this breaks downstream parsers. "
                "Update the literal here only with a deprecation path."
            )


# =============================================================================
# Required TSG structure — consumed by publishers and validators
# =============================================================================

class TestStructureContract:
    """Required headings and mandatory literals must stay stable."""

    @pytest.mark.unit
    def test_required_toc_frozen(self):
        assert tsg_constants.REQUIRED_TOC == "[[_TOC_]]"

    @pytest.mark.unit
    def test_required_diagnosis_line_frozen(self):
        assert tsg_constants.REQUIRED_DIAGNOSIS_LINE == (
            "Don't Remove This Text: Results of the Diagnosis should be "
            "attached in the Case notes/ICM."
        )

    @pytest.mark.unit
    def test_required_headings_frozen(self):
        assert tsg_constants.REQUIRED_TSG_HEADINGS == [
            "# **Issue Description / Symptoms**",
            "# **When does the TSG not Apply**",
            "# **Diagnosis**",
            "# **Questions to Ask the Customer**",
            "# **Cause**",
            "# **Mitigation or Resolution**",
            "# **Root Cause to be shared with Customer**",
            "# **Related Information**",
            "# **Tags or Prompts**",
        ]


# =============================================================================
# Function return shapes — consumers destructure these dicts
# =============================================================================

class TestReturnShapeContract:
    """validate_tsg_output() must keep its documented keys."""

    @pytest.mark.unit
    def test_validate_tsg_output_keys(self):
        result = validate_tsg_output("")
        assert set(result.keys()) >= {
            "valid",
            "issues",
            "tsg_content",
            "questions_content",
        }

    @pytest.mark.unit
    def test_public_functions_exist(self):
        # Additive-only surface: these must remain importable for consumers.
        assert callable(validate_tsg_output)
        assert callable(ensure_required_diagnosis_line)
        assert callable(extract_review_block)
        assert callable(extract_research_block)

    @pytest.mark.unit
    def test_ensure_required_diagnosis_line_signature(self):
        sig = inspect.signature(ensure_required_diagnosis_line)
        assert list(sig.parameters) == ["tsg_content"]


# =============================================================================
# Review JSON schema — the reviewer output keys consumers rely on
# =============================================================================

class TestReviewSchemaContract:
    """The review block must parse and expose its documented keys."""

    @pytest.mark.unit
    def test_review_block_documented_keys_parse(self):
        review_json = (
            '{\n'
            '  "approved": true,\n'
            '  "structure_issues": [],\n'
            '  "accuracy_issues": [],\n'
            '  "completeness_issues": [],\n'
            '  "format_issues": [],\n'
            '  "suggestions": [],\n'
            '  "corrected_tsg": null\n'
            '}'
        )
        response = f"{tsg_constants.REVIEW_BEGIN}\n{review_json}\n{tsg_constants.REVIEW_END}"
        parsed = extract_review_block(response)
        assert parsed is not None
        assert set(parsed.keys()) == {
            "approved",
            "structure_issues",
            "accuracy_issues",
            "completeness_issues",
            "format_issues",
            "suggestions",
            "corrected_tsg",
        }
