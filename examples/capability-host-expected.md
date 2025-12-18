[[_TOC_]]

# **Azure AI Foundry Agents Cannot See Model Deployments from Connected Azure OpenAI Resources**

# **Issue Description / Symptoms**
- **What** is the issue?  
  When creating an Agent in an Azure AI Foundry project (GA version, not hub-based), users cannot select or use model deployments from connected Azure OpenAI resources. Only models deployed at the project level are visible in the UI dropdown and available for agent creation via SDK.

- **Who** does this affect?  
  Users of Azure AI Foundry (Classic portal) who have connected existing Azure OpenAI resources to their project and want to use those model deployments for Agents.

- **Where** does the issue occur? Where does it not occur?  
  - Occurs in: Azure AI Foundry Classic portal UI and SDK when creating/configuring agents
  - Does not occur: When using model deployments deployed directly on the project's AI Services resource

- **When** does it occur?  
  When attempting to create an agent and selecting a model deployment from a connected Azure OpenAI resource (not the project's default AI Services resource).

# **When does the TSG not Apply**
- This TSG does not apply to hub-based projects (legacy Azure AI Studio projects)
- This TSG does not apply if the user is using model deployments from the project's own AI Services resource (those work by default)
- This TSG does not apply to the new Microsoft Foundry portal (non-classic) which may have different behavior

# **Diagnosis**
- [ ] Confirm the user is using Azure AI Foundry Classic portal (not the new Foundry portal)
- [ ] Verify the user has a connected Azure OpenAI resource (check Management Center > Connected Resources)
- [ ] Confirm the model deployment exists on the connected Azure OpenAI resource (not the project's AI Services resource)
- [ ] Check if the connected Azure OpenAI resource is in the same region as the AI Services resource
- [ ] Ask the user to check if they can see the model deployments when creating agents via SDK

Don't Remove This Text: Results of the Diagnosis should be attached in the Case notes/ICM.

# **Questions to Ask the Customer**
- Are you using the Azure AI Foundry Classic portal or the new Microsoft Foundry portal?
- Is your connected Azure OpenAI resource in the same region as your project's AI Services resource?
- Have you created any capability hosts for your project, or are you using the default configuration?
- Are you trying to create the agent via the portal UI, SDK, or both?

# **Cause**
The project capability host is configured by default to only see the project's AI Services resource. Connected Azure OpenAI resources are not automatically visible to the capability host configuration. This is a known feature gap in the Azure AI Foundry Classic UI - there is currently no UX for managing capability hosts.

The capability host determines which Azure resources the Agent Service can use for model deployments. Without explicitly configuring the capability host to include the connected Azure OpenAI resource via the `aiServicesConnections` property, agents cannot access those deployments.

# **Mitigation or Resolution**
**Workaround: Create a capability host that points to your connected Azure OpenAI resource**

**Prerequisites:**
- The connected OpenAI resource must be in the **same region** as the AI Services resource
- Changing capability hosts may disrupt existing agents under the AI Services resource

**Steps:**

1. **Get an Azure management token:**
```python
from azure.identity import DefaultAzureCredential
token = DefaultAzureCredential().get_token("https://management.azure.com/.default").token
```

2. **Create an account-level capability host:**
```python
import requests

url = "https://management.azure.com/subscriptions/{sub-id}/resourceGroups/{res-group-name}/providers/Microsoft.CognitiveServices/accounts/{ai-services-resource}/capabilityHosts/{any-cap-host-name}/"
querystring = {"api-version":"2025-04-01-preview"}
payload = {"properties": {"capabilityHostKind": "Agents"}}
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}
response = requests.put(url, json=payload, headers=headers, params=querystring)
print(response.text)
```

3. **Create a project-level capability host with your Azure OpenAI connection:**
```python
url = "https://management.azure.com/subscriptions/{sub-id}/resourceGroups/{res-group-name}/providers/Microsoft.CognitiveServices/accounts/{ai-services-resource}/projects/{project-name}/capabilityHosts/{any-proj-cap-host-name}/"
querystring = {"api-version":"2025-04-01-preview"}
payload = {
    "properties": {
        "capabilityHostKind": "Agents",
        "aiServicesConnections": ["{connection-name-of-aoai-resource}"]
    }
}
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}
response = requests.put(url, json=payload, headers=headers, params=querystring)
print(response.text)
```

**Important:** After this configuration, agents will ONLY see deployments from the specified Azure OpenAI resource in `aiServicesConnections`. To use deployments from the parent AI Services resource again, you would need to delete and recreate the capability host with an edited `aiServicesConnections` (UPDATE is not supported for capability hosts). 

For a Bicep-based approach, see the [Use your own resources documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/use-your-own-resources?view=foundry-classic#basic-agent-setup-use-an-existing-azure-openai-resource).

# **Root Cause to be shared with Customer**
This is a known limitation in the Azure AI Foundry Classic portal. By default, the project capability host is only configured to see model deployments from the project's AI Services resource. Connected Azure OpenAI resources require manual capability host configuration to be visible to agents. There is currently no portal UI to manage this configuration - it must be done via REST API or ARM templates.

# **Related Information**
- [Use your own resources - Azure AI Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/use-your-own-resources?view=foundry-classic#basic-agent-setup-use-an-existing-azure-openai-resource)
- [Capability hosts - Azure AI Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/capability-hosts?view=foundry-classic)
- [Environment setup for agents](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/environment-setup?view=foundry-classic)
- [GitHub Discussion: Connected OpenAI resources not visible](https://github.com/orgs/azure-ai-foundry/discussions/59)
- [Microsoft Foundry portals overview](https://learn.microsoft.com/en-us/azure/ai-foundry/what-is-azure-ai-foundry?view=foundry-classic#microsoft-foundry-portals)

# **Tags or Prompts**
_This TSG helps answer:_
- Why can't I see my connected Azure OpenAI model deployments when creating an agent?
- Agent cannot use model from connected Azure OpenAI resource
- Azure AI Foundry agent model deployment not showing
- How to configure capability host for agents
- Agents only see project-level models not connected resources
- aiServicesConnections capability host configuration
