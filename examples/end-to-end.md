Sample with gpt-4.1 on Dec 18 2025:

--- Input: ---

Problem/questions:

When I try to create an Agent in my project (with the GA version in an Azure AI Foundry project, not a hub-based project), I can only use model deployments deployed in my current Azure AI Foundry resource, despite having connected Azure OpenAI resources. From: https://github.com/orgs/azure-ai-foundry/discussions/59


	1. When the OAI model is deployed on project level, the option to select a model is available when trying to create an agent from the studio. But the models deployed on the connected OpenAI resource does not show up. Is this a limitation?
	2. Even if we create the agent via SDK using a model deployment from the connected OpenAI resource, there is no option to select the deployments from the OpenAI resource. The only model available in the dropdown are the models deployed on the project level and not on the connect OAI resource level. 

Generally: "When using an Agent in my project, why can't I use it/see it with a model deployment in a connected Azure OpenAI resource?" 


Background:

https://learn.microsoft.com/en-us/azure/ai-foundry/agents/environment-setup?view=foundry-classic
https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/capability-hosts?view=foundry-classic
https://learn.microsoft.com/en-us/azure/ai-foundry/what-is-azure-ai-foundry?view=foundry-classic#microsoft-foundry-portals 


Limitation:

Known issue with Agents seeing connected OpenAI resource deployments in the UI. Agents deployed by template also can't use connected resources unless their capability host is configured to see that resource. This applies to Foundry Classic UI. 

There is a known feature gap with Agents being able to see connected OpenAI resource model deployments. Specifically, Currently, we lack a UX for managing capability hosts. (Classic Foundry UI).
 
The project capability host is only configured by default with the project AI Services resource by default and in the templates we publish. It can be deleted/recreated to point to an Azure OpenAI resource instead of the AI Services resource so that all Agents in the project see the OpenAI resource deployments instead. 



Workaround: 

Create new capability host that points at an OpenAI resource instead of the AI Services resource using the aiServicesConnections property:
https://github.com/orgs/azure-ai-foundry/discussions/59

As of now there's no easy way to do this. However, this is a way.
	1. The connected OpenAI resource should be in the same region as the AIServices resource.
	2. You would need to create capability host. This could disrupt any existing agents under the AIServices resource.
How to create capability host?
Below is a python code - replace everywhere you see {something}.

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
The above would let you use Agents ONLY with the connected AOAI resource mentioned in the "aiServicesConnections" parameter. You could update or delete the capability host to be able to use deployments from other AOAI resource connection or from the parent AIServices resource.

From <https://github.com/orgs/azure-ai-foundry/discussions/59>


NOTE: you cannot update a capability host, only delete and recreate. 



--- Questions asked by model: --- 


{{MISSING::Issue Description::Exact error messages or UI text presented when attempting to select a model from the connected Azure OpenAI resource}} -> What is the exact error message or UI text seen when attempting to select a model from the connected Azure OpenAI resource?
{{MISSING::Diagnosis::Diagnostic commands/scripts to list capability hosts and their aiServicesConnections for the project}} -> What diagnostic command, query, or script did you use to list existing capability hosts and their aiServicesConnections for the project?
{{MISSING::Questions to Ask the Customer::Other relevant environmental details or support logs}} -> Are there other relevant environmental details (settings, logs, configuration) that should be provided by the customer for troubleshooting?


--- Answers provided: ---


Issue Description: There is no error message; the UI simply doesn't show the desired model deployments.  
&nbsp;  
Diagnosis: reference https://learn.microsoft.com/en-us/rest/api/aifoundry/accountmanagement/project-capability-hosts/get?view=rest-aifoundry-accountmanagement-2025-06-01&tabs=HTTP for checking a capability host  
&nbsp;  
Questions to ask the customer: there are no other relevant details besides what was shared


--- Result (Completed): ---


# **Title**
Azure AI Foundry Agents unable to use model deployments from connected Azure OpenAI resources in Foundry Classic projects

# **Issue Description / Symptoms**
When attempting to create an Agent in an Azure AI Foundry project (Classic portal, GA version), users are unable to select or use model deployments from connected Azure OpenAI resources. Only model deployments within the current Azure AI Foundry resource (AI Services resource) appear in the UI dropdown. This limitation affects users trying to leverage models deployed in linked Azure OpenAI resources when building or managing Agents within a Foundry Classic project.

- **What**: Models deployed in connected Azure OpenAI resources are not visible/selectable when creating Agents; only project-level deployments are available.
- **Who**: Any user trying to use Foundry Classic project Agents with Azure OpenAI connected resources.
- **Where**: Azure AI Foundry Classic portal (non-hub projects), agent creation UI and SDK.
- **When**: On agent creation or modification within a Foundry Classic project.

There is no error message; the UI simply does not show the desired model deployments.

# **When does the TSG not Apply**
This TSG does not apply to:
- Azure AI Foundry hub-based projects (which have different resource linking and management behavior)
- Scenarios where only project-level AI Services resources are used for model deployment
- Other portals or agent management interfaces outside of Foundry Classic

# **Diagnosis**
- Confirm the project type (Classic Foundry project, not hub-based)
- Verify the connected Azure OpenAI resource in the project's configuration:
  - Check "Linked Azure OpenAI resource" status under project settings
- Attempt to create an Agent:
  - Observe the dropdown list of available model deployments and note which resources/connection sources are missing.
- Review capability host configuration for the project using Azure Resource Manager (see [Related Information]).
- Check the capability host using Azure AI Foundry REST API: [Get Project Capability Hosts](https://learn.microsoft.com/en-us/rest/api/aifoundry/accountmanagement/project-capability-hosts/get?view=rest-aifoundry-accountmanagement-2025-06-01&tabs=HTTP)
Don't Remove This Text: Results of the Diagnosis should be attached in the Case notes/ICM.

# **Questions to Ask the Customer**
- Which region are your Azure AI Services and connected Azure OpenAI resources deployed in?
- Are you using the Classic Foundry project UI or the hub-based experience?
- Did you receive any error or informational messages when trying to select a model from the connected Azure OpenAI resource?
- Have you previously configured or modified capability hosts for your project? If so, please provide the configuration details.
- Are other agents under the same project able to see deployments from the connected OpenAI resource?
- Has any workaround, such as capability host recreation, been attempted?

# **Cause**
Azure AI Foundry Classic projects are designed such that the default capability host is configured to use the project-level AI Services resource. Foundry Classic UI does not provide a UX for managing capability hosts, nor does it allow agents to natively see or use model deployments in connected Azure OpenAI resources. Only deployments within the current project's AI Services resource are shown and available in the agent creation UI.

Additionally, capability hosts cannot be updated—only deleted and recreated. If a capability host is created or reconfigured with the "aiServicesConnections" property pointing at a connected AOAI resource, then only deployments from that resource become visible to all agents in the project, which may disrupt existing agents using the previous resource.

# **Mitigation or Resolution**
To enable Agent access to model deployments in a connected Azure OpenAI resource:

1. Ensure the connected AOAI resource is in the same region as the AI Services resource.
2. Delete the existing project capability host (if present).
3. Create a new project capability host targeted at the AOAI resource using the "aiServicesConnections" property.

Sample Python code for capability host creation:
```python
import requests
import json
from azure.identity import DefaultAzureCredential

token = DefaultAzureCredential().get_token("https://management.azure.com/.default").token

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
}
response = requests.request("PUT", url, json=payload, headers=headers, params=querystring)
print(response.text)
```
Replace placeholder values as needed. Note: Once changed, all agents in the project will use ONLY the specified AOAI resource for model deployments.

Caution: Modifying capability hosts may disrupt existing agent operations linked to the original AI Services resource.

Reference: https://github.com/orgs/azure-ai-foundry/discussions/59
Note: You cannot update a capability host, only delete and recreate.

# **Root Cause to be shared with Customer**
In Foundry Classic projects, Agents can only access model deployments from the capability host resource they are configured with by default—the project's AI Services resource. The current UI and SDK do not support selecting deployments from connected Azure OpenAI resources unless the capability host is manually reconfigured. This is a known limitation of the Foundry Classic experience.

# **Related Information**
- [Azure AI Foundry Agents Environment Setup](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/environment-setup?view=foundry-classic)
- [Azure AI Foundry Agents Concepts: Capability Hosts](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/capability-hosts?view=foundry-classic)
- [What is Azure AI Foundry?](https://learn.microsoft.com/en-us/azure/ai-foundry/what-is-azure-ai-foundry?view=foundry-classic#microsoft-foundry-portals)
- [GitHub Discussion: Agents/Model Deployments and Capability Hosts](https://github.com/orgs/azure-ai-foundry/discussions/59)
- [Get Project Capability Hosts API](https://learn.microsoft.com/en-us/rest/api/aifoundry/accountmanagement/project-capability-hosts/get?view=rest-aifoundry-accountmanagement-2025-06-01&tabs=HTTP)

# **Tags or Prompts**
Azure AI Foundry, capability host, agent model deployment, Azure OpenAI resource, Foundry Classic UI, aiServicesConnections, agent creation issue, connected resource limitation, capability host recreation, model selection dropdown