#!/usr/bin/env powershell
$ErrorActionPreference = "Stop"

$chromeExe = "C:\Program Files\Google\Chrome\Application\chrome.exe"
if (-not (Test-Path $chromeExe)) {
    $chromeExe = "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
}
if (-not (Test-Path $chromeExe)) {
    $chromeExe = (Get-Command chrome -ErrorAction SilentlyContinue).Source
}
if (-not $chromeExe) {
    Write-Host "ERROR: Chrome not found." -ForegroundColor Red
    exit 1
}

$ProfileDir = "C:\Users\prest\keepapi-mcp\chrome_profile"
$DebugPort = 9333
$VaultDir = "C:\dev\Desktop-Projects\Helpful-Docs-Prompts\VAULTS-OBSIDIAN\Notesandclippings\Notesandclippings\Keep Notes"
$scriptDir = "C:\Users\prest\keepapi-mcp"

New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null

# Check if Chrome already running on port
$tcp = Test-NetConnection -ComputerName localhost -Port $DebugPort -WarningAction SilentlyContinue
if (-not $tcp.TcpTestSucceeded) {
    Write-Host "Launching Chrome with remote debugging on port $DebugPort..." -ForegroundColor Green
    $chromeProcess = Start-Process -FilePath $chromeExe -ArgumentList @(
        "--remote-debugging-port=$DebugPort",
        "--user-data-dir=`"$ProfileDir`"",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "https://keep.google.com"
    ) -PassThru -WindowStyle Hidden

    # Wait for port
    $tries = 0
    $ready = $false
    while ($tries -lt 40) {
        $test = Test-NetConnection -ComputerName localhost -Port $DebugPort -WarningAction SilentlyContinue
        if ($test.TcpTestSucceeded) {
            $ready = $true
            break
        }
        Start-Sleep -Milliseconds 500
        $tries++
    }
    if (-not $ready) {
        Write-Host "ERROR: Chrome did not start on port $DebugPort" -ForegroundColor Red
        exit 1
    }
    Write-Host "Chrome is ready." -ForegroundColor Green
    Start-Sleep -Seconds 2
} else {
    Write-Host "Reusing existing Chrome on port $DebugPort." -ForegroundColor Cyan
}

try {
    Write-Host "Extracting Keep notes to vault..." -ForegroundColor Green
    python "$scriptDir\extract_all_keep.py" --vault "$VaultDir"
    $exitCode = $LASTEXITCODE
} finally {
    Write-Host "Cleaning up automation Chrome..." -ForegroundColor Yellow
    if ($chromeProcess -and -not $chromeProcess.HasExited) {
        Stop-Process -Id $chromeProcess.Id -Force -ErrorAction SilentlyContinue
    }
    Get-Process chrome -ErrorAction SilentlyContinue | Where-Object {
        try { $_.CommandLine -like "*$ProfileDir*" } catch { $false }
    } | Stop-Process -Force -ErrorAction SilentlyContinue
    $tcp = Get-NetTCPConnection -LocalPort $DebugPort -ErrorAction SilentlyContinue
    if ($tcp) {
        try { Stop-Process -Id $tcp.OwningProcess -Force -ErrorAction SilentlyContinue } catch {}
    }
    Write-Host "Cleanup complete." -ForegroundColor Green
}

exit $exitCode
