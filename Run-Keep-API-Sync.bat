@echo off
cls
echo ===========================================
echo  Keep API Sync (gkeepapi)
echo ===========================================
echo.
cd /d "%~dp0"
C:\Users\prest\keepapi-venv\Scripts\python.exe keep_api_sync.py
pause
