"""Shared quality vocabulary for feedback capture and offline evals.

Defining these enums once keeps in-product feedback (``tsg_feedback`` telemetry)
and the offline eval harness comparable — a "missing_steps" failure reported by a
user and one found by an eval scorer mean the same thing.

Values here are a **telemetry/data contract**. Only add to these sets; do not
rename or repurpose existing values without a migration plan for downstream
dashboards and eval datasets.
"""

from __future__ import annotations

# How a generated TSG turned out for the user.
FEEDBACK_OUTCOMES = frozenset(
    {
        "published",              # published as-is
        "published_after_edits",  # published after manual edits
        "discarded",              # not published
        "regenerated",            # re-ran the pipeline instead of using this output
    }
)

# The single most important thing the user had to fix (or an eval flagged).
# Kept as a closed enum specifically so no free-form user text (a PII risk)
# ever enters telemetry.
QUALITY_FAILURE_MODES = frozenset(
    {
        "none",           # nothing needed fixing
        "missing_steps",  # workaround/procedure was incomplete
        "wrong_command",  # incorrect code / command / API detail
        "structure",      # headings, markers, or template structure
        "tone",           # wording / voice / attributions
        "other",
    }
)

# Coarse buckets for self-reported time saved. Numeric, low-cardinality.
MINUTES_SAVED_BUCKETS = frozenset({0, 15, 30, 60})


def is_valid_outcome(value: str | None) -> bool:
    return value in FEEDBACK_OUTCOMES


def is_valid_failure_mode(value: str | None) -> bool:
    return value in QUALITY_FAILURE_MODES


def coerce_minutes_saved(value: object) -> int | None:
    """Return the value if it maps to an allowed bucket, else ``None``."""
    try:
        bucket = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return bucket if bucket in MINUTES_SAVED_BUCKETS else None
