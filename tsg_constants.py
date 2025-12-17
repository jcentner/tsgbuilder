"""
Shared TSG template, markers, and instruction text.
"""

# Agent versioning for the new Agents API.
AGENT_VERSION = "1"

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


def agent_reference(name: str) -> dict:
    """Return the agent reference payload used by responses.create/stream."""
    return {"type": "agent_reference", "name": name, "version": AGENT_VERSION}


# System/agent instructions for creation and inference.
AGENT_INSTRUCTIONS = """You are a senior support engineer Agent that transforms raw troubleshooting notes into precise, production-quality Technical Support Guides (TSGs) using a strict markdown template.

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
- Do NOT include customer-facing questions here; those belong inside the TSG section "# **Questions to Ask the Customer" only.

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
    """Build the user prompt for the agent."""
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
