---
applyTo: "pipeline.py,tsg_constants.py,pii_check.py,error_utils.py"
---

# Pipeline & Constants — Copilot Instructions

These instructions apply when editing pipeline orchestration, stage prompts, validation, PII gating, or error classification.

## Three-Stage Pipeline

Research → Write → Review. Each stage is a separate Azure AI Foundry agent. See `docs/architecture.md` for the full architecture diagram.

### Stage 1: Research

**Purpose**: Gather public references as internal material for the Writer. Output never appears in the final TSG.

**Tools**: `WebSearchPreviewTool` (Microsoft-managed), Microsoft Learn MCP. `BING_CONNECTION_NAME` is deprecated.

Expected behavior:
- Verify and summarize URLs from user notes first
- Prioritize issue-specific docs and community workarounds
- Note internal diagnostic tooling (Kusto, ASC, Acis) in Research Gaps as informational
- Research Gaps are informational, NOT directives for the Writer to create MISSING placeholders

Output contract: `<!-- RESEARCH_BEGIN --> ... <!-- RESEARCH_END -->` containing Topic Summary, URLs from User Notes, Sources & Findings, Research Gaps.

### Stage 2: Write

**Purpose**: Produce the TSG from notes + research. No tools (intentional — prevents hallucinated searches).

Expected behavior:
- Use notes as authoritative input; include code samples/workarounds
- Use `{{MISSING::<Section>::<Hint>}}` only when required content is truly absent from both notes and research
- Fill all 10 required sections with content or MISSING placeholder
- No source attribution language in TSG body ("from docs", "per research", etc.)
- QUESTIONS block: one line per MISSING (`- {{MISSING::...}} -> question`) or exactly `NO_MISSING`

Output contract:
```
<!-- TSG_BEGIN -->
[Complete TSG with all 10 required sections]
<!-- TSG_END -->

<!-- QUESTIONS_BEGIN -->
[Questions or NO_MISSING]
<!-- QUESTIONS_END -->
```

**Critical**: `<!-- QUESTIONS_BEGIN/END -->` is for the pipeline to ask the TSG *author* follow-up questions. It is NOT the same as the `# **Questions to Ask the Customer**` TSG section.

### Stage 3: Review

**Purpose**: Validate structure and surface actionable warnings. No tools.

Expected behavior:
- Validate all 10 required sections and markers exist
- Accept note-derived content as authoritative (do not flag as "unverified")
- Surface doc discrepancies as `accuracy_issues` warnings, not blockers
- Provide `corrected_tsg` for fixable issues; return `null` for issues needing re-research
- Keep QUESTIONS markers outside and after TSG block
- `approved: true` for structurally valid TSGs (even with warnings); `approved: false` only for structural failures

Output contract:
```json
{
  "approved": true/false,
  "structure_issues": [],
  "accuracy_issues": [],
  "completeness_issues": [],
  "format_issues": [],
  "suggestions": [],
  "corrected_tsg": null or "[full corrected TSG]"
}
```

## TSG Template Contract

Every TSG must:
1. Start with `[[_TOC_]]`
2. Use `<!-- TSG_BEGIN/END -->` markers around content
3. Use `<!-- QUESTIONS_BEGIN/END -->` markers AFTER `<!-- TSG_END -->`
4. Include the diagnosis line: "Don't Remove This Text: Results of the Diagnosis should be attached in the Case notes/ICM."

Required sections (10 total) — see `REQUIRED_TSG_HEADINGS` in `tsg_constants.py`:
1. First H1 = title (e.g., `# **Issue Title**`), not a literal heading
2. `# **Issue Description / Symptoms**`
3. `# **When does the TSG not Apply**`
4. `# **Diagnosis**`
5. `# **Questions to Ask the Customer**`
6. `# **Cause**`
7. `# **Mitigation or Resolution**`
8. `# **Root Cause to be shared with Customer**`
9. `# **Related Information**`
10. `# **Tags or Prompts**`

## Iteration Behavior

1. Writer receives prior review feedback (`accuracy_issues`, `suggestions`, `completeness_issues`) when available
2. User follow-up answers may include MISSING answers and reviewer-feedback acceptance/rejection
3. Reviewer receives prior review + user response context; should not re-raise explicitly dismissed suggestions
4. Re-raise only new issues or accepted-but-not-applied issues

## PII Gate (`pii_check.py`)

- **Fail-closed**: blocks generation if PII found OR on any service error
- Uses `DefaultAzureCredential` against AI Services endpoint derived from `PROJECT_ENDPOINT`
- Categories defined in `PII_CATEGORIES`; `Organization` intentionally excluded
- Confidence threshold: `PII_CONFIDENCE_THRESHOLD = 0.8`
- Defense-in-depth: frontend checks before sending, backend re-checks at `/api/generate/stream` and `/api/answer/stream`

## Error Classification (`error_utils.py`)

Shared error classification for Azure SDK errors. Always import from `error_utils.py` — do not duplicate classification logic in `pipeline.py` or `web_app.py`.

## Common Gotchas

- **NO_MISSING with research gaps**: Correct if content exists in notes. Gaps are informational.
- **`approved: false` but TSG returned**: Edge case; preferred behavior is `approved: true` for structurally valid TSGs with warnings only.
- **PII false positives on `Person`**: May flag service names. User can edit or redact-and-continue. Adjust `PII_CATEGORIES` or threshold if persistent.
