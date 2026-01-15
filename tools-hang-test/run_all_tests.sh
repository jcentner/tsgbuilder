#!/bin/bash
# Quick test runner for different tool configurations

cd "$(dirname "$0")"

echo "=============================================="
echo "Test 1: MCP Only"
echo "=============================================="
python3 test_tools.py --mcp-only --timeout 120

echo ""
echo "=============================================="
echo "Test 2: Bing Only"
echo "=============================================="
python3 test_tools.py --bing-only --timeout 120

echo ""
echo "=============================================="
echo "Test 3: Both Tools"
echo "=============================================="
python3 test_tools.py --both --timeout 300
