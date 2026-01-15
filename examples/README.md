# Examples

This directory contains example input files, expected outputs, and test run results to help you understand the TSG Builder workflow.

## Files

### Inputs

| File | Description |
|------|-------------|
| `capability-host-input.txt` | Input about Azure AI Foundry agents not seeing connected OpenAI resources |
| `tool-type-exists.txt` | Input about tool type already exists error |

### Expected Outputs

| File | Description |
|------|-------------|
| `capability-host-expected.md` | Reference TSG (ground truth, written by a human) for capability-host-input |
| `sample-output.md` | Output TSG for capability-host-input, written by TSG Builder |

### Test Run Results

JSON files named `test_output_{date}_{time}` show full end-to-end capture of test runs. 

## Usage

1. Start the web UI: `make ui`
2. Open http://localhost:5000
3. Click "Load example" to load `capability-host-input.txt`, or paste content from your own notes
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
