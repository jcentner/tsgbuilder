# TSG Builder — Copilot Instructions

This document codifies the design philosophy, architecture decisions, and expected behaviors for the TSG Builder project. Use this as authoritative guidance when making changes or answering questions about the codebase.

> **📝 Maintenance Note**: When discussing this codebase, if we identify undocumented intentions or expected behaviors, prompt the user to update this file to capture that knowledge.

## Project Purpose

TSG Builder transforms raw troubleshooting notes into structured **Technical Support Guides (TSGs)** using a multi-stage AI pipeline. It's designed for Azure Support teams who need to quickly document known issues and their resolutions.

## Core Design Principles

### 1. User Notes Are Authoritative

**User-provided content (notes, code samples, workarounds) should be treated as authoritative source material**, equivalent to public documentation.

- The user is typically a support engineer with direct knowledge of the issue, working from product manager or engineering-provided notes.
- Code samples in notes should be included in the TSG (with version caveats if needed)
- Internal details (Kusto queries, ASC actions, Acis commands) won't be publicly documented—this is expected
- The pipeline should **never reject or block output** because user notes differ from public docs

### 2. Warnings Surface Discrepancies, Never Block

When public documentation explicitly differs from user notes:
- **Surface as a warning** to the user (via UI, not in TSG content)
- **Do not block** TSG generation
- **Do not insert warnings into the TSG itself** — the TSG is the final product

Examples of warning-worthy discrepancies:
- API version in notes differs from official docs
- Behavior described in notes contradicts public documentation
- Constraints mentioned in notes but not officially documented

### 3. MISSING Placeholders Are for Absent Content, Not Unverified Content

Use `{{MISSING::<Section>::<Hint>}}` placeholders **only when required TSG content is completely absent** from both user notes and research.

Do NOT use MISSING placeholders for:
- Content from user notes that couldn't be independently verified
- Internal tools/queries that aren't publicly documented (expected)
- API versions or SDK versions from user notes

### 4. The Pipeline Always Produces Output

The three-stage pipeline (Research → Write → Review) should **always return a TSG** unless there's a technical failure. Quality concerns surface as warnings, not blockers.

---

## Pipeline Stage Behaviors

For technical architecture details, see [docs/architecture.md](../docs/architecture.md).

### Stage 1: Research

**Purpose**: Gather supporting documentation from public sources.

**Tools**: Bing Search, Microsoft Learn MCP

#### Expected Behaviors

| Behavior | Correct | Incorrect |
|----------|---------|-----------|
| URLs from user notes | Verify and summarize first | Skip them |
| Official docs search | Find docs about specific error/feature | Include general product overviews |
| GitHub/community search | Find issues and workarounds for this problem | Include unrelated discussions |
| Internal tools (Kusto, ASC, Acis) | Note as "not publicly documented" in Research Gaps | Try to find docs for them |
| Research Gaps section | List items from notes that couldn't be verified (informational) | Frame as "Writer must mark MISSING" |

#### Output Format

Research report with `<!-- RESEARCH_BEGIN/END -->` markers containing:
- Topic Summary
- URLs from User Notes (verified)
- Official Documentation
- Community/GitHub Findings
- Key Technical Facts
- Cause Analysis
- Customer-Safe Root Cause
- Solutions/Workarounds Found
- When This Doesn't Apply
- Suggested Customer Questions
- Suggested Tags/Keywords
- Research Gaps (informational only)

### Stage 2: Write

**Purpose**: Create the TSG using notes + research.

**Tools**: None (intentional — prevents hallucinated searches)

#### Expected Behaviors

| Behavior | Correct | Incorrect |
|----------|---------|-----------|
| Content from user notes | Include as authoritative | Mark as MISSING because unverified |
| Code samples from notes | Include in Mitigation/Resolution with version caveat | Omit or reject |
| Research Gaps from Stage 1 | Acknowledge but don't auto-create MISSING | Create MISSING for every research gap |
| Missing required content | Use `{{MISSING::<Section>::<Hint>}}` | Leave section empty or skip |
| All required sections | Must have content or MISSING placeholder | Skip optional-seeming sections |
| Questions block | List question for each MISSING, or `NO_MISSING` | Empty block or wrong format |

#### Output Format

```
<!-- TSG_BEGIN -->
[Complete TSG with all 10 required sections]
<!-- TSG_END -->

<!-- QUESTIONS_BEGIN -->
[One line per MISSING: `- {{MISSING::...}} -> question`]
[OR exactly: `NO_MISSING`]
<!-- QUESTIONS_END -->
```

⚠️ **Critical**: The `<!-- QUESTIONS_BEGIN/END -->` block is for the **pipeline to ask the TSG author** follow-up questions. It is NOT the same as the `# **Questions to Ask the Customer**` TSG section (which is for support engineers to ask customers).

### Stage 3: Review

**Purpose**: Validate structure and identify discrepancies.

**Tools**: None

#### Expected Behaviors

| Behavior | Correct | Incorrect |
|----------|---------|-----------|
| Structure validation | Check all 10 required sections exist | Only check a few |
| Content from user notes | Accept as authoritative | Flag as "unverified" accuracy issue |
| Public docs differ from notes | Add to `accuracy_issues` as warning | Block/reject the TSG |
| Fixable issues (format, structure) | Provide `corrected_tsg` | Return null and force retry |
| Non-fixable issues (needs re-research) | Return `corrected_tsg: null` | Attempt partial fix |
| QUESTIONS markers | Keep AFTER TSG_END | Move inside TSG content |
| TSG with all content | `approved: true` even with warnings | `approved: false` for warnings alone |

#### Output Format

```json
{
  "approved": true/false,
  "structure_issues": [],
  "accuracy_issues": [],      // → becomes UI warnings
  "completeness_issues": [],
  "format_issues": [],
  "suggestions": [],          // → becomes UI warnings
  "corrected_tsg": null or "[full corrected TSG]"
}
```

#### Approval Logic

| Structure Valid | Has Warnings | `approved` Value |
|-----------------|--------------|------------------|
| ✅ Yes | No | `true` |
| ✅ Yes | Yes (accuracy/suggestions) | `true` |
| ❌ No | — | `false` |

---

## TSG Template Requirements

Every TSG must:
1. Start with `[[_TOC_]]`
2. Contain all required section headings (see `REQUIRED_TSG_HEADINGS` in `tsg_constants.py`)
3. Include the required diagnosis line: "Don't Remove This Text: Results of the Diagnosis should be attached in the Case notes/ICM."
4. Use `<!-- TSG_BEGIN/END -->` markers around content
5. Use `<!-- QUESTIONS_BEGIN/END -->` markers for follow-up questions (AFTER TSG_END, not inside)

### Required Sections (10 total)

1. `# **Title**`
2. `# **Issue Description / Symptoms**`
3. `# **When does the TSG not Apply**`
4. `# **Diagnosis**`
5. `# **Questions to Ask the Customer**`
6. `# **Cause**`
7. `# **Mitigation or Resolution**`
8. `# **Root Cause to be shared with Customer**`
9. `# **Related Information**`
10. `# **Tags or Prompts**`

---

## Warning System

### What Generates Warnings

| Source | Warning Type | Example |
|--------|--------------|---------|
| Review Stage | `accuracy_issues` | "API version 2025-04-01-preview in notes differs from 2025-06-01 in official docs" |
| Review Stage | `suggestions` | "Consider adding hub-based projects to 'When TSG not Apply'" |

### Warning Flow

1. **Pipeline** returns `review_result` with issues
2. **Web App** extracts `accuracy_issues` + `suggestions` into `warnings` array
3. **UI** displays warnings in a banner (does NOT insert into TSG)

### Warnings Must NOT

- Block TSG generation
- Appear in the TSG content itself
- Cause the pipeline to retry indefinitely
- Override user-provided content

---

## File Reference

| File | Purpose |
|------|---------|
| `pipeline.py` | Multi-stage pipeline orchestration |
| `tsg_constants.py` | TSG template, stage prompts, validation functions |
| `web_app.py` | Flask server, SSE streaming, session management |
| `templates/index.html` | Web UI |
| `.agent_ids.json` | Stored agent names/IDs (created by setup) |
| `docs/architecture.md` | Technical architecture details |
| `examples/` | Test inputs, expected outputs, test run captures |

---

## Testing

Run the pipeline in test mode to capture raw stage outputs:

```python
from pipeline import run_pipeline
result = run_pipeline(notes="...", test_mode=True)
# Writes to examples/test_output_YYYYMMDD_HHMMSS.json
```

Test output includes:
- `stage_outputs.research.raw_response` — Full research agent response
- `stage_outputs.write.raw_response` — Full writer agent response  
- `stage_outputs.review.raw_response` — Full reviewer agent response
- `stage_outputs.review.parsed_result` — Parsed review JSON

---

## Common Issues

### "TSG has NO_MISSING but research gaps exist"

This is **correct behavior** if the content exists in user notes. Research gaps are informational ("couldn't verify from public sources") not actionable ("content is missing").

### Review stage returns `approved: false` but TSG is accepted

This is **correct behavior**. `approved: false` with issues means "TSG is structurally valid but has warnings." The pipeline accepts it and surfaces warnings to the user.

### Warnings not appearing in UI

Check that `templates/index.html` handles `data.warnings` in the result event handler. As of this writing, this is a known gap that needs implementation.

---

## Known Gaps / TODOs

- [ ] UI does not display `data.warnings` from API response
- [ ] Research stage "Research Gaps" wording could be clearer (informational vs actionable)
- [ ] Review stage may flag user-provided content as accuracy issues incorrectly
- [ ] Test mode outputs to repo root; need to change this to output to examples/ directory