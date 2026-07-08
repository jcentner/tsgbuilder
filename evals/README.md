# TSG Builder Eval Harness

A fast, offline, **publication-focused** quality guardrail for generated TSGs.
TSG Builder is consumed both standalone and by downstream internal apps, so a
silent quality regression is a multi-consumer event. These evals catch the
failure modes that actually block publishing — not elegant prose metrics.

## Design

- **Deterministic first.** All v1 scorers are pure functions of
  `(tsg_content, rubric)` — no model calls, no network — so they run in CI.
  LLM-judge scorers (publishability, unsupported-claim detection) are a future
  opt-in phase, gated behind a flag so the default path stays offline and free.
- **Shared vocabulary.** Scorer failure modes map to
  `quality_taxonomy.QUALITY_FAILURE_MODES`, so offline eval results and
  in-product user feedback (`tsg_feedback` telemetry) are comparable.

## Scorers (v1)

| Scorer | Checks | Failure mode |
|--------|--------|--------------|
| `template_compliance` | TOC, title, all required headings, diagnosis line | `structure` |
| `missing_hygiene` | `{{MISSING::...}}` present only when the rubric expects it | `structure` |
| `code_fidelity` | Expected code/command tokens survived into the TSG | `missing_steps` |
| `no_source_attribution` | No `(from notes)` / "according to the discussion" leakage | `tone` |

## Running

```bash
make eval                    # score all offline cases, print a table
python evals/run_evals.py --strict   # exit non-zero on any failure (CI gate)
```

Results are written to `evals/results/results.json`.

## Adding a case

1. Create `evals/cases/<name>/`.
2. Add `rubric.json`:
   ```json
   {
     "label": "Short human-readable name",
     "output_file": "path/to/captured-tsg.md",
     "expects_missing": false,
     "expected_snippet_tokens": ["someCommand", "api-version=2024-..."]
   }
   ```
   `output_file` is resolved relative to the case directory. Point it at a
   captured pipeline output or a human ground-truth TSG.
3. Run `make eval`.

Keep rubrics **token/flag based**, not exact-match golden text — that avoids
overfitting to a specific model's prose while still catching real regressions.

> Cases may contain sensitive material. Scrub before committing, or keep the
> case's `output_file` outside version control and point the rubric at a local
> path.
