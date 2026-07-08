"""
test_eval_runner.py — Tests for the offline eval runner strict-mode semantics.

Run with: pytest tests/test_eval_runner.py -v
"""

import sys

import pytest

import evals.run_evals as runner


@pytest.mark.unit
def test_seed_cases_pass_strict(monkeypatch):
    """The committed case set passes in strict mode (returns 0)."""
    monkeypatch.setattr(sys, "argv", ["run_evals.py", "--strict"])
    assert runner.run() == 0


@pytest.mark.unit
def test_empty_case_set_fails_strict(monkeypatch, tmp_path):
    """An empty/missing case dir must fail strict mode, not silently pass."""
    monkeypatch.setattr(runner, "CASES_DIR", tmp_path / "cases")
    monkeypatch.setattr(runner, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(sys, "argv", ["run_evals.py", "--strict"])
    assert runner.run() == 1


@pytest.mark.unit
def test_empty_case_set_passes_non_strict(monkeypatch, tmp_path):
    """Without --strict, an empty case set is a no-op success."""
    monkeypatch.setattr(runner, "CASES_DIR", tmp_path / "cases")
    monkeypatch.setattr(runner, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(sys, "argv", ["run_evals.py"])
    assert runner.run() == 0


@pytest.mark.unit
def test_harness_error_fails_strict(monkeypatch, tmp_path):
    """A rubric pointing at a missing output file is a harness error (strict fail)."""
    cases = tmp_path / "cases" / "broken"
    cases.mkdir(parents=True)
    (cases / "rubric.json").write_text(
        '{"label": "broken", "output_file": "does-not-exist.md"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "CASES_DIR", tmp_path / "cases")
    monkeypatch.setattr(runner, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(sys, "argv", ["run_evals.py", "--strict"])
    assert runner.run() == 1
