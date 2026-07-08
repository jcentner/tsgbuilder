"""Deterministic scorers for the TSG eval harness.

These are pure functions of ``(tsg_content, rubric)`` — no model calls, no
network — so they run fast in CI and give a stable, publication-focused
quality signal. They score the **final TSG content** (what the pipeline emits
as ``result.tsg_content``), not the raw marker-wrapped response.

The failure-mode vocabulary aligns with ``quality_taxonomy.QUALITY_FAILURE_MODES``
so offline eval results and real-world user feedback are comparable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from tsg_constants import (
    REQUIRED_TSG_HEADINGS,
    REQUIRED_DIAGNOSIS_LINE,
    REQUIRED_TOC,
)

# Attribution phrases the Writer/Reviewer rules forbid in TSG bodies.
_BANNED_ATTRIBUTION_PATTERNS = [
    r"\(from notes\)",
    r"\(per docs\)",
    r"\(per research\)",
    r"\(community[- ]sourced\)",
    r"\(as provided in notes\)",
    r"according to the (?:github|research|discussion|community)",
]

# Maps each scorer to the shared failure-mode taxonomy value.
SCORER_FAILURE_MODE = {
    "template_compliance": "structure",
    "missing_hygiene": "structure",
    "code_fidelity": "missing_steps",
    "no_source_attribution": "tone",
}


@dataclass
class ScoreResult:
    name: str
    passed: bool
    detail: str

    @property
    def failure_mode(self) -> str | None:
        return None if self.passed else SCORER_FAILURE_MODE.get(self.name)


def score_template_compliance(tsg: str) -> ScoreResult:
    """All required headings, the TOC, the title, and the diagnosis line present."""
    problems: list[str] = []
    if REQUIRED_TOC not in tsg:
        problems.append("missing TOC")
    if not re.search(r"\[\[_TOC_\]\]\s*\n+\s*# \*\*[^*]+\*\*", tsg):
        problems.append("missing title heading")
    missing_headings = [h for h in REQUIRED_TSG_HEADINGS if h not in tsg]
    if missing_headings:
        problems.append("missing headings: " + ", ".join(missing_headings))
    if REQUIRED_DIAGNOSIS_LINE not in tsg:
        problems.append("missing diagnosis line")
    passed = not problems
    return ScoreResult("template_compliance", passed, "ok" if passed else "; ".join(problems))


def score_missing_hygiene(tsg: str, rubric: dict) -> ScoreResult:
    """MISSING placeholders appear only when the rubric expects them."""
    has_missing = "{{MISSING::" in tsg
    expects = bool(rubric.get("expects_missing", False))
    if expects and not has_missing:
        return ScoreResult("missing_hygiene", False, "expected MISSING placeholders, found none")
    if not expects and has_missing:
        return ScoreResult("missing_hygiene", False, "unexpected MISSING placeholders present")
    return ScoreResult("missing_hygiene", True, "ok")


def score_code_fidelity(tsg: str, rubric: dict) -> ScoreResult:
    """Expected code/command tokens survived into the TSG (case-insensitive)."""
    tokens = rubric.get("expected_snippet_tokens", [])
    if not tokens:
        return ScoreResult("code_fidelity", True, "no tokens specified")
    low = tsg.lower()
    missing = [t for t in tokens if t.lower() not in low]
    passed = not missing
    return ScoreResult("code_fidelity", passed, "ok" if passed else "missing tokens: " + ", ".join(missing))


def score_no_source_attribution(tsg: str) -> ScoreResult:
    """No source-attribution phrases leaked into the TSG body."""
    hits = [p for p in _BANNED_ATTRIBUTION_PATTERNS if re.search(p, tsg, re.IGNORECASE)]
    passed = not hits
    return ScoreResult("no_source_attribution", passed, "ok" if passed else f"{len(hits)} attribution phrase(s)")


def score_tsg(tsg: str, rubric: dict) -> list[ScoreResult]:
    """Run all deterministic scorers for one TSG against its rubric."""
    return [
        score_template_compliance(tsg),
        score_missing_hygiene(tsg, rubric),
        score_code_fidelity(tsg, rubric),
        score_no_source_attribution(tsg),
    ]
