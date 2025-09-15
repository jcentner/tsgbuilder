[[_TOC_]]

# **Title**
Agents in Azure AI Foundry projects cannot use connected Azure OpenAI resource model deployments.

# **Issue Description / Symptoms**
- **What** is the issue?  
  Agents in Azure AI Foundry projects can only use model deployments from the default AI Services resource, even when Azure OpenAI resources are connected.
- **Who** does this affect?  
  Users attempting to configure Agents in Azure AI Foundry projects with connected Azure OpenAI resources.
- **Where** does the issue occur? Where does it not occur?  
  Occurs in Azure AI Foundry projects using the GA version, not in hub-based projects.  
- **When** does it occur?  
  When trying to create or configure an Agent in the project.

# **When does the TSG not Apply**
This TSG does not apply to hub-based Azure AI Foundry projects or scenarios where Agents are not being used.

# **Diagnosis**
- [ ] Verify that the Azure OpenAI resource is connected to the Azure AI Foundry project.  
- [ ] Check if the connected Azure OpenAI resource is in the same region as the AI Services resource.  
- [ ] Confirm that the Agent setup only displays deployments from the AI Services resource.  
- [ ] Review the capability host configuration for the project.  

Don't Remove This Text: Results of the Diagnosis should be attached in the Case notes/ICM.

# **Questions to Ask the Customer**
- Is the Azure OpenAI resource in the same region as the AI Services resource?  
- Are there any existing Agents under the AI Services resource that could be disrupted by creating a new capability host?  
- Have you attempted to modify or recreate the capability host configuration?  

# **Cause**
The issue occurs due to a feature gap in the Azure AI Foundry platform. By default, the project capability host is configured to use the AI Services resource, and there is no user interface (UX) for managing or modifying capability hosts to include connected Azure OpenAI resources.

# **Mitigation or Resolution**
To resolve this issue, you need to create a new capability host that points to the Azure OpenAI resource. This process involves the following steps:

1. Ensure the connected Azure OpenAI resource is in the same region as the AI Services resource.
2. Use the provided Python script to create a new capability host:
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
3. After creating the capability host, the Agents UI in Foundry will allow CRUD operations using the Azure OpenAI resource specified in the `aiServicesConnections` parameter.

Note: This process may disrupt existing Agents under the AI Services resource.

# **Root Cause to be shared with Customer**
The issue arises due to a default configuration in Azure AI Foundry projects where the capability host is set to use the AI Services resource. Currently, there is no user interface for modifying this configuration to include connected Azure OpenAI resources.

# **Related Information**
- [Capability Hosts Overview](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/capability-hosts)  
- [Capability Host Optional Properties](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/capability-hosts#optional-property)  

# **Tags or Prompts**
This TSG helps answer:  
- "Why can't my Azure AI Foundry Agent use connected Azure OpenAI resources?"  
- "How do I configure capability hosts for Azure AI Foundry Agents?"  
- "Azure AI Foundry Agent configuration with Azure OpenAI resources."