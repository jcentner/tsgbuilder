# TSG Builder Makefile
# Common operations for the TSG Builder project

.PHONY: setup install validate clean help ui lint build

# Default Python interpreter
PYTHON ?= python3

help:
	@echo "TSG Builder - Available Commands"
	@echo "================================="
	@echo ""
	@echo "Quick Start (recommended):"
	@echo "  make setup        - First-time setup (venv + deps + .env)"
	@echo "  make ui           - Start the web UI (http://localhost:5000)"
	@echo "                      Setup, validation, and agent creation are all"
	@echo "                      available in the UI. The setup wizard opens"
	@echo "                      automatically if configuration is needed."
	@echo "                      Add TEST=1 to capture stage outputs to JSON file"
	@echo ""
	@echo "Utility commands:"
	@echo "  make validate     - Validate environment configuration (CLI)"
	@echo "  make install      - Install dependencies only (assumes venv exists)"
	@echo "  make build        - Build standalone executable with PyInstaller"
	@echo "  make clean        - Remove generated files and virtual environment"
	@echo "                      Add DELETE_AGENTS=1 to also delete agents from Azure"
	@echo "  make lint         - Check Python syntax"
	@echo ""
	@echo "Example:"
	@echo "  make setup && make ui    # Recommended: setup then open UI"
	@echo "  make ui TEST=1           # Run with test output capture"
	@echo "  make clean DELETE_AGENTS=1  # Clean and delete agents from Azure"

setup: .venv install env-file
	@echo ""
	@echo "========================================="
	@echo "Setup complete!"
	@echo "========================================="
	@echo ""
	@echo "Next step: Run 'make ui' to start the web interface."
	@echo ""
	@echo "The UI will guide you through:"
	@echo "  1. Configuring your Azure settings"
	@echo "  2. Validating your setup"
	@echo "  3. Creating the agent"
	@echo ""
	@echo "Then open http://localhost:5000 in your browser."

.venv:
	@echo "Creating virtual environment..."
	$(PYTHON) -m venv .venv
	@echo "Virtual environment created at .venv/"

install: requirements.txt
	@echo "Installing dependencies..."
	@if [ -d ".venv" ]; then \
		.venv/bin/pip install -r requirements.txt; \
	else \
		pip install -r requirements.txt; \
	fi
	@echo "Dependencies installed."

env-file:
	@if [ ! -f ".env" ]; then \
		echo "Creating .env from .env-sample..."; \
		cp .env-sample .env; \
		echo ".env created. Please edit it with your Azure configuration."; \
	else \
		echo ".env already exists."; \
	fi

validate:
	@echo "Validating environment..."
	@if [ -d ".venv" ]; then \
		.venv/bin/python validate_setup.py; \
	else \
		$(PYTHON) validate_setup.py; \
	fi

ui:
	@echo "Starting TSG Builder web UI..."
ifdef TEST
	@echo "Test mode enabled - stage outputs will be captured to test_output_*.json"
endif
	@if [ -d ".venv" ]; then \
		TSG_TEST_MODE=$(TEST) PIPELINE_VERBOSE=1 .venv/bin/python web_app.py; \
	else \
		TSG_TEST_MODE=$(TEST) PIPELINE_VERBOSE=1 $(PYTHON) web_app.py; \
	fi

clean:
	@echo "Cleaning up..."
ifdef DELETE_AGENTS
	@echo "Deleting agents from Azure..."
	@if [ -d ".venv" ]; then \
		.venv/bin/python delete_agents.py --yes || true; \
	else \
		$(PYTHON) delete_agents.py --yes || true; \
	fi
endif
	rm -rf .venv
	rm -f .agent_ids.json
	rm -rf __pycache__ *.pyc
	rm -f output.md
	@echo "Cleaned. Run 'make setup' to start fresh."

# Development helpers
lint:
	@if [ -d ".venv" ]; then \
		.venv/bin/python -m py_compile *.py; \
	else \
		$(PYTHON) -m py_compile *.py; \
	fi
	@echo "Syntax check passed."

build: .venv install
	@echo "Building standalone executable..."
	.venv/bin/python build_exe.py --clean
