#!/usr/bin/env python3
"""Offline TSG eval runner.

Loads eval cases from ``evals/cases/<name>/rubric.json`` and scores each case's
captured output with the deterministic scorers in ``evals.scorers``. No Azure or
network access is required — this is the CI-friendly guardrail against
publication-blocking regressions in generated TSGs.

Usage:
    python evals/run_evals.py            # score all offline cases, print a table
    python evals/run_evals.py --strict   # exit non-zero if any scorer fails

A case directory contains:
    rubric.json   required. Fields:
        label                  human-readable name
        output_file            path (relative to the case dir) to the TSG
                               content to score offline
        expects_missing        bool (default false)
        expected_snippet_tokens  list[str] code/command tokens that must survive
Live regeneration from notes is intentionally out of scope for this v1.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

# Allow running as a script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.scorers import score_tsg  # noqa: E402

CASES_DIR = Path(__file__).resolve().parent / "cases"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _load_cases() -> list[tuple[str, dict, Path]]:
    cases = []
    if not CASES_DIR.exists():
        return cases
    for case_dir in sorted(p for p in CASES_DIR.iterdir() if p.is_dir()):
        rubric_path = case_dir / "rubric.json"
        if not rubric_path.exists():
            continue
        rubric = json.loads(rubric_path.read_text(encoding="utf-8"))
        cases.append((case_dir.name, rubric, case_dir))
    return cases


def run() -> int:
    parser = argparse.ArgumentParser(description="Offline TSG eval runner")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on any scorer failure, harness error, or empty case set (CI gate)",
    )
    args = parser.parse_args()

    cases = _load_cases()
    if not cases:
        print("No eval cases found under evals/cases/.")
        # In strict mode, an empty/broken case set is a failure, not a pass.
        return 1 if args.strict else 0

    all_results = []
    total = 0
    failed = 0
    errors = 0  # harness problems (missing/invalid config), distinct from scorer failures

    print(f"{'CASE':<28} {'SCORER':<24} {'RESULT':<6} DETAIL")
    print("-" * 90)
    for name, rubric, case_dir in cases:
        output_file = rubric.get("output_file")
        if not output_file:
            errors += 1
            print(f"{name:<28} {'(error)':<24} {'ERR':<6} no output_file in rubric")
            continue
        output_path = (case_dir / output_file).resolve()
        if not output_path.exists():
            errors += 1
            print(f"{name:<28} {'(error)':<24} {'ERR':<6} output not found: {output_path}")
            continue

        tsg = output_path.read_text(encoding="utf-8")
        for result in score_tsg(tsg, rubric):
            total += 1
            if not result.passed:
                failed += 1
            status = "PASS" if result.passed else "FAIL"
            print(f"{name:<28} {result.name:<24} {status:<6} {result.detail}")
            all_results.append(
                {"case": name, "label": rubric.get("label", name), **asdict(result),
                 "failure_mode": result.failure_mode}
            )

    print("-" * 90)
    passed = total - failed
    print(f"{passed}/{total} scorer checks passed across {len(cases)} case(s).")
    if errors:
        print(f"{errors} case(s) could not be scored (harness errors).")

    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "results.json").write_text(
        json.dumps(all_results, indent=2), encoding="utf-8"
    )

    if args.strict and (failed or errors or total == 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
