# TSG Builder Architecture

This document describes the internal architecture and design details of TSG Builder.

## Multi-Stage Pipeline

TSG Builder uses a **three-stage pipeline** to separate concerns and improve reliability:

```
┌─────────────────┐     
│  Raw Notes      │     
│  (input.txt)    │     
└────────┬────────┘     
         │
         ▼
┌────────────────────────────────────────────────────────────────────┐
│                    TSG PIPELINE                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  Stage 1: RESEARCH (has tools)                               │ │
│  │  - Microsoft Learn MCP → official docs, APIs, limits         │ │
│  │  - Bing Search → GitHub issues, community solutions          │ │
│  │  → Output: Structured research report with URLs              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                              │                                     │
│                              ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  Stage 2: WRITE (no tools)                                   │ │
│  │  - Uses ONLY notes + research report                         │ │
│  │  - Follows TSG template exactly                              │ │
│  │  → Output: Draft TSG + {{MISSING::...}} placeholders         │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                              │                                     │
│                              ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  Stage 3: REVIEW (no tools)                                  │ │
│  │  - Structure validation (headings, markers)                  │ │
│  │  - Fact-check against research (soft warnings)               │ │
│  │  - Auto-fix simple issues, retry if needed                   │ │
│  │  → Output: Validated TSG + review notes                      │ │
│  └──────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────┐
│  Structured TSG (markdown)               │
│  + Follow-up Questions OR NO_MISSING     │
│  + Review warnings (if any)              │
└──────────────────────────────────────────┘
```

## Stage Details

### Stage 1: Research

The Research agent has access to external tools and is responsible for gathering information:

- **Microsoft Learn MCP** searches for:
  - Azure service documentation
  - Known limitations and workarounds
  - Configuration guides

- **Bing Search** for:
  - GitHub discussions and issues
  - Community workarounds
  - Stack Overflow solutions

**Output**: A structured research report with URLs and key findings.

**Why tools here?** Research needs external data. By isolating tool use to this stage, we ensure research actually happens and can track what sources were used.

### Stage 2: Write

The Writer agent has **no tool access** and works only from:
- Original user notes
- Research report from Stage 1

**Output**: Draft TSG following the template, with `{{MISSING::...}}` placeholders for gaps.

**Why no tools?** Prevents the writer from making ad-hoc searches that could introduce unverified information. All claims must trace back to the research report.

### Stage 3: Review

The Reviewer agent validates the draft:

- **Structure validation**: All required sections and markers present
- **Fact-checking**: Claims match the research report (flags potential hallucinations)
- **Auto-correction**: Fixes simple issues automatically
- **Retry logic**: Up to 2 retries if validation fails

**Output**: Validated TSG + review notes/warnings.

## Output Format

The pipeline outputs structured markers for parsing:

```
<!-- TSG_BEGIN -->
[TSG markdown content]
<!-- TSG_END -->

<!-- QUESTIONS_BEGIN -->
[Follow-up questions or NO_MISSING]
<!-- QUESTIONS_END -->
```

### Missing Information Placeholders

When information is missing, the agent inserts placeholders:

```
{{MISSING::<SECTION>::<HINT>}}
```

For example:
```
{{MISSING::Root Cause::Specify the exact error code from the customer's logs}}
```

## Iteration Flow

When the TSG has missing information:

1. Agent inserts `{{MISSING::...}}` placeholders in the TSG
2. Agent generates targeted follow-up questions
3. User provides answers
4. Pipeline regenerates with the new information
5. Repeat until `NO_MISSING` is returned

## File Structure

| File | Purpose |
|------|---------|
| `pipeline.py` | Multi-stage pipeline orchestration |
| `tsg_constants.py` | TSG template, agent instructions, and stage prompts |
| `web_app.py` | Flask web UI + agent creation |
| `.agent_ids.json` | Stores agent IDs after creation |

## Design Decisions

### Why Three Separate Agents?

1. **Separation of concerns** — Each agent has a focused role with appropriate capabilities
2. **Tool isolation** — Only the researcher has tool access, preventing uncontrolled external calls
3. **Traceability** — Clear audit trail of what was researched vs. what was generated
4. **Retry granularity** — Can retry individual stages without re-running the whole pipeline

### Why Remove Tools from Writer?

Early experiments showed that giving the writer tool access led to:
- Ad-hoc searches that contradicted the research report
- Hallucinated URLs (the model would "search" but make up results)
- Inconsistent quality

By forcing the writer to use only the research report, outputs are more consistent and traceable.
