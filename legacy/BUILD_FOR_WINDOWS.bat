@echo off
REM =============================================
REM  PLC Toolkit - Windows Builder
REM  Run this on a Windows machine to build .exe
REM =============================================

cls
color 0A
echo.
echo =============================================
echo  PLC Toolkit
echo  Windows Executable Builder
echo =============================================
echo.

REM Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH
    echo.
    echo Please install Python 3.8 or later from python.org
    echo Then run this script again.
    echo.
    pause
    exit /b 1
)

echo [1/3] Installing required packages...
echo.
pip install pyinstaller pycomm3 openpyxl

echo.
echo [2/3] Building executable with PyInstaller...
echo.

REM Clean previous builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist PLC_Toolkit.exe del PLC_Toolkit.exe
if exist PLC_Toolkit.spec del PLC_Toolkit.spec

REM Build the executable
pyinstaller --onefile --console --name PLC_Toolkit plc_toolkit_consolidated.py

echo.
echo [3/3] Creating distribution package...
echo.

REM Move exe to current directory
if exist dist\PLC_Toolkit.exe (
    move dist\PLC_Toolkit.exe . >nul
    
    REM Create launcher
    (
    echo @echo off
    echo cls
    echo echo.
    echo echo ============================================
    echo echo   PLC Toolkit
    echo echo   Tag Discovery and Monitoring
    echo echo ============================================
    echo echo.
    echo if not exist plc_scans mkdir plc_scans
    echo PLC_Toolkit.exe
    echo if %%ERRORLEVEL%% NEQ 0 pause
    ) > Run_Toolkit.bat
    
    REM Create quick readme
    (
    echo PLC TOOLKIT - QUICK START
    echo =========================
    echo.
    echo 1. Double-click Run_Toolkit.bat
    echo 2. Enter PLC IP address
    echo 3. Enter slot number ^(usually 0^)
    echo.
    echo Files will be saved in plc_scans folder
    ) > Quick_Start.txt
    
    echo.
    echo =============================================
    echo  BUILD SUCCESSFUL!
    echo =============================================
    echo.
    echo Created files:
    echo   - PLC_Toolkit.exe (main program)
    echo   - Run_Toolkit.bat (launcher)
    echo   - Quick_Start.txt (instructions)
    echo.
    echo Package these files and send to users!
    echo.
) else (
    echo.
    echo =============================================
    echo  BUILD FAILED!
    echo =============================================
    echo.
    echo Could not find the executable.
    echo Check for error messages above.
    echo.
)

REM Cleanup
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist PLC_Toolkit.spec del PLC_Toolkit.spec

echo.
pause
