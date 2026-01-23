#!/usr/bin/env bash
# ============================================================================
# TSG Builder Setup Script for macOS and Linux
# ============================================================================
#
# Usage: ./setup.sh [options]
#
# Options:
#   --help        Show usage information and exit
#   --no-install  Skip automatic dependency installation (check only)
#   --ui-only     Skip setup, just launch the web UI
#
# Supported platforms:
#   - macOS (uses Homebrew)
#   - Debian/Ubuntu (uses apt)
#   - RHEL/Fedora (uses dnf)
#
# ============================================================================

set -e

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

# Global variables
PYTHON_CMD=""
NO_INSTALL=false
UI_ONLY=false

# ============================================================================
# Helper Functions
# ============================================================================

print_header() {
    echo ""
    echo -e "${CYAN}============================================================${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}============================================================${NC}"
    echo ""
}

print_step() {
    echo -e "${YELLOW}>> $1${NC}"
}

print_ok() {
    echo -e "   ${GREEN}[OK]${NC} $1"
}

print_fail() {
    echo -e "   ${RED}[FAIL]${NC} $1"
}

print_warn() {
    echo -e "   ${YELLOW}[WARN]${NC} $1"
}

print_info() {
    echo -e "   ${GRAY}$1${NC}"
}

confirm_action() {
    local prompt="$1"
    local response
    read -r -p "$prompt (y/N): " response
    [[ "$response" =~ ^[Yy]$ ]]
}

command_exists() {
    command -v "$1" &> /dev/null
}

# ============================================================================
# OS Detection
# ============================================================================

detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ -f /etc/debian_version ]]; then
        echo "debian"
    elif [[ -f /etc/redhat-release ]] || [[ -f /etc/fedora-release ]]; then
        echo "rhel"
    else
        echo "unknown"
    fi
}

# ============================================================================
# Dependency Checks
# ============================================================================

check_python_version() {
    # Try python3 first (preferred on Unix)
    if command_exists python3; then
        local version
        version=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
        local major minor
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [[ $major -ge 3 ]] && [[ $minor -ge 9 ]]; then
            PYTHON_CMD="python3"
            echo "$version"
            return 0
        fi
    fi

    # Try python as fallback
    if command_exists python; then
        local version
        version=$(python --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
        local major minor
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [[ $major -ge 3 ]] && [[ $minor -ge 9 ]]; then
            PYTHON_CMD="python"
            echo "$version"
            return 0
        fi
    fi

    return 1
}

check_azure_cli() {
    if command_exists az; then
        local version
        version=$(az version --query '"azure-cli"' -o tsv 2>/dev/null || echo "unknown")
        echo "$version"
        return 0
    fi
    return 1
}

check_azure_login() {
    if az account show &>/dev/null; then
        local user subscription
        user=$(az account show --query "user.name" -o tsv 2>/dev/null)
        subscription=$(az account show --query "name" -o tsv 2>/dev/null)
        echo "$user|$subscription"
        return 0
    fi
    return 1
}

# ============================================================================
# Installation Functions
# ============================================================================

install_python_macos() {
    if ! command_exists brew; then
        print_fail "Homebrew not found. Please install it first:"
        print_info "/bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        return 1
    fi

    print_step "Installing Python 3.12 via Homebrew..."
    brew install python@3.12
    if [[ $? -eq 0 ]]; then
        print_ok "Python 3.12 installed"
        print_warn "You may need to restart your terminal"
        return 0
    fi
    return 1
}

install_python_debian() {
    print_step "Installing Python 3 via apt..."
    sudo apt update
    sudo apt install -y python3 python3-venv python3-pip
    if [[ $? -eq 0 ]]; then
        print_ok "Python 3 installed"
        return 0
    fi
    return 1
}

install_python_rhel() {
    print_step "Installing Python 3 via dnf..."
    sudo dnf install -y python3 python3-pip
    if [[ $? -eq 0 ]]; then
        print_ok "Python 3 installed"
        return 0
    fi
    return 1
}

install_azure_cli_macos() {
    if ! command_exists brew; then
        print_fail "Homebrew not found"
        return 1
    fi

    print_step "Installing Azure CLI via Homebrew..."
    brew install azure-cli
    if [[ $? -eq 0 ]]; then
        print_ok "Azure CLI installed"
        return 0
    fi
    return 1
}

install_azure_cli_debian() {
    print_step "Installing Azure CLI..."

    # Install prerequisites
    sudo apt update
    sudo apt install -y ca-certificates curl apt-transport-https lsb-release gnupg

    # Download and install Microsoft signing key
    sudo mkdir -p /etc/apt/keyrings
    curl -sLS https://packages.microsoft.com/keys/microsoft.asc | \
        gpg --dearmor | \
        sudo tee /etc/apt/keyrings/microsoft.gpg > /dev/null
    sudo chmod go+r /etc/apt/keyrings/microsoft.gpg

    # Add Azure CLI repository
    local az_dist
    az_dist=$(lsb_release -cs)
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/microsoft.gpg] https://packages.microsoft.com/repos/azure-cli/ $az_dist main" | \
        sudo tee /etc/apt/sources.list.d/azure-cli.list

    # Install Azure CLI
    sudo apt update
    sudo apt install -y azure-cli

    if [[ $? -eq 0 ]]; then
        print_ok "Azure CLI installed"
        return 0
    fi
    return 1
}

install_azure_cli_rhel() {
    print_step "Installing Azure CLI..."

    # Import Microsoft repository key
    sudo rpm --import https://packages.microsoft.com/keys/microsoft.asc

    # Add Azure CLI repository
    sudo dnf install -y https://packages.microsoft.com/config/rhel/9.0/packages-microsoft-prod.rpm 2>/dev/null || \
    sudo dnf install -y https://packages.microsoft.com/config/rhel/8/packages-microsoft-prod.rpm 2>/dev/null

    # Install Azure CLI
    sudo dnf install -y azure-cli

    if [[ $? -eq 0 ]]; then
        print_ok "Azure CLI installed"
        return 0
    fi
    return 1
}

# ============================================================================
# Main Setup Functions
# ============================================================================

show_help() {
    cat << 'EOF'
TSG Builder Setup Script (macOS/Linux)
==============================================

Usage: ./setup.sh [options]

Options:
  --help        Show this help message and exit
  --no-install  Skip automatic dependency installation (check only)
  --ui-only     Skip setup, just launch the web UI

Examples:
  ./setup.sh              # Full setup with prompts
  ./setup.sh --no-install # Check dependencies only
  ./setup.sh --ui-only    # Launch web UI directly

Supported platforms:
  - macOS (uses Homebrew for package management)
  - Debian/Ubuntu (uses apt)
  - RHEL/Fedora (uses dnf)

Requirements:
  - Python 3.9 or higher
  - Azure CLI (az)
  - Azure login (az login)

What this script does:
  1. Detects your operating system
  2. Checks for Python 3.9+ (offers to install via package manager)
  3. Checks for Azure CLI (offers to install via package manager)
  4. Checks Azure login status
  5. Creates .venv virtual environment
  6. Installs Python dependencies from requirements.txt
  7. Copies .env-sample to .env (if not exists)
  8. Offers to launch the web UI

EOF
}

check_dependencies() {
    print_header "Checking Dependencies"

    local os_type
    os_type=$(detect_os)
    print_step "Detected OS: $os_type"
    echo ""

    local deps_ok=true

    # Check Python
    print_step "Checking Python..."
    local py_version
    if py_version=$(check_python_version); then
        print_ok "Python $py_version found ($PYTHON_CMD)"
    else
        print_fail "Python 3.9+ not found"
        deps_ok=false

        if [[ "$NO_INSTALL" == "false" ]]; then
            if confirm_action "Would you like to install Python?"; then
                case "$os_type" in
                    macos)  install_python_macos ;;
                    debian) install_python_debian ;;
                    rhel)   install_python_rhel ;;
                    *)
                        print_fail "Unsupported OS for automatic installation"
                        print_info "Please install Python 3.9+ manually"
                        ;;
                esac
                # Re-check after installation
                if py_version=$(check_python_version); then
                    print_ok "Python $py_version now available"
                    deps_ok=true
                else
                    print_warn "Please restart this script after Python installation"
                fi
            fi
        else
            case "$os_type" in
                macos)  print_info "Run: brew install python@3.12" ;;
                debian) print_info "Run: sudo apt install python3 python3-venv python3-pip" ;;
                rhel)   print_info "Run: sudo dnf install python3 python3-pip" ;;
                *)      print_info "Install Python 3.9+ from https://python.org" ;;
            esac
        fi
    fi

    # Check Azure CLI
    print_step "Checking Azure CLI..."
    local az_version
    if az_version=$(check_azure_cli); then
        print_ok "Azure CLI $az_version found"

        # Check Azure login
        print_step "Checking Azure login status..."
        local login_info
        if login_info=$(check_azure_login); then
            local user subscription
            user=$(echo "$login_info" | cut -d'|' -f1)
            subscription=$(echo "$login_info" | cut -d'|' -f2)
            print_ok "Logged in as: $user"
            print_info "Subscription: $subscription"
        else
            print_warn "Not logged in to Azure"
            print_info "Run 'az login' to authenticate before using the TSG Builder"
        fi
    else
        print_fail "Azure CLI not found"
        deps_ok=false

        if [[ "$NO_INSTALL" == "false" ]]; then
            if confirm_action "Would you like to install Azure CLI?"; then
                case "$os_type" in
                    macos)  install_azure_cli_macos ;;
                    debian) install_azure_cli_debian ;;
                    rhel)   install_azure_cli_rhel ;;
                    *)
                        print_fail "Unsupported OS for automatic installation"
                        print_info "See: https://docs.microsoft.com/cli/azure/install-azure-cli"
                        ;;
                esac
                # Re-check after installation
                if az_version=$(check_azure_cli); then
                    print_ok "Azure CLI $az_version now available"
                    deps_ok=true
                else
                    print_warn "Please restart this script after Azure CLI installation"
                fi
            fi
        else
            case "$os_type" in
                macos)  print_info "Run: brew install azure-cli" ;;
                debian) print_info "See: https://docs.microsoft.com/cli/azure/install-azure-cli-linux" ;;
                rhel)   print_info "See: https://docs.microsoft.com/cli/azure/install-azure-cli-linux" ;;
                *)      print_info "See: https://docs.microsoft.com/cli/azure/install-azure-cli" ;;
            esac
        fi
    fi

    if [[ "$deps_ok" == "true" ]]; then
        return 0
    else
        return 1
    fi
}

setup_venv() {
    print_header "Setting Up Virtual Environment"

    local venv_path="$SCRIPT_DIR/.venv"

    # Check if venv exists and determine its type
    local venv_type="none"
    if [[ -d "$venv_path" ]]; then
        if [[ -f "$venv_path/bin/activate" ]]; then
            venv_type="unix"
        elif [[ -f "$venv_path/Scripts/activate" ]]; then
            venv_type="windows"
        fi
    fi

    # If Windows-style venv exists, offer to recreate for Unix
    if [[ "$venv_type" == "windows" ]]; then
        print_warn "Existing .venv was created on Windows (has Scripts/ instead of bin/)"
        print_info "This can happen if you ran setup in Windows PowerShell/CMD"

        if confirm_action "Would you like to recreate the virtual environment for Unix?"; then
            print_step "Removing old virtual environment..."
            rm -rf "$venv_path"
            venv_type="none"
        else
            print_fail "Cannot use Windows-style venv on Unix"
            return 1
        fi
    fi

    # Create venv if it doesn't exist or was removed
    if [[ ! -d "$venv_path" ]]; then
        print_step "Creating virtual environment..."
        $PYTHON_CMD -m venv "$venv_path"
        if [[ $? -ne 0 ]]; then
            print_fail "Failed to create virtual environment"
            return 1
        fi
        print_ok "Virtual environment created at .venv/"
    else
        print_ok "Virtual environment already exists"
    fi

    # Activate venv
    print_step "Activating virtual environment..."
    if [[ -f "$venv_path/bin/activate" ]]; then
        source "$venv_path/bin/activate"
        print_ok "Virtual environment activated"
    else
        print_fail "Could not find activation script"
        return 1
    fi

    # Install requirements
    print_step "Installing Python dependencies..."
    if [[ -f "$SCRIPT_DIR/requirements.txt" ]]; then
        pip install -r "$SCRIPT_DIR/requirements.txt"
        if [[ $? -ne 0 ]]; then
            print_fail "Failed to install dependencies"
            return 1
        fi
        print_ok "Dependencies installed"
    else
        print_fail "requirements.txt not found"
        return 1
    fi

    return 0
}

setup_env() {
    print_header "Setting Up Environment File"

    local env_path="$SCRIPT_DIR/.env"
    local env_sample_path="$SCRIPT_DIR/.env-sample"

    if [[ -f "$env_path" ]]; then
        print_ok ".env file already exists"
    elif [[ -f "$env_sample_path" ]]; then
        print_step "Creating .env from .env-sample..."
        cp "$env_sample_path" "$env_path"
        print_ok ".env file created"
        print_warn "Please edit .env with your Azure configuration"
    else
        print_fail ".env-sample not found"
        return 1
    fi

    return 0
}

launch_ui() {
    print_header "Starting Web UI"

    local venv_python="$SCRIPT_DIR/.venv/bin/python"
    local web_app="$SCRIPT_DIR/web_app.py"

    if [[ ! -f "$web_app" ]]; then
        print_fail "web_app.py not found"
        return 1
    fi

    if [[ -f "$venv_python" ]]; then
        print_step "Starting Flask server..."
        echo ""
        echo -e "   ${GREEN}Web UI will be available at: http://localhost:5000${NC}"
        echo -e "   ${GRAY}Press Ctrl+C to stop the server${NC}"
        echo ""
        "$venv_python" "$web_app"
    elif [[ -n "$PYTHON_CMD" ]]; then
        print_warn "Using system Python (virtual environment not found)"
        $PYTHON_CMD "$web_app"
    else
        print_fail "Python not available"
        return 1
    fi
}

# ============================================================================
# Main Entry Point
# ============================================================================

main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --help|-h)
                show_help
                exit 0
                ;;
            --no-install)
                NO_INSTALL=true
                shift
                ;;
            --ui-only)
                UI_ONLY=true
                shift
                ;;
            *)
                echo "Unknown option: $1"
                echo "Run './setup.sh --help' for usage"
                exit 1
                ;;
        esac
    done

    print_header "TSG Builder Setup (macOS/Linux)"
    echo "This script will set up the TSG Builder project."
    echo ""

    # UI-only mode: skip setup, just launch
    if [[ "$UI_ONLY" == "true" ]]; then
        # Still need to check for Python
        check_python_version > /dev/null 2>&1
        launch_ui
        exit $?
    fi

    # Check dependencies
    if ! check_dependencies; then
        echo ""
        print_fail "Please install missing dependencies and run this script again."
        exit 1
    fi

    # Set up virtual environment
    if ! setup_venv; then
        print_fail "Virtual environment setup failed"
        exit 1
    fi

    # Set up .env file
    if ! setup_env; then
        print_fail "Environment file setup failed"
        exit 1
    fi

    # Success!
    print_header "Setup Complete!"
    echo -e "${GREEN}Next steps:${NC}"
    echo "  1. Edit .env with your Azure configuration"
    echo "  2. Run 'az login' if not already logged in"
    echo "  3. Start the web UI"
    echo ""

    # Offer to launch UI
    if confirm_action "Would you like to start the web UI now?"; then
        launch_ui
    else
        echo ""
        echo -e "${GRAY}To start the web UI later, run:${NC}"
        echo "  ./setup.sh --ui-only"
        echo "  or"
        echo "  ./.venv/bin/python web_app.py"
    fi
}

# Run main function
main "$@"
