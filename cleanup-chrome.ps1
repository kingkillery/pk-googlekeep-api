#!/usr/bin/env powershell
<#
.SYNOPSIS
    Kill any Chrome processes using the Keep automation profile.
.DESCRIPTION
    Use this to clean up orphaned Chrome instances left by failed or
    interrupted automation runs. Safe to run anytime.
#>
param(
    [string]$ProfileDir = "C:\Users\prest\keepapi-mcp\chrome_profile"
)

$ErrorActionPreference = "SilentlyContinue"

Write-Host "Scanning for Chrome processes using automation profile..." -ForegroundColor Cyan

# Method 1: Kill by command-line match
$killed = 0
Get-Process chrome | ForEach-Object {
    try {
        $cmd = $_.CommandLine
        if ($cmd -and $cmd -like "*$ProfileDir*") {
            Write-Host "  Killing PID $($_.Id) (automation profile)" -ForegroundColor Yellow
            Stop-Process -Id $_.Id -Force
            $killed++
        }
    } catch {}
}

# Method 2: Kill by port 9333
$tcp = Get-NetTCPConnection -LocalPort 9333 -ErrorAction SilentlyContinue
if ($tcp) {
    $pid = $tcp.OwningProcess
    try {
        $proc = Get-Process -Id $pid
        if ($proc.ProcessName -eq "chrome") {
            Write-Host "  Killing PID $pid (listening on :9333)" -ForegroundColor Yellow
            Stop-Process -Id $pid -Force
            $killed++
        }
    } catch {}
}

if ($killed -eq 0) {
    Write-Host "No automation Chrome instances found. You're clean." -ForegroundColor Green
} else {
    Write-Host "Cleaned up $killed automation Chrome instance(s)." -ForegroundColor Green
}
