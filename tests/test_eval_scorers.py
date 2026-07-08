"""
test_eval_scorers.py — Tests for the deterministic eval scorers.

Run with: pytest tests/test_eval_scorers.py -v
"""

import pytest

from tsg_constants import (
    REQUIRED_TSG_HEADINGS,
    REQUIRED_DIAGNOSIS_LINE,
    REQUIRED_TOC,
)
from evals.scorers import (
    score_template_compliance,
    score_missing_hygiene,
    score_code_fidelity,
    score_no_source_attribution,
    score_tsg,
)


def _complete_tsg(body_extra: str = "") -> str:
    headings = "\n\n".join(
        f"{h}\n\nContent." for h in REQUIRED_TSG_HEADINGS
    )
    # Inject the diagnosis line into the Diagnosis section.
    headings = headings.replace(
        "# **Diagnosis**\n\nContent.",
        f"# **Diagnosis**\n\n{REQUIRED_DIAGNOSIS_LINE}\n\nContent.",
    )
    return f"{REQUIRED_TOC}\n\n# **Sample Title**\n\n{headings}\n{body_extra}"


class TestTemplateCompliance:
    @pytest.mark.unit
    def test_complete_tsg_passes(self):
        assert score_template_compliance(_complete_tsg()).passed

    @pytest.mark.unit
    def test_missing_heading_fails(self):
        tsg = _complete_tsg().replace("# **Cause**", "# **Reason**")
        result = score_template_compliance(tsg)
        assert not result.passed
        assert "Cause" in result.detail

    @pytest.mark.unit
    def test_missing_diagnosis_line_fails(self):
        tsg = _complete_tsg().replace(REQUIRED_DIAGNOSIS_LINE, "")
        result = score_template_compliance(tsg)
        assert not result.passed
        assert "diagnosis line" in result.detail

    @pytest.mark.unit
    def test_failure_mode_is_structure(self):
        tsg = _complete_tsg().replace(REQUIRED_TOC, "")
        assert score_template_compliance(tsg).failure_mode == "structure"


class TestMissingHygiene:
    @pytest.mark.unit
    def test_no_missing_when_not_expected_passes(self):
        assert score_missing_hygiene("clean tsg", {"expects_missing": False}).passed

    @pytest.mark.unit
    def test_unexpected_missing_fails(self):
        tsg = "body {{MISSING::Cause::hint}}"
        assert not score_missing_hygiene(tsg, {"expects_missing": False}).passed

    @pytest.mark.unit
    def test_expected_missing_present_passes(self):
        tsg = "body {{MISSING::Cause::hint}}"
        assert score_missing_hygiene(tsg, {"expects_missing": True}).passed

    @pytest.mark.unit
    def test_expected_missing_absent_fails(self):
        assert not score_missing_hygiene("clean", {"expects_missing": True}).passed


class TestCodeFidelity:
    @pytest.mark.unit
    def test_all_tokens_present_passes(self):
        rubric = {"expected_snippet_tokens": ["capabilityHost", "DefaultAzureCredential"]}
        tsg = "use capabilityHost with DefaultAzureCredential()"
        assert score_code_fidelity(tsg, rubric).passed

    @pytest.mark.unit
    def test_case_insensitive(self):
        rubric = {"expected_snippet_tokens": ["CapabilityHost"]}
        assert score_code_fidelity("the capabilityhost value", rubric).passed

    @pytest.mark.unit
    def test_missing_token_fails_with_detail(self):
        rubric = {"expected_snippet_tokens": ["capabilityHost", "aiServicesConnections"]}
        result = score_code_fidelity("only capabilityHost here", rubric)
        assert not result.passed
        assert "aiServicesConnections" in result.detail
        assert result.failure_mode == "missing_steps"

    @pytest.mark.unit
    def test_no_tokens_specified_passes(self):
        assert score_code_fidelity("anything", {}).passed


class TestNoSourceAttribution:
    @pytest.mark.unit
    def test_clean_tsg_passes(self):
        assert score_no_source_attribution("The resource must be in the same region.").passed

    @pytest.mark.unit
    def test_attribution_phrase_fails(self):
        assert not score_no_source_attribution("This is true (from notes).").passed

    @pytest.mark.unit
    def test_according_to_discussion_fails(self):
        result = score_no_source_attribution("According to the discussion, set X.")
        assert not result.passed
        assert result.failure_mode == "tone"


class TestScoreTsg:
    @pytest.mark.unit
    def test_returns_all_scorers(self):
        results = score_tsg(_complete_tsg(), {})
        names = {r.name for r in results}
        assert names == {
            "template_compliance",
            "missing_hygiene",
            "code_fidelity",
            "no_source_attribution",
        }

    @pytest.mark.unit
    def test_ground_truth_example_passes_all(self):
        """The human ground-truth capability-host TSG passes every scorer."""
        from pathlib import Path

        example = Path(__file__).parent.parent / "examples" / "capability-host-expected.md"
        tsg = example.read_text(encoding="utf-8")
        rubric = {
            "expects_missing": False,
            "expected_snippet_tokens": [
                "capabilityHost",
                "aiServicesConnections",
                "DefaultAzureCredential",
            ],
        }
        results = score_tsg(tsg, rubric)
        failed = [r for r in results if not r.passed]
        assert not failed, f"unexpected failures: {[(r.name, r.detail) for r in failed]}"
