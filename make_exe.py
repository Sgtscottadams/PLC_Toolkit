"""
Simple build script to create Windows executable
Run: python make_exe.py
"""

import subprocess
import sys
import os
import shutil
from pathlib import Path

print("\n" + "="*50)
print(" Building PLC Toolkit for Windows")
print("="*50 + "\n")

# Install PyInstaller if needed
print("Checking PyInstaller...")
try:
    import PyInstaller
    print("✓ PyInstaller found")
except ImportError:
    print("Installing PyInstaller...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    print("✓ PyInstaller installed")

# Build the executable
print("\nBuilding executable (this may take a minute)...")

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",           # Single exe file
    "--console",           # Console app (not windowed)
    "--clean",            # Clean build
    "--name", "PLC_Toolkit",
    "--distpath", ".",     # Output in current directory
    "--specpath", "build", # Spec file in build folder
    "--workpath", "build", # Work files in build folder
    # Hidden imports for dependencies
    "--hidden-import", "pycomm3",
    "--hidden-import", "pycomm3.packets",
    "--hidden-import", "pycomm3.cip",
    "--hidden-import", "openpyxl",
    "--hidden-import", "openpyxl.styles",
    "--hidden-import", "sqlite3",
    # Exclude unnecessary modules to reduce size
    "--exclude-module", "matplotlib",
    "--exclude-module", "numpy", 
    "--exclude-module", "pandas",
    "--exclude-module", "scipy",
    "--exclude-module", "tkinter",
    "--exclude-module", "PIL",
    # Main script
    "plc_toolkit_consolidated.py"
]

result = subprocess.run(cmd)

if result.returncode == 0:
    print("\n✓ Build successful!")
    print(f"Executable created: PLC_Toolkit.exe")
    print(f"Size: {os.path.getsize('PLC_Toolkit.exe') / 1024 / 1024:.1f} MB")
    
    # Create simple launcher
    launcher = """@echo off
cls
color 0A
echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   PLC Toolkit                            ║
echo  ║   Tag Discovery and Monitoring           ║
echo  ╚══════════════════════════════════════════╝
echo.
if not exist plc_scans mkdir plc_scans
PLC_Toolkit.exe
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Press any key to exit...
    pause >nul
)"""
    
    with open("Run_Toolkit.bat", "w") as f:
        f.write(launcher)
    
    print("\nCreated launcher: Run_Toolkit.bat")
    print("\n" + "="*50)
    print(" READY FOR DISTRIBUTION")
    print("="*50)
    print("\nFiles to send to users:")
    print("  1. PLC_Toolkit.exe")
    print("  2. Run_Toolkit.bat")
    print("\nUsers just double-click Run_Toolkit.bat!")
    
else:
    print("\n✗ Build failed!")
    print("Check error messages above")
