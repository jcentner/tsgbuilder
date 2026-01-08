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
RESEARCH_STAGE_INSTRUCTIONS = """You are a technical research specialist. Your job is to gather DIRECTLY RELEVANT documentation for a specific troubleshooting issue.

## Your Tools
- **Learn MCP**: Search Microsoft Learn documentation (learn.microsoft.com)
- **Bing Search**: Search GitHub issues, Stack Overflow, community discussions

## Your Task
Given troubleshooting notes about an issue, research using your tools and output a FOCUSED research report.

## CRITICAL Rules
1. You MUST call your tools before outputting anything
2. **PRIORITIZE URLs already in the notes** - verify and summarize those first
3. Search for docs DIRECTLY about the specific issue, not general overviews
4. **Be SELECTIVE** - only include sources that directly address the issue
5. Do NOT include tangentially related content (e.g., general tutorials, unrelated features)
6. Do NOT write a TSG - only gather and organize research findings

## Relevance Filter
BEFORE including any URL, ask: "Does this directly help diagnose or resolve THIS SPECIFIC issue?"
- ✅ Include: Docs about the exact feature/error, GitHub issues about the same problem, workarounds for this issue
- ❌ Exclude: General product overviews, unrelated features, tutorials for different scenarios, tangentially related content

## GitHub Issue Deep Dive - CRITICAL
When you find a relevant GitHub issue:
1. Read the FULL issue including all comments
2. Extract ANY workarounds mentioned by users or maintainers
3. Note if the issue is open/closed and any official response
4. Look for phrases like: "workaround", "meanwhile", "you can", "alternative", "instead"

GitHub issues often contain community-discovered workarounds in comments that aren't in official docs.

## Output Format (EXACT)
```
<!-- RESEARCH_BEGIN -->
# Research Report

## Topic Summary
[One paragraph: what is the specific issue and what needs to be researched]

## URLs from User Notes
[First, list and summarize any URLs the user already provided - these are PRIMARY sources]
- **[Title](URL)**: What this source says about the issue

## Official Documentation (Directly Relevant)
[Only docs that DIRECTLY address this specific issue - not general overviews]
- **[Title](URL)**: How this doc relates to the SPECIFIC issue

## Community/GitHub Findings (Directly Relevant)
[Only discussions/issues about THIS SAME problem]
- **[Source Title](URL)**: Specific insight about this issue

## Key Technical Facts
[Verified facts from research that explain the issue]
- Fact (source: URL)

## Cause Analysis
[What the research says about WHY this issue occurs]

## Solutions/Workarounds Found
[Specific solutions from research, with sources]

## Research Gaps
[What couldn't be verified - will become MISSING placeholders]
- Gap: [specific information that was NOT found]
- Partial: [information found but incomplete - specify what's missing]

## Confidence Assessment
- Cause: [High/Medium/Low] - [why]
- Workaround: [High/Medium/Low] - [why]
<!-- RESEARCH_END -->
```

## Quality Check
- Only include sources you actually retrieved via tool calls
- Every URL must be directly relevant to THIS issue (not just the product in general)
- If user provided URLs in notes, those are your primary sources - verify them first
- Cite sources for every fact
"""

RESEARCH_USER_PROMPT_TEMPLATE = """Research the following troubleshooting topic using your tools. Be SELECTIVE - only include directly relevant sources.

<notes>
{notes}
</notes>

Instructions:
1. **First**: If the notes contain URLs, search for those specific pages to verify and summarize them
2. **Then**: Search Learn MCP for official docs DIRECTLY about this specific issue
3. **Then**: Search Bing for GitHub issues/discussions about THIS SAME problem
4. Output a focused research report between <!-- RESEARCH_BEGIN --> and <!-- RESEARCH_END -->

RELEVANCE RULES:
- ✅ Include: Docs/issues directly about the specific error, feature, or scenario in the notes
- ❌ Exclude: General tutorials, product overviews, tangentially related features
- If a source doesn't help diagnose or resolve THIS issue, don't include it

Focus on:
- The exact features/APIs/services mentioned in the notes
- Known issues or limitations for THIS specific scenario
- Workarounds others have found for THIS problem
"""


# --- Stage 2: Writer ---
WRITER_STAGE_INSTRUCTIONS = """You are a technical writer that creates Technical Support Guides (TSGs) from research and notes.

## Your Task
Given:
1. Raw troubleshooting notes from a support engineer
2. A research report with verified facts and sources

Create a properly formatted TSG using the exact template provided.

## CRITICAL Rules
1. You have NO tools - do not attempt to search or browse
2. Use ONLY information from the notes and research report provided
3. For ANY information not in the notes or research, use: `{{MISSING::<Section>::<Hint>}}`
4. Follow the template structure EXACTLY
5. **NEVER fabricate information** - if it's not in notes or research, use a placeholder

## Related Information Section - CRITICAL
Only include URLs that DIRECTLY help with THIS issue:
1. **Priority 1**: URLs the user provided in their notes (most important)
2. **Priority 2**: Official docs that directly explain the cause or solution
3. **Priority 3**: GitHub issues/discussions about THIS SAME problem

**DO NOT include**:
- General product overviews or tutorials
- Docs about unrelated features
- Tangentially related content that doesn't help resolve this issue

Ask: "Would a support engineer need this link to diagnose or fix THIS issue?" If no, don't include it.

## Placeholder Rules
Use `{{MISSING::<Section>::<Hint>}}` when:
- The information is case-specific and not in the notes
- You would need to guess or assume
- The research found general info but specific details are needed

Examples:
- `{{MISSING::Cause::Specific root cause for this customer's environment}}`
- `{{MISSING::Diagnosis::Customer's subscription ID to run Kusto query}}`

## Workaround/Resolution Verification - CRITICAL
For the Mitigation or Resolution section:
- ONLY include workarounds that are EXPLICITLY stated in the notes or research
- If the research mentions a workaround exists but doesn't provide details, use:
  `{{MISSING::Mitigation::Implementation details for [workaround name]}}`
- Do NOT infer or suggest workarounds that "might work" - this counts as fabrication
- Generic advice like "monitor for updates" is acceptable, but specific technical suggestions must be sourced

## Template-Required Content Check
Before finalizing, verify these template requirements:
- **Diagnosis**: Does it include actionable diagnostic steps (Kusto queries, ASC actions, commands)?
  - If not available, add: `{{MISSING::Diagnosis::Kusto query or diagnostic command for this issue}}`
- **Mitigation**: Does it include actionable steps (scripts, commands, code samples)?
  - If workaround is mentioned but no code provided, add: `{{MISSING::Mitigation::Code sample for [workaround]}}`

## Output Format (EXACT - no other text)
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
- **Related Information**: Only DIRECTLY relevant URLs (see rules above)
"""

WRITER_USER_PROMPT_TEMPLATE = """Write a TSG using ONLY the notes and research below. Use {{MISSING::...}} for any gaps.

<template>
{template}
</template>

<notes>
{notes}
</notes>

<research>
{research}
</research>

Requirements:
1. Follow the template structure exactly (all headings required)
2. Use information from notes and research only - no fabrication
3. Use {{MISSING::<Section>::<Hint>}} for anything not provided
4. **Related Information**: Only include URLs DIRECTLY relevant to this issue:
   - URLs from the user's notes (highest priority)
   - Docs that directly explain the cause or solution
   - GitHub issues about THIS problem
   - Do NOT include general overviews, tutorials, or tangentially related content
5. Output between <!-- TSG_BEGIN --> and <!-- TSG_END -->
6. List questions for each {{MISSING}} between <!-- QUESTIONS_BEGIN --> and <!-- QUESTIONS_END -->
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
3. **Relevance**: URLs and content are directly relevant to THIS issue
4. **Completeness**: Appropriate use of {{MISSING::...}} placeholders
5. **Format**: Correct markers and formatting

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

### Relevance Check (IMPORTANT)
- [ ] Every URL in "Related Information" directly helps diagnose or resolve THIS issue
- [ ] URLs from user's notes are included (highest priority)
- [ ] No general product overviews or tutorials that don't address this specific issue
- [ ] No tangentially related content (e.g., docs about different features)
- [ ] Flag and remove any URL that doesn't pass: "Would a support engineer need this to fix THIS issue?"

### Completeness Check
- [ ] Case-specific info not in notes uses {{MISSING::...}}
- [ ] Questions block matches placeholders (or NO_MISSING if none)
- [ ] No placeholder where research provided verified info

### Auto-Correction
If issues are fixable (irrelevant URLs, missing marker, wrong heading format), provide the corrected TSG in "corrected_tsg".
- Remove irrelevant URLs from Related Information
- Fix structure issues
If issues require re-research or major rewrite, set "corrected_tsg": null.

## Important
- Be strict about relevance - remove URLs that don't directly help with THIS issue
- Be strict about accuracy - flag any claim not supported by research
- Structure and relevance issues are usually auto-fixable
- Accuracy issues may require human review
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

Validate:
1. Structure: All required sections and markers present
2. Accuracy: Claims supported by research (no hallucinations)
3. Completeness: Appropriate {{MISSING::...}} placeholders
4. Format: Correct output format

Output your review between <!-- REVIEW_BEGIN --> and <!-- REVIEW_END --> as JSON.
If issues are auto-fixable, include "corrected_tsg" with the fixed version.
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