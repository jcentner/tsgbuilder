# TSG Builder Migration Plan: v1 → v2 Azure AI Foundry Agents

## Overview

This document outlines a phased migration plan for upgrading TSG Builder from v1 agents (classic Azure AI Studio) to v2 agents (new Microsoft Foundry) with GPT-5.2.

### Current State
- **SDK**: `azure-ai-projects==1.0.0` + `azure-ai-agents>=1.2.0b6`
- **Model**: `gpt-4.1`
- **Portal**: Classic Azure AI Studio
- **Pattern**: Threads/Messages API with `AgentEventHandler` streaming

### Target State
- **SDK**: `azure-ai-projects>=2.0.0b3` (NO `azure-ai-agents`)
- **Model**: `gpt-5.2`
- **Portal**: New Microsoft Foundry
- **Pattern**: Conversations API with `responses.create(stream=True)` streaming

---

## Key API Changes Summary

| Component | v1 (Classic) | v2 (New Foundry) |
|-----------|--------------|------------------|
| Agent creation | `create_agent()` | `create_version()` |
| Agent definition | Inline params | `PromptAgentDefinition` |
| Bing tool | `BingGroundingTool` from `azure.ai.agents.models` | `BingGroundingAgentTool` from `azure.ai.projects.models` |
| MCP tool | `McpTool` from `azure.ai.agents.models` | `MCPTool` from `azure.ai.projects.models` |
| Conversations | `threads.create()` + `messages.create()` | `conversations.create()` with items |
| Run execution | `runs.stream()` with `AgentEventHandler` | `responses.create(stream=True)` with event loop |
| Session tracking | Thread IDs | Conversation IDs |
| Streaming events | `on_message_delta`, `on_thread_run`, etc. | `response.output_text.delta`, `response.completed`, etc. |

---

## Phase 1: Environment & Dependencies Preparation
**Goal**: Set up v2 SDK alongside v1 for parallel testing  
**Risk**: Low  
**Estimated Time**: 1 hour

### Tasks

1. **Create a new requirements file for v2**
   ```bash
   # requirements-v2.txt
   azure-ai-projects>=2.0.0b3
   azure-identity>=1.19.0
   python-dotenv>=1.0.1
   flask>=3.0.0
   openai>=1.0.0
   # NOTE: Do NOT include azure-ai-agents - it forces classic mode!
   ```

2. **Update `.env` with new model deployment**
   ```bash
   MODEL_DEPLOYMENT_NAME=gpt-5.2
   # Optionally keep old model for rollback
   MODEL_DEPLOYMENT_NAME_V1=gpt-4.1
   ```

3. **Verify v2 test agent works**
   ```bash
   cd v2-agents
   python v2-agent-test.py
   ```

### Verification Checklist
- [ ] v2 SDK installs successfully (`azure-ai-projects` version 2.0.0b3+)
- [ ] `azure-ai-agents` is NOT installed in v2 environment
- [ ] Test agent appears in new Foundry portal (not classic)
- [ ] MCP tool works with v2 agent

---

## Phase 2: Tool Migration
**Goal**: Convert tool initialization to v2 patterns  
**Risk**: Medium (tools are critical for research stage)  
**Estimated Time**: 2 hours

### Current v1 Tool Setup (web_app.py lines ~547-554)
```python
from azure.ai.agents.models import BingGroundingTool, McpTool

bing_tool = BingGroundingTool(connection_id=conn_id)
research_tools.extend(bing_tool.definitions)

mcp_tool = McpTool(server_label="learn", server_url=LEARN_MCP_URL)
mcp_tool.set_approval_mode("never")
research_tools.extend(mcp_tool.definitions)
```

### Target v2 Tool Setup
```python
from azure.ai.projects.models import (
    BingGroundingAgentTool,
    BingGroundingSearchToolParameters,
    BingGroundingSearchConfiguration,
    MCPTool,
)

# Bing tool - v2 pattern
bing_tool = BingGroundingAgentTool(
    bing_grounding=BingGroundingSearchToolParameters(
        search_configurations=[
            BingGroundingSearchConfiguration(
                project_connection_id=conn_id
            )
        ]
    )
)

# MCP tool - v2 pattern (note capitalization change)
mcp_tool = MCPTool(
    server_label="learn",
    server_url=LEARN_MCP_URL,
    require_approval="never",
)

research_tools = [bing_tool, mcp_tool]
```

### Tasks

1. **Create `tools_v2.py` helper module**
   - Encapsulate v2 tool creation
   - Add connection resolution via `project_client.connections.get()`

2. **Update tool initialization in web_app.py**
   - Replace v1 imports with v2 imports
   - Update `BingGroundingTool` → `BingGroundingAgentTool`
   - Update `McpTool` → `MCPTool` with new structure

3. **Test tools in isolation**
   - Create test script that creates agent with tools and runs one query

### Verification Checklist
- [ ] Bing grounding tool retrieves search results
- [ ] MCP tool queries Microsoft Learn successfully
- [ ] Tool calls appear in response output
- [ ] No errors about missing tool definitions

---

## Phase 3: Agent Creation Migration
**Goal**: Convert from `create_agent()` to `create_version()` with `PromptAgentDefinition`  
**Risk**: Medium  
**Estimated Time**: 2 hours

### Current v1 Agent Creation (web_app.py lines ~560-590)
```python
researcher = project.agents.create_agent(
    model=model,
    name=f"{agent_name}-Researcher",
    instructions=RESEARCH_STAGE_INSTRUCTIONS,
    tools=research_tools,
    tool_resources=mcp_tool.resources,
    temperature=0,
)
```

### Target v2 Agent Creation
```python
from azure.ai.projects.models import PromptAgentDefinition

researcher = project_client.agents.create_version(
    agent_name=f"{agent_name}-Researcher",
    definition=PromptAgentDefinition(
        model=model,
        instructions=RESEARCH_STAGE_INSTRUCTIONS,
        tools=research_tools,
        temperature=0,
    ),
)
```

### Key Changes
| Aspect | v1 | v2 |
|--------|----|----|
| Method | `create_agent()` | `create_version()` |
| Model param | Direct `model=` | Inside `PromptAgentDefinition(model=)` |
| Instructions | Direct `instructions=` | Inside `PromptAgentDefinition(instructions=)` |
| Tools | Direct `tools=` | Inside `PromptAgentDefinition(tools=)` |
| Tool resources | `tool_resources=mcp_tool.resources` | Not needed (tools are self-contained) |
| Return value | Agent with `.id` | Agent with `.id`, `.name`, `.version` |

### Tasks

1. **Update agent creation in `/api/agents/setup` endpoint**
   - Convert all 3 agents (Researcher, Writer, Reviewer)
   - Update `PromptAgentDefinition` imports

2. **Update agent storage format (`.agent_ids.json`)**
   ```json
   // v1 format
   {"researcher": "agent_id", "writer": "agent_id", ...}
   
   // v2 format (need name + version for deletion)
   {
     "researcher": {"name": "TSG-Builder-Researcher", "version": "1"},
     "writer": {"name": "TSG-Builder-Writer", "version": "1"},
     ...
   }
   ```

3. **Update `delete_agents.py` for v2**
   - Change from `delete_agent(id)` to `delete_version(agent_name, agent_version)`

### Verification Checklist
- [ ] All 3 agents create successfully
- [ ] Agents appear in new Foundry portal
- [ ] Agent IDs/names stored correctly
- [ ] Agents can be deleted via cleanup script

---

## Phase 4: Session & Conversation Migration
**Goal**: Replace Threads/Messages API with Conversations API  
**Risk**: High (affects all message handling)  
**Estimated Time**: 4 hours

### Current v1 Thread Pattern (pipeline.py, web_app.py)
```python
# Create thread
thread = project.agents.threads.create()

# Add message
project.agents.messages.create(
    thread_id=thread.id,
    role="user",
    content=user_message,
)

# Run agent
with project.agents.runs.stream(
    thread_id=thread_id,
    agent_id=agent_id,
    event_handler=handler,
) as stream:
    stream.until_done()
```

### Target v2 Conversation Pattern
```python
with project_client.get_openai_client() as openai_client:
    # Create conversation with initial message
    conversation = openai_client.conversations.create(
        items=[{
            "type": "message",
            "role": "user",
            "content": user_message
        }],
    )
    
    # Get response from agent (non-streaming)
    response = openai_client.responses.create(
        conversation=conversation.id,
        extra_body={
            "agent": {"name": agent.name, "type": "agent_reference"}
        },
        input="",
    )
    
    # Add follow-up message
    openai_client.conversations.items.create(
        conversation_id=conversation.id,
        items=[{
            "type": "message",
            "role": "user",
            "content": follow_up_message
        }],
    )
```

### Session Storage Changes
```python
# v1 sessions dict
sessions[thread_id] = {
    "notes": str,
    "current_tsg": str,
    "questions": str | None,
    "research_report": str,
}

# v2 sessions dict (conversation-based)
sessions[conversation_id] = {
    "notes": str,
    "current_tsg": str,
    "questions": str | None,
    "research_report": str,
    "agent_name": str,  # Need to track which agent to use
}
```

### Tasks

1. **Create `conversations_v2.py` helper module**
   - Wrapper for conversation create/items/delete
   - Handle agent reference in responses

2. **Update session management in web_app.py**
   - Replace `thread_id` keys with `conversation_id`
   - Update session cleanup to delete conversations

3. **Update pipeline.py for v2 conversation flow**
   - Replace `threads.create()` → `conversations.create()`
   - Replace `messages.create()` → `conversations.items.create()`

4. **Test multi-turn conversations**
   - Verify follow-up answers work
   - Verify conversation context is maintained

### Verification Checklist
- [ ] Initial message creates conversation
- [ ] Agent responds to initial query
- [ ] Follow-up messages add to same conversation
- [ ] Conversation context maintained across turns
- [ ] Session cleanup deletes conversations

---

## Phase 5: Streaming Migration (CRITICAL)
**Goal**: Replace `AgentEventHandler` with v2 streaming pattern  
**Risk**: High (core of user experience)  
**Estimated Time**: 6 hours

### Current v1 Streaming (web_app.py SSEEventHandler)
```python
from azure.ai.agents.models import (
    AgentEventHandler,
    MessageDeltaChunk,
    ThreadMessage,
    ThreadRun,
    RunStep,
)

class SSEEventHandler(AgentEventHandler):
    def on_message_delta(self, delta: MessageDeltaChunk) -> None:
        # Stream text chunks
        self._send_event("delta", {"text": delta.text})
    
    def on_thread_run(self, run: ThreadRun) -> None:
        # Status updates
        self._send_event("status", {"status": run.status})
    
    def on_run_step(self, step: RunStep) -> None:
        # Tool calls
        self._handle_tool_calls(step)

# Usage
with project.agents.runs.stream(
    thread_id=thread_id,
    agent_id=agent_id,
    event_handler=handler,
) as stream:
    stream.until_done()
```

### Target v2 Streaming Pattern
```python
# v2 streaming via OpenAI client
stream_response = openai_client.responses.create(
    stream=True,
    conversation=conversation_id,
    input="",
    extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
)

for event in stream_response:
    if event.type == "response.created":
        # Response started
        yield sse_event("status", {"status": "running"})
    
    elif event.type == "response.output_text.delta":
        # Text chunk
        yield sse_event("delta", {"text": event.delta})
    
    elif event.type == "response.output_item.done":
        if event.item.type == "message":
            # Check for tool calls, citations
            item = event.item
            if hasattr(item, 'content') and item.content:
                for content in item.content:
                    if hasattr(content, 'annotations'):
                        for ann in content.annotations:
                            if ann.type == "url_citation":
                                yield sse_event("citation", {"url": ann.url})
    
    elif event.type == "response.completed":
        # Done
        yield sse_event("complete", {"text": event.response.output_text})
```

### v2 Event Types Reference
| Event Type | When Fired | Data Available |
|------------|------------|----------------|
| `response.created` | Response starts | `event.response.id` |
| `response.output_text.delta` | Text chunk | `event.delta` |
| `response.text.done` | Text complete | `event.text` |
| `response.output_item.done` | Output item complete | `event.item` (message, tool call, etc.) |
| `response.completed` | Full response done | `event.response.output_text` |

### Tasks

1. **Create new SSE streaming generator for v2**
   ```python
   def generate_v2_sse_events(openai_client, conversation_id, agent_name):
       stream = openai_client.responses.create(
           stream=True,
           conversation=conversation_id,
           extra_body={"agent": {"name": agent_name, "type": "agent_reference"}},
           input="",
       )
       for event in stream:
           yield from handle_v2_event(event)
   ```

2. **Map v1 events to v2 events for SSE**
   | v1 Event | v2 Event | SSE Type |
   |----------|----------|----------|
   | `on_thread_run(status="running")` | `response.created` | `status` |
   | `on_message_delta(text)` | `response.output_text.delta` | `delta` |
   | `on_run_step(tool_call)` | `response.output_item.done(type=...)` | `tool_call` |
   | `on_done()` | `response.completed` | `complete` |

3. **Update Flask SSE endpoints**
   - `/api/generate/stream` — Initial generation
   - `/api/followup/stream` — Follow-up answers

4. **Handle tool call events in v2 streaming**
   - MCP tool calls
   - Bing search calls
   - URL citations from search results

### Verification Checklist
- [ ] Text streams to browser in real-time
- [ ] Status updates appear (processing, running, complete)
- [ ] Tool call events show in debug info
- [ ] Citations extracted from Bing results
- [ ] Error handling works for failed runs
- [ ] Streaming doesn't timeout on long responses

---

## Phase 6: Pipeline Integration
**Goal**: Update full 3-stage pipeline for v2  
**Risk**: High (end-to-end functionality)  
**Estimated Time**: 4 hours

### Pipeline Flow Changes

```
v1 Pipeline:
┌─────────────────────────────────────────────────────────────┐
│ Thread A                                                     │
│ ├── Message: User notes                                      │
│ ├── Run: Researcher agent (tools)                            │
│ ├── Message: Research report                                 │
│ └── (Thread reused for follow-ups)                           │
├─────────────────────────────────────────────────────────────┤
│ Thread B                                                     │
│ ├── Message: Notes + Research                                │
│ ├── Run: Writer agent (no tools)                             │
│ └── Message: TSG draft                                       │
├─────────────────────────────────────────────────────────────┤
│ Thread C                                                     │
│ ├── Message: TSG draft                                       │
│ ├── Run: Reviewer agent (no tools)                           │
│ └── Message: Review feedback / approved TSG                  │
└─────────────────────────────────────────────────────────────┘

v2 Pipeline:
┌─────────────────────────────────────────────────────────────┐
│ Conversation A (persistent for user)                         │
│ ├── Item: User notes                                         │
│ ├── Response: Researcher → Research report                   │
│ ├── Item: Follow-up answers (if any)                         │
│ └── Response: Researcher → Updated research                  │
├─────────────────────────────────────────────────────────────┤
│ Internal processing (may use same or different conversation) │
│ ├── Writer agent: Notes + Research → TSG draft               │
│ └── Reviewer agent: TSG draft → Feedback/Approved            │
└─────────────────────────────────────────────────────────────┘
```

### Tasks

1. **Update `pipeline.py` for v2**
   - Convert `run_pipeline()` to use v2 conversations
   - Update agent invocation to use `responses.create()`

2. **Update `generate_pipeline_sse_events()` in web_app.py**
   - Use v2 streaming for each pipeline stage
   - Maintain stage-by-stage status updates

3. **Handle inter-stage communication**
   - Research report passed to Writer
   - TSG draft passed to Reviewer
   - Determine if same conversation or separate per stage

4. **Test full pipeline end-to-end**
   - Input raw notes
   - Verify research stage with tools
   - Verify writer stage produces TSG
   - Verify reviewer stage validates

### Verification Checklist
- [ ] Research stage uses tools and produces report
- [ ] Writer stage generates TSG from notes + research
- [ ] Reviewer stage validates TSG structure
- [ ] All 3 stages stream to browser
- [ ] Pipeline handles errors gracefully
- [ ] Follow-up flow works after initial generation

---

## Phase 7: UI & Error Handling
**Goal**: Update frontend integration and error handling  
**Risk**: Low  
**Estimated Time**: 2 hours

### Tasks

1. **Update `templates/index.html` SSE handling (if needed)**
   - Event types should remain same (SSE format unchanged)
   - Verify status messages still display correctly

2. **Update error messages for v2-specific errors**
   - Rate limit errors
   - Authentication errors
   - Tool execution errors

3. **Update `/api/status` endpoint**
   - Check for v2 SDK version
   - Validate agent storage format

4. **Update `validate_setup.py`**
   - Check for correct SDK version
   - Warn if `azure-ai-agents` is installed

### Verification Checklist
- [ ] UI displays streaming text correctly
- [ ] Status messages show pipeline progress
- [ ] Error messages are user-friendly
- [ ] Setup validation catches configuration issues

---

## Phase 8: Cleanup & Documentation
**Goal**: Remove v1 code, update documentation  
**Risk**: Low  
**Estimated Time**: 2 hours

### Tasks

1. **Remove v1 imports and code**
   - Remove all `from azure.ai.agents.models import ...`
   - Remove `AgentEventHandler` class
   - Remove thread-based session handling

2. **Update `requirements.txt`**
   ```
   azure-ai-projects>=2.0.0b3
   azure-identity>=1.19.0
   python-dotenv>=1.0.1
   flask>=3.0.0
   openai>=1.0.0
   ```

3. **Update `docs/architecture.md`**
   - Document v2 API patterns
   - Update diagrams for conversation-based flow

4. **Update `README.md`**
   - New setup instructions for v2 SDK
   - Note about gpt-5.2 model

5. **Archive v2-agents/ test folder**
   - Can be removed after main migration complete

### Verification Checklist
- [ ] No v1 imports remain
- [ ] All tests pass with v2 SDK
- [ ] Documentation reflects v2 patterns
- [ ] README has updated setup instructions

---

## Rollback Plan

If issues are discovered during migration:

1. **Quick rollback**: Revert to v1 `requirements.txt` and restore from git
2. **Partial rollback**: Keep v2 agents but use v1 streaming (not recommended)
3. **Model rollback**: Change `MODEL_DEPLOYMENT_NAME` back to `gpt-4.1`

### Critical Files to Backup
- `web_app.py`
- `pipeline.py`
- `requirements.txt`
- `.agent_ids.json`
- `.env`

---

## Testing Strategy

### Unit Tests (per phase)
- Tool initialization
- Agent creation/deletion
- Conversation create/items/delete
- SSE event generation

### Integration Tests
- Full pipeline with test input
- Follow-up question flow
- Error scenarios (rate limits, auth failures)

### Manual Tests
- Web UI end-to-end
- Verify agents in Foundry portal
- Check streaming performance
- Test with multiple concurrent users

---

## Timeline Estimate

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1: Environment | 1 hour | None |
| Phase 2: Tools | 2 hours | Phase 1 |
| Phase 3: Agent Creation | 2 hours | Phase 2 |
| Phase 4: Conversations | 4 hours | Phase 3 |
| Phase 5: Streaming | 6 hours | Phase 4 |
| Phase 6: Pipeline | 4 hours | Phase 5 |
| Phase 7: UI/Errors | 2 hours | Phase 6 |
| Phase 8: Cleanup | 2 hours | Phase 7 |

**Total: ~23 hours** (spread across multiple days for testing)

---

## Success Criteria

1. ✅ All agents appear in **new Foundry portal** (not classic)
2. ✅ GPT-5.2 model used for all agents
3. ✅ Bing and MCP tools work correctly
4. ✅ Real-time streaming works in browser
5. ✅ 3-stage pipeline completes successfully
6. ✅ Follow-up question flow works
7. ✅ No `azure-ai-agents` package in dependencies
8. ✅ SDK version is `azure-ai-projects>=2.0.0b3`
