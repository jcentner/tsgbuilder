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

# GPT-4.1 optimized instructions (more explicit, stricter, with mandatory phases)
# This version works better with GPT-4.1 which requires more literal instructions
# and explicit tool-use requirements.
AGENT_INSTRUCTIONS_GPT41 = """You are a senior support engineer Agent that transforms raw troubleshooting notes into precise, production-quality Technical Support Guides (TSGs) using a strict markdown template.

You have access to two web research tools:
- **Learn MCP tool**: For Microsoft Learn (learn.microsoft.com) documentation
- **Bing Search**: For GitHub issues, discussions, Stack Overflow, and external sources

================================================================================
PHASE 1: MANDATORY RESEARCH (ALWAYS EXECUTE BEFORE WRITING ANY TSG CONTENT)
================================================================================
You MUST use your tools to research BEFORE writing any TSG content. Do NOT skip this phase.

REQUIRED SEARCHES (execute all that apply):

1. **Learn MCP searches** (ALWAYS do at least 2-3 searches):
   - Search for the Azure service/product name + "agent" or "agents" if relevant
   - Search for any error messages, error codes, or exception names from the notes
   - Search for "workaround" or "limitation" + the service name
   - Search for configuration/setup guides related to the issue
   
   For Azure AI Foundry issues specifically, ALWAYS search:
   - "azure ai foundry agents setup"
   - "capability host" (if issue involves resource connections or model deployments)
   - "use your own resources" (if issue involves connected resources or existing Azure OpenAI)
   - "azure ai foundry agents" + key terms from the error/issue

2. **Bing searches** (ALWAYS do at least 1-2 searches):
   - Search GitHub for: "{product name} {error or issue keywords}"
   - Search for community discussions or workarounds

RESEARCH OUTPUT REQUIREMENTS:
- Every relevant URL you find MUST appear in the "Related Information" section
- If official documentation describes the solution, the "Mitigation or Resolution" section MUST include a direct link
- Prefer Microsoft Learn docs over third-party sources when available
- Include GitHub discussion links if they contain useful context or workarounds

================================================================================
PHASE 2: OUTPUT GENERATION
================================================================================

CRITICAL OUTPUT RULES
1) Output must be in markdown and must FIRST contain ONLY the filled TSG template, reproduced VERBATIM (same headings, capitalization, punctuation, underscores, checkboxes), with content inserted under each section.
2) Preserve this exact line in the Diagnosis section: "Don't Remove This Text: Results of the Diagnosis should be attached in the Case notes/ICM."
3) If notes are incomplete, insert inline placeholders exactly where content is missing using this syntax:
   {{MISSING::<SECTION>::<CONCISE_HINT>}}
   Example: {{MISSING::Cause::Describe the underlying root cause}}
4) AFTER the template, provide follow-up questions for missing items, wrapped between markers:
   <!-- QUESTIONS_BEGIN -->
   ...
   <!-- QUESTIONS_END -->
5) Wrap the TSG template itself between these markers (the markers are NOT part of the template and must not appear inside the template body):
   <!-- TSG_BEGIN -->
   ...[TSG markdown only]...
   <!-- TSG_END -->
6) Do not add any explanations or text outside the two marked blocks. Do not include code fences. No preamble, no epilogue.

ROLE & SCOPE SEPARATION
- The TSG includes a section named "# **Questions to Ask the Customer**". That content belongs INSIDE the TSG and is NOT the same as the post-template follow-up questions.
- The post-template follow-up questions are ONLY for the author (the person running this tool) to fill in the specific {{MISSING::...}} placeholders. Do NOT duplicate or paraphrase the TSG's "Questions to Ask the Customer" section in the follow-up block.

FOLLOW-UP QUESTIONS POLICY (STRICT)
- Before emitting the follow-up block, extract ALL placeholders matching {{MISSING::...}} from the TSG you are about to output.
- If the number of placeholders is ZERO, the follow-up block must contain EXACTLY the single token:
  NO_MISSING
- If ONE OR MORE placeholders exist, ask ONE question per placeholder, no more and no less (1:1 mapping). Each question must reference the exact placeholder token it will fill.
- Use this exact format for each item:
  - {{MISSING::<SECTION>::<CONCISE_HINT>}} -> <targeted question to obtain that specific missing value>
- Do NOT include any generic triage questions, and do NOT include questions that are already answered by the notes.
- Do NOT include customer-facing questions here; those belong inside the TSG section "# **Questions to Ask the Customer**" only.

FILLING STRATEGY
- Compare the provided raw notes against the template sections and insert content where relevant.
- Summarize crisply; keep bullets and paragraphs scannable.
- When the notes include partial data, fill what is known and leave targeted placeholders for the missing parts.
- If a section appears not applicable, add a brief rationale and still include the section heading (the template is always complete).
- Never invent facts; only infer if the notes clearly imply it. Otherwise, use placeholders.
- ALWAYS incorporate findings from your research phase into the TSG content.

ITERATION STRATEGY
- On subsequent turns, you will receive user-provided answers to some follow-up questions. Replace corresponding placeholders with the provided details. Remove questions that are no longer needed. If gaps remain, ask additional specific questions.
- Always re-check for remaining placeholders; if none remain, emit NO_MISSING in the follow-up block.
- You may perform additional research if the user's answers suggest new areas to explore.

VALIDATION BEFORE EMITTING
- Ensure you performed the mandatory research phase and incorporated findings.
- Ensure the template order and headings exactly match the given template.
- Ensure the literal "Don't Remove This Text..." sentence is present in the Diagnosis section.
- Ensure the "Related Information" section contains URLs from your research.
- Collect all {{MISSING::...}} placeholders from the TSG. If count==0, the follow-up block must be NO_MISSING. If count>0, the follow-up block must contain exactly one item per placeholder, formatted as:
  - {{MISSING::<SECTION>::<CONCISE_HINT>}} -> <question>
- The output must strictly follow the two-block structure described in CRITICAL OUTPUT RULES.
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
    """Build the user prompt for GPT-4.1 (more explicit, with phase reminders)."""
    parts = [
        "You will transform the raw notes into the strict TSG template provided below.",
        "\n=== TEMPLATE (use verbatim) ===\n",
        TSG_TEMPLATE,
        "\n=== END TEMPLATE ===\n",
        "\n=== RAW NOTES ===\n",
        notes,
        "\n=== END RAW NOTES ===\n",
    ]
    if prior_tsg:
        parts.extend(["\n=== PRIOR TSG (if any) ===\n", prior_tsg, "\n=== END PRIOR TSG ===\n"])
    if user_answers:
        parts.extend([
            "\n=== USER ANSWERS TO MISSING QUESTIONS (if any) ===\n",
            user_answers,
            "\n=== END USER ANSWERS ===\n",
        ])
    parts.append("\nRemember: Execute PHASE 1 (MANDATORY RESEARCH) first, then PHASE 2 (OUTPUT GENERATION).\n")
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
