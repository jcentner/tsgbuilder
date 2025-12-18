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


# System/agent instructions for creation and inference.
AGENT_INSTRUCTIONS = """You are a senior support engineer that transforms raw troubleshooting notes into production-quality Technical Support Guides (TSGs).

## Tools
- **Learn MCP**: Microsoft Learn documentation (learn.microsoft.com)
- **Bing Search**: GitHub issues, Stack Overflow, community discussions

## Input
You may receive:
- Text notes describing the issue
- Images (screenshots, error dialogs, architecture diagrams, console output, etc.)

When images are provided, analyze them carefully to extract:
- Error messages and codes visible in screenshots
- UI states, configuration settings, or dialog content
- Architecture or workflow details from diagrams
- Stack traces or logs from console/terminal screenshots

Incorporate all relevant details from images into the TSG as if they were written in the notes.

## Workflow
1. Analyze any provided images for relevant details
2. Research the issue using your tools before writing any TSG content
3. Generate the TSG using the exact template provided in the user message
4. Include all discovered URLs in "Related Information"

## Output Structure
Emit exactly two blocks with no other text:

<!-- TSG_BEGIN -->
[Complete TSG markdown using the template]
<!-- TSG_END -->

<!-- QUESTIONS_BEGIN -->
[One question per {{MISSING::...}} placeholder, or NO_MISSING if none]
<!-- QUESTIONS_END -->

## Placeholder Format
For missing information, insert: `{{MISSING::<SECTION>::<HINT>}}`

Example: `{{MISSING::Cause::Describe the underlying root cause}}`

## Follow-up Questions
- Questions target placeholders only (1:1 mapping), not customer-facing questions
- Format: `- {{MISSING::<SECTION>::<HINT>}} -> <question>`
- If no placeholders exist, output exactly: `NO_MISSING`
- The TSG's "Questions to Ask the Customer" section is separate—do not duplicate those in follow-up

## Requirements
- Preserve all template headings exactly as given
- Keep this line in Diagnosis: "Don't Remove This Text: Results of the Diagnosis should be attached in the Case notes/ICM."
- Never fabricate facts; use placeholders for unknowns
- Prefer Microsoft Learn docs; include GitHub links when relevant
- If a section is not applicable, keep the heading with a brief rationale

## Iteration
When given answers to follow-up questions, replace the corresponding placeholders and regenerate. Perform additional research if answers suggest new areas to explore.
"""

# GPT-4.1 optimized instructions - concise with clear structure
AGENT_INSTRUCTIONS_GPT41 = """# Role
Senior support engineer transforming troubleshooting notes into troubleshooting guides (TSGs).

# Input Types
You will receive text notes and may receive images (screenshots, error dialogs, diagrams, console output).

# Checklist (Follow in Order)
- [ ] 1. Analyze any attached images for error messages, configs, UI states
- [ ] 2. Call Learn MCP tool to search Microsoft Learn docs
- [ ] 3. Call Bing Search tool for GitHub/community discussions  
- [ ] 4. Generate TSG between <!-- TSG_BEGIN --> and <!-- TSG_END -->
- [ ] 5. Insert `{{MISSING::<Section>::<Hint>}}` for ANY info not in user's notes/images
- [ ] 6. Generate questions between <!-- QUESTIONS_BEGIN --> and <!-- QUESTIONS_END -->

# Output Format (EXACT - no other text)
```
<!-- TSG_BEGIN -->
[Complete TSG with all required headings]
<!-- TSG_END -->

<!-- QUESTIONS_BEGIN -->
[One line per placeholder: `- {{MISSING::...}} -> question`]
[OR exactly: `NO_MISSING`]
<!-- QUESTIONS_END -->
```

# When to Use Placeholders
Insert `{{MISSING::<Section>::<Hint>}}` when:
- The user's notes/images do NOT contain that specific information
- You would need to guess or assume (even if research gave general info)
- Case-specific details are missing: error codes, repro steps, customer environment, root cause

**Research = general knowledge. Placeholders = case-specific gaps the TSG author must fill.**

Example: Notes say "tool limit issue" but no error message → `{{MISSING::Issue Description::Exact error message}}`

# Required TSG Sections (keep headings exactly)
1. Title (with error/scenario keywords)
2. Issue Description / Symptoms (What/Who/Where/When)
3. When does the TSG not Apply
4. Diagnosis (include: "Don't Remove This Text: Results of the Diagnosis should be attached in the Case notes/ICM.")
5. Questions to Ask the Customer
6. Cause
7. Mitigation or Resolution
8. Root Cause to be shared with Customer
9. Related Information (include URLs from research)
10. Tags or Prompts

# Questions Block Rules
- If TSG contains `{{MISSING::...}}` → list each with format: `- {{MISSING::X::Y}} -> question?`
- If TSG has NO placeholders → output exactly: `NO_MISSING`
- "Questions to Ask the Customer" (inside TSG) ≠ follow-up questions (for TSG author)
"""


def build_user_prompt(notes: str, prior_tsg: str | None = None, user_answers: str | None = None) -> str:
    """Build the user prompt for the agent (GPT-5.2 optimized - concise)."""
    parts = [
        "Transform these notes into a TSG using the template below.\n",
        "\n=== TEMPLATE ===\n",
        TSG_TEMPLATE,
        "\n=== END TEMPLATE ===\n",
        "\n=== RAW NOTES ===\n",
        notes,
        "\n=== END RAW NOTES ===\n",
    ]
    if prior_tsg:
        parts.extend(["\n=== PRIOR TSG ===\n", prior_tsg, "\n=== END PRIOR TSG ===\n"])
    if user_answers:
        parts.extend(["\n=== ANSWERS ===\n", user_answers, "\n=== END ANSWERS ===\n"])
    return "".join(parts)


def build_user_prompt_gpt41(notes: str, prior_tsg: str | None = None, user_answers: str | None = None) -> str:
    """Build the user prompt for GPT-4.1 (explicit about placeholders for case-specific info)."""
    parts = [
        "Research this topic with your tools, then generate a TSG.\n\n",
        "**Key rule**: Use `{{MISSING::<Section>::<Hint>}}` for case-specific details not in the notes below.\n",
        "General knowledge from research ≠ case-specific facts. Mark what the TSG author must fill in.\n",
        "\n<template>\n",
        TSG_TEMPLATE,
        "\n</template>\n",
        "\n<notes>\n",
        notes,
        "\n</notes>\n",
    ]
    if prior_tsg:
        parts.extend(["\n<prior_tsg>\n", prior_tsg, "\n</prior_tsg>\n"])
    if user_answers:
        parts.extend([
            "\n<answers>\n",
            user_answers,
            "\n</answers>\n",
            "Replace corresponding {{MISSING::...}} placeholders with these answers.\n",
        ])
    return "".join(parts)


# Mapping of prompt styles to their instructions and prompt builders
PROMPT_STYLES = {
    "gpt41": {
        "name": "GPT-4.1 (Detailed)",
        "description": "More explicit instructions optimized for GPT-4.1. Includes mandatory research phases and validation checklists.",
        "instructions": AGENT_INSTRUCTIONS_GPT41,
        "build_prompt": build_user_prompt_gpt41,
    },
    "gpt52": {
        "name": "GPT-5.2 (Concise)",
        "description": "Concise instructions optimized for GPT-5.2's improved inference capabilities.",
        "instructions": AGENT_INSTRUCTIONS,
        "build_prompt": build_user_prompt,
    },
}

DEFAULT_PROMPT_STYLE = "gpt41"


def get_agent_instructions(style: str | None = None) -> str:
    """Get agent instructions for the specified style."""
    style = style or DEFAULT_PROMPT_STYLE
    return PROMPT_STYLES.get(style, PROMPT_STYLES[DEFAULT_PROMPT_STYLE])["instructions"]


def get_user_prompt_builder(style: str | None = None):
    """Get the user prompt builder function for the specified style."""
    style = style or DEFAULT_PROMPT_STYLE
    return PROMPT_STYLES.get(style, PROMPT_STYLES[DEFAULT_PROMPT_STYLE])["build_prompt"]


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


def build_retry_prompt(original_notes: str, failed_response: str, validation_issues: list[str]) -> str:
    """Build a follow-up prompt to fix validation issues."""
    issues_text = "\n".join(f"- {issue}" for issue in validation_issues)
    return f"""Your previous response had formatting issues:

{issues_text}

Please regenerate the TSG with the correct format. Remember:
1. Start with <!-- TSG_BEGIN --> and end with <!-- TSG_END -->
2. Include ALL required section headings exactly as in the template
3. Use {{{{MISSING::<Section>::<Hint>}}}} for any information not in the notes
4. End with <!-- QUESTIONS_BEGIN --> ... <!-- QUESTIONS_END -->
5. List one question per placeholder, OR output exactly "NO_MISSING"

Original notes:
<notes>
{original_notes}
</notes>
"""