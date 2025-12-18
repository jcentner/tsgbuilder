# TSG Builder – Agent-based Troubleshooting Guide Generator

Transform raw troubleshooting notes into structured **Technical Support Guides (TSGs)** using an Azure AI Foundry Agent with Bing Search and Microsoft Learn MCP integration.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Web UI](#web-ui)
- [Prerequisites](#prerequisites)
  - [Azure Resources Required](#azure-resources-required)
  - [Local Requirements](#local-requirements)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Finding Your Configuration Values](#finding-your-configuration-values)
- [CLI Usage](#cli-usage)
- [Makefile Commands](#makefile-commands)
- [How It Works](#how-it-works)
  - [Agent Research Phase](#agent-research-phase)
  - [Output Format](#output-format)
  - [Iteration](#iteration)
- [Troubleshooting](#troubleshooting)
- [Architecture](#architecture)
- [Files](#files)
- [Contributing](#contributing)
- [License](#license)

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

# 2. Start the Web UI
make ui
# Open http://localhost:5000 in your browser
```

The web UI will automatically open the setup wizard if configuration is needed. The setup wizard guides you through:
1. **Configure** — Enter your Azure AI Foundry settings
2. **Validate** — Verify authentication and connectivity
3. **Create Agent** — Create the AI agent with one click

## Web UI

The web interface is the recommended way to use TSG Builder:

```bash
make ui
```

Then open **http://localhost:5000** in your browser.

**Features:**
- ⚙️ **Built-in setup wizard** — Configure, validate, and create agent from the browser
- 📝 Paste notes directly in the browser
- �️ **Image support** — Attach screenshots via drag-and-drop, file picker, or paste
- 🔄 Interactive follow-up questions
- 📋 One-click copy to clipboard
- 📊 Real-time status indicator
- 💡 Load example input with one click

### Attaching Images

You can include screenshots or images with your troubleshooting notes:

1. **Drag and drop** — Drag image files onto the upload zone
2. **Click to upload** — Click the upload zone to open file picker
3. **Paste from clipboard** — Copy an image and paste anywhere on the page (Ctrl+V / Cmd+V)

Supported formats: PNG, JPG, GIF, WebP. Maximum 10 images per request.

Images are sent to the AI agent for visual analysis, which is especially useful for:
- Error screenshots
- Architecture diagrams
- Console/terminal output
- Configuration screenshots

![TSG Builder UI](docs/ui-screenshot.png)

## Prerequisites

### Azure Resources Required

| Resource | Purpose | How to Get |
|----------|---------|------------|
| **Azure AI Foundry Project** | Hosts the agent | [Create a project](https://learn.microsoft.com/azure/ai-foundry/how-to/create-projects) |
| **Model Deployment** | LLM for the agent (e.g., `gpt-4.1` or `gpt-5.2`) | Deploy in your project |
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

Configuration can be done in two ways:

### Option 1: Via Web UI (Recommended)

1. Run `make ui` and open http://localhost:5000
2. Click the **⚙️ Setup** button (or it opens automatically)
3. Enter your Azure configuration values
4. Click **Save Configuration**
5. Run **Validation** to verify everything works
6. Click **Create Agent**

### Option 2: Edit .env Manually

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

# Optional: Custom name for your agent (default: TSG-Builder)
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
2. Use the name of your deployed model (e.g., `gpt-4.1`)

## CLI Usage

The command-line interface is available as an alternative to the web UI.

### Validate Setup

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

### Create the Agent

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
| `make ui` | **Start the web UI** at http://localhost:5000 |
| `make validate` | Check environment configuration (CLI) |
| `make create-agent` | Create the Azure AI agent (CLI) |
| `make run` | Run with `input.txt` (CLI) |
| `make run NOTES_FILE=x.txt` | Run with custom notes file (CLI) |
| `make run-example` | Run with `input-example.txt` |
| `make run-save` | Run and save output to `output.md` |
| `make install` | Install dependencies only |
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

MIT