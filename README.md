# TSG Builder – Agent-based Troubleshooting Guide Generator

## Overview
TSG Builder converts **raw troubleshooting notes** into **structured Technical Support Guides (TSG)** in markdown. It uses **Azure AI Foundry Agents** with a strict template to fill known details, insert `{{MISSING::<SECTION>::<HINT>}}` placeholders, and ask targeted follow-up questions until the TSG is complete.

Source template: [TSG-Template.md - ADO](https://dev.azure.com/Supportability/AzureCognitiveServices/_git/AzureML?path=/AzureML/Welcome/TSG-Template.md&version=GBmaster&_a=preview)

## Prerequisites
- Python 3.9+
- Azure AI Foundry project with an Agent-compatible model deployment (e.g., `gpt-4o`)
- Bing Search connection in the project
- Environment variables:
  - `PROJECT_ENDPOINT` – your Azure AI Foundry project endpoint
  - `MODEL_DEPLOYMENT_NAME` – deployment name (e.g., `gpt-4o`)
  - `BING_CONNECTION_NAME` – connection id for Bing Search
  - Optional: `AGENT_NAME`, `ENABLE_LEARN_MCP` (true/false), `AGENT_ID` override

## Setup
```bash
pip install -r requirements.txt
```
Create a `.env` with the required variables or export them in your shell.

## Usage
1) Create the agent (once):
```bash
python create_agent.py
```
- Writes the new agent id to `.agent_id` for reuse.

2) Run inference with your notes:
```bash
python ask_agent.py --notes-file input.txt
# or paste interactively if --notes-file is omitted
```
- The script streams the TSG, shows missing placeholders, and prompts you to answer follow-up questions until none remain.

## Template Compliance
- Strict headings/order and required Diagnosis line: `Don't Remove This Text: Results of the Diagnosis should be attached in the Case notes/ICM.`
- Output wrapped in markers: `<!-- TSG_BEGIN --> ... <!-- TSG_END -->` and `<!-- QUESTIONS_BEGIN --> ... <!-- QUESTIONS_END -->`.
- Follow-up block is `NO_MISSING` when all placeholders are filled.

## Legacy (optional)
`old/tsg_builder.py` contains a prior flow using the Azure OpenAI SDK directly. It remains for reference but the recommended path is the agent-based flow above.
