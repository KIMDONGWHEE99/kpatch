@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Patch.ps1" -Mode Uninstall %*
set "exitCode=%ERRORLEVEL%"
echo.
pause
exit /b %exitCode%
