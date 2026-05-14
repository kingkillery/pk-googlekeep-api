#!/usr/bin/env powershell
<#
.SYNOPSIS
    Google Keep to Obsidian vault automation via Chrome CDP.
.DESCRIPTION
    Launches Chrome with remote debugging on a dedicated profile,
    extracts ALL Keep notes (Main + Archive + Trash), deduplicates,
    and saves as Markdown to your Obsidian vault.
    
    FIRST-RUN: Chrome will open keep.google.com. Log in with your
    Google account. The login persists in the dedicated profile.
    
    SUBSEQUENT RUNS: Fully hands-off -- notes extract automatically.
    
    SELF-HEALING: If Chrome is stuck or port 9333 is occupied, the
    script automatically runs cleanup-chrome.ps1 and retries once.
.EXAMPLE
    .\keep_automation.ps1
    .\keep_automation.ps1 -CloseChromeAfter
    .\keep_automation.ps1 -NoChromeLaunch   # use existing Chrome on :9333
#>
param(
    [switch]$CloseChromeAfter,
    [switch]$NoChromeLaunch,
    [int]$DebugPort = 9333,
    [string]$VaultDir = "C:\dev\Desktop-Projects\Helpful-Docs-Prompts\VAULTS-OBSIDIAN\Notesandclippings\Notesandclippings\Untitled",
    [string]$ProfileDir = "C:\Users\prest\keepapi-mcp\chrome_profile"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$chromeExe = "C:\Program Files\Google\Chrome\Application\chrome.exe"
if (-not (Test-Path $chromeExe)) {
    $chromeExe = "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
}
if (-not (Test-Path $chromeExe)) {
    $chromeExe = (Get-Command chrome -ErrorAction SilentlyContinue).Source
}
if (-not $chromeExe) {
    Write-Host "ERROR: Chrome not found. Please install Google Chrome." -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null

# Preflight: kill any zombie Chrome from previous runs to prevent accumulation
$tcp = Get-NetTCPConnection -LocalPort $DebugPort -ErrorAction SilentlyContinue
if ($tcp) {
    Write-Host "Preflight: Found stale Chrome on port $DebugPort. Cleaning up..." -ForegroundColor Magenta
    Invoke-CleanupChrome -Port $DebugPort -Profile $ProfileDir
}

$chromeProcess = $null
$weLaunchedChrome = $false

function Invoke-CleanupChrome {
    param([int]$Port = 9333, [string]$Profile = "C:\Users\prest\keepapi-mcp\chrome_profile")
    Write-Host "Running self-healing Chrome cleanup..." -ForegroundColor Magenta
    $cleanupScript = Join-Path $scriptDir "cleanup-chrome.ps1"
    if (Test-Path $cleanupScript) {
        & $cleanupScript -ProfileDir $Profile
    } else {
        # Fallback inline cleanup
        Get-Process chrome -ErrorAction SilentlyContinue | Where-Object {
            try { $_.CommandLine -like "*$Profile*" } catch { $false }
        } | Stop-Process -Force -ErrorAction SilentlyContinue
        $tcp = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        if ($tcp) {
            try { Stop-Process -Id $tcp.OwningProcess -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
    Start-Sleep -Seconds 3
}

function Test-ChromePort {
    param([int]$Port = 9333)
    $tcp = Test-NetConnection -ComputerName localhost -Port $Port -WarningAction SilentlyContinue
    return $tcp.TcpTestSucceeded
}

function Start-AutomationChrome {
    param([int]$Port = 9333, [string]$Profile, [string]$ChromePath)
    Write-Host "Launching Chrome with remote debugging on port $Port..." -ForegroundColor Green
    $proc = Start-Process -FilePath $ChromePath -ArgumentList @(
        "--remote-debugging-port=$Port",
        "--user-data-dir=`"$Profile`"",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "https://keep.google.com"
    ) -PassThru -WindowStyle Hidden
    return $proc
}

function Wait-ForChromePort {
    param([int]$Port = 9333, [int]$MaxWaitSec = 20)
    $tries = 0
    $maxTries = $MaxWaitSec * 2  # 500ms intervals
    while ($tries -lt $maxTries) {
        if (Test-ChromePort -Port $Port) {
            return $true
        }
        Start-Sleep -Milliseconds 500
        $tries++
    }
    return $false
}

try {
    if (-not $NoChromeLaunch) {
        if (Test-ChromePort -Port $DebugPort) {
            Write-Host "Chrome already running on debug port $DebugPort. Reusing existing session." -ForegroundColor Cyan
        } else {
            # Attempt 1: Launch Chrome
            $chromeProcess = Start-AutomationChrome -Port $DebugPort -Profile $ProfileDir -ChromePath $chromeExe
            $weLaunchedChrome = $true
            Write-Host "Waiting for Chrome to start..." -ForegroundColor Yellow
            
            if (-not (Wait-ForChromePort -Port $DebugPort -MaxWaitSec 20)) {
                Write-Host "WARNING: Chrome did not respond. Running self-healing cleanup..." -ForegroundColor Magenta
                
                # Kill the failed process if we know it
                if ($chromeProcess -and -not $chromeProcess.HasExited) {
                    Stop-Process -Id $chromeProcess.Id -Force -ErrorAction SilentlyContinue
                }
                
                # Self-healing: cleanup and retry once
                Invoke-CleanupChrome -Port $DebugPort -Profile $ProfileDir
                
                Write-Host "Retrying Chrome launch..." -ForegroundColor Yellow
                $chromeProcess = Start-AutomationChrome -Port $DebugPort -Profile $ProfileDir -ChromePath $chromeExe
                
                if (-not (Wait-ForChromePort -Port $DebugPort -MaxWaitSec 20)) {
                    Write-Host "ERROR: Chrome failed to start after cleanup and retry." -ForegroundColor Red
                    Write-Host "Please run .\cleanup-chrome.ps1 manually, then try again." -ForegroundColor Red
                    exit 1
                }
            }
            Write-Host "Chrome is ready." -ForegroundColor Green
        }
    } else {
        if (-not (Test-ChromePort -Port $DebugPort)) {
            Write-Host "ERROR: No Chrome found on port $DebugPort." -ForegroundColor Red
            Write-Host "Launch Chrome with: --remote-debugging-port=$DebugPort" -ForegroundColor Yellow
            exit 1
        }
        Write-Host "Skipping Chrome launch - using existing Chrome on port $DebugPort." -ForegroundColor Cyan
    }

    Write-Host ""
    Write-Host "Extracting ALL notes from Google Keep (Main + Archive + Trash)..." -ForegroundColor Green
    python "$scriptDir\extract_all_keep.py"
    $exitCode = $LASTEXITCODE

    if ($exitCode -eq 0) {
        Write-Host ""
        Write-Host "Automation completed successfully." -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "Automation finished with warnings. Check output above." -ForegroundColor Yellow
    }
}
finally {
    if ($weLaunchedChrome -or $CloseChromeAfter) {
        Write-Host "Cleaning up automation Chrome..." -ForegroundColor Yellow
        if ($chromeProcess -and -not $chromeProcess.HasExited) {
            Stop-Process -Id $chromeProcess.Id -Force -ErrorAction SilentlyContinue
        }
        Invoke-CleanupChrome -Port $DebugPort -Profile $ProfileDir
        Write-Host "Chrome cleanup complete." -ForegroundColor Green
    }
}
