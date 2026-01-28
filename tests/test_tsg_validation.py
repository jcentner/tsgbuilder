"""
test_tsg_validation.py — Tests for TSG output validation.

Tests the validate_tsg_output() function from tsg_constants.py.

Run with: pytest tests/test_tsg_validation.py -v
"""

import pytest
from tsg_constants import (
    validate_tsg_output,
    TSG_BEGIN,
    TSG_END,
    QUESTIONS_BEGIN,
    QUESTIONS_END,
    REQUIRED_TSG_HEADINGS,
    REQUIRED_DIAGNOSIS_LINE,
    REQUIRED_TOC,
)


# =============================================================================
# FIXTURES: Sample TSG Content
# =============================================================================

@pytest.fixture
def valid_tsg_content():
    """Create a complete valid TSG content block."""
    headings = "\n\n".join(REQUIRED_TSG_HEADINGS)
    return f"""{REQUIRED_TOC}

{headings}

{REQUIRED_DIAGNOSIS_LINE}

Some content here.
"""


@pytest.fixture
def valid_tsg_response(valid_tsg_content):
    """Create a complete valid TSG response with all markers."""
    return f"""
{TSG_BEGIN}
{valid_tsg_content}
{TSG_END}

{QUESTIONS_BEGIN}
NO_MISSING
{QUESTIONS_END}
"""


@pytest.fixture
def valid_tsg_with_missing(valid_tsg_content):
    """Create a TSG response with MISSING placeholders and questions."""
    content_with_missing = valid_tsg_content.replace(
        "Some content here.",
        "{{MISSING::Cause::What is the root cause?}}"
    )
    return f"""
{TSG_BEGIN}
{content_with_missing}
{TSG_END}

{QUESTIONS_BEGIN}
- {{{{MISSING::Cause::What is the root cause?}}}} -> What was the root cause of the issue?
{QUESTIONS_END}
"""


# =============================================================================
# TESTS: Complete Valid TSG
# =============================================================================

class TestValidTSG:
    """Tests for valid TSG responses."""
    
    @pytest.mark.unit
    def test_valid_tsg_returns_valid_true(self, valid_tsg_response):
        """A complete valid TSG should return valid=True."""
        result = validate_tsg_output(valid_tsg_response)
        assert result["valid"] is True
        assert result["issues"] == []
    
    @pytest.mark.unit
    def test_valid_tsg_extracts_content(self, valid_tsg_response):
        """Should extract TSG content between markers."""
        result = validate_tsg_output(valid_tsg_response)
        assert REQUIRED_TOC in result["tsg_content"]
        assert "# **Title**" in result["tsg_content"]
    
    @pytest.mark.unit
    def test_valid_tsg_extracts_questions(self, valid_tsg_response):
        """Should extract questions content."""
        result = validate_tsg_output(valid_tsg_response)
        assert result["questions_content"] == "NO_MISSING"
    
    @pytest.mark.unit
    def test_valid_tsg_with_missing_placeholders(self, valid_tsg_with_missing):
        """TSG with MISSING placeholders and matching questions should be valid."""
        result = validate_tsg_output(valid_tsg_with_missing)
        assert result["valid"] is True


# =============================================================================
# TESTS: Missing Markers
# =============================================================================

class TestMissingMarkers:
    """Tests for missing required markers."""
    
    @pytest.mark.unit
    def test_missing_tsg_begin_marker(self, valid_tsg_content):
        """Missing TSG_BEGIN marker should fail validation."""
        response = f"""
{valid_tsg_content}
{TSG_END}

{QUESTIONS_BEGIN}
NO_MISSING
{QUESTIONS_END}
"""
        result = validate_tsg_output(response)
        assert result["valid"] is False
        assert any("TSG_BEGIN" in issue for issue in result["issues"])
    
    @pytest.mark.unit
    def test_missing_tsg_end_marker(self, valid_tsg_content):
        """Missing TSG_END marker should fail validation."""
        response = f"""
{TSG_BEGIN}
{valid_tsg_content}

{QUESTIONS_BEGIN}
NO_MISSING
{QUESTIONS_END}
"""
        result = validate_tsg_output(response)
        assert result["valid"] is False
        assert any("TSG_END" in issue for issue in result["issues"])
    
    @pytest.mark.unit
    def test_missing_questions_begin_marker(self, valid_tsg_content):
        """Missing QUESTIONS_BEGIN marker should fail validation."""
        response = f"""
{TSG_BEGIN}
{valid_tsg_content}
{TSG_END}

NO_MISSING
{QUESTIONS_END}
"""
        result = validate_tsg_output(response)
        assert result["valid"] is False
        assert any("QUESTIONS_BEGIN" in issue for issue in result["issues"])
    
    @pytest.mark.unit
    def test_missing_questions_end_marker(self, valid_tsg_content):
        """Missing QUESTIONS_END marker should fail validation."""
        response = f"""
{TSG_BEGIN}
{valid_tsg_content}
{TSG_END}

{QUESTIONS_BEGIN}
NO_MISSING
"""
        result = validate_tsg_output(response)
        assert result["valid"] is False
        assert any("QUESTIONS_END" in issue for issue in result["issues"])
    
    @pytest.mark.unit
    def test_missing_all_markers(self):
        """Response with no markers should fail with multiple issues."""
        response = "Just some plain text without any markers"
        result = validate_tsg_output(response)
        assert result["valid"] is False
        assert len(result["issues"]) >= 4  # All 4 markers missing


# =============================================================================
# TESTS: Missing Required Content
# =============================================================================

class TestMissingContent:
    """Tests for missing required TSG content."""
    
    @pytest.mark.unit
    def test_missing_toc(self):
        """Missing [[_TOC_]] should fail validation."""
        # Create content without TOC
        headings = "\n\n".join(REQUIRED_TSG_HEADINGS)
        content = f"""
{headings}

{REQUIRED_DIAGNOSIS_LINE}
"""
        response = f"""
{TSG_BEGIN}
{content}
{TSG_END}

{QUESTIONS_BEGIN}
NO_MISSING
{QUESTIONS_END}
"""
        result = validate_tsg_output(response)
        assert result["valid"] is False
        assert any("table of contents" in issue.lower() for issue in result["issues"])
    
    @pytest.mark.unit
    def test_missing_required_heading(self, valid_tsg_content):
        """Missing a required heading should fail validation."""
        # Remove one heading
        content = valid_tsg_content.replace("# **Title**", "")
        response = f"""
{TSG_BEGIN}
{content}
{TSG_END}

{QUESTIONS_BEGIN}
NO_MISSING
{QUESTIONS_END}
"""
        result = validate_tsg_output(response)
        assert result["valid"] is False
        assert any("Title" in issue for issue in result["issues"])
    
    @pytest.mark.unit
    def test_missing_diagnosis_line(self, valid_tsg_content):
        """Missing required diagnosis line should fail validation."""
        content = valid_tsg_content.replace(REQUIRED_DIAGNOSIS_LINE, "")
        response = f"""
{TSG_BEGIN}
{content}
{TSG_END}

{QUESTIONS_BEGIN}
NO_MISSING
{QUESTIONS_END}
"""
        result = validate_tsg_output(response)
        assert result["valid"] is False
        assert any("diagnosis line" in issue.lower() for issue in result["issues"])


# =============================================================================
# TESTS: Questions Block Validation
# =============================================================================

class TestQuestionsBlock:
    """Tests for questions block validation logic."""
    
    @pytest.mark.unit
    def test_missing_placeholder_with_no_missing(self, valid_tsg_content):
        """TSG without placeholders should have NO_MISSING in questions block."""
        response = f"""
{TSG_BEGIN}
{valid_tsg_content}
{TSG_END}

{QUESTIONS_BEGIN}
NO_MISSING
{QUESTIONS_END}
"""
        result = validate_tsg_output(response)
        assert result["valid"] is True
    
    @pytest.mark.unit
    def test_has_placeholder_but_says_no_missing(self, valid_tsg_content):
        """TSG with placeholders but NO_MISSING in questions should fail."""
        content_with_placeholder = valid_tsg_content + "\n{{MISSING::Section::Hint}}"
        response = f"""
{TSG_BEGIN}
{content_with_placeholder}
{TSG_END}

{QUESTIONS_BEGIN}
NO_MISSING
{QUESTIONS_END}
"""
        result = validate_tsg_output(response)
        assert result["valid"] is False
        assert any("NO_MISSING" in issue for issue in result["issues"])
    
    @pytest.mark.unit
    def test_no_placeholder_but_not_no_missing(self, valid_tsg_content):
        """TSG without placeholders but questions block not NO_MISSING should fail."""
        response = f"""
{TSG_BEGIN}
{valid_tsg_content}
{TSG_END}

{QUESTIONS_BEGIN}
Some other content
{QUESTIONS_END}
"""
        result = validate_tsg_output(response)
        assert result["valid"] is False
        assert any("not NO_MISSING" in issue for issue in result["issues"])
    
    @pytest.mark.unit
    def test_has_placeholder_but_no_questions_listed(self, valid_tsg_content):
        """TSG with placeholders but questions block doesn't list them should fail."""
        content_with_placeholder = valid_tsg_content + "\n{{MISSING::Section::Hint}}"
        response = f"""
{TSG_BEGIN}
{content_with_placeholder}
{TSG_END}

{QUESTIONS_BEGIN}
Just some text without the proper format
{QUESTIONS_END}
"""
        result = validate_tsg_output(response)
        assert result["valid"] is False
        assert any("doesn't list" in issue for issue in result["issues"])


# =============================================================================
# TESTS: Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    @pytest.mark.unit
    def test_empty_response(self):
        """Empty response should fail with multiple issues."""
        result = validate_tsg_output("")
        assert result["valid"] is False
        assert len(result["issues"]) >= 4
    
    @pytest.mark.unit
    def test_markers_in_wrong_order(self, valid_tsg_content):
        """Markers in wrong order should fail to extract content properly."""
        response = f"""
{TSG_END}
{valid_tsg_content}
{TSG_BEGIN}

{QUESTIONS_END}
NO_MISSING
{QUESTIONS_BEGIN}
"""
        result = validate_tsg_output(response)
        # Content extraction should fail or be empty
        assert result["tsg_content"] == ""
        assert result["valid"] is False
    
    @pytest.mark.unit
    def test_whitespace_in_questions_content(self, valid_tsg_content):
        """Questions content should be stripped of whitespace."""
        response = f"""
{TSG_BEGIN}
{valid_tsg_content}
{TSG_END}

{QUESTIONS_BEGIN}
   NO_MISSING   
{QUESTIONS_END}
"""
        result = validate_tsg_output(response)
        assert result["questions_content"] == "NO_MISSING"
        assert result["valid"] is True
