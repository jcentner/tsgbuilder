# Tools Hang Test

Minimal test harness to reproduce and debug hanging behavior when using MCP + Bing tools together.

## Usage

```bash
# Test with both tools (default) - this is what hangs
python test_tools.py

# Test with MCP only
python test_tools.py --mcp-only

# Test with Bing only  
python test_tools.py --bing-only

# Custom prompt
python test_tools.py --prompt "Search for Azure capability hosts"

# Longer timeout (default is 300s)
python test_tools.py --timeout 600

# Keep agent after test (for inspection)
python test_tools.py --no-cleanup
```

## What It Does

1. Creates a temporary agent with the specified tools
2. Sends a test prompt and streams the response
3. Logs all events with timestamps to identify where hangs occur
4. Shows warnings for gaps > 30s between events
5. Cleans up the agent when done

## Interpreting Output

```
[  0.0s] 🔧 Tool call started: microsoft_docs_search
[ 15.2s] ✅ Tool call complete: microsoft_docs_search (15.2s)
[ 15.3s] 🔧 Tool call started: bing_grounding
[315.3s] ⚠️  Long gap: 300.0s since last event    <-- THIS IS THE HANG
```

## Hypotheses to Test

1. **Sequential tool execution**: Does it hang when both tools are called in sequence?
2. **Bing after MCP**: Does Bing specifically hang after MCP completes?
3. **Timeout accumulation**: Is the 10min timeout per-tool or cumulative?
4. **Connection reuse**: Is there a connection pool issue between tools?

## Test Matrix

| Test | MCP | Bing | Expected | Actual |
|------|-----|------|----------|--------|
| MCP only | ✅ | ❌ | Fast | ? |
| Bing only | ❌ | ✅ | Fast | ? |
| Both tools | ✅ | ✅ | ??? | HANGS |
