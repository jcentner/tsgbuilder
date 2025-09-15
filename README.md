# TSG Builder – Automated Troubleshooting Guide Generator

Author: Jacob Centner - jacobcentner@microsoft.com 

## Overview
TSG Builder is a command-line tool that converts **raw troubleshooting notes** into **structured Technical Support Guides (TSG)** in markdown format.  
It uses **Azure OpenAI** to: 
- Compare your notes against the TSG template, strictly.
- Fill in known details and insert placeholders for missing information.
- Ask targeted follow-up questions for missing pieces.
- Iterate until the TSG is complete and ready to share.

The output is **fully markdown-compliant**, follows the template verbatim, and includes placeholders like `{{MISSING::<SECTION>::<HINT>}}` for gaps.

Source for TSG template: [TSG-Template.md - ADO](https://dev.azure.com/Supportability/AzureCognitiveServices/_git/AzureML?path=/AzureML/Welcome/TSG-Template.md&version=GBmaster&_a=preview)

---

## Features
- **Strict template adherence** – preserves headings, order, and required text.
- **Interactive refinement** – answer follow-up questions to fill gaps.
- **Deterministic output** – low temperature for consistent formatting.
- **Auto-save** – latest TSG saved after each iteration.

---

## Prerequisites
- **Python** 3.9 or later
- **Azure OpenAI** resource with a deployed model (recommended: `gpt-4o`)
- **Environment variables**:
  - `AZURE_OPENAI_API_KEY` – your Azure OpenAI key
  - `AZURE_OPENAI_ENDPOINT` – e.g., `https://<your-resource>.openai.azure.com/`
  - `AZURE_OPENAI_API_VERSION` – e.g., `2024-02-15-preview`

---

## Setup
1. **Install dependencies**:
   ```bash
   pip install openai
   ```
2. **Set environment variables**:
   ```bash
   export AZURE_OPENAI_API_KEY="<your-key>"
   export AZURE_OPENAI_ENDPOINT="https://<your-resource>.openai.azure.com/"
   export AZURE_OPENAI_API_VERSION="2024-02-15-preview"
   ```

   Alternatively, create a .env file with the appropriate fields and source it.

  .env sample: 
   ```bash
   AZURE_OPENAI_API_KEY="<your-key>"
   AZURE_OPENAI_ENDPOINT="https://<your-resource>.openai.azure.com/"
   AZURE_OPENAI_API_VERSION="2024-02-15-preview"
   ```

---

## Usage
Run the script from your terminal:

```bash
python tsg_builder.py --deployment gpt-4o --out my_issue_tsg.md
```

- `--deployment` : Name of your Azure OpenAI deployment (e.g., `gpt-4o`)
- `--out` : Output markdown file (default: `tsg_output.md`)
- `--notes-file` : Optional path to a text file with raw notes (otherwise, paste interactively)

### Example Workflow
1. Paste raw notes when prompted.
2. Review the generated TSG and any follow-up questions.
3. Provide answers or type `done` to finish.
4. The final TSG is saved to the specified output file.

---

## Template Compliance
- The script enforces:
  - Required headings and sections.
  - Mandatory line in Diagnosis:  
    `Don't Remove This Text: Results of the Diagnosis should be attached in the Case notes/ICM.`
- Missing details are clearly marked with placeholders for easy follow-up.

---

## Next Steps
- Integrate with Teams or SharePoint for sharing.
- Add chunking for very large logs.
- Build a simple web UI for broader team use.

---

**Quick Start Command**:
```bash
python tsg_builder.py --deployment gpt-4o
```
