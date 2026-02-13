# TSG Builder — Copilot Instructions

This document codifies the design philosophy, architecture decisions, and expected behaviors for the TSG Builder project. Use this as authoritative guidance when making changes or answering questions about the codebase.

> **📝 Maintenance Note**: When discussing this codebase, if we identify undocumented intentions or expected behaviors, prompt the user to update this file to capture that knowledge.

## Project Purpose

TSG Builder transforms raw troubleshooting notes into structured **Technical Support Guides (TSGs)** using a multi-stage AI pipeline. It's designed for Azure Support teams who need to quickly document known issues and their resolutions.

## Core Design Principles

### 0. TSGs Are Operations Manuals, Not Research Reports

**A TSG is an internal operations manual** — it presents facts and procedures as established institutional knowledge. Think product documentation or SOP, not research synthesis.

- **Write as the authoritative author**: The reader needs actionable content; they don't need to know where it came from
- **No source attributions**: Never include "(from docs)", "(per research)", "(community-sourced)", "(as provided in notes)", or similar
- **No meta-commentary**: Avoid "according to research", "the notes indicate", "based on the GitHub discussion"
- **Production-ready**: The TSG should be copy-paste ready, requiring no cleanup

The Research stage produces internal reference material with citations. The Writer extracts facts and **discards attributions**. The final TSG reads like it was written by an expert who simply knows the information.

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

## Supported Model

**Only gpt-5.2 deployments are supported.** The pipeline prompts, structured output expectations, and Foundry SDK usage are all designed for gpt-5.2. The setup UI asks for a deployment name but clarifies it must be a gpt-5.2 deployment. Validation warns (but does not block) if the underlying model is not gpt-5.2.

---

## Pipeline Stage Behaviors

For technical architecture details, see [docs/architecture.md](../docs/architecture.md).

### Stage 1: Research

**Purpose**: Gather supporting documentation from public sources. The research report is **internal reference material** for the Writer — it will NOT appear in the final TSG.

**Tools**: Web Search, Microsoft Learn MCP

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
- Sources & Findings (official docs, community/GitHub, ARM refs — grouped by source with key insights)
- Research Gaps (informational only)

### Stage 2: Write

**Purpose**: Create the TSG using notes + research. The TSG is an **operations manual** — authoritative, no source attributions or commentary.

**Tools**: None (intentional — prevents hallucinated searches)

#### Expected Behaviors

| Behavior | Correct | Incorrect |
|----------|---------|----------|
| Content from user notes | Include as authoritative | Mark as MISSING because unverified |
| Code samples from notes | Include in Mitigation/Resolution with version caveat | Omit or reject |
| Research Gaps from Stage 1 | Acknowledge but don't auto-create MISSING | Create MISSING for every research gap |
| Missing required content | Use `{{MISSING::<Section>::<Hint>}}` | Leave section empty or skip |
| All required sections | Must have content or MISSING placeholder | Skip optional-seeming sections |
| Questions block | List question for each MISSING, or `NO_MISSING` | Empty block or wrong format |
| Source attributions | Never include "(from docs)", "(per notes)", etc. | Add inline citations or meta-commentary |

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

### What Blocks Generation

| Source | Behavior | Example |
|--------|----------|--------|
| PII Check (`pii_check.py`) | **Blocks generation** — user must edit or redact before proceeding | Email, phone number, IP address, Azure credentials detected in input notes or follow-up answers |
| PII Check error | **Blocks generation** — Language service unreachable, auth failure, or rate limit | "PII check failed: Azure authentication failed" with actionable hint |
### Warning Flow

1. **Pipeline** returns `review_result` with `accuracy_issues` and `suggestions` (regardless of `approved` status)
2. **Web App** extracts both into `warnings` array
3. **UI** displays warnings in a banner below the TSG output (before follow-up questions)

### Warnings Must NOT

- Block TSG generation
- Appear in the TSG content itself
- Cause the pipeline to retry indefinitely
- Override user-provided content

---

## File Reference

| File | Purpose |
|------|---------|
| `version.py` | **Single source of truth** for version, GitHub URL, and TSG signature |
| `pipeline.py` | Multi-stage pipeline orchestration, error classification |
| `tsg_constants.py` | TSG template, stage prompts, validation functions |
| `pii_check.py` | PII detection via Azure AI Language API (pre-flight gate) |
| `error_utils.py` | Shared Azure SDK error classification utilities |
| `web_app.py` | Flask server, SSE streaming, session management |
| `build_exe.py` | PyInstaller build script (bundles templates/, static/) |
| `templates/index.html` | Web UI HTML structure |
| `static/css/styles.css` | Web UI styles (CSS custom properties, component styles) |
| `static/js/main.js` | Core UI logic (streaming, TSG generation, images, PII modal) |
| `static/js/setup.js` | Setup modal (config, validation, agent creation) |
| `.agent_ids.json` | Stored agent names/IDs (created by setup) |
| `docs/architecture.md` | Technical architecture details |
| `examples/` | Test inputs, expected outputs, test run captures |
| `tests/` | Pytest test suite |
| `tests/conftest.py` | Shared fixtures and test utilities |

---

## Testing

### Unit Tests

Run the test suite with pytest:

```bash
make test          # Run all tests
make test-verbose  # Verbose output
make test-cov      # With coverage report
make test-unit     # Only unit tests (fast)
make test-quick    # Skip dep install (fastest)
```

Tests are in `tests/` and use shared fixtures from `tests/conftest.py`. See `tests/README.md` for details on writing tests.

### Pipeline Test Mode

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

### PII check flags a false positive (e.g., a person's name that is actually a service name)

The PII detection uses a curated category list to minimize noise (e.g., `Organization` is intentionally excluded). The `Person` category may occasionally flag service names or technical terms. The user can click **"Go Back & Edit"** to adjust their notes, or click **"Redact & Continue"** to accept the API's redaction. If a category consistently produces false positives, consider removing it from `PII_CATEGORIES` in `pii_check.py`. The confidence threshold (`PII_CONFIDENCE_THRESHOLD = 0.8`) can also be adjusted.

### PII check fails with "authentication error" or "access denied"

The PII check uses `DefaultAzureCredential` against the AI Services endpoint built into the user's Foundry resource (derived from `PROJECT_ENDPOINT`). Fix: run `az login` to refresh credentials, or verify the user has access to their Foundry project.

---

## Version Management

**`version.py` is the single source of truth** for all version-related constants:

- `APP_VERSION` — Semantic version string (e.g., `"1.0.0"`)
- `GITHUB_URL` — Project repository URL
- `TSG_SIGNATURE` — Signature appended to every generated TSG for usage tracking

When releasing a new version:
1. Update `APP_VERSION` in `version.py` only
2. Tag the commit with `v{version}` (e.g., `v1.0.0`)
3. Push the tag to trigger the release workflow

The signature appears at the bottom of every TSG as:
```
---
*Drafted with [TSG Builder](https://github.com/jcentner/tsgbuilder) v1.0.0*
```

This enables searching for TSG Builder-generated content in the ADO wiki.

---

