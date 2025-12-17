# TSG Builder Makefile
# Common operations for the TSG Builder project

.PHONY: setup install validate create-agent run run-example clean help

# Default Python interpreter
PYTHON ?= python3

# Default notes file
NOTES_FILE ?= input.txt

help:
	@echo "TSG Builder - Available Commands"
	@echo "================================="
	@echo ""
	@echo "Setup commands:"
	@echo "  make setup        - Create virtual environment and install dependencies"
	@echo "  make install      - Install dependencies only (assumes venv exists)"
	@echo "  make validate     - Validate environment configuration"
	@echo ""
	@echo "Agent commands:"
	@echo "  make create-agent - Create the Azure AI Foundry agent"
	@echo "  make run          - Run inference with default notes file (input.txt)"
	@echo "  make run-example  - Run inference with example input"
	@echo ""
	@echo "Utility commands:"
	@echo "  make clean        - Remove generated files and virtual environment"
	@echo ""
	@echo "Variables:"
	@echo "  NOTES_FILE=<path> - Specify notes file for 'make run'"
	@echo "  PYTHON=<python>   - Specify Python interpreter (default: python3)"
	@echo ""
	@echo "Examples:"
	@echo "  make setup                           # First-time setup"
	@echo "  make run NOTES_FILE=my-notes.txt     # Run with custom notes"
	@echo "  make run-example                     # Run with input-example.txt"
	@echo "  make run-save NOTES_FILE=my-notes.txt # Run and save output to output.md"

setup: .venv install env-file
	@echo ""
	@echo "Setup complete! Next steps:"
	@echo "  1. Edit .env with your Azure configuration"
	@echo "  2. Run 'make validate' to verify setup"
	@echo "  3. Run 'make create-agent' to create the agent"
	@echo "  4. Run 'make run' to generate a TSG"

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

create-agent:
	@echo "Creating Azure AI Foundry agent..."
	@if [ -d ".venv" ]; then \
		.venv/bin/python create_agent.py; \
	else \
		$(PYTHON) create_agent.py; \
	fi

run:
	@echo "Running TSG agent with $(NOTES_FILE)..."
	@if [ ! -f "$(NOTES_FILE)" ]; then \
		echo "ERROR: Notes file not found: $(NOTES_FILE)"; \
		exit 1; \
	fi
	@if [ -d ".venv" ]; then \
		.venv/bin/python ask_agent.py --notes-file $(NOTES_FILE); \
	else \
		$(PYTHON) ask_agent.py --notes-file $(NOTES_FILE); \
	fi

run-example:
	@$(MAKE) run NOTES_FILE=input-example.txt

run-save:
	@echo "Running TSG agent and saving output..."
	@if [ ! -f "$(NOTES_FILE)" ]; then \
		echo "ERROR: Notes file not found: $(NOTES_FILE)"; \
		exit 1; \
	fi
	@if [ -d ".venv" ]; then \
		.venv/bin/python ask_agent.py --notes-file $(NOTES_FILE) --output output.md; \
	else \
		$(PYTHON) ask_agent.py --notes-file $(NOTES_FILE) --output output.md; \
	fi

clean:
	@echo "Cleaning up..."
	rm -rf .venv
	rm -f .agent_id .agent_ref
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
