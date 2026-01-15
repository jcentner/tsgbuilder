# Tool Hang Test Harness

Minimal test scripts to isolate and diagnose hanging behavior with Azure AI Agent tools.

## Quick Start

```bash
# From the tsgbuilder root directory
cd tools-hang-test
source ../.venv/bin/activate

# Basic tests (direct API call)
python test_tools.py --mcp-only --timeout 120    # MCP (Microsoft Learn) only
python test_tools.py --bing-only --timeout 120   # Bing Search only
python test_tools.py --both --timeout 300        # Both tools (default)

# SSE mode (mirrors Flask pipeline pattern)
python test_tools.py --both --sse-mode --timeout 300

# Realistic research prompt
python test_tools.py --both --sse-mode --research --timeout 300

# Custom prompt
python test_tools.py --both --prompt "Your custom question here"
```

## Test Modes

### Direct Mode (default)
Single-threaded, synchronous API call. Good for isolating tool behavior.

### SSE Mode (`--sse-mode`)
Mirrors the Flask web app pattern:
- Background thread runs the API call
- Main thread consumes events via queue (30s keepalive timeout)
- Uses same httpx timeout configuration as pipeline.py

This mode replicates how the real pipeline operates and can help identify
threading or queue-related issues.

## What It Tests

| Component | Mirrored From |
|-----------|---------------|
| httpx Timeout | pipeline.py (600s read, 120s pool) |
| Client context manager | pipeline.py (`with openai_client:`) |
| Threading + Queue | web_app.py SSE generator |
| 30s keepalive timeout | web_app.py `event_queue.get(timeout=30)` |
| Tool configuration | web_app.py agent creation |

## Interpreting Results

### Successful Run
```
[  11.8s] 🏁 Response completed
Test completed in 11.9s
```

### Tool Call Tracking
```
[   2.1s] 🔧 Tool call started: bing_grounding
[   8.5s] ✅ Tool call complete: bing_grounding (6.4s)
```

### Rate Limiting (MCP)
```
❌ Error: Error encountered while enumerating tools from remote server: 
https://learn.microsoft.com:443/api/mcp. Details: 429 (Too Many Requests).
```
The Microsoft Learn MCP endpoint has rate limits. Wait 1-2 minutes between tests.

### Long Gap Warning
```
[  45.2s] ⚠️  Long gap: 35.1s since last event
```
Indicates the API went 30+ seconds without sending any events.

### Keepalive (SSE Mode)
```
[  60.0s] 💓 Keepalive (no events for 30s) - would send SSE keepalive
```
Main thread didn't receive any events for 30s. In production, this would
trigger an SSE keepalive to prevent client timeout.

## Test Matrix Results

| Test | MCP | Bing | SSE Mode | Duration | Result |
|------|-----|------|----------|----------|--------|
| MCP only | ✅ | ❌ | No | ~12s | ✅ Pass |
| Bing only | ❌ | ✅ | No | ~11s | ✅ Pass |
| Both tools | ✅ | ✅ | No | ~26-53s | ✅ Pass |
| Bing SSE | ❌ | ✅ | Yes | ~13s | ✅ Pass |

## Files

- `test_tools.py` - Main test script with SSE mode support
- `README.md` - This file
- `run_all_tests.sh` - Runs all test configurations
