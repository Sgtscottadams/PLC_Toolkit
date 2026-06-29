@echo off
cd /d "%~dp0"
cls
echo.
echo ============================================
echo   Allen-Bradley PLC Toolkit
echo   Tag Discovery and Monitoring
echo ============================================
echo.
if not exist plc_scans mkdir plc_scans
PLC_Toolkit.exe
if %ERRORLEVEL% NEQ 0 pause