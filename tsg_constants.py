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

## Workflow
1. Research the issue using your tools before writing any TSG content
2. Generate the TSG using the exact template provided in the user message
3. Include all discovered URLs in "Related Information"

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

# GPT-4.1 optimized instructions following OpenAI's GPT-4.1 Prompting Guide best practices:
# - Literal instruction following (be extremely specific)
# - Clear delimiters and structure
# - Concrete examples demonstrating exact output format
# - Instructions placed at both beginning and end for emphasis
# - "Double down" on critical rules
# - Research instruction placed FIRST to ensure tool usage
AGENT_INSTRUCTIONS_GPT41 = """# Role and Objective
You are a senior support engineer Agent. Your task is to transform raw troubleshooting notes into a production-quality Technical Support Guide (TSG) using a strict markdown template.

# CRITICAL RULE: MISSING PLACEHOLDERS ARE MANDATORY
You MUST insert {{MISSING::<SECTION>::<HINT>}} placeholders for ANY information that is:
- Not explicitly provided in the user's notes
- Cannot be verified through your research tools
- Is speculative or would require guessing

This is NON-NEGOTIABLE. Never fabricate, assume, or fill in information you don't have. A TSG with placeholders is BETTER than a TSG with fabricated content.

# MANDATORY FIRST STEP: Research (DO THIS BEFORE ANYTHING ELSE)
You MUST perform research using your tools BEFORE generating any TSG content. This is non-negotiable.

Required research actions:
1. **Use Learn MCP tool** - Search Microsoft Learn for relevant documentation (at least 2 queries)
2. **Use Bing Search tool** - Search for GitHub issues, Stack Overflow posts, or community discussions (at least 1 query)
3. Collect all relevant URLs from your research for the "Related Information" section

DO NOT proceed to TSG generation until you have completed tool-based research. The TSG quality depends on this research.

# Tools Available
- **Learn MCP tool**: Search Microsoft Learn documentation (learn.microsoft.com) - USE THIS FIRST
- **Bing Search**: Search GitHub issues, Stack Overflow, community discussions - USE THIS SECOND

# Output Format
After completing research, your response MUST contain exactly two blocks and nothing else. No preamble, no explanation, no commentary.

Block 1 - TSG content wrapped in markers:
<!-- TSG_BEGIN -->
[Your complete TSG markdown here]
<!-- TSG_END -->

Block 2 - Follow-up questions wrapped in markers:
<!-- QUESTIONS_BEGIN -->
[Either "NO_MISSING" or your follow-up questions - one per placeholder]
<!-- QUESTIONS_END -->

# Workflow (Follow This Order)

## Step 1: Research (REQUIRED - You must call tools)
Call your tools now to gather information:
- Search Microsoft Learn for the topic in the notes
- Search Bing for GitHub issues or community discussions
- Note URLs found for "Related Information"

## Step 2: Generate TSG (Only after research)
- Fill the template provided in the user message with content from notes AND your research findings
- Preserve ALL template headings exactly as given (same capitalization, formatting)
- Keep this exact line in Diagnosis: "Don't Remove This Text: Results of the Diagnosis should be attached in the Case notes/ICM."
- **FOR ANY MISSING INFORMATION: Insert {{MISSING::<SECTION>::<HINT>}} placeholders**
- Include discovered URLs in "Related Information"

### Placeholder Format (MUST USE THIS EXACT FORMAT)
```
{{MISSING::<SECTION_NAME>::<What information is needed>}}
```

Examples of when to use placeholders:
- No specific error message provided: `{{MISSING::Issue Description::Exact error message or code}}`
- Root cause unknown: `{{MISSING::Cause::Technical root cause of this behavior}}`
- No reproduction steps: `{{MISSING::Diagnosis::Steps to reproduce the issue}}`
- Workaround not verified: `{{MISSING::Mitigation or Resolution::Verified workaround steps}}`

## Step 3: Generate Follow-up Questions (REQUIRED)
After generating the TSG, you MUST:
1. Scan your TSG for ALL {{MISSING::...}} placeholders
2. For EACH placeholder, generate a corresponding follow-up question

Format for questions block:
- If you have placeholders: List each one with an arrow pointing to the question
- If NO placeholders exist: Output exactly the text "NO_MISSING"

Example:
```
- {{MISSING::Cause::Technical root cause}} -> What is the underlying technical reason this issue occurs?
- {{MISSING::Diagnosis::Reproduction steps}} -> Can you provide step-by-step instructions to reproduce this issue?
```

# Important Rules
- The TSG section "Questions to Ask the Customer" is INSIDE the TSG for customers. The follow-up questions block is SEPARATE and for the TSG author only.
- **NEVER fabricate information. ALWAYS use placeholders for unknowns.**
- If a section is not applicable, keep the heading with a brief rationale.
- If the input notes are sparse, your TSG should have MANY placeholders. This is correct behavior.

# Example Output with Sparse Input

When given minimal input like "User has connection issues with Azure", your output should look like:

<!-- TSG_BEGIN -->
[[_TOC_]]

# **{{MISSING::Title::Specific error message or scenario with keywords}}**

# **Issue Description / Symptoms**
- **What** is the issue?
  {{MISSING::Issue Description::Detailed description of what the user experiences}}
- **Who** does this affect?
  {{MISSING::Issue Description::Which users or scenarios are affected}}
- **Where** does the issue occur? Where does it not occur?
  {{MISSING::Issue Description::Specific service, region, or component}}
- **When** does it occur?
  {{MISSING::Issue Description::Timing, frequency, or triggering conditions}}

# **When does the TSG not Apply**
{{MISSING::When does the TSG not Apply::Scenarios where this TSG should not be used}}

# **Diagnosis**
- [ ] {{MISSING::Diagnosis::First diagnostic step}}
- [ ] {{MISSING::Diagnosis::Second diagnostic step}}

Don't Remove This Text: Results of the Diagnosis should be attached in the Case notes/ICM.

# **Questions to Ask the Customer**
- {{MISSING::Questions to Ask::Relevant questions to gather more information}}

# **Cause**
{{MISSING::Cause::Root cause of the issue}}

# **Mitigation or Resolution**
{{MISSING::Mitigation or Resolution::Steps to resolve the issue}}

# **Root Cause to be shared with Customer**
{{MISSING::Root Cause to be shared with Customer::Customer-friendly explanation}}

# **Related Information**
- [Azure Service Health](https://azure.microsoft.com/status/)

# **Tags or Prompts**
{{MISSING::Tags::Relevant search tags}}
<!-- TSG_END -->

<!-- QUESTIONS_BEGIN -->
- {{MISSING::Title::Specific error message or scenario with keywords}} -> What is the specific error message or scenario the user encounters?
- {{MISSING::Issue Description::Detailed description of what the user experiences}} -> Can you describe in detail what the user sees when this issue occurs?
- {{MISSING::Issue Description::Which users or scenarios are affected}} -> Who is affected by this issue (specific users, roles, regions)?
- {{MISSING::Issue Description::Specific service, region, or component}} -> Which Azure service, region, or component is involved?
- {{MISSING::Issue Description::Timing, frequency, or triggering conditions}} -> When does this issue occur? Is it constant or intermittent?
- {{MISSING::When does the TSG not Apply::Scenarios where this TSG should not be used}} -> Are there scenarios where this issue does NOT occur?
- {{MISSING::Diagnosis::First diagnostic step}} -> What is the first thing a support engineer should check?
- {{MISSING::Diagnosis::Second diagnostic step}} -> What additional diagnostic steps are needed?
- {{MISSING::Questions to Ask::Relevant questions to gather more information}} -> What questions should we ask the customer?
- {{MISSING::Cause::Root cause of the issue}} -> What is the technical root cause?
- {{MISSING::Mitigation or Resolution::Steps to resolve the issue}} -> What are the steps to resolve or work around this issue?
- {{MISSING::Root Cause to be shared with Customer::Customer-friendly explanation}} -> What explanation can we share with the customer?
- {{MISSING::Tags::Relevant search tags}} -> What keywords should this TSG be tagged with?
<!-- QUESTIONS_END -->

# Final Reminder
1. YOU MUST USE YOUR TOOLS FOR RESEARCH before generating output.
2. YOU MUST USE {{MISSING::...}} PLACEHOLDERS for any information not provided or verified.
3. Sparse input = Many placeholders. This is CORRECT.

Your output MUST:
1. Start with <!-- TSG_BEGIN -->
2. Contain the complete TSG (with placeholders for missing info)
3. Have <!-- TSG_END --> after the TSG
4. Have <!-- QUESTIONS_BEGIN --> next
5. Have follow-up questions for EACH placeholder, OR "NO_MISSING" if none
6. End with <!-- QUESTIONS_END -->

Do NOT include any text before <!-- TSG_BEGIN --> or after <!-- QUESTIONS_END -->.
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
    """Build the user prompt for GPT-4.1 (more explicit, research-first workflow)."""
    parts = [
        "FIRST: Use your Learn MCP and Bing Search tools to research the topic in these notes.\n",
        "THEN: Transform the raw notes into a TSG using the template provided.\n",
        "CRITICAL: Use {{MISSING::<SECTION>::<HINT>}} placeholders for ANY information not in the notes.\n",
        "\n<template>\n",
        TSG_TEMPLATE,
        "\n</template>\n",
        "\n<raw_notes>\n",
        notes,
        "\n</raw_notes>\n",
    ]
    if prior_tsg:
        parts.extend(["\n<prior_tsg>\n", prior_tsg, "\n</prior_tsg>\n"])
    if user_answers:
        parts.extend([
            "\n<user_answers>\n",
            user_answers,
            "\n</user_answers>\n",
            "Replace the {{MISSING::...}} placeholders that correspond to these answers.\n",
        ])
    # Reinforce tool usage first, then output format (GPT-4.1 best practice)
    parts.append("""
IMPORTANT WORKFLOW:
1. FIRST: Call your tools (Learn MCP and Bing Search) to research the topic
2. THEN: Generate the TSG with {{MISSING::...}} placeholders for unknown info
3. FINALLY: Output follow-up questions for EACH placeholder

<!-- TSG_BEGIN -->
[Complete TSG here - USE PLACEHOLDERS for missing information]
<!-- TSG_END -->

<!-- QUESTIONS_BEGIN -->
[One question per {{MISSING::...}} placeholder, OR "NO_MISSING" if none exist]
<!-- QUESTIONS_END -->

Remember: Sparse input = Many placeholders. This is CORRECT behavior.
""")
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
