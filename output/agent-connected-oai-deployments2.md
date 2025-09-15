[[_TOC_]]

# **Title**
Agents in Azure AI Foundry projects cannot use connected Azure OpenAI resource model deployments.

# **Issue Description / Symptoms**
- **What** is the issue?  
  Agents in Azure AI Foundry projects can only use model deployments from the default AI Services resource, even when Azure OpenAI resources are connected.
- **Who** does this affect?  
  Customers using Azure AI Foundry projects who want their Agents to leverage connected Azure OpenAI resource model deployments.
- **Where** does the issue occur? Where does it not occur?  
  The issue occurs in Azure AI Foundry projects (GA version) and does not apply to hub-based projects.
- **When** does it occur?  
  The issue occurs when attempting to create or configure an Agent in a Foundry project with connected Azure OpenAI resources.

# **When does the TSG not Apply**
This TSG does not apply to hub-based projects or scenarios where the default AI Services resource is sufficient for the Agent's requirements.

# **Diagnosis**
- [ ] Verify that the Azure OpenAI resource is connected to the Azure AI Foundry project.
- [ ] Check if the connected Azure OpenAI resource is in the same region as the AI Services resource.
- [ ] Confirm that the Agent configuration only shows deployments from the AI Services resource and not from the connected Azure OpenAI resource.
- [ ] Review the project capability host configuration to determine if it is set to the default AI Services resource.

Don't Remove This Text: Results of the Diagnosis should be attached in the Case notes/ICM.

# **Questions to Ask the Customer**
- Are the Azure OpenAI and AI Services resources in the same region?
- Have you attempted to modify or recreate the capability host for the project?
- Are there any existing Agents under the AI Services resource that could be disrupted by creating a new capability host?

# **Cause**
The issue occurs because the project capability host is configured by default to use the AI Services resource. Currently, there is no user interface (UX) for managing capability hosts, and the default configuration does not include connected Azure OpenAI resources.

# **Mitigation or Resolution**
To resolve this issue, you need to create a new capability host that points to the Azure OpenAI resource. This will allow Agents in the project to use the connected Azure OpenAI resource deployments. Note that this process may disrupt existing Agents under the AI Services resource.

### Steps to Create a New Capability Host
1. Ensure that the connected Azure OpenAI resource is in the same region as the AI Services resource.
2. Use the following Python script to create a new capability host. Replace placeholders (e.g., `{sub-id}`, `{res-group-name}`) with your specific values.

```python
import requests
import json
from azure.identity import DefaultAzureCredential

token = DefaultAzureCredential().get_token("https://management.azure.com/.default").token 

# Create account capability host
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

# Create project capability host
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

3. Once the capability host is created, the Agents UI in Foundry can be used to manage Agents with the specified Azure OpenAI resource.

### Additional Notes
- This process can also be performed using Bicep or Terraform (azapi) by modifying the appropriate fields.
- For more details, refer to the [Capability Hosts documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/capability-hosts).

# **Root Cause to be shared with Customer**
The issue occurs because the project capability host is configured by default to use the AI Services resource. Currently, there is no user interface for managing capability hosts, and the default configuration does not include connected Azure OpenAI resources. A new capability host must be created to enable the use of Azure OpenAI resource deployments.

# **Related Information**
- [Capability Hosts Documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/capability-hosts)
- [Capability Hosts Optional Property](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/capability-hosts#optional-property)

# **Tags or Prompts**
This TSG helps answer:
- "Why can't my Agent use connected Azure OpenAI resource deployments in Azure AI Foundry?"
- "How do I configure a capability host for Azure OpenAI resources?"
- "Azure AI Foundry Agent configuration issues with OpenAI resources."