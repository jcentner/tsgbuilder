---
description: "Review or implement a TSG Builder pipeline, prompt, or template change"
---

# Pipeline Change

Use this prompt when changing `pipeline.py`, `tsg_constants.py`, stage instructions, marker parsing, retry behavior, or review warning behavior.

## Task

Make the requested pipeline change while preserving the Research -> Write -> Review contracts.

## Steps

1. Read `.github/instructions/pipeline.instructions.md` and the relevant code/tests.
2. Preserve marker contracts: `<!-- TSG_BEGIN/END -->` and `<!-- QUESTIONS_BEGIN/END -->` after the TSG block.
3. Preserve Writer tool isolation unless the request explicitly changes architecture.
4. Keep review `accuracy_issues` and `suggestions` as warnings, not blockers.
5. Update tests before or with behavior changes.
6. If prompts or required headings change, update path-scoped instructions and docs in the same change.

## Validate

Run the narrow affected tests, then:

```bash
.venv/bin/pytest tests/test_tsg_validation.py tests/test_pipeline_sdk_contract.py tests/test_iteration_feedback.py -q
make test-quick
```
