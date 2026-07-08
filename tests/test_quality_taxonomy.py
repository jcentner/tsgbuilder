"""
test_quality_taxonomy.py — Tests for the shared quality vocabulary.

Run with: pytest tests/test_quality_taxonomy.py -v
"""

import pytest

from quality_taxonomy import (
    FEEDBACK_OUTCOMES,
    QUALITY_FAILURE_MODES,
    MINUTES_SAVED_BUCKETS,
    is_valid_outcome,
    is_valid_failure_mode,
    coerce_minutes_saved,
)


class TestOutcomes:
    @pytest.mark.unit
    def test_known_outcomes_valid(self):
        for value in FEEDBACK_OUTCOMES:
            assert is_valid_outcome(value)

    @pytest.mark.unit
    def test_unknown_outcome_invalid(self):
        assert not is_valid_outcome("shipped")
        assert not is_valid_outcome(None)
        assert not is_valid_outcome("")


class TestFailureModes:
    @pytest.mark.unit
    def test_known_modes_valid(self):
        for value in QUALITY_FAILURE_MODES:
            assert is_valid_failure_mode(value)

    @pytest.mark.unit
    def test_freeform_text_invalid(self):
        # PII boundary: arbitrary text must never validate.
        assert not is_valid_failure_mode("customer email was leaked")
        assert not is_valid_failure_mode(None)


class TestMinutesSaved:
    @pytest.mark.unit
    def test_valid_buckets_pass_through(self):
        for bucket in MINUTES_SAVED_BUCKETS:
            assert coerce_minutes_saved(bucket) == bucket
            assert coerce_minutes_saved(str(bucket)) == bucket

    @pytest.mark.unit
    def test_out_of_bucket_returns_none(self):
        assert coerce_minutes_saved(7) is None
        assert coerce_minutes_saved(999) is None

    @pytest.mark.unit
    def test_non_numeric_returns_none(self):
        assert coerce_minutes_saved("lots") is None
        assert coerce_minutes_saved(None) is None
        assert coerce_minutes_saved({}) is None
