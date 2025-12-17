"""
Shared TSG template, markers, and instruction text.
"""

# Agent versioning for the new Agents API.
AGENT_VERSION = "2"

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


def build_user_prompt(notes: str, prior_tsg: str | None = None, user_answers: str | None = None) -> str:
    """Build the user prompt for the agent."""
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
