#!/usr/bin/env python3
# tsg_builder.py
import os
import sys
import argparse
from typing import Tuple, List, Optional

from dotenv import load_dotenv
load_dotenv()

# Azure OpenAI (Python openai SDK 1.x)
# pip install openai
from openai import AzureOpenAI

SYSTEM_PROMPT = """You are a senior support engineer expert at transforming raw troubleshooting notes into precise, production-quality Technical Support Guides (TSGs) using a strict markdown template.

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
- When the notes include partial data, fill what’s known and leave targeted placeholders for the missing parts.
- If a section appears not applicable, add a brief rationale and still include the section heading (the template is always complete).
- Never invent facts; only infer if the notes clearly imply it. Otherwise, use placeholders.

ITERATION STRATEGY
- On subsequent turns, you will receive user-provided answers to some follow-up questions. Replace corresponding placeholders with the provided details. Remove questions that are no longer needed. If gaps remain, ask additional specific questions.
- Always re-check for remaining placeholders; if none remain, emit NO_MISSING in the follow-up block.

VALIDATION BEFORE EMITTING
- Ensure the template order and headings exactly match the given template.
- Ensure the literal “Don’t Remove This Text…” sentence is present in the Diagnosis section.
- Collect all {{MISSING::...}} placeholders from the TSG. If count==0, the follow-up block must be NO_MISSING. If count>0, the follow-up block must contain exactly one item per placeholder, formatted as:
  - {{MISSING::<SECTION>::<CONCISE_HINT>}} -> <question>
- The output must strictly follow the two-block structure described in CRITICAL OUTPUT RULES.
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
- _For inline scripts, please give entire script and don’t give instructions_ 
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

def build_client() -> AzureOpenAI:
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
    if not api_key or not endpoint:
        print("ERROR: Please set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT (and optionally AZURE_OPENAI_API_VERSION).", file=sys.stderr)
        sys.exit(1)
    return AzureOpenAI(api_key=api_key, azure_endpoint=endpoint, api_version=api_version)

def call_llm(client: AzureOpenAI, deployment: str, notes: str, prior_tsg: Optional[str], user_answers: Optional[str]) -> str:
    """
    Calls Azure OpenAI chat.completions with system prompt, template, notes, and optional prior state.
    Returns the raw assistant content (string) which should contain both TSG and QUESTIONS blocks.
    """
    # Construct messages
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "You will transform the raw notes into the strict TSG template provided below.\n\n"
                "=== TEMPLATE (use verbatim) ===\n"
                f"{TSG_TEMPLATE}\n"
                "=== END TEMPLATE ===\n\n"
                "=== RAW NOTES ===\n"
                f"{notes}\n"
                "=== END RAW NOTES ===\n"
                + (
                    f"\n=== PRIOR TSG (if any) ===\n{prior_tsg}\n=== END PRIOR TSG ===\n"
                    if prior_tsg else ""
                )
                + (
                    f"\n=== USER ANSWERS TO MISSING QUESTIONS (if any) ===\n{user_answers}\n=== END USER ANSWERS ===\n"
                    if user_answers else ""
                )
                + "\nRemember the CRITICAL OUTPUT RULES."
            ),
        },
    ]

    resp = client.chat.completions.create(
        model=deployment,
        messages=messages,
        temperature=0.2,
        top_p=0.9,
        max_tokens=6000,
        n=1,
    )
    return resp.choices[0].message.content or ""

def split_blocks(content: str) -> Tuple[str, str]:
    """
    Returns (tsg_block, questions_block). Either may be empty if not found.
    """
    def extract_between(s: str, start: str, end: str) -> str:
        i = s.find(start)
        j = s.find(end)
        if i == -1 or j == -1 or j <= i:
            return ""
        return s[i + len(start): j].strip()

    tsg = extract_between(content, TSG_BEGIN, TSG_END)
    questions = extract_between(content, QUESTIONS_BEGIN, QUESTIONS_END)
    return tsg, questions

def ensure_required_line(tsg: str) -> str:
    if REQUIRED_DIAGNOSIS_LINE in tsg:
        return tsg
    # Attempt to insert after the Diagnosis checkboxes block if missing.
    DIAGNOSIS_HEADER = "# **Diagnosis**"
    idx = tsg.find(DIAGNOSIS_HEADER)
    if idx == -1:
        # Append at end as fallback
        return tsg + f"\n\n{REQUIRED_DIAGNOSIS_LINE}\n"
    # Insert after the header section; simple heuristic: find next two newlines after the header.
    return tsg + f"\n\n{REQUIRED_DIAGNOSIS_LINE}\n" if REQUIRED_DIAGNOSIS_LINE not in tsg else tsg

def validate_tsg(tsg: str) -> List[str]:
    errors = []
    if not tsg.strip().startswith("[[_TOC_]]"):
        errors.append("TSG does not start with [[_TOC_]].")
    if "# **Title**" not in tsg:
        errors.append("Missing '# **Title**' heading.")
    if REQUIRED_DIAGNOSIS_LINE not in tsg:
        errors.append("Required Diagnosis line was missing (auto-inserted).")
    # Basic required sections present?
    required_sections = [
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
    for sec in required_sections:
        if sec not in tsg:
            errors.append(f"Missing section: {sec}")
    return errors

def save_tsg(tsg: str, path: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(tsg)

def interactive_loop(client: AzureOpenAI, deployment: str, initial_notes: str, out_path: str):
    prior_tsg = None
    notes = initial_notes
    iteration = 1

    while True:
        print(f"\n=== Generating TSG (iteration {iteration}) ===\n")
        content = call_llm(client, deployment, notes=notes, prior_tsg=prior_tsg, user_answers=None)
        tsg, questions = split_blocks(content)

        if not tsg:
            print("ERROR: Model output did not include a TSG block. Full output below:\n")
            print(content)
            sys.exit(2)

        tsg = ensure_required_line(tsg)
        errs = validate_tsg(tsg)
        if errs:
            print("WARNINGS:")
            for e in errs:
                print(f" - {e}")

        save_tsg(tsg, out_path)
        print(f"\n--- TSG saved to: {out_path} ---\n")
        print(tsg)

        if questions:
            print("\n--- Missing information requested ---")
            print(questions)
            print("\nPaste answers (free text, numbered list, or 'done' to finish).")
            user_input = read_multiline_input()
            if user_input.strip().lower() == "done":
                print("\nFinished. Your latest TSG is saved.")
                return
            # Re-call model with user answers to fill placeholders
            content2 = call_llm(client, deployment, notes=notes, prior_tsg=tsg, user_answers=user_input)
            tsg2, questions2 = split_blocks(content2)
            if not tsg2:
                print("ERROR: Model output did not include a TSG block on refinement. Full output below:\n")
                print(content2)
                sys.exit(3)
            tsg2 = ensure_required_line(tsg2)
            errs2 = validate_tsg(tsg2)
            if errs2:
                print("WARNINGS:")
                for e in errs2:
                    print(f" - {e}")
            save_tsg(tsg2, out_path)
            print(f"\n--- Updated TSG saved to: {out_path} ---\n")
            print(tsg2)
            prior_tsg = tsg2
            # Continue if still has questions
            if questions2:
                print("\n--- Additional missing information ---")
                print(questions2)
                print("\nProvide more answers, or type 'done' to finish.")
                user_input2 = read_multiline_input()
                if user_input2.strip().lower() == "done":
                    print("\nFinished. Your latest TSG is saved.")
                    return
                # Update again with more answers
                content3 = call_llm(client, deployment, notes=notes, prior_tsg=tsg2, user_answers=user_input2)
                tsg3, questions3 = split_blocks(content3)
                if tsg3:
                    tsg3 = ensure_required_line(tsg3)
                    save_tsg(tsg3, out_path)
                    print(f"\n--- Final TSG saved to: {out_path} ---\n")
                    print(tsg3)
                print("\nDone.")
                return
            else:
                print("\nNo more missing items. Done.")
                return
        else:
            print("\nNo missing items were detected. Done.")
            return

def read_multiline_input() -> str:
    print("(End input with an empty line)")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "":
            break
        lines.append(line)
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="Build a TSG from raw notes using Azure OpenAI.")
    parser.add_argument("--deployment", required=True, help="Azure OpenAI deployment name (e.g., gpt-4o)")
    parser.add_argument("--out", default="tsg_output.md", help="Output markdown file path")
    parser.add_argument("--notes-file", help="Path to a text file with raw notes (if not provided, you will paste interactively)")
    args = parser.parse_args()

    if args.notes_file:
        if not os.path.exists(args.notes_file):
            print(f"ERROR: Notes file not found: {args.notes_file}", file=sys.stderr)
            sys.exit(1)
        with open(args.notes_file, "r", encoding="utf-8") as f:
            notes = f.read()
    else:
        print("Paste raw notes about the issue. Press Enter twice to end.")
        notes = read_multiline_input()

    if not notes.strip():
        print("ERROR: No notes provided.", file=sys.stderr)
        sys.exit(1)

    client = build_client()
    interactive_loop(client, deployment=args.deployment, initial_notes=notes, out_path=args.out)

if __name__ == "__main__":
    main()
