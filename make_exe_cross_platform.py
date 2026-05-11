"""
Cross-platform build script for PLC Toolkit
Detects OS and provides appropriate build instructions
"""

import subprocess
import sys
import os
import platform
import shutil
from pathlib import Path

def get_platform_info():
    """Detect current platform."""
    system = platform.system()
    machine = platform.machine()
    return system, machine

def build_for_current_platform():
    """Build executable for current platform."""
    system, machine = get_platform_info()
    
    print("\n" + "="*50)
    print(f" Building PLC Toolkit on {system} ({machine})")
    print("="*50 + "\n")
    
    if system == "Darwin":  # macOS
        print("⚠️  WARNING: You're on macOS")
        print("PyInstaller creates Mac apps, NOT Windows .exe files!")
        print("\nYou have three options to create Windows executables:")
        print("\n1. Use a Windows machine or VM")
        print("2. Use GitHub Actions (automated)")
        print("3. Ask a colleague with Windows to build it")
        print("\nDo you want to:")
        print("  [1] Create Mac app anyway (for testing)")
        print("  [2] Get Windows build instructions")
        print("  [3] Setup GitHub Actions workflow")
        print("  [4] Exit")
        
        choice = input("\nChoice [1-4]: ").strip()
        
        if choice == "1":
            build_mac_app()
        elif choice == "2":
            show_windows_instructions()
        elif choice == "3":
            create_github_workflow()
        else:
            print("Exiting.")
            return
            
    elif system == "Windows":
        build_windows_exe()
    
    elif system == "Linux":
        print("⚠️  Linux detected. You can only build Linux executables here.")
        print("To create Windows .exe files, you need a Windows machine.")
        return

def build_mac_app():
    """Build Mac application."""
    print("\nBuilding Mac application for testing...")
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console", 
        "--clean",
        "--name", "PLC_Toolkit",
        "--distpath", ".",
        "--specpath", "build",
        "--workpath", "build",
        "--hidden-import", "pycomm3",
        "--hidden-import", "openpyxl",
        "--hidden-import", "sqlite3",
        "plc_toolkit_consolidated.py"
    ]
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("\n✓ Mac app created: PLC_Toolkit")
        print("Run with: ./PLC_Toolkit")
        print("\nNOTE: This will NOT work on Windows!")
        print("You still need to build on Windows for Windows users.")

def build_windows_exe():
    """Build Windows executable on Windows."""
    print("\nBuilding Windows executable...")
    
    # Check for PyInstaller
    try:
        import PyInstaller
        print("✓ PyInstaller found")
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",
        "--clean",
        "--name", "PLC_Toolkit",
        "--distpath", ".",
        "--specpath", "build",
        "--workpath", "build",
        "--hidden-import", "pycomm3",
        "--hidden-import", "openpyxl", 
        "--hidden-import", "sqlite3",
        "plc_toolkit_consolidated.py"
    ]
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("\n✓ Build successful!")
        print("Executable created: PLC_Toolkit.exe")
        
        # Create launcher
        launcher = """@echo off
cls
color 0A
echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   PLC Toolkit                            ║
echo  ╚══════════════════════════════════════════╝
echo.
if not exist plc_scans mkdir plc_scans
PLC_Toolkit.exe
if %ERRORLEVEL% NEQ 0 pause"""
        
        with open("Run_Toolkit.bat", "w") as f:
            f.write(launcher)
        
        print("\nFiles ready for distribution:")
        print("  1. PLC_Toolkit.exe")
        print("  2. Run_Toolkit.bat")

def show_windows_instructions():
    """Show instructions for building on Windows."""
    instructions = """
==================================================
 WINDOWS BUILD INSTRUCTIONS
==================================================

Since you're on Mac, you need Windows to build .exe files.

OPTION 1: Windows Machine/VM
----------------------------
1. Copy these files to a Windows machine:
   - plc_toolkit_consolidated.py
   - make_exe.py

2. On the Windows machine:
   pip install pyinstaller pycomm3 openpyxl
   python make_exe.py

3. Copy back the .exe file


OPTION 2: Parallels/VMware/VirtualBox
--------------------------------------
1. Install Windows 10/11 in a VM
2. Install Python 3.8+ in the VM
3. Share your project folder with the VM
4. Build inside the VM


OPTION 3: Wine + PyInstaller (Less Reliable)
--------------------------------------------
1. Install Wine: brew install wine-stable
2. Install Windows Python in Wine
3. Use Wine to run PyInstaller
(This often has compatibility issues)


OPTION 4: Ask a Colleague
-------------------------
Send these files to someone with Windows:
- plc_toolkit_consolidated.py  
- make_exe.py

They run: python make_exe.py
Send back: PLC_Toolkit.exe


OPTION 5: Cloud Build Service
-----------------------------
Use GitHub Actions (see option 3 in main menu)
or use a service like AppVeyor
"""
    print(instructions)

def create_github_workflow():
    """Create GitHub Actions workflow for automated Windows builds."""
    
    workflow = """name: Build Windows Executable

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]
  workflow_dispatch:  # Allow manual trigger

jobs:
  build-windows:
    runs-on: windows-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install pyinstaller pycomm3 openpyxl
    
    - name: Build executable
      run: |
        pyinstaller --onefile --console --name PLC_Toolkit plc_toolkit_consolidated.py
    
    - name: Create launcher
      run: |
        echo @echo off > Run_Toolkit.bat
        echo if not exist plc_scans mkdir plc_scans >> Run_Toolkit.bat
        echo PLC_Toolkit.exe >> Run_Toolkit.bat
        echo if %%ERRORLEVEL%% NEQ 0 pause >> Run_Toolkit.bat
    
    - name: Upload artifacts
      uses: actions/upload-artifact@v3
      with:
        name: PLC-Toolkit-Windows
        path: |
          dist/PLC_Toolkit.exe
          Run_Toolkit.bat
"""
    
    print("\nCreating GitHub Actions workflow...")
    
    # Create .github/workflows directory
    workflow_dir = Path(".github/workflows")
    workflow_dir.mkdir(parents=True, exist_ok=True)
    
    # Write workflow file
    workflow_file = workflow_dir / "build-windows.yml"
    with open(workflow_file, "w") as f:
        f.write(workflow)
    
    print(f"✓ Created {workflow_file}")
    print("\nTo use this workflow:")
    print("1. Commit and push to GitHub")
    print("2. Go to Actions tab in your repo")
    print("3. Run the 'Build Windows Executable' workflow")
    print("4. Download the artifact (PLC-Toolkit-Windows.zip)")
    print("\nThe workflow will automatically build on every push to main.")
    
    # Also create a simple build script for Windows
    windows_script = """@echo off
echo Building PLC Toolkit for Windows...
pip install pyinstaller pycomm3 openpyxl
pyinstaller --onefile --console --name PLC_Toolkit plc_toolkit_consolidated.py
echo.
echo Build complete! Check dist folder for PLC_Toolkit.exe
pause"""
    
    with open("build_on_windows.bat", "w") as f:
        f.write(windows_script)
    
    print("\nAlso created: build_on_windows.bat")
    print("(Give this to anyone with Windows to build for you)")

if __name__ == "__main__":
    build_for_current_platform()
