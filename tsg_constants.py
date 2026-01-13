"""
Shared TSG template, markers, and instruction text.
"""

TSG_TEMPLATE = """[[_TOC_]]

# **Title**
_Include, ideally, Error Message/ Error code or Scenario with keywords._
_For example_ **'message': 'ScriptExecutionException was caused by StreamAccessException.\\n StreamAccessException was caused by AuthenticationException.** OR 
**Datareference to ADLSGen2 Datastore fails.**

# **Issue Description / Symptoms**
_Describe what the Customer/CSS Engineer would see as an issue. This would include the error message and the stack trace (if available)_
- **What** is the issue?  
- **Who** does this affect?  
- **Where** does the issue occur? Where does it not occur?  
- **When** does it occur?  
 
# **When does the TSG not Apply**
_For example the TSG might not apply to Private Endpoint workspace etc._

# **Diagnosis**
_How can I debug further and mitigate this issue? Add more details on how to diagnose this issue._  
- [ ] _Put quick steps to check before doing any deep dives._ 
- [ ] _This section can include Kusto queries, Acis commands or ASC actions (preferable) for getting more diagnostic information_  
- [ ] _If is a common query link to a separate How-To Page containing the entire Kusto query, Acis Command or ASC action._  

Don't Remove This Text: Results of the Diagnosis should be attached in the Case notes/ICM.

# **Questions to Ask the Customer**
_If there is no diagnostic information available or to further drill into the issue, list down any questions you can ask the customer.-

# **Cause**
_**Why** does the issue occur? Include both internal and external details about the cause, if possible._

# **Mitigation or Resolution**
_How can I fix this issue? Add more details on how to fix this issue once it has been identified._  
- _This should be a short step by step guide.
- _This section can include Acis commands or scripts/ adhoc steps to perform resolution operations_  
- _Create a script file if possible and place a link to the script file (parameterize the script to take in user specific inputs.)_ 
- _For inline scripts, please give entire script and don't give instructions_ 
- _Put a link to a How-To Page that contains the above for common steps_ 

# **Root Cause to be shared with Customer**
_**Why** does the issue occur? If applicable, list a short root cause that can be shared with customer.Include both internal and external details about the cause, if possible_

# **Related Information**
_Where can I find more information about this issue? Add links to related content here._  
_This could be links to other TSGs, ICMs, AVA threads, Bugs, Known Issues._ 
_If there is a Public Documentation about this issue, link that here too and make sure you also update the public doc._

# **Tags or Prompts**
_Add common tags or prompts statements that can improve the searchability and copilot recommendation of this TSG._
(E.g.: This TSG helps answer _<prompt>_)
"""

TSG_BEGIN = "<!-- TSG_BEGIN -->"
TSG_END = "<!-- TSG_END -->"
QUESTIONS_BEGIN = "<!-- QUESTIONS_BEGIN -->"
QUESTIONS_END = "<!-- QUESTIONS_END -->"
REQUIRED_DIAGNOSIS_LINE = "Don't Remove This Text: Results of the Diagnosis should be attached in the Case notes/ICM."


# --- Output Validation ---

# Required TSG section headings (must appear exactly as written)
REQUIRED_TSG_HEADINGS = [
    "# **Issue Description / Symptoms**",
    "# **When does the TSG not Apply**",
    "# **Diagnosis**",
    "# **Questions to Ask the Customer**",
    "# **Cause**",
    "# **Mitigation or Resolution**",
    "# **Root Cause to be shared with Customer**",
    "# **Related Information**",
    "# **Tags or Prompts**",
]


def validate_tsg_output(response_text: str) -> dict:
    """
    Validate that the agent response follows the required format.
    Returns a dict with 'valid' bool and 'issues' list.
    """
    issues = []
    
    # Check for required markers
    if TSG_BEGIN not in response_text:
        issues.append("Missing <!-- TSG_BEGIN --> marker")
    if TSG_END not in response_text:
        issues.append("Missing <!-- TSG_END --> marker")
    if QUESTIONS_BEGIN not in response_text:
        issues.append("Missing <!-- QUESTIONS_BEGIN --> marker")
    if QUESTIONS_END not in response_text:
        issues.append("Missing <!-- QUESTIONS_END --> marker")
    
    # Extract TSG content
    tsg_content = ""
    if TSG_BEGIN in response_text and TSG_END in response_text:
        start = response_text.find(TSG_BEGIN) + len(TSG_BEGIN)
        end = response_text.find(TSG_END)
        tsg_content = response_text[start:end]
    
    # Check for required headings
    for heading in REQUIRED_TSG_HEADINGS:
        if heading not in tsg_content:
            issues.append(f"Missing required heading: {heading}")
    
    # Check for required diagnosis line
    if REQUIRED_DIAGNOSIS_LINE not in tsg_content:
        issues.append("Missing required diagnosis line")
    
    # Extract questions block
    questions_content = ""
    if QUESTIONS_BEGIN in response_text and QUESTIONS_END in response_text:
        start = response_text.find(QUESTIONS_BEGIN) + len(QUESTIONS_BEGIN)
        end = response_text.find(QUESTIONS_END)
        questions_content = response_text[start:end].strip()
    
    # Check questions block validity
    if questions_content:
        has_missing_placeholders = "{{MISSING::" in tsg_content
        has_no_missing = questions_content == "NO_MISSING"
        has_questions = "{{MISSING::" in questions_content and "->" in questions_content
        
        if has_missing_placeholders and has_no_missing:
            issues.append("TSG has {{MISSING::...}} placeholders but questions block says NO_MISSING")
        elif not has_missing_placeholders and not has_no_missing:
            issues.append("TSG has no placeholders but questions block is not NO_MISSING")
        elif has_missing_placeholders and not has_questions:
            issues.append("TSG has placeholders but questions block doesn't list them")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "tsg_content": tsg_content,
        "questions_content": questions_content,
    }


# =============================================================================
# MULTI-STAGE PIPELINE PROMPTS
# =============================================================================

# --- Stage 1: Research ---
RESEARCH_STAGE_INSTRUCTIONS = """You are a technical research specialist. Your job is to gather directly relevant documentation for a specific troubleshooting issue.

## Your Tools
- **Learn MCP**: Search Microsoft Learn documentation (learn.microsoft.com)
- **Bing Search**: Search GitHub issues, Stack Overflow, community discussions

## Your Task
Given troubleshooting notes about an issue, research using your tools and output a focused research report.

<tool_usage_rules>
- Call tools before outputting any content
- Parallelize independent searches (Learn MCP + Bing) when possible to reduce latency
- Prefer tools over internal knowledge for:
  - Current documentation and known issues
  - Specific URLs, document titles, or issue IDs
- After each tool call, briefly note: what was found, source URL, and any follow-up needed
</tool_usage_rules>

<core_rules>
1. Prioritize URLs already in the notes—verify and summarize those first
2. Search for docs directly about the specific issue, not general overviews
3. Be selective—only include sources that directly address the issue
4. Do not include tangentially related content (general tutorials, unrelated features)
5. Do not write a TSG—only gather and organize research findings
</core_rules>

<verbosity_constraints>
- Topic Summary: 2-4 sentences maximum
- Each URL entry: 1-2 sentences explaining relevance
- Key Technical Facts: ≤7 bullet points
- Cause Analysis: 1 short paragraph
- Do not rephrase or repeat content across sections
</verbosity_constraints>

<uncertainty_handling>
- If search results are ambiguous, explicitly note this in Research Gaps
- Never fabricate URLs, issue numbers, or version details when uncertain
- Use language like "Based on search results..." instead of absolute claims
- If multiple interpretations exist, present the most likely one and note alternatives
</uncertainty_handling>

## Relevance Filter
Before including any URL, ask: "Does this directly help diagnose or resolve this specific issue?"
- Include: Docs about the exact feature/error, GitHub issues about the same problem, workarounds for this issue
- Exclude: General product overviews, unrelated features, tutorials for different scenarios

## GitHub Issue Deep Dive
When you find a relevant GitHub issue:
1. Read the full issue including all comments
2. Extract any workarounds mentioned by users or maintainers
3. Note if the issue is open/closed and any official response
4. Look for phrases like: "workaround", "meanwhile", "you can", "alternative", "instead"

GitHub issues often contain community-discovered workarounds in comments that aren't in official docs.

## Output Format
```
<!-- RESEARCH_BEGIN -->
# Research Report

## Topic Summary
[2-4 sentences: what is the specific issue and what needs to be researched]

## URLs from User Notes
[First, list and summarize any URLs the user already provided - these are primary sources]
- **[Title](URL)**: What this source says about the issue (1-2 sentences)

## Official Documentation (Directly Relevant)
[Only docs that directly address this specific issue - not general overviews]
- **[Title](URL)**: How this doc relates to the specific issue (1-2 sentences)

## Community/GitHub Findings (Directly Relevant)
[Only discussions/issues about this same problem]
- **[Source Title](URL)**: Specific insight about this issue

## Key Technical Facts
[Verified facts from research that explain the issue, ≤7 bullets]
- Fact (source: URL)

## Cause Analysis
[One paragraph: what the research says about why this issue occurs]

## Customer-Safe Root Cause
[A concise explanation suitable to share with customers - no internal details]

## Solutions/Workarounds Found
[Specific solutions from research, with sources]

## Scope / When This Doesn't Apply
[Scenarios where this issue does NOT occur, e.g., specific configurations, versions, or environments that are unaffected]

## Suggested Customer Questions
[Questions to ask the customer to gather more diagnostic info, based on what research indicates is needed]

## Suggested Tags/Keywords
[Terms that would help support engineers find this TSG: error codes, feature names, symptoms]

## Research Gaps
[What couldn't be verified - will become MISSING placeholders]
- Gap: [specific information that was not found]
- Partial: [information found but incomplete - specify what's missing]

## Confidence Assessment
- Cause: [High/Medium/Low] - [why]
- Workaround: [High/Medium/Low] - [why]
<!-- RESEARCH_END -->
```

Note: Internal diagnostic tools (Kusto queries, ASC actions, Acis commands) are not publicly documented. Do not search for these - the Writer will mark them as MISSING for internal teams to fill.

## Quality Check
- Only include sources you actually retrieved via tool calls
- Every URL must be directly relevant to this issue (not just the product in general)
- If user provided URLs in notes, those are your primary sources—verify them first
- Cite sources for every fact
"""

RESEARCH_USER_PROMPT_TEMPLATE = """Research the following troubleshooting topic using your tools. Be selective—only include directly relevant sources.

<notes>
{notes}
</notes>

<instructions>
1. If the notes contain URLs, search for those specific pages to verify and summarize them first
2. Search Learn MCP for official docs directly about this specific issue
3. Search Bing for GitHub issues/discussions about this same problem
4. Output a focused research report between <!-- RESEARCH_BEGIN --> and <!-- RESEARCH_END -->
</instructions>

<relevance_filter>
- Include: Docs/issues directly about the specific error, feature, or scenario in the notes
- Exclude: General tutorials, product overviews, tangentially related features
- If a source doesn't help diagnose or resolve this issue, don't include it
</relevance_filter>

<focus_areas>
- The exact features/APIs/services mentioned in the notes
- Known issues or limitations for this specific scenario
- Workarounds others have found for this problem
- Scenarios where this issue does NOT apply (for "When TSG not Apply" section)
- Customer-facing questions that help diagnose the issue
- Keywords and error codes for searchability
</focus_areas>
"""


# --- Stage 2: Writer ---
WRITER_STAGE_INSTRUCTIONS = """You are a technical writer that creates Technical Support Guides (TSGs) from research and notes.

## Your Task
Given:
1. Raw troubleshooting notes from a support engineer
2. A research report with verified facts and sources

Create a properly formatted TSG using the exact template provided.

<scope_constraints>
- Implement exactly and only what the task requires
- No extra sections, no added recommendations, no embellishments beyond the template
- If any instruction is ambiguous, choose the simplest valid interpretation
- Do not expand the task beyond what was asked
</scope_constraints>

<core_rules>
1. You have no tools—do not attempt to search or browse
2. Use only information from the notes and research report provided
3. For any required template content not found in notes or research, use: `{{MISSING::<Section>::<Hint>}}`
4. Follow the template structure exactly
5. Never fabricate information—if it's not in notes or research, use a placeholder
</core_rules>

<long_context_handling>
- For inputs longer than 5000 tokens:
  - First, mentally outline key sections relevant to the TSG
  - Anchor claims to specific sections ("In the research Cause Analysis section...")
  - If the answer depends on fine details (dates, versions, thresholds), quote or paraphrase them
- Re-state constraints before the final output if context is long
</long_context_handling>

<uncertainty_handling>
- If a template section requires content that is not available in notes or research, use a {{MISSING::...}} placeholder
- Never fabricate exact figures, version numbers, or external references to fill gaps
- Prefer "Based on the provided research..." over absolute claims when confidence is limited
</uncertainty_handling>

## Related Information Section
Only include URLs that directly help with this issue:
1. Priority 1: URLs the user provided in their notes (most important)
2. Priority 2: Official docs that directly explain the cause or solution
3. Priority 3: GitHub issues/discussions about this same problem

Do not include:
- General product overviews or tutorials
- Docs about unrelated features
- Tangentially related content that doesn't help resolve this issue

Ask: "Would a support engineer need this link to diagnose or fix this issue?" If no, don't include it.

## Placeholder Rules
Use `{{MISSING::<Section>::<Hint>}}` to flag required template content that:
1. The user did not include in their initial notes, AND
2. The researcher could not find in documentation or community sources

This ensures all template sections are complete—either with real content or explicit gaps for the TSG author to fill.

Examples:
- `{{MISSING::Cause::Root cause not identified in notes or research}}`
- `{{MISSING::Diagnosis::Kusto query for this specific error not found}}`
- `{{MISSING::Mitigation::Step-by-step resolution not documented}}`

## Workaround/Resolution Verification
For the Mitigation or Resolution section:
- Only include workarounds that are explicitly stated in the notes or research
- If neither notes nor research provide resolution steps, use:
  `{{MISSING::Mitigation::Resolution steps not found in notes or research}}`
- Do not infer or suggest workarounds that "might work"—this counts as fabrication
- Generic advice like "monitor for updates" is acceptable, but specific technical suggestions must be sourced

## Template-Required Content Check
Before finalizing, verify each template section has content from notes/research or a MISSING placeholder:
- **Diagnosis**: Does it include actionable diagnostic steps?
  - Internal tools (Kusto queries, ASC actions, Acis commands) are not in public research—use: `{{MISSING::Diagnosis::Internal diagnostic query/command needed}}`
  - External diagnostic steps from research can be included
- **Mitigation**: Does it include actionable steps (scripts, commands, code samples)?
  - If not available in notes or research: `{{MISSING::Mitigation::Resolution steps not found}}`
- **Cause**: Is the root cause identified?
  - If not available in notes or research: `{{MISSING::Cause::Root cause not identified}}`

## Output Format
```
<!-- TSG_BEGIN -->
[Complete TSG with all required headings from template]
<!-- TSG_END -->

<!-- QUESTIONS_BEGIN -->
[One line per placeholder: `- {{MISSING::...}} -> question for TSG author`]
[OR exactly: `NO_MISSING` if no placeholders]
<!-- QUESTIONS_END -->
```

## Section Guidelines
- **Title**: Include error message or scenario keywords
- **Issue Description**: What/Who/Where/When format
- **Diagnosis**: Include the required line: "Don't Remove This Text: Results of the Diagnosis should be attached in the Case notes/ICM."
- **Questions to Ask Customer**: Customer-facing questions (different from MISSING placeholders)
- **Related Information**: Only directly relevant URLs (see rules above)
"""

WRITER_USER_PROMPT_TEMPLATE = """Write a TSG using only the notes and research below. Use {{MISSING::...}} for required template content not found in either source.

<template>
{template}
</template>

<notes>
{notes}
</notes>

<research>
{research}
</research>

<requirements>
1. Follow the template structure exactly (all headings required)
2. Use information from notes and research only—no fabrication
3. Use {{MISSING::<Section>::<Hint>}} for any required template content not in notes or research
4. Related Information: Only include URLs directly relevant to this issue:
   - URLs from the user's notes (highest priority)
   - Docs that directly explain the cause or solution
   - GitHub issues about this problem
   - Do not include general overviews, tutorials, or tangentially related content
5. Output between <!-- TSG_BEGIN --> and <!-- TSG_END -->
6. List questions for each {{MISSING}} between <!-- QUESTIONS_BEGIN --> and <!-- QUESTIONS_END -->
</requirements>
"""


# --- Stage 3: Review ---
REVIEW_STAGE_INSTRUCTIONS = """You are a QA reviewer for Technical Support Guides. Your job is to validate TSG quality, accuracy, and relevance.

## Your Task
Given:
1. A draft TSG
2. The original research report
3. The original notes

Review the TSG for:
1. **Structure**: All required sections present with correct headings
2. **Accuracy**: Claims match the research and notes (no hallucinations)
3. **Relevance**: URLs and content are directly relevant to this issue
4. **Completeness**: Appropriate use of {{MISSING::...}} placeholders
5. **Format**: Correct markers and formatting

<interpretation_guidance>
- If a claim in the TSG is a reasonable inference from the research, do not flag it as inaccurate
- If a URL is borderline relevant, err on the side of keeping it if it provides useful context
- For ambiguous cases, note them in "suggestions" rather than "accuracy_issues"
- Focus accuracy flags on clear fabrications, not stylistic differences
</interpretation_guidance>

<self_check_steps>
Before outputting your review JSON:
1. Re-read each accuracy_issue—is it a true fabrication or just a rephrasing?
2. Re-check each relevance_issue—would removing this URL leave a gap?
3. Verify structure_issues against the actual template requirements
4. Ensure corrected_tsg (if provided) actually fixes the issues listed
</self_check_steps>

## Output Format
Output a JSON review result:

```
<!-- REVIEW_BEGIN -->
{
    "approved": true/false,
    "structure_issues": ["issue1", "issue2"],
    "accuracy_issues": ["claim X not supported by research", ...],
    "relevance_issues": ["URL X is not directly relevant to this issue", ...],
    "completeness_issues": ["missing placeholder for X", ...],
    "format_issues": ["missing marker X", ...],
    "suggestions": ["optional improvement suggestions"],
    "corrected_tsg": null or "[full corrected TSG if fixable]"
}
<!-- REVIEW_END -->
```

## Review Checklist

### Structure Check
- [ ] Has <!-- TSG_BEGIN --> and <!-- TSG_END --> markers
- [ ] Has <!-- QUESTIONS_BEGIN --> and <!-- QUESTIONS_END --> markers
- [ ] Contains all 9+ required section headings
- [ ] Diagnosis includes required text: "Don't Remove This Text: Results of the Diagnosis should be attached in the Case notes/ICM."

### Accuracy Check
- [ ] Technical claims match research findings
- [ ] Code snippets match those from notes/research (not fabricated)
- [ ] No hallucinated features, APIs, or procedures

### Relevance Check
- [ ] Every URL in "Related Information" directly helps diagnose or resolve this issue
- [ ] URLs from user's notes are included (highest priority)
- [ ] No general product overviews or tutorials that don't address this specific issue
- [ ] No tangentially related content (e.g., docs about different features)
- [ ] Flag and remove any URL that doesn't pass: "Would a support engineer need this to fix this issue?"

### Completeness Check
- [ ] Required template content not in notes AND not in research uses {{MISSING::...}}
- [ ] Questions block matches placeholders (or NO_MISSING if none)
- [ ] No placeholder where research provided verified info
- [ ] Internal-only content (Kusto queries, ASC actions) appropriately marked MISSING

### Auto-Correction
If issues are fixable (irrelevant URLs, missing marker, wrong heading format), provide the corrected TSG in "corrected_tsg".
- Remove irrelevant URLs from Related Information
- Fix structure issues
If issues require re-research or major rewrite, set "corrected_tsg": null.

## Guidelines
- Be strict about accuracy—flag any claim not supported by research
- Structure and relevance issues are usually auto-fixable
- Accuracy issues may require human review
- Apply self_check_steps before finalizing output
"""

REVIEW_USER_PROMPT_TEMPLATE = """Review this TSG draft for quality and accuracy.

<draft_tsg>
{draft_tsg}
</draft_tsg>

<research>
{research}
</research>

<original_notes>
{notes}
</original_notes>

<validation_criteria>
1. Structure: All required sections and markers present
2. Accuracy: Claims supported by research (no hallucinations)
3. Completeness: Appropriate {{MISSING::...}} placeholders
4. Format: Correct output format
</validation_criteria>

<output_instructions>
- Output your review between <!-- REVIEW_BEGIN --> and <!-- REVIEW_END --> as JSON
- If issues are auto-fixable, include "corrected_tsg" with the fixed version
- Apply self-check steps before finalizing: verify each issue is valid and corrections actually fix them
</output_instructions>
"""


# Research stage markers
RESEARCH_BEGIN = "<!-- RESEARCH_BEGIN -->"
RESEARCH_END = "<!-- RESEARCH_END -->"
REVIEW_BEGIN = "<!-- REVIEW_BEGIN -->"
REVIEW_END = "<!-- REVIEW_END -->"


def build_research_prompt(notes: str) -> str:
    """Build the prompt for the research stage."""
    return RESEARCH_USER_PROMPT_TEMPLATE.format(notes=notes)


def build_writer_prompt(notes: str, research: str, prior_tsg: str | None = None, user_answers: str | None = None) -> str:
    """Build the prompt for the writer stage."""
    prompt = WRITER_USER_PROMPT_TEMPLATE.format(
        template=TSG_TEMPLATE,
        notes=notes,
        research=research,
    )
    if prior_tsg:
        prompt += f"\n\n<prior_tsg>\n{prior_tsg}\n</prior_tsg>\n"
    if user_answers:
        prompt += f"\n\n<answers>\n{user_answers}\n</answers>\nReplace {{MISSING::...}} placeholders with these answers.\n"
    return prompt


def build_review_prompt(draft_tsg: str, research: str, notes: str) -> str:
    """Build the prompt for the review stage."""
    return REVIEW_USER_PROMPT_TEMPLATE.format(
        draft_tsg=draft_tsg,
        research=research,
        notes=notes,
    )


def extract_research_block(response: str) -> str | None:
    """Extract the research report from agent response."""
    if RESEARCH_BEGIN in response and RESEARCH_END in response:
        start = response.find(RESEARCH_BEGIN) + len(RESEARCH_BEGIN)
        end = response.find(RESEARCH_END)
        return response[start:end].strip()
    return None


def extract_review_block(response: str) -> dict | None:
    """Extract and parse the review JSON from agent response."""
    import json
    if REVIEW_BEGIN in response and REVIEW_END in response:
        start = response.find(REVIEW_BEGIN) + len(REVIEW_BEGIN)
        end = response.find(REVIEW_END)
        json_str = response[start:end].strip()
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code block
            if "```" in json_str:
                # Find JSON between code fences
                lines = json_str.split("\n")
                in_block = False
                json_lines = []
                for line in lines:
                    if line.strip().startswith("```"):
                        if in_block:
                            break
                        in_block = True
                        continue
                    if in_block:
                        json_lines.append(line)
                if json_lines:
                    try:
                        return json.loads("\n".join(json_lines))
                    except json.JSONDecodeError:
                        pass
            return None
    return None