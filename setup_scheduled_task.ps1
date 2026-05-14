#!/usr/bin/env powershell
<#
.SYNOPSIS
    [DEPRECATED] Scheduled task setup for Google Keep extraction.
.DESCRIPTION
    THIS SCRIPT IS DEPRECATED. The KeepAPI workflow is explicitly designed
    as an on-demand tool, NOT a scheduled background process.
    
    Chrome is launched and killed per run. Scheduling this would:
    - Leave Chrome running between syncs (violates the Chrome lifecycle policy)
    - Consume resources unnecessarily
    - Risk interfering with the user's normal browsing sessions
    
    Use keep_automation.ps1 directly when you want to sync.
    Do not schedule it.
    
    If you still want a scheduled task despite these warnings, you can
    adapt this script, but it is NOT supported or recommended.
#>

Write-Host "WARNING: Scheduled tasks are NOT supported for KeepAPI." -ForegroundColor Red
Write-Host "This tool is designed for on-demand use only." -ForegroundColor Yellow
Write-Host ""
Write-Host "To sync notes, run:" -ForegroundColor Cyan
Write-Host "  .\keep_automation.ps1 -CloseChromeAfter" -ForegroundColor White
Write-Host ""
Write-Host "To schedule anyway (not recommended), edit this script and remove this warning." -ForegroundColor DarkGray
