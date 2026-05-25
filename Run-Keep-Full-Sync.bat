@echo off
cls
echo ===========================================
echo  Keep Full Sync (Browser-based)
echo ===========================================
echo.
cd /d "%~dp0"
python keep_full_sync.py --section all
echo.
pause
