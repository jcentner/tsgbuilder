user reports Azure OpenAI gpt-4.1 fails with error:

Error code: 400 - {'error': {'message': "Invalid 'tools[0].function.description': string too long. Expected a string with maximum length 1048576, but got a string with length 2778531 instead.", 'type': 'invalid_request_error', 'param': 'tools[0].function.description', 'code': 'string_above_max_length'}}

This is despite a 1,047,576 token context window. 

The issue is that gpt-4.1 requests result in errors with tool or function call definitions exceeding 300,000 tokens. 
While we support up to 1,047,576 context tokens for gpt-4.1, this limitation is specifically for tool or function call definitions.
We have documented the limitation: https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-models/concepts/models-sold-directly-by-azure?view=foundry-classic&tabs=global-standard-aoai%2Cglobal-standard&pivots=azure-openai#capabilities-1
Requests can still contain up to 1,047,576 total context tokens, but the total length of tool and function call definitions should not exceed this limit.
This is viewed as a product limitation, not a bug.
We don't have an ETA for support for over 300,000 tokens in tool/function call definitions, or a guarantee that this will be supported in the future. 

From here, the path to mitigation is to split up the tool or function call definitions to separate calls.

One option might be to break up the call by using an initial LLM stage that evaluates which tools/functions should be used and then make the call inserting the definition for those tools/functions.
Another option would be using an orchestrator/sub-agent architecture, where individual functions are delegated to sub-agents. 