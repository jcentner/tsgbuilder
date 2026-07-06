---
name: tsg-pipeline
description: "Use when: changing TSG Builder pipeline behavior, stage prompts, TSG markers, required headings, review warnings, retries, or Research/Write/Review contracts."
---

# TSG Pipeline Skill

Use this workflow for changes to `pipeline.py`, `tsg_constants.py`, stage instructions, marker contracts, or review behavior.

## Contracts

- Pipeline order is Research -> Write -> Review.
- Research has Web Search and Microsoft Learn MCP tools; Writer and Reviewer have no tools.
- User notes are authoritative.
- Research gaps are informational, except absent internal diagnostic/tool details such as Kusto, ASC, or Acis, which the Writer marks as `{{MISSING::...}}` when not present in notes or research.
- Final TSG content must stay between `<!-- TSG_BEGIN -->` and `<!-- TSG_END -->`.
- Follow-up questions must stay after the TSG block between `<!-- QUESTIONS_BEGIN -->` and `<!-- QUESTIONS_END -->`.
- Review `accuracy_issues` and `suggestions` are warnings, not blockers.

## Workflow

1. Read `.github/instructions/pipeline.instructions.md`.
2. Inspect the narrow stage/function/test surface before editing.
3. Add or update focused tests for the changed contract.
4. Keep docs and instructions synchronized with prompt/contract changes.

## Validation

Run the narrow affected tests first, then `make test-quick`.
