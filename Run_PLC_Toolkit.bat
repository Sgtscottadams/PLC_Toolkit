@echo off
setlocal

cd /d "%~dp0\ab_poller"

title PLC Toolkit GUI
echo.
echo ============================================
echo   PLC Toolkit GUI
echo   PySide6 + pylogix
echo ============================================
echo.

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

echo Using Python: %PYTHON%
echo.

%PYTHON% -m plc_toolkit
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
    echo.
    echo ============================================
    echo   PLC Toolkit exited with code %EXITCODE%
    echo ============================================
    echo.
    echo If dependencies are missing, run:
    echo   cd /d "%~dp0\ab_poller"
    echo   %PYTHON% -m pip install -r requirements.txt
    echo.
    pause
)

exit /b %EXITCODE%
