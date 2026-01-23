@echo off
setlocal EnableDelayedExpansion

REM ============================================================================
REM TSG Builder Setup Script for Windows (CMD/Batch)
REM ============================================================================
REM
REM Usage: setup.bat [/help] [/no-install] [/ui-only]
REM
REM Options:
REM   /help        Show usage information and exit
REM   /no-install  Skip automatic dependency installation (check only)
REM   /ui-only     Skip setup, just launch the web UI
REM
REM ============================================================================

REM Parse command line arguments
set "SHOW_HELP=0"
set "NO_INSTALL=0"
set "UI_ONLY=0"

:parse_args
if "%~1"=="" goto :end_parse_args
if /i "%~1"=="/help" set "SHOW_HELP=1" & shift & goto :parse_args
if /i "%~1"=="--help" set "SHOW_HELP=1" & shift & goto :parse_args
if /i "%~1"=="-h" set "SHOW_HELP=1" & shift & goto :parse_args
if /i "%~1"=="/no-install" set "NO_INSTALL=1" & shift & goto :parse_args
if /i "%~1"=="--no-install" set "NO_INSTALL=1" & shift & goto :parse_args
if /i "%~1"=="/ui-only" set "UI_ONLY=1" & shift & goto :parse_args
if /i "%~1"=="--ui-only" set "UI_ONLY=1" & shift & goto :parse_args
shift
goto :parse_args
:end_parse_args

REM Show help if requested
if "%SHOW_HELP%"=="1" goto :show_help

REM Change to script directory
cd /d "%~dp0"

echo.
echo ============================================================
echo TSG Builder Setup (Windows CMD)
echo ============================================================
echo.

REM UI-only mode: skip setup, just launch
if "%UI_ONLY%"=="1" goto :launch_ui

REM Check dependencies
call :check_dependencies
if errorlevel 1 (
    echo.
    echo [FAIL] Please install missing dependencies and run this script again.
    exit /b 1
)

REM Set up virtual environment
call :setup_venv
if errorlevel 1 (
    echo [FAIL] Virtual environment setup failed.
    exit /b 1
)

REM Set up .env file
call :setup_env
if errorlevel 1 (
    echo [FAIL] Environment file setup failed.
    exit /b 1
)

REM Success
echo.
echo ============================================================
echo Setup Complete!
echo ============================================================
echo.
echo Next steps:
echo   1. Edit .env with your Azure configuration
echo   2. Run 'az login' if not already logged in
echo   3. Start the web UI
echo.

set /p "LAUNCH_UI=Would you like to start the web UI now? (y/N): "
if /i "%LAUNCH_UI%"=="y" goto :launch_ui

echo.
echo To start the web UI later, run:
echo   setup.bat /ui-only
echo   or
echo   .venv\Scripts\python.exe web_app.py
echo.
exit /b 0

REM ============================================================================
REM Functions
REM ============================================================================

:show_help
echo TSG Builder Setup Script (Windows CMD)
echo ==============================================
echo.
echo Usage: setup.bat [options]
echo.
echo Options:
echo   /help        Show this help message and exit
echo   /no-install  Skip automatic dependency installation (check only)
echo   /ui-only     Skip setup, just launch the web UI
echo.
echo Examples:
echo   setup.bat              # Full setup with prompts
echo   setup.bat /no-install  # Check dependencies only
echo   setup.bat /ui-only     # Launch web UI directly
echo.
echo Requirements:
echo   - Python 3.9 or higher
echo   - Azure CLI (az)
echo   - Azure login (az login)
echo.
echo What this script does:
echo   1. Checks for Python 3.9+ (offers to install via winget)
echo   2. Checks for Azure CLI (offers to install via winget)
echo   3. Checks Azure login status
echo   4. Creates .venv virtual environment
echo   5. Installs Python dependencies from requirements.txt
echo   6. Copies .env-sample to .env (if not exists)
echo   7. Offers to launch the web UI
echo.
exit /b 0

:check_dependencies
echo.
echo ============================================================
echo Checking Dependencies
echo ============================================================
echo.

set "DEPS_OK=1"
set "PYTHON_CMD="

REM Check Python
echo ^>^> Checking Python...
where python >nul 2>&1
if %errorlevel%==0 (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
    for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
        set "PY_MAJOR=%%a"
        set "PY_MINOR=%%b"
    )
    if !PY_MAJOR! GEQ 3 (
        if !PY_MINOR! GEQ 9 (
            echo    [OK] Python !PY_VER! found
            set "PYTHON_CMD=python"
            goto :check_az
        )
    )
)

REM Try python3
where python3 >nul 2>&1
if %errorlevel%==0 (
    for /f "tokens=2" %%v in ('python3 --version 2^>^&1') do set "PY_VER=%%v"
    for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
        set "PY_MAJOR=%%a"
        set "PY_MINOR=%%b"
    )
    if !PY_MAJOR! GEQ 3 (
        if !PY_MINOR! GEQ 9 (
            echo    [OK] Python !PY_VER! found
            set "PYTHON_CMD=python3"
            goto :check_az
        )
    )
)

REM Python not found or too old
echo    [FAIL] Python 3.9+ not found
set "DEPS_OK=0"

if "%NO_INSTALL%"=="1" (
    echo    Install Python 3.9+ from https://python.org
    echo    or run: winget install Python.Python.3.12
    goto :check_az
)

set /p "INSTALL_PYTHON=Would you like to install Python 3.12 via winget? (y/N): "
if /i not "%INSTALL_PYTHON%"=="y" goto :check_az

echo ^>^> Installing Python 3.12 via winget...
powershell -ExecutionPolicy Bypass -Command "winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements"
if %errorlevel%==0 (
    echo    [OK] Python 3.12 installed
    echo    [WARN] Please restart this script after installation completes
    exit /b 0
) else (
    echo    [FAIL] Failed to install Python
)

:check_az
REM Check Azure CLI
echo ^>^> Checking Azure CLI...
where az >nul 2>&1
if %errorlevel%==0 (
    echo    [OK] Azure CLI found
    goto :check_az_login
)

echo    [FAIL] Azure CLI not found
set "DEPS_OK=0"

if "%NO_INSTALL%"=="1" (
    echo    Install Azure CLI from https://aka.ms/installazurecliwindows
    echo    or run: winget install Microsoft.AzureCLI
    goto :deps_done
)

set /p "INSTALL_AZ=Would you like to install Azure CLI via winget? (y/N): "
if /i not "%INSTALL_AZ%"=="y" goto :deps_done

echo ^>^> Installing Azure CLI via winget...
powershell -ExecutionPolicy Bypass -Command "winget install Microsoft.AzureCLI --accept-package-agreements --accept-source-agreements"
if %errorlevel%==0 (
    echo    [OK] Azure CLI installed
    echo    [WARN] Please restart this script after installation completes
    exit /b 0
) else (
    echo    [FAIL] Failed to install Azure CLI
)
goto :deps_done

:check_az_login
REM Check Azure login status
echo ^>^> Checking Azure login status...
az account show >nul 2>&1
if %errorlevel%==0 (
    for /f "tokens=*" %%u in ('az account show --query "user.name" -o tsv 2^>nul') do set "AZ_USER=%%u"
    echo    [OK] Logged in as: !AZ_USER!
) else (
    echo    [WARN] Not logged in to Azure
    echo    Run 'az login' to authenticate before using the TSG Builder
)

:deps_done
if "%DEPS_OK%"=="0" exit /b 1
exit /b 0

:setup_venv
echo.
echo ============================================================
echo Setting Up Virtual Environment
echo ============================================================
echo.

REM Determine venv structure (Windows uses Scripts, Unix/WSL uses bin)
set "VENV_TYPE=none"
set "VENV_ACTIVATE="
set "VENV_PIP="

if exist ".venv\Scripts\activate.bat" (
    set "VENV_TYPE=windows"
    set "VENV_ACTIVATE=.venv\Scripts\activate.bat"
    set "VENV_PIP=.venv\Scripts\pip.exe"
) else if exist ".venv\bin\activate" (
    set "VENV_TYPE=unix"
    set "VENV_PIP=.venv\bin\pip"
)

REM If Unix venv exists, offer to recreate for Windows
if "%VENV_TYPE%"=="unix" (
    echo    [WARN] Existing .venv was created on Unix/WSL (has bin/ instead of Scripts/)
    echo    This can happen if you ran 'make setup' in WSL
    set /p "RECREATE_VENV=Would you like to recreate the virtual environment for Windows? (y/N): "
    if /i "!RECREATE_VENV!"=="y" (
        echo ^>^> Removing old virtual environment...
        rmdir /s /q .venv
        set "VENV_TYPE=none"
    )
)

REM Create venv if it doesn't exist or was removed
if not exist ".venv" (
    echo ^>^> Creating virtual environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo    [FAIL] Failed to create virtual environment
        exit /b 1
    )
    echo    [OK] Virtual environment created at .venv\
    set "VENV_TYPE=windows"
    set "VENV_ACTIVATE=.venv\Scripts\activate.bat"
    set "VENV_PIP=.venv\Scripts\pip.exe"
) else (
    echo    [OK] Virtual environment already exists
)

REM Activate venv if Windows-style
echo ^>^> Activating virtual environment...
if "%VENV_TYPE%"=="windows" (
    call .venv\Scripts\activate.bat
    if errorlevel 1 (
        echo    [FAIL] Could not activate virtual environment
        exit /b 1
    )
    echo    [OK] Virtual environment activated
) else (
    echo    [WARN] Unix-style venv detected, using direct pip path
)

REM Install requirements
echo ^>^> Installing Python dependencies...
if exist "requirements.txt" (
    if exist "%VENV_PIP%" (
        "%VENV_PIP%" install -r requirements.txt
    ) else (
        pip install -r requirements.txt
    )
    if errorlevel 1 (
        echo    [FAIL] Failed to install dependencies
        exit /b 1
    )
    echo    [OK] Dependencies installed
) else (
    echo    [FAIL] requirements.txt not found
    exit /b 1
)

exit /b 0

:setup_env
echo.
echo ============================================================
echo Setting Up Environment File
echo ============================================================
echo.

if exist ".env" (
    echo    [OK] .env file already exists
) else if exist ".env-sample" (
    echo ^>^> Creating .env from .env-sample...
    copy .env-sample .env >nul
    echo    [OK] .env file created
    echo    [WARN] Please edit .env with your Azure configuration
) else (
    echo    [FAIL] .env-sample not found
    exit /b 1
)

exit /b 0

:launch_ui
echo.
echo ============================================================
echo Starting Web UI
echo ============================================================
echo.

if not exist "web_app.py" (
    echo [FAIL] web_app.py not found
    exit /b 1
)

REM Check for Windows-style venv first, then Unix-style
set "VENV_PYTHON="
if exist ".venv\Scripts\python.exe" (
    set "VENV_PYTHON=.venv\Scripts\python.exe"
) else if exist ".venv\bin\python" (
    set "VENV_PYTHON=.venv\bin\python"
)

if defined VENV_PYTHON (
    echo ^>^> Starting Flask server...
    echo.
    echo    Web UI will be available at: http://localhost:5000
    echo    Press Ctrl+C to stop the server
    echo.
    "%VENV_PYTHON%" web_app.py
) else if defined PYTHON_CMD (
    echo [WARN] Using system Python (virtual environment not found)
    %PYTHON_CMD% web_app.py
) else (
    echo [FAIL] Python not available. Run setup first.
    exit /b 1
)

exit /b 0
