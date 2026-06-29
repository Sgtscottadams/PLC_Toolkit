@echo off
REM =============================================
REM  PLC Toolkit — Windows portable package
REM  Builds exe + zip for server / field deploy
REM =============================================

cls
echo.
echo =============================================
echo  PLC Toolkit — Portable Package Builder
echo =============================================
echo.

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    where py >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set "PYTHON=py -3"
    ) else (
        set "PYTHON=python"
    )
)

echo Using: %PYTHON%
echo.

%PYTHON% build_windows.py
set "EXITCODE=%ERRORLEVEL%"

echo.
if "%EXITCODE%"=="0" (
    echo =============================================
    echo  BUILD SUCCESSFUL
    echo =============================================
    echo.
    echo Copy to server:
    echo   dist_package\PLC_Toolkit.zip
    echo.
    echo Extract the zip (one PLC_Toolkit folder), then double-click
    echo PLC_Toolkit.exe inside it.
    echo.
) else (
    echo =============================================
    echo  BUILD FAILED — exit code %EXITCODE%
    echo =============================================
    echo.
)

pause
exit /b %EXITCODE%
