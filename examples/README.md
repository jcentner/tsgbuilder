# Example Inputs

This directory contains example input files and their expected outputs to help you understand the TSG Builder workflow.

## Files

| File | Description |
|------|-------------|
| `capability-host-input.txt` | Input about Azure AI Foundry agents not seeing connected OpenAI resources |
| `capability-host-expected.md` | Expected TSG output (what the agent should produce) |

## Usage

1. Start the web UI: `make ui`
2. Open http://localhost:5000
3. Click "Load example" to load `input-example.txt`, or paste content from your own notes on an issue
4. Click "Generate TSG"

## Notes

- The expected outputs are **reference examples**, not exact matches
- Your actual output may vary based on:
  - Current documentation available on Microsoft Learn
  - Bing search results at time of execution
  - Model behavior variations
- The key things to verify:
  - All TSG sections are present
  - Relevant Microsoft Learn links are included
  - The workaround/resolution is accurate
