@echo off
REM Google Keep -> Obsidian Vault Sync
REM Double-click to run, or pin to taskbar for one-click sync.
REM First run: Chrome opens for Google login. After that, fully automatic.

powershell -ExecutionPolicy Bypass -File "C:\Users\prest\keepapi-mcp\keep_automation.ps1" -CloseChromeAfter

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Sync completed with warnings. Press any key to exit.
    pause >nul
)
