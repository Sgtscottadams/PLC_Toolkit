@echo off
REM ========================================
REM  PLC Toolkit - Windows Package Builder
REM ========================================

echo.
echo ============================================
echo  PLC Toolkit
echo  Windows Executable Builder
echo ============================================
echo.

REM Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8 or later
    pause
    exit /b 1
)

echo [1/4] Installing required packages...
pip install pyinstaller pycomm3 openpyxl

echo.
echo [2/4] Creating executable...
pyinstaller --onefile --console --clean ^
    --name "PLC_Toolkit" ^
    --hidden-import pycomm3 ^
    --hidden-import openpyxl ^
    --hidden-import xml.etree.ElementTree ^
    --hidden-import xml.dom.minidom ^
    --exclude-module matplotlib ^
    --exclude-module numpy ^
    --exclude-module pandas ^
    plc_toolkit_consolidated.py

echo.
echo [3/4] Creating distribution package...

REM Create distribution folder
if exist "PLC_Toolkit_Package" rmdir /s /q "PLC_Toolkit_Package"
mkdir "PLC_Toolkit_Package"

REM Copy executable
copy "dist\PLC_Toolkit.exe" "PLC_Toolkit_Package\" >nul

echo.
echo [4/4] Creating launcher and documentation...

REM Create launcher batch file
(
echo @echo off
echo title PLC Toolkit
echo color 0A
echo.
echo echo ============================================
echo echo  PLC Toolkit
echo echo  Tag Discovery - Export - Live Monitoring
echo echo ============================================
echo echo.
echo.
echo REM Create required folders
echo if not exist "plc_scans" mkdir plc_scans
echo.
echo REM Run the toolkit
echo PLC_Toolkit.exe
echo.
echo if %%ERRORLEVEL%% NEQ 0 pause
) > "PLC_Toolkit_Package\Start_PLC_Toolkit.bat"

REM Create quick instructions
(
echo PLC TOOLKIT - QUICK START
echo ========================================
echo.
echo TO RUN:
echo   1. Double-click "Start_PLC_Toolkit.bat"
echo   2. Enter your PLC's IP address
echo   3. Enter slot number ^(usually 0^)
echo.
echo FEATURES:
echo   - Discover all PLC tags
echo   - Export to Excel, JSON, XML
echo   - Read live tag values
echo   - Monitor tag changes
echo.
echo FILES CREATED:
echo   - plc_data.db = Tag database
echo   - plc_scans\ = Export folder
echo.
echo REQUIREMENTS:
echo   - Windows 10/11 or Server
echo   - Network access to PLC
echo   - Allen-Bradley PLC with EtherNet/IP
echo.
echo ========================================
) > "PLC_Toolkit_Package\Quick_Start.txt"

echo.
echo ============================================
echo  BUILD COMPLETE!
echo ============================================
echo.
echo Package created in: PLC_Toolkit_Package\
echo.
echo Contents:
echo   - PLC_Toolkit.exe (main program)
echo   - Start_PLC_Toolkit.bat (launcher)
echo   - Quick_Start.txt (instructions)
echo.
echo To distribute:
echo   1. Zip the "PLC_Toolkit_Package" folder
echo   2. Send to users
echo   3. They extract and run Start_PLC_Toolkit.bat
echo.
echo No Python required on user machines!
echo.
pause
