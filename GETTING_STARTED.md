# TSG Builder — Getting Started

Turn raw troubleshooting notes into polished **Technical Support Guides (TSGs)** in minutes.

---

## Prerequisites

1. **Azure CLI** — installed and logged in
   - [Install Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli)
   - Run `az login` to authenticate
2. **Azure AI Foundry project with a `gpt-5.2` model deployed** — follow the guide below if you don't have one yet

---

## Setting Up Azure AI Foundry

> These steps use the **new** Microsoft Foundry portal at [ai.azure.com](https://ai.azure.com). If you see a "New Foundry" toggle in the portal, make sure it is **on**.

### Step 1: Create a Foundry Project

A project organizes your models, agents, and other resources. The following details how to create a new project (and resource) from the Foundry portal, or you can use an existing Foundry project if you have one. 

1. Go to [ai.azure.com](https://ai.azure.com) and sign in with your Azure account
2. Select the **project name** in the upper-left corner, then select **Create new project**
3. Enter a project name (e.g., `tsg-builder-project`)
4. Select **Advanced options** to choose a specific resource group and region
   - TSG Builder is designed for gpt-5.2 Check [Supported regions](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/model-region-support?view=foundry&tabs=global-standard#available-models) to ensure your Foundry resource is in a region that supports this model (eastus2, southcentralus, swedencentral).
5. Select **Create project**

> **What gets created**: Azure creates a *Foundry resource* (of type AI Services) and a *project* inside it. You don't need to create these separately. See the [Foundry quickstart](https://learn.microsoft.com/azure/ai-foundry/tutorials/quickstart-create-foundry-resources?view=foundry) for more details.

### Step 2: Deploy a gpt-5.2 Model

1. In your project, select **Discover** in the top navigation
2. Select **Models**
3. Search for **gpt-5.2**
4. Select the model, then select **Deploy** → **Default settings**
5. Note the **deployment name** shown (e.g., `gpt-5.2`) — you'll need this for TSG Builder setup

> **Can't find gpt-5.2?** Check that your project is in a [supported region](https://learn.microsoft.com/azure/ai-foundry/agents/concepts/model-region-support?view=foundry). 
> **Can't deploy - the model is locked?** GPT-5.2 access requires filling out a [registration form](https://customervoice.microsoft.com/Pages/ResponsePage.aspx?id=v4j5cvGGr0GRqy180BHbR7en2Ais5pxKtso_Pz4b1_xUQ1VGQUEzRlBIMVU2UFlHSFpSNkpOR0paRSQlQCN0PWcu) - use your Microsoft email and, if you have one, a nonprod subscription for quick approval. 

### Step 3: Find Your Project Endpoint

1. In your project, go to the main **Overview** / welcome page
2. Copy the **Foundry project endpoint** shown on the page
   - It looks like: `https://<resource-name>.services.ai.azure.com/api/projects/<project-name>`

You now have the two values TSG Builder needs: the **project endpoint** and the **deployment name**.

---

## Quick Start

### 1. Extract the zip

Extract this zip file to a folder of your choosing.

### 2. Run the executable

**Linux / macOS:**
```bash
./tsg-builder-linux    # or ./tsg-builder-macos
```

> **macOS**: Right-click the executable → **Open** → **Open** to bypass Gatekeeper on the first launch.

**Windows:**
```
tsg-builder-windows.exe
```

> **Windows notes:**
> - Windows SmartScreen may warn about an unrecognized app. Click **More info** → **Run anyway**.
> - The first startup may be slow as Windows Defender scans the application files. Subsequent launches will be faster.

### 3. Complete setup in the browser

Your browser opens to `http://localhost:5000`. The setup wizard guides you through:

1. Enter your **Azure AI Foundry project endpoint**
2. Enter your **model deployment name**
3. Click **Save Configuration**
4. Run **Validation** to verify connectivity
5. Click **Create Agents**

You're ready to build TSGs!

---

## Finding Your Configuration Values

If you already have a Foundry project set up, here's where to find the values TSG Builder asks for:

### PROJECT_ENDPOINT

1. Go to [ai.azure.com](https://ai.azure.com) and select your project
2. The **Foundry project endpoint** is displayed on the project welcome/overview page
3. Copy the full URL (e.g., `https://<resource-name>.services.ai.azure.com/api/projects/<project-name>`)

### MODEL_DEPLOYMENT_NAME

1. In your project at [ai.azure.com](https://ai.azure.com), select **Discover** → **Models** → **My models** (or **Operate** → **Deployments** in the sidebar)
2. Use the name shown in the **Deployment name** column (e.g., `gpt-5.2`)

---

## Usage Tips

- **Paste notes** directly into the text area, or **load an example** with one click
- **Attach images** — drag-and-drop screenshots (error dialogs, architecture diagrams, console output)
- **Follow-up questions** — if the agent detects missing info, it asks you to fill in gaps
- **Copy to clipboard** — one-click copy of the finished TSG markdown
- **Raw/Preview toggle** — switch between raw markdown and rendered preview
- **PII check** — your input is scanned before generation; you'll be prompted to edit or redact if PII is detected

A full run (Research → Write → Review) typically takes **2–5 minutes**.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "PROJECT_ENDPOINT is required" | Run the setup wizard (⚙️ button) and enter your endpoint |
| "Azure authentication failed" | Run `az login` to refresh credentials |
| "Failed to connect to project" | Verify your `PROJECT_ENDPOINT` is correct and you have the "Azure AI User" role |
| "Agent not found" | Use the Setup wizard to create agents |
| PII check flags false positive | Click **Go Back & Edit** to adjust, or **Redact & Continue** to accept |
| An agent fails and retries | The Agents Service may be experiencing temporary issues; typically retries succeed |

---

## Telemetry

TSG Builder collects **anonymous usage telemetry** (event counts, durations, token counts, version info) to improve the tool. **No content, PII, or credentials are ever collected.**

To opt out, add this to the `.env` file (created automatically next to the executable):

```
TSG_TELEMETRY=0
```

---

## More Information

- **Full documentation**: [github.com/jcentner/tsgbuilder](https://github.com/jcentner/tsgbuilder)
- **Report issues**: [github.com/jcentner/tsgbuilder/issues](https://github.com/jcentner/tsgbuilder/issues)
- **Releases**: [github.com/jcentner/tsgbuilder/releases](https://github.com/jcentner/tsgbuilder/releases)
