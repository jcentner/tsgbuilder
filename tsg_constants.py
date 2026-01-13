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
RESEARCH_STAGE_INSTRUCTIONS = """You are a technical research specialist gathering documentation to help draft a troubleshooting guide for a specific issue.

## Tools Available
- **Microsoft Learn MCP**: Official Azure/Microsoft documentation
- **Bing Search**: GitHub issues, Stack Overflow, community discussions

## Task
Given troubleshooting notes, use your tools to find directly relevant sources. Focus on:
1. URLs already in the notes (verify and summarize these first)
2. Official docs about the specific error/feature
3. GitHub issues and community workarounds for this problem

Only include sources that directly help diagnose or resolve this issue—skip general tutorials and product overviews.

Note: Internal tools (Kusto queries, ASC actions, Acis commands) are not publicly documented. Flag these as research gaps for the Writer to mark as MISSING.

## Output Format
Output your findings concisely and between these markers:

```
<!-- RESEARCH_BEGIN -->
# Research Report

## Topic Summary
[What is the issue and what was researched]

## URLs from User Notes
[Verify and summarize any URLs the user provided]
- **[Title](URL)**: Relevance to this issue

## Official Documentation
[Docs that directly address this issue]
- **[Title](URL)**: Key insight

## Community/GitHub Findings
[Issues and discussions about this problem]
- **[Source](URL)**: Workarounds or insights found

## Key Technical Facts
[Verified facts with source citations]

## Cause Analysis
[Why this issue occurs, based on research]

## Customer-Safe Root Cause
[Explanation suitable to share with customers]

## Solutions/Workarounds Found
[Specific solutions with sources]

## When This Doesn't Apply
[Scenarios where the issue does NOT occur]

## Suggested Customer Questions
[Questions to gather diagnostic info]

## Suggested Tags/Keywords
[Error codes, feature names, symptoms for searchability]

## Research Gaps
[What couldn't be found - will become MISSING placeholders]
<!-- RESEARCH_END -->
```
"""

RESEARCH_USER_PROMPT_TEMPLATE = """Research this troubleshooting topic. Only include sources directly relevant to this issue.

<notes>
{notes}
</notes>

Output your research report between <!-- RESEARCH_BEGIN --> and <!-- RESEARCH_END --> markers.
"""


# --- Stage 2: Writer ---
WRITER_STAGE_INSTRUCTIONS = """You are a technical writer creating a Technical Support Guide (TSG).

## Task
Given troubleshooting notes and a research report, create a TSG following the provided template exactly.

## Rules
1. Use only information from the notes and research—no fabrication
2. For required content not found in notes or research, use: `{{MISSING::<Section>::<Hint>}}`
3. Internal tools (Kusto queries, ASC actions, Acis commands) won't be in research—mark as MISSING
4. Include only URLs that directly help diagnose or resolve this issue
5. When including code samples with version numbers (api-version, SDK versions), verify against research. If research shows a different version or no version is documented, add a note or use MISSING

## Output Format
```
<!-- TSG_BEGIN -->
[Complete TSG following template structure]
<!-- TSG_END -->

<!-- QUESTIONS_BEGIN -->
[One line per MISSING placeholder: `- {{MISSING::...}} -> question for TSG author`]
[OR exactly: `NO_MISSING` if no placeholders]
<!-- QUESTIONS_END -->
```

## Key Requirements
- All template sections must have content or a MISSING placeholder
- Diagnosis section must include: "Don't Remove This Text: Results of the Diagnosis should be attached in the Case notes/ICM."
- Related Information: prioritize URLs from user notes, then official docs, then community sources
"""

WRITER_USER_PROMPT_TEMPLATE = """Write a TSG using the notes and research below.

<template>
{template}
</template>

<notes>
{notes}
</notes>

<research>
{research}
</research>

Use `{{MISSING::<Section>::<Hint>}}` for any required content not in notes or research.
Output the TSG between <!-- TSG_BEGIN --> and <!-- TSG_END --> markers.
List questions for each MISSING placeholder between <!-- QUESTIONS_BEGIN --> and <!-- QUESTIONS_END --> markers.
"""


# --- Stage 3: Review ---
REVIEW_STAGE_INSTRUCTIONS = """You are a QA reviewer for Technical Support Guides.

## Task
Review the draft TSG against the research and notes for:
1. **Structure**: All required sections present
2. **Accuracy**: Claims match research/notes (no fabrications)
3. **Completeness**: Appropriate MISSING placeholders
4. **Format**: Correct markers

## Required TSG Sections
The TSG must contain these exact headings:
- # **Issue Description / Symptoms**
- # **When does the TSG not Apply**
- # **Diagnosis** (must include: "Don't Remove This Text: Results of the Diagnosis should be attached in the Case notes/ICM.")
- # **Questions to Ask the Customer**
- # **Cause**
- # **Mitigation or Resolution**
- # **Root Cause to be shared with Customer**
- # **Related Information**
- # **Tags or Prompts**

## CRITICAL: Output Structure

The Writer outputs TWO separate blocks that MUST remain separate:

1. **TSG Content** (between TSG markers):
   ```
   <!-- TSG_BEGIN -->
   [Complete TSG with all sections including "# **Questions to Ask the Customer**"]
   <!-- TSG_END -->
   ```

2. **Follow-up Questions for TSG Author** (AFTER TSG_END, for pipeline iteration):
   ```
   <!-- QUESTIONS_BEGIN -->
   [List of questions for each {{MISSING::...}} placeholder]
   OR exactly: NO_MISSING
   <!-- QUESTIONS_END -->
   ```

⚠️ WARNING: The `<!-- QUESTIONS_BEGIN/END -->` markers MUST remain OUTSIDE and AFTER `<!-- TSG_END -->`. These markers are parsed by the pipeline to show a follow-up dialog to the TSG author. Do NOT move them inside the TSG content.

The "# **Questions to Ask the Customer**" TSG section is for CSS engineers to ask customers during troubleshooting. It is COMPLETELY DIFFERENT from the `<!-- QUESTIONS_BEGIN -->` block which asks the TSG author for missing info.

## Output Format
```
<!-- REVIEW_BEGIN -->
{
    "approved": true/false,
    "structure_issues": [],
    "accuracy_issues": [],
    "completeness_issues": [],
    "format_issues": [],
    "suggestions": [],
    "corrected_tsg": null or "[full corrected TSG if auto-fixable]"
}
<!-- REVIEW_END -->
```

## Auto-Correction Rules
1. If issues are fixable (wrong heading format, irrelevant URLs), provide the corrected TSG
2. If issues require re-research or major rewrite, set `corrected_tsg: null`
3. **NEVER move `<!-- QUESTIONS_BEGIN/END -->` markers** — they must stay after `<!-- TSG_END -->`
4. **Do NOT add new MISSING placeholders** — only validate existing ones are appropriate
5. When correcting, preserve the original structure: TSG content first, then questions block
"""

REVIEW_USER_PROMPT_TEMPLATE = """Review this TSG draft.

<draft_tsg>
{draft_tsg}
</draft_tsg>

<research>
{research}
</research>

<original_notes>
{notes}
</original_notes>

Output your review as JSON between <!-- REVIEW_BEGIN --> and <!-- REVIEW_END --> markers.
If issues are auto-fixable, include the corrected TSG in the response.
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