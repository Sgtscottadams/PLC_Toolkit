#!/usr/bin/env python3
"""
Build script for creating Windows executable of PLC Toolkit
Run this to create a standalone .exe file
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

def check_requirements():
    """Check if required packages are installed."""
    required = ['pyinstaller', 'pycomm3', 'openpyxl']
    missing = []
    
    for package in required:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)
    
    if missing:
        print("Missing required packages:")
        for pkg in missing:
            print(f"  - {pkg}")
        print("\nInstalling missing packages...")
        
        for pkg in missing:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg])
        print("✓ All packages installed")
    else:
        print("✓ All requirements satisfied")

def create_spec_file():
    """Create PyInstaller spec file with all dependencies."""
    spec_content = '''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['plc_toolkit_consolidated.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'pycomm3',
        'pycomm3.cip',
        'pycomm3.cip.data_types',
        'pycomm3.packets',
        'pycomm3.utils',
        'openpyxl',
        'openpyxl.styles',
        'openpyxl.worksheet',
        'openpyxl.chart',
        'xml.etree.ElementTree',
        'xml.dom.minidom',
        'sqlite3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'tkinter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='PLC_Toolkit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='plc_icon.ico'  # Optional: add an icon file
)
'''
    
    with open('plc_toolkit.spec', 'w') as f:
        f.write(spec_content)
    print("✓ Created plc_toolkit.spec")

def build_executable():
    """Build the executable using PyInstaller."""
    print("\nBuilding executable...")
    
    # Run PyInstaller
    subprocess.check_call([
        sys.executable, '-m', 'PyInstaller',
        '--clean',
        '--onefile',
        '--console',
        '--name', 'PLC_Toolkit',
        'plc_toolkit_consolidated.py'
    ])
    
    print("✓ Executable built successfully")

def create_distribution():
    """Create distribution folder with all necessary files."""
    dist_dir = Path('PLC_Toolkit_Windows')
    
    # Clean and create distribution directory
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    dist_dir.mkdir()
    
    # Copy executable
    exe_source = Path('dist/PLC_Toolkit.exe')
    if exe_source.exists():
        shutil.copy2(exe_source, dist_dir / 'PLC_Toolkit.exe')
    
    # Create batch file launcher
    batch_content = '''@echo off
title PLC Toolkit
echo.
echo ============================================
echo  PLC Toolkit
echo  Starting...
echo ============================================
echo.

REM Check if running as administrator (optional)
net session >nul 2>&1
if %errorLevel% == 0 (
    echo Running with administrator privileges
) else (
    echo Running with standard privileges
)

REM Create required directories if they don't exist
if not exist "plc_scans" mkdir plc_scans
if not exist "debug" mkdir debug

REM Run the toolkit
PLC_Toolkit.exe

REM Keep window open if there was an error
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ============================================
    echo  An error occurred. Error code: %ERRORLEVEL%
    echo ============================================
    pause
)
'''
    
    with open(dist_dir / 'Run_PLC_Toolkit.bat', 'w') as f:
        f.write(batch_content)
    
    # Create README
    readme_content = '''# PLC Toolkit - Windows Edition

## Quick Start

1. **Run the toolkit:**
   - Double-click `Run_PLC_Toolkit.bat`
   - OR double-click `PLC_Toolkit.exe`

2. **Enter PLC connection details:**
   - IP Address: The IP of your Allen-Bradley PLC
   - Slot: Usually 0 (default) for most PLCs

3. **Use the tools:**
   - **Discovery**: Scans and saves all PLC tags
   - **Export**: Creates Excel/JSON/XML reports
   - **Tag Checker**: Read live values or monitor changes

## Requirements

- Windows 10/11 or Windows Server
- Network access to Allen-Bradley PLC
- PLC must support EtherNet/IP protocol

## Output Files

- **Database**: `plc_data.db` (stores discovered tags)
- **Reports**: Created in `plc_scans/` folder
  - Excel files (.xlsx)
  - JSON files (.json)
  - XML files (.xml)

## Troubleshooting

**Cannot connect to PLC:**
- Verify PLC IP address is correct
- Check network connectivity (ping the PLC)
- Ensure no firewall is blocking the connection
- Try different slot numbers (0, 1, 2)

**Excel export not working:**
- The toolkit will skip Excel if there's an issue
- JSON and XML exports will still work

**"Missing DLL" errors:**
- Install Visual C++ Redistributable from Microsoft
- Run Windows Update to get latest system files

## Features

- **Tag Discovery**: Automatically finds all PLC tags
- **Case-Insensitive**: Type tag names in any case
- **Live Monitoring**: Watch tag values update in real-time
- **Multiple Formats**: Export to Excel, JSON, or XML
- **Database Storage**: Tags are saved locally for offline viewing

## Support

For issues or questions, contact your system administrator.

---
Created by Scott Adams
'''
    
    with open(dist_dir / 'README.txt', 'w') as f:
        f.write(readme_content)
    
    # Create a simple config file
    config_content = '''# PLC Toolkit Configuration
# Edit these defaults if needed

[DEFAULT]
timeout = 10
refresh_seconds = 5
history_size = 10

[DATABASE]
filename = plc_data.db

[OUTPUT]
folder = plc_scans
'''
    
    with open(dist_dir / 'config.ini', 'w') as f:
        f.write(config_content)
    
    print(f"✓ Distribution created in '{dist_dir}' folder")
    print(f"\nPackage contents:")
    print(f"  - PLC_Toolkit.exe (main program)")
    print(f"  - Run_PLC_Toolkit.bat (launcher)")
    print(f"  - README.txt (instructions)")
    print(f"  - config.ini (optional settings)")

def main():
    """Main build process."""
    print("=" * 50)
    print(" PLC Toolkit - Windows Build Script")
    print("=" * 50)
    
    # Check requirements
    check_requirements()
    
    # Build executable
    build_executable()
    
    # Create distribution
    create_distribution()
    
    print("\n" + "=" * 50)
    print(" BUILD COMPLETE!")
    print("=" * 50)
    print("\nTo distribute:")
    print("1. Zip the 'PLC_Toolkit_Windows' folder")
    print("2. Send the zip file to end users")
    print("3. Users extract and run 'Run_PLC_Toolkit.bat'")
    print("\nNo Python installation required on target machines!")

if __name__ == "__main__":
    main()
