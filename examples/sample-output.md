[[_TOC_]]

# **Title**
**Azure AI Foundry (classic) Agents: Model dropdown does not show deployments from connected Azure OpenAI resource (only project/default resource deployments)**

# **Issue Description / Symptoms**
When creating an **Agent** in an **Azure AI Foundry (classic) project (GA, non-hub-based)**, the **model selection dropdown** in the Studio only shows model deployments that exist in the project’s default configured resource (for example, the project’s AI Services/AOAI resource). **Deployments from a connected Azure OpenAI resource do not appear**.

- **What is the issue?**  
  Agents cannot see/use model deployments from a *connected* Azure OpenAI resource in the UI model picker; only project/default resource deployments appear.
- **Who does this affect?**  
  Users creating Agents in Azure AI Foundry (classic) projects who expect to use deployments from connected Azure OpenAI resources.
- **Where does the issue occur / not occur?**  
  - Occurs in Foundry **classic** Agent creation experience (UI model dropdown).  
  - Does not occur when the deployment is in the same resource already configured for the project’s Agent capability host (those deployments appear normally).
- **When does it occur?**  
  When the project’s Agent capability host is not configured to include the connected Azure OpenAI resource via `aiServicesConnections`.

# **When does the TSG not Apply**
- Scenarios where the model deployment is already in the resource configured for the project’s Agent capability host (models should appear normally).
- Scenarios specifically involving **models behind API Management (APIM)**; that is a different limitation/support boundary than “connected AOAI deployments not visible.” (See related GitHub discussion in **Related Information**.)

# **Diagnosis**
- [ ] Confirm the user is using **Azure AI Foundry (classic)** (the notes/research are specific to classic and mention a UX gap there).
- [ ] Confirm the model deployment exists in a **connected Azure OpenAI resource** (not the project’s default resource).
- [ ] Check whether the project has a **project capability host** for `capabilityHostKind: Agents`, and whether it includes the expected AOAI connection name in `aiServicesConnections`.  
      - Capability hosts control which model deployments Agents can use, and `aiServicesConnections` is the mechanism to “use your own model deployments” from Azure OpenAI.  
      - Capability hosts **cannot be updated**; they must be deleted and recreated to change configuration.
- [ ] If attempting to create a new capability host at the same scope, watch for **409 Conflict** (only one capability host per scope).

Don't Remove This Text: Results of the Diagnosis should be attached in the Case notes/ICM.

# **Questions to Ask the Customer**
- Are you using **Foundry classic** or the newer Foundry experience?
- What is the **connection name** of the connected Azure OpenAI resource whose deployments you expect to see?
- Does the project already have a **project capability host** for Agents? If yes, what is its `aiServicesConnections` value?
- Are the AI Services resource and the connected Azure OpenAI resource in the **same region**? (This requirement is stated in the community workaround.)
- Do you have existing Agents that could be impacted if the capability host is **deleted/recreated**?

# **Cause**
In Foundry classic, the set of model deployments available to Agents is governed by the project’s **Agent capability host** configuration. If the project capability host is only configured for the project’s default AI Services/AOAI resource (the default behavior and what templates publish), then **deployments from connected Azure OpenAI resources will not be surfaced** in the Agent model picker. Additionally, there is a **UX/feature gap** in Foundry classic for managing capability hosts, contributing to the symptom that connected deployments are not selectable in the UI.

# **Mitigation or Resolution**
Configure the project’s **Agent capability host** to use the connected Azure OpenAI resource by setting `aiServicesConnections` to the AOAI connection name. Because capability hosts are immutable, you may need to **delete and recreate** the capability host to change which connection is used.

> Important notes from the provided workaround:
> - The connected Azure OpenAI resource should be in the **same region** as the AI Services resource. (Community guidance)
> - Changing capability host configuration **could disrupt existing agents** under the AI Services resource.
> - **You cannot update a capability host**, only delete and recreate. (Documented)

## Python example (from notes)
Replace every `{...}` placeholder with your values.

> Note: Verify the `api-version` against official documentation before use.

```python
import requests
import json
from azure.identity import DefaultAzureCredential
token = DefaultAzureCredential().get_token("https://management.azure.com/.default").token 
 
 
 ## Create account capability host
url = "https://management.azure.com/subscriptions/{sub-id}/resourceGroups/{res-group-name}/providers/Microsoft.CognitiveServices/accounts/{ai-services-resource}/capabilityHosts/{any-cap-host-name}/"
querystring = {"api-version":"2025-04-01-preview"}
payload = {"properties": {"capabilityHostKind": "Agents"}}
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "User-Agent": "insomnia/11.0.1"
}
response = requests.request("PUT", url, json=payload, headers=headers, params=querystring)
print(response.text)

## Create project capability host
url = "https://management.azure.com/subscriptions/{sub-id}/resourceGroups/{res-group-name}/providers/Microsoft.CognitiveServices/accounts/{ai-services-resource}/projects/{project-name}/capabilityHosts/{any-proj-cap-host-name}/"
querystring = {"api-version":"2025-04-01-preview"}
payload = {"properties": {
        "capabilityHostKind": "Agents",
        "aiServicesConnections": ["{connection-name-of-aoai-resource}"]
    }}
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "User-Agent": "insomnia/11.0.1"
}
response = requests.request("PUT", url, json=payload, headers=headers, params=querystring)
print(response.text)
```

Expected outcome:
- After creating the project capability host with `aiServicesConnections`, Agents in the project should be able to use **ONLY** the deployments from the connected AOAI resource specified in `aiServicesConnections`.
- To switch to a different AOAI connection (or back to the parent AI Services resource), delete and recreate the capability host accordingly.

# **Root Cause to be shared with Customer**
Agents in Foundry classic only list model deployments from the Azure AI Services/Azure OpenAI resources configured on the project’s **Agent capability host**. Connected Azure OpenAI resources won’t appear in the Agent model picker unless the project capability host is explicitly configured to use that connection (via `aiServicesConnections`). Capability hosts can’t be edited; they must be deleted and recreated to change the configuration.

# **Related Information**
- Capability hosts (Azure AI Foundry classic): https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/capability-hosts?view=foundry-classic
- Set up your environment (Azure AI Foundry classic Agents): https://learn.microsoft.com/en-us/azure/ai-foundry/agents/environment-setup?view=foundry-classic
- GitHub Discussion #59 (workaround using `aiServicesConnections`): https://github.com/orgs/azure-ai-foundry/discussions/59
- GitHub Discussion #141 (related but different scenario—APIM/connected resources): https://github.com/orgs/azure-ai-foundry/discussions/141

# **Tags or Prompts**
- Tags: Azure AI Foundry, Foundry classic, Agents, Agent Service, capability host, aiServicesConnections, connected Azure OpenAI, model deployment not showing, model dropdown, 409 Conflict
- Prompts:
  - “Agents model dropdown doesn’t show connected Azure OpenAI deployments”
  - “How to configure capability host aiServicesConnections for Foundry classic Agents”
  - “Use connected Azure OpenAI resource deployments in Foundry classic Agents”