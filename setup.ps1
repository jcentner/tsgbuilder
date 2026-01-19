#Requires -Version 5.1
<#
.SYNOPSIS
    TSG Builder setup script for Windows (PowerShell 5.1+)

.DESCRIPTION
    Sets up the TSG Builder project:
    - Checks for Python 3.9+ and Azure CLI
    - Offers to install missing dependencies via winget
    - Creates virtual environment and installs requirements
    - Copies .env-sample to .env if needed
    - Optionally launches the web UI

.PARAMETER Help
    Show usage information and exit

.PARAMETER NoInstall
    Skip automatic dependency installation (check only)

.PARAMETER UIOnly
    Skip setup, just launch the web UI (assumes already set up)

.EXAMPLE
    .\setup.ps1
    # Full setup with prompts for missing dependencies

.EXAMPLE
    .\setup.ps1 -NoInstall
    # Check dependencies without installing

.EXAMPLE
    .\setup.ps1 -UIOnly
    # Launch web UI directly
#>

param(
    [switch]$Help,
    [switch]$NoInstall,
    [switch]$UIOnly
)

$ErrorActionPreference = "Stop"

# ============================================================================
# Helper Functions
# ============================================================================

function Write-Header {
    param([string]$Message)
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host $Message -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step {
    param([string]$Message)
    Write-Host ">> $Message" -ForegroundColor Yellow
}

function Write-Ok {
    param([string]$Message)
    Write-Host "   [OK] $Message" -ForegroundColor Green
}

function Write-Fail {
    param([string]$Message)
    Write-Host "   [FAIL] $Message" -ForegroundColor Red
}

function Write-Warn {
    param([string]$Message)
    Write-Host "   [WARN] $Message" -ForegroundColor Yellow
}

function Write-Info {
    param([string]$Message)
    Write-Host "   $Message" -ForegroundColor Gray
}

function Test-Command {
    param([string]$Command)
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        if (Get-Command $Command) { return $true }
    } catch {}
    $ErrorActionPreference = $oldPreference
    return $false
}

function Test-PythonVersion {
    <#
    .SYNOPSIS
        Check if Python 3.9+ is installed and return the command to use
    .OUTPUTS
        Returns the python command (python or python3) or $null if not found
    #>

    # Try 'python' first (common on Windows)
    if (Test-Command "python") {
        try {
            $version = & python --version 2>&1
            if ($version -match "Python (\d+)\.(\d+)") {
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                if ($major -ge 3 -and $minor -ge 9) {
                    return @{ Command = "python"; Version = "$major.$minor" }
                }
            }
        } catch {}
    }

    # Try 'python3' as fallback
    if (Test-Command "python3") {
        try {
            $version = & python3 --version 2>&1
            if ($version -match "Python (\d+)\.(\d+)") {
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                if ($major -ge 3 -and $minor -ge 9) {
                    return @{ Command = "python3"; Version = "$major.$minor" }
                }
            }
        } catch {}
    }

    return $null
}

function Test-AzureCLI {
    if (Test-Command "az") {
        try {
            $version = & az version --output json 2>&1 | ConvertFrom-Json
            return @{ Installed = $true; Version = $version.'azure-cli' }
        } catch {
            return @{ Installed = $true; Version = "unknown" }
        }
    }
    return @{ Installed = $false }
}

function Test-AzureLogin {
    try {
        $account = & az account show --output json 2>&1 | ConvertFrom-Json
        if ($account.user) {
            return @{ LoggedIn = $true; User = $account.user.name; Subscription = $account.name }
        }
    } catch {}
    return @{ LoggedIn = $false }
}

function Test-Winget {
    return Test-Command "winget"
}

function Install-WithWinget {
    param(
        [string]$PackageId,
        [string]$DisplayName
    )

    if (-not (Test-Winget)) {
        Write-Fail "winget is not available. Please install $DisplayName manually."
        return $false
    }

    Write-Step "Installing $DisplayName via winget..."
    try {
        & winget install $PackageId --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "$DisplayName installed successfully"
            Write-Warn "You may need to restart your terminal for PATH changes to take effect"
            return $true
        }
    } catch {}

    Write-Fail "Failed to install $DisplayName"
    return $false
}

function Confirm-Action {
    param([string]$Message)
    $response = Read-Host "$Message (y/N)"
    return ($response -eq 'y' -or $response -eq 'Y')
}

# ============================================================================
# Main Setup Functions
# ============================================================================

function Show-Help {
    Write-Host @"
TSG Builder Setup Script (Windows PowerShell)
==============================================

Usage: .\setup.ps1 [options]

Options:
  -Help         Show this help message and exit
  -NoInstall    Skip automatic dependency installation (check only)
  -UIOnly       Skip setup, just launch the web UI

Examples:
  .\setup.ps1              # Full setup with prompts
  .\setup.ps1 -NoInstall   # Check dependencies only
  .\setup.ps1 -UIOnly      # Launch web UI directly

Requirements:
  - Python 3.9 or higher
  - Azure CLI (az)
  - Azure login (az login)

What this script does:
  1. Checks for Python 3.9+ (offers to install via winget)
  2. Checks for Azure CLI (offers to install via winget)
  3. Checks Azure login status
  4. Creates .venv virtual environment
  5. Installs Python dependencies from requirements.txt
  6. Copies .env-sample to .env (if not exists)
  7. Offers to launch the web UI

"@
}

function Test-Dependencies {
    param([bool]$AllowInstall = $true)

    Write-Header "Checking Dependencies"

    $allOk = $true

    # Check Python
    Write-Step "Checking Python..."
    $python = Test-PythonVersion
    if ($python) {
        Write-Ok "Python $($python.Version) found ($($python.Command))"
        $script:PythonCmd = $python.Command
    } else {
        Write-Fail "Python 3.9+ not found"
        if ($AllowInstall) {
            if (Confirm-Action "Would you like to install Python 3.12 via winget?") {
                if (Install-WithWinget "Python.Python.3.12" "Python 3.12") {
                    Write-Warn "Please restart this script after Python is installed"
                    exit 0
                }
            }
        } else {
            Write-Info "Install Python 3.9+ from https://python.org or run: winget install Python.Python.3.12"
        }
        $allOk = $false
    }

    # Check Azure CLI
    Write-Step "Checking Azure CLI..."
    $az = Test-AzureCLI
    if ($az.Installed) {
        Write-Ok "Azure CLI $($az.Version) found"
    } else {
        Write-Fail "Azure CLI not found"
        if ($AllowInstall) {
            if (Confirm-Action "Would you like to install Azure CLI via winget?") {
                if (Install-WithWinget "Microsoft.AzureCLI" "Azure CLI") {
                    Write-Warn "Please restart this script after Azure CLI is installed"
                    exit 0
                }
            }
        } else {
            Write-Info "Install Azure CLI from https://aka.ms/installazurecliwindows or run: winget install Microsoft.AzureCLI"
        }
        $allOk = $false
    }

    # Check Azure login (only if CLI is installed)
    if ($az.Installed) {
        Write-Step "Checking Azure login status..."
        $login = Test-AzureLogin
        if ($login.LoggedIn) {
            Write-Ok "Logged in as: $($login.User)"
            Write-Info "Subscription: $($login.Subscription)"
        } else {
            Write-Warn "Not logged in to Azure"
            Write-Info "Run 'az login' to authenticate before using the TSG Builder"
        }
    }

    return $allOk
}

function Get-VenvPaths {
    <#
    .SYNOPSIS
        Get the correct paths for a virtual environment, handling both Windows and Unix structures
    #>
    param([string]$VenvPath)

    # Windows-native venv uses Scripts/
    $windowsActivate = Join-Path $VenvPath "Scripts\Activate.ps1"
    $windowsPython = Join-Path $VenvPath "Scripts\python.exe"
    $windowsPip = Join-Path $VenvPath "Scripts\pip.exe"

    # Unix/WSL venv uses bin/
    $unixActivate = Join-Path $VenvPath "bin\Activate.ps1"
    $unixPython = Join-Path $VenvPath "bin\python"
    $unixPip = Join-Path $VenvPath "bin\pip"

    if (Test-Path $windowsActivate) {
        return @{
            Activate = $windowsActivate
            Python = $windowsPython
            Pip = $windowsPip
            Type = "Windows"
        }
    } elseif (Test-Path $unixActivate) {
        return @{
            Activate = $unixActivate
            Python = $unixPython
            Pip = $unixPip
            Type = "Unix"
        }
    } elseif (Test-Path (Join-Path $VenvPath "bin\python")) {
        # Unix venv without PowerShell activation script
        return @{
            Activate = $null
            Python = $unixPython
            Pip = $unixPip
            Type = "Unix-NoPwsh"
        }
    }

    return $null
}

function Setup-VirtualEnv {
    Write-Header "Setting Up Virtual Environment"

    $venvPath = Join-Path $PSScriptRoot ".venv"

    # Check if venv exists and determine its type
    $existingVenv = $null
    if (Test-Path $venvPath) {
        $existingVenv = Get-VenvPaths -VenvPath $venvPath
    }

    # If venv exists but is Unix-style (from WSL/Linux), offer to recreate
    if ($existingVenv -and $existingVenv.Type -like "Unix*") {
        Write-Warn "Existing .venv was created on Unix/WSL (has bin/ instead of Scripts/)"
        Write-Info "This can happen if you ran 'make setup' in WSL"

        if (Confirm-Action "Would you like to recreate the virtual environment for Windows?") {
            Write-Step "Removing old virtual environment..."
            Remove-Item -Recurse -Force $venvPath
            $existingVenv = $null
        } else {
            # Try to use the Unix venv anyway
            Write-Warn "Attempting to use Unix-style venv (may have issues)"
        }
    }

    # Create venv if it doesn't exist
    if (-not (Test-Path $venvPath)) {
        Write-Step "Creating virtual environment..."
        & $script:PythonCmd -m venv $venvPath
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "Failed to create virtual environment"
            return $false
        }
        Write-Ok "Virtual environment created at .venv/"
    } else {
        Write-Ok "Virtual environment already exists"
    }

    # Get venv paths
    $venvPaths = Get-VenvPaths -VenvPath $venvPath
    if (-not $venvPaths) {
        Write-Fail "Could not find virtual environment structure"
        Write-Info "Try deleting .venv and running setup again"
        return $false
    }

    # Activate venv if possible
    Write-Step "Activating virtual environment..."
    if ($venvPaths.Activate -and (Test-Path $venvPaths.Activate)) {
        . $venvPaths.Activate
        Write-Ok "Virtual environment activated"
    } else {
        Write-Warn "No PowerShell activation script found, using direct pip path"
    }

    # Install requirements using the venv's pip
    Write-Step "Installing Python dependencies..."
    $requirementsPath = Join-Path $PSScriptRoot "requirements.txt"
    if (Test-Path $requirementsPath) {
        if (Test-Path $venvPaths.Pip) {
            & $venvPaths.Pip install -r $requirementsPath
        } else {
            & pip install -r $requirementsPath
        }
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "Failed to install dependencies"
            return $false
        }
        Write-Ok "Dependencies installed"
    } else {
        Write-Fail "requirements.txt not found"
        return $false
    }

    return $true
}

function Setup-EnvFile {
    Write-Header "Setting Up Environment File"

    $envPath = Join-Path $PSScriptRoot ".env"
    $envSamplePath = Join-Path $PSScriptRoot ".env-sample"

    if (Test-Path $envPath) {
        Write-Ok ".env file already exists"
    } elseif (Test-Path $envSamplePath) {
        Write-Step "Creating .env from .env-sample..."
        Copy-Item $envSamplePath $envPath
        Write-Ok ".env file created"
        Write-Warn "Please edit .env with your Azure configuration"
    } else {
        Write-Fail ".env-sample not found"
        return $false
    }

    return $true
}

function Start-WebUI {
    Write-Header "Starting Web UI"

    $venvPath = Join-Path $PSScriptRoot ".venv"
    $webAppPath = Join-Path $PSScriptRoot "web_app.py"

    if (-not (Test-Path $webAppPath)) {
        Write-Fail "web_app.py not found"
        return
    }

    # Get venv paths (handles both Windows and Unix structures)
    $venvPaths = Get-VenvPaths -VenvPath $venvPath
    $pythonExe = $null

    if ($venvPaths -and (Test-Path $venvPaths.Python)) {
        $pythonExe = $venvPaths.Python
    }

    # Use venv python if available, otherwise system python
    if ($pythonExe) {
        Write-Step "Starting Flask server..."
        Write-Host ""
        Write-Host "   Web UI will be available at: http://localhost:5000" -ForegroundColor Green
        Write-Host "   Press Ctrl+C to stop the server" -ForegroundColor Gray
        Write-Host ""
        & $pythonExe $webAppPath
    } elseif ($script:PythonCmd) {
        Write-Warn "Using system Python (virtual environment not found)"
        & $script:PythonCmd $webAppPath
    } else {
        Write-Fail "Python not available"
    }
}

# ============================================================================
# Main Entry Point
# ============================================================================

function Main {
    # Show help if requested
    if ($Help) {
        Show-Help
        exit 0
    }

    Write-Header "TSG Builder Setup (Windows)"
    Write-Host "This script will set up the TSG Builder project."
    Write-Host ""

    # UI-only mode: skip setup, just launch
    if ($UIOnly) {
        Start-WebUI
        exit 0
    }

    # Check dependencies
    $depsOk = Test-Dependencies -AllowInstall (-not $NoInstall)

    if (-not $depsOk) {
        Write-Host ""
        Write-Fail "Please install missing dependencies and run this script again."
        exit 1
    }

    # Set up virtual environment
    if (-not (Setup-VirtualEnv)) {
        Write-Fail "Virtual environment setup failed"
        exit 1
    }

    # Set up .env file
    if (-not (Setup-EnvFile)) {
        Write-Fail "Environment file setup failed"
        exit 1
    }

    # Success!
    Write-Header "Setup Complete!"
    Write-Host "Next steps:" -ForegroundColor Green
    Write-Host "  1. Edit .env with your Azure configuration" -ForegroundColor White
    Write-Host "  2. Run 'az login' if not already logged in" -ForegroundColor White
    Write-Host "  3. Start the web UI" -ForegroundColor White
    Write-Host ""

    # Offer to launch UI
    if (Confirm-Action "Would you like to start the web UI now?") {
        Start-WebUI
    } else {
        Write-Host ""
        Write-Host "To start the web UI later, run:" -ForegroundColor Gray
        Write-Host "  .\setup.ps1 -UIOnly" -ForegroundColor White
        Write-Host "  or" -ForegroundColor Gray
        Write-Host "  .\.venv\Scripts\python.exe web_app.py" -ForegroundColor White
    }
}

# Run main function
Main
