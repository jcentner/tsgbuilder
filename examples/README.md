# Example Inputs

This directory contains example input files and their expected outputs to help you understand the TSG Builder workflow.

## Files

| File | Description |
|------|-------------|
| `capability-host-input.txt` | Input about Azure AI Foundry agents not seeing connected OpenAI resources |
| `capability-host-expected.md` | Expected TSG output (what the agent should produce) |

## Usage

```bash
# Run with the example input
python ask_agent.py --notes-file examples/capability-host-input.txt --output examples/my-output.md

# Compare your output to the expected output
diff examples/my-output.md examples/capability-host-expected.md
```

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
