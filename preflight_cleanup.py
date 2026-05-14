#!/usr/bin/env python3
"""
Preflight cleanup: kill any zombie Chrome using the automation profile or port 9333.
Called at the start of every Keep operation to prevent accumulation.
"""

import subprocess
import time
from pathlib import Path

PROFILE_DIR = Path(r"C:\Users\prest\keepapi-mcp\chrome_profile")
DEBUG_PORT = 9333


def preflight_cleanup(port: int = DEBUG_PORT, profile_dir: Path = PROFILE_DIR):
    """Kill any Chrome processes using the automation profile or listening on the debug port."""
    # Check if anything is listening on the port
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             f"$tcp = Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue; "
             "if ($tcp) { $tcp.OwningProcess } else { 0 }"],
            capture_output=True, text=True, timeout=10
        )
        pid_str = result.stdout.strip()
        if pid_str and pid_str != "0":
            try:
                pid = int(pid_str)
                # Verify it's chrome
                proc_check = subprocess.run(
                    ["powershell", "-Command",
                     f"$p = Get-Process -Id {pid} -ErrorAction SilentlyContinue; "
                     "if ($p -and $p.ProcessName -eq 'chrome') { 'YES' } else { 'NO' }"],
                    capture_output=True, text=True, timeout=10
                )
                if proc_check.stdout.strip() == "YES":
                    print(f"[preflight] Found stale Chrome (PID {pid}) on port {port}. Killing...")
                    subprocess.run(
                        ["powershell", "-Command", f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"],
                        capture_output=True, timeout=10
                    )
                    time.sleep(2)
                    print(f"[preflight] Stale Chrome killed.")
                    return True
            except ValueError:
                pass
    except Exception:
        pass

    # Fallback: kill by profile directory match
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             f"Get-Process chrome -ErrorAction SilentlyContinue | "
             f"Where-Object {{ $_.CommandLine -like '*{profile_dir}*' }} | "
             "Stop-Process -Force -ErrorAction SilentlyContinue; "
             "$count = (Get-Process chrome -ErrorAction SilentlyContinue | "
             f"Where-Object {{ $_.CommandLine -like '*{profile_dir}*' }}).Count; "
             "$count"],
            capture_output=True, text=True, timeout=10
        )
        count_str = result.stdout.strip()
        if count_str and count_str != "0":
            print(f"[preflight] Killed {count_str} stale Chrome process(es) matching profile.")
            return True
    except Exception:
        pass

    return False


if __name__ == "__main__":
    cleaned = preflight_cleanup()
    if not cleaned:
        print("[preflight] No stale Chrome found.")
