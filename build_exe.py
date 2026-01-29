#!/usr/bin/env python3
"""
build_exe.py — Build TSG Builder as a standalone executable using PyInstaller.

Usage:
    python build_exe.py          # Build for current platform
    python build_exe.py --clean  # Clean build artifacts first

The executable will be created in the dist/ folder.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def get_platform_name() -> str:
    """Get a friendly platform name for the output."""
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    return system  # "linux" or "windows"


def clean_build_artifacts():
    """Remove previous build artifacts."""
    dirs_to_remove = ["build", "dist", "__pycache__"]
    # Remove auto-generated .spec files (PyInstaller creates these)
    files_to_remove = list(Path(".").glob("*.spec"))
    
    for dir_name in dirs_to_remove:
        dir_path = Path(dir_name)
        if dir_path.exists():
            print(f"Removing {dir_path}/")
            shutil.rmtree(dir_path)
    
    for file_path in files_to_remove:
        print(f"Removing {file_path}")
        file_path.unlink()


def check_pyinstaller():
    """Ensure PyInstaller is installed."""
    try:
        import PyInstaller
        print(f"✓ PyInstaller {PyInstaller.__version__} found")
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
        print("✓ PyInstaller installed")


def build_executable():
    """Build the executable using PyInstaller."""
    platform_name = get_platform_name()
    exe_name = f"tsg-builder-{platform_name}"
    
    # PyInstaller arguments
    args = [
        sys.executable, "-m", "PyInstaller",
        "--name", exe_name,
        "--onefile",  # Single executable file
        "--console",  # Console app (needed for Flask server output)
        # Add data files (templates and static assets for Flask)
        "--add-data", f"templates{os.pathsep}templates",
        "--add-data", f"static{os.pathsep}static",
        # Hidden imports that PyInstaller might miss
        "--hidden-import", "azure.identity",
        "--hidden-import", "azure.ai.projects",
        "--hidden-import", "azure.ai.projects.models",
        "--hidden-import", "azure.core",
        "--hidden-import", "flask",
        "--hidden-import", "dotenv",
        "--hidden-import", "openai",
        "--hidden-import", "httpx",
        "--hidden-import", "msal",
        "--hidden-import", "msal_extensions",
        # Collect all Azure packages (they have many submodules)
        "--collect-all", "azure.identity",
        "--collect-all", "azure.ai.projects",
        "--collect-all", "azure.core",
        "--collect-all", "msal",
        # Entry point
        "web_app.py",
    ]
    
    print(f"\n🔨 Building {exe_name}...")
    print(f"Command: {' '.join(args[2:])}\n")
    
    result = subprocess.run(args, check=False)
    
    if result.returncode != 0:
        print("\n❌ Build failed!")
        sys.exit(1)
    
    # Determine output path
    if platform_name == "windows":
        exe_path = Path("dist") / f"{exe_name}.exe"
    else:
        exe_path = Path("dist") / exe_name
    
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\n✅ Build successful!")
        print(f"   Executable: {exe_path}")
        print(f"   Size: {size_mb:.1f} MB")
        print(f"\n📋 To run:")
        if platform_name == "windows":
            print(f"   .\\dist\\{exe_name}.exe")
        else:
            print(f"   ./dist/{exe_name}")
        print(f"\n📝 On first run, a .env file will be created automatically.")
        print(f"   The setup wizard will open in your browser to configure Azure settings.")
    else:
        print(f"\n❌ Expected output not found: {exe_path}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Build TSG Builder as a standalone executable"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean build artifacts before building",
    )
    parser.add_argument(
        "--clean-only",
        action="store_true",
        help="Only clean build artifacts, don't build",
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("TSG Builder — Executable Build Script")
    print("=" * 60)
    print(f"Platform: {platform.system()} ({platform.machine()})")
    print(f"Python: {sys.version}")
    print("=" * 60)
    
    if args.clean or args.clean_only:
        print("\n🧹 Cleaning build artifacts...")
        clean_build_artifacts()
        if args.clean_only:
            print("✓ Clean complete")
            return
    
    check_pyinstaller()
    build_executable()


if __name__ == "__main__":
    main()
