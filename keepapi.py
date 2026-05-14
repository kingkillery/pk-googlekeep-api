#!/usr/bin/env python3
"""
KeepAPI -- Unified CLI for Google Keep to Obsidian extraction.

This is the canonical entry point that all agents should use.
It handles preflight cleanup, Chrome lifecycle, and extraction.

Usage:
    python keepapi.py                    # Extract all notes to default vault
    python keepapi.py --vault "C:\\path"  # Extract to custom vault
    python keepapi.py --help             # Show help

Agents: Invoke this script directly. Do not try to manage Chrome yourself.
"""

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_VAULT = r"C:\dev\Desktop-Projects\Helpful-Docs-Prompts\VAULTS-OBSIDIAN\Notesandclippings\Notesandclippings\Untitled"
SCRIPT_DIR = Path(__file__).parent


def main():
    parser = argparse.ArgumentParser(
        description="Extract ALL Google Keep notes (Main + Archive + Trash) to Obsidian vault"
    )
    parser.add_argument(
        "--vault",
        default=DEFAULT_VAULT,
        help="Target Obsidian vault directory",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9333,
        help="Chrome remote debugging port (default: 9333)",
    )
    parser.add_argument(
        "--close-chrome",
        action="store_true",
        default=True,
        help="Close Chrome after extraction (default: True)",
    )
    parser.add_argument(
        "--no-close-chrome",
        action="store_true",
        help="Leave Chrome running after extraction (not recommended)",
    )
    args = parser.parse_args()

    close = not args.no_close_chrome

    # Use the PowerShell wrapper for full lifecycle management
    ps_script = SCRIPT_DIR / "keep_automation.ps1"
    if not ps_script.exists():
        print(f"ERROR: {ps_script} not found.")
        sys.exit(1)

    cmd = [
        "powershell",
        "-ExecutionPolicy", "Bypass",
        "-File", str(ps_script),
        "-VaultDir", args.vault,
        "-DebugPort", str(args.port),
    ]
    if close:
        cmd.append("-CloseChromeAfter")

    print(f"[keepapi] Invoking: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
