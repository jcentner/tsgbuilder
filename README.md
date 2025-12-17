# TSG Builder – Agent-based Troubleshooting Guide Generator

Transform raw troubleshooting notes into structured **Technical Support Guides (TSGs)** using an Azure AI Foundry Agent with Bing Search and Microsoft Learn MCP integration.

## Overview

TSG Builder uses an Azure AI Foundry Agent (classic API) to:
1. **Research** the issue using Bing Search and Microsoft Learn MCP
2. **Generate** a structured TSG following your team's template
3. **Iterate** by asking follow-up questions for missing information
4. **Output** a production-ready markdown TSG

Source template: [TSG-Template.md - ADO](https://dev.azure.com/Supportability/AzureCognitiveServices/_git/AzureML?path=/AzureML/Welcome/TSG-Template.md&version=GBmaster&_a=preview)

## Quick Start

```bash
# 1. Clone and setup
git clone <repo-url>
cd tsgbuilder
make setup

# 2. Configure (edit .env with your values)
nano .env

# 3. Validate your setup
make validate

# 4. Create the agent (one-time)
make create-agent

# 5. Generate a TSG
make run NOTES_FILE=your-notes.txt

# Or save output to file
python ask_agent.py --notes-file your-notes.txt --output my-tsg.md
```

## Prerequisites

### Azure Resources Required

| Resource | Purpose | How to Get |
|----------|---------|------------|
| **Azure AI Foundry Project** | Hosts the agent | [Create a project](https://learn.microsoft.com/azure/ai-foundry/how-to/create-projects) |
| **Model Deployment** | LLM for the agent (e.g., `gpt-4o`, `gpt-4.1`) | Deploy in your project |
| **Bing Search Connection** | Web research capability | [Connect Bing Search](https://learn.microsoft.com/azure/ai-foundry/how-to/connections-add) |

### Local Requirements

- Python 3.9+
- Azure CLI (logged in with `az login`)
- Access to the Azure AI Foundry project

## Installation

### Option 1: Using Make (Recommended)

```bash
make setup
```

This will:
- Create a virtual environment (`.venv/`)
- Install dependencies
- Copy `.env-sample` to `.env`

### Option 2: Manual Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env-sample .env
```

## Configuration

Edit `.env` with your Azure configuration:

```bash
# Required: Your Azure AI Foundry project endpoint
# Found in: Azure Portal > AI Foundry > Project > Overview
PROJECT_ENDPOINT=https://your-resource.services.ai.azure.com/api/projects/your-project

# Required: Full resource ID of your Bing Search connection
# Found in: AI Foundry Portal > Management Center > Connected Resources
BING_CONNECTION_NAME=/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>/connections/<bing-connection>

# Required: Name of your model deployment (recommended: GPT 5.2)
MODEL_DEPLOYMENT_NAME=gpt-5.2

# Optional: Custom name for your agent (default: tsg-agent)
AGENT_NAME=TSG-Builder
```

### Finding Your Configuration Values

#### PROJECT_ENDPOINT
1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to your AI Foundry resource
3. Select your project
4. Copy the endpoint from the Overview page

#### BING_CONNECTION_NAME
1. Go to [AI Foundry Portal](https://ai.azure.com)
2. Open Management Center
3. Go to Connected Resources
4. Find your Bing Search connection
5. Copy the full resource ID

#### MODEL_DEPLOYMENT_NAME
1. In AI Foundry Portal, go to Deployments
2. Use the name of your deployed model (e.g., `gpt-4o`)

## Usage

### Validate Setup First

```bash
make validate
# or
python validate_setup.py
```

This checks:
- ✓ Required environment variables
- ✓ Azure authentication
- ✓ Project connectivity
- ✓ Python dependencies

### Create the Agent (One-Time)

```bash
make create-agent
# or
python create_agent.py
```

This creates an agent with:
- Bing Search tool for web research
- Microsoft Learn MCP for official documentation
- TSG generation instructions

### Generate a TSG

```bash
# Interactive mode (paste notes)
python ask_agent.py

# From a file
python ask_agent.py --notes-file your-notes.txt

# Save output to file
python ask_agent.py --notes-file your-notes.txt --output tsg-output.md

# Using make
make run NOTES_FILE=your-notes.txt
```

### Input Format

Create a text file with your raw troubleshooting notes. Include:
- Error messages and codes
- Customer symptoms
- Any known workarounds
- Relevant links (GitHub issues, Teams threads, etc.)

See `input-example.txt` for a sample input.

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make setup` | First-time setup (venv + deps + .env) |
| `make install` | Install dependencies only |
| `make validate` | Check environment configuration |
| `make create-agent` | Create the Azure AI agent |
| `make run` | Run with `input.txt` |
| `make run NOTES_FILE=x.txt` | Run with custom notes file |
| `make run-example` | Run with `input-example.txt` |
| `make run-save` | Run and save output to `output.md` |
| `make clean` | Remove venv and generated files |
| `make help` | Show all commands |

## How It Works

### Agent Research Phase

The agent is instructed to **always research** before generating the TSG:

1. **Microsoft Learn MCP** searches for:
   - Azure service documentation
   - Known limitations and workarounds
   - Configuration guides
   - Capability hosts, agent setup (for AI Foundry issues)

2. **Bing Search** for:
   - GitHub discussions and issues
   - Community workarounds
   - Stack Overflow solutions

### Output Format

The agent outputs:
1. **TSG Block** - The complete markdown TSG
2. **Questions Block** - Follow-up questions for missing info (or `NO_MISSING`)

Output is wrapped in markers for parsing:
```
<!-- TSG_BEGIN -->
[TSG markdown content]
<!-- TSG_END -->

<!-- QUESTIONS_BEGIN -->
[Follow-up questions or NO_MISSING]
<!-- QUESTIONS_END -->
```

### Iteration

If information is missing, the agent:
1. Inserts `{{MISSING::<SECTION>::<HINT>}}` placeholders
2. Asks targeted follow-up questions
3. Waits for your answers
4. Regenerates the TSG with your input

## Troubleshooting

### "PROJECT_ENDPOINT is required"
- Ensure `.env` file exists and contains `PROJECT_ENDPOINT`
- Run `make validate` to check all variables

### "Azure authentication failed"
- Run `az login` to authenticate
- Ensure your account has access to the AI Foundry project

### "Failed to connect to project"
- Verify `PROJECT_ENDPOINT` is correct
- Check you have the "Azure AI User" role on the project

### "Agent not found"
- Run `python create_agent.py` to create the agent
- Check `.agent_id` file exists

### Agent doesn't use tools / research
- The agent instructions mandate research before output
- If this persists, recreate the agent: `make clean && make create-agent`

### TSG missing documentation links
- The agent is instructed to include URLs from research in "Related Information"
- Check the agent is correctly configured with both Bing and Learn MCP tools

## Architecture

```
┌─────────────────┐     ┌──────────────────────────────────────────┐
│  Raw Notes      │────▶│    Azure AI Foundry Agent (Classic)      │
│  (input.txt)    │     │  ┌─────────────────────────────────────┐ │
└─────────────────┘     │  │  1. Research (Learn MCP + Bing)     │ │
                        │  │  2. Generate TSG from template      │ │
                        │  │  3. Mark gaps with placeholders     │ │
                        │  └─────────────────────────────────────┘ │
                        └──────────────────┬───────────────────────┘
                                           │
                                           ▼
                        ┌──────────────────────────────────────────┐
                        │  Structured TSG (markdown)              │
                        │  + Follow-up Questions OR NO_MISSING    │
                        └──────────────────────────────────────────┘
```

## Files

| File | Purpose |
|------|---------|
| `create_agent.py` | Create the Azure AI Foundry agent |
| `ask_agent.py` | Run inference / generate TSGs |
| `validate_setup.py` | Validate environment configuration |
| `tsg_constants.py` | TSG template and agent instructions |
| `Makefile` | Common operations |
| `.env` | Your configuration (git-ignored) |
| `.env-sample` | Configuration template |
| `.agent_id` | Agent ID after creation |
| `input-example.txt` | Example input notes |

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run `make lint` to check syntax
5. Submit a pull request

## License

Internal use only.
