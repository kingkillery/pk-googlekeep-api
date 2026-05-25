#!/usr/bin/env python3
"""
Keep API Sync — uses gkeepapi to download FULL note content from Google's servers.
Tracks downloaded note IDs so only NEW notes are saved on each run.

First run: prompts for email + Google App Password, then saves a master token.
Subsequent runs: fully automatic, no password needed.

Usage:
    python keep_api_sync.py
"""

import argparse
import json
import re
import getpass
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import gkeepapi
    from gkeepapi.node import ColorValue
except ImportError:
    print("ERROR: gkeepapi is not installed.")
    print("Run: C:\\Users\\prest\\keepapi-venv\\Scripts\\pip install gkeepapi")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
VAULT_DIR = Path(r"C:\dev\Desktop-Projects\Helpful-Docs-Prompts\VAULTS-OBSIDIAN\Notesandclippings\Notesandclippings\Keep Notes")
STATE_FILE = Path(__file__).parent / "keep_api_state.json"
TOKEN_FILE = Path(__file__).parent / "keep_token.json"

COLOR_MAP = {
    ColorValue.White: "White",
    ColorValue.Red: "Red",
    ColorValue.Orange: "Orange",
    ColorValue.Yellow: "Yellow",
    ColorValue.Green: "Green",
    ColorValue.Teal: "Teal",
    ColorValue.Blue: "Blue",
    ColorValue.DarkBlue: "DarkBlue",
    ColorValue.Purple: "Purple",
    ColorValue.Pink: "Pink",
    ColorValue.Brown: "Brown",
    ColorValue.Gray: "Gray",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '_', name).strip()
    name = re.sub(r'^[.\s]+|[.\s]+$', '', name)
    return name[:100] or "untitled"


def note_to_markdown(note) -> str:
    """Convert a gkeepapi note to Markdown with YAML frontmatter."""
    title = note.title or ""
    is_list = hasattr(note, "items") and note.items is not None and len(note.items) > 0
    labels = [lbl.name for lbl in note.labels.all()] if hasattr(note, "labels") else []
    color = COLOR_MAP.get(note.color, str(note.color)) if hasattr(note, "color") else ""
    pinned = bool(note.pinned) if hasattr(note, "pinned") else False
    archived = bool(note.archived) if hasattr(note, "archived") else False
    trashed = bool(note.trashed) if hasattr(note, "trashed") else False

    section = "trash" if trashed else ("archive" if archived else "main")

    fm = {
        "title": title,
        "source": "google_keep",
        "source_section": section,
        "color": color,
        "pinned": pinned,
        "archived": archived,
        "labels": labels,
        "is_list": is_list,
    }

    md = "---\n"
    for k, v in fm.items():
        if isinstance(v, list):
            md += f"{k}:\n" + "".join(f"  - {i}\n" for i in v)
        elif isinstance(v, bool):
            md += f"{k}: {str(v).lower()}\n"
        else:
            md += f"{k}: {v}\n"
    md += "---\n\n"

    if title:
        md += f"# {title}\n\n"

    if is_list:
        for item in note.items:
            checked = item.checked if hasattr(item, "checked") else False
            text = item.text if hasattr(item, "text") else ""
            md += f"- {'[x]' if checked else '[ ]'} {text}\n"
        md += "\n"
    else:
        text = note.text if hasattr(note, "text") else ""
        if text:
            md += f"{text}\n\n"

    md += "---\n*Imported from Google Keep*"
    return md


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"downloaded_ids": [], "last_sync": None}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def load_token() -> tuple:
    if TOKEN_FILE.exists():
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        return data.get("email"), data.get("token")
    return None, None


def save_token(email: str, token: str):
    TOKEN_FILE.write_text(json.dumps({"email": email, "token": token}, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Sync Google Keep notes to local vault")
    parser.add_argument("--email", help="Google email address")
    parser.add_argument("--password", help="Google App Password (16 characters)")
    args = parser.parse_args()

    print("=" * 60)
    print("Keep API Sync")
    print("=" * 60)

    state = load_state()
    downloaded_ids = set(state.get("downloaded_ids", []))

    email, token = load_token()
    keep = gkeepapi.Keep()

    # ---- Authenticate -----------------------------------------------------
    if email and token:
        print(f"Resuming session for {email}...")
        try:
            keep.resume(email, token)
            keep.sync()
            print("Session resumed successfully.")
        except Exception as e:
            print(f"Saved token failed ({e}). Re-authenticating...")
            email, token = None, None

    if not email or not token:
        print("\nFirst-time setup: Google Keep login")
        print("----------------------------------------")
        print("Use an App Password (NOT your main password).")
        print("Generate one at: https://myaccount.google.com/apppasswords")
        print("----------------------------------------\n")

        email = args.email or input("Google email: ").strip()
        if not email:
            print("Email required.")
            sys.exit(1)

        password = args.password or getpass.getpass("App password: ")
        if not password:
            print("Password required.")
            sys.exit(1)

        print("Logging in...")
        try:
            keep.authenticate(email, password)
        except Exception as e:
            print(f"Login failed: {e}")
            print("\nTroubleshooting:")
            print("  1. Make sure 2-Step Verification is ON for your Google account.")
            print("  2. Generate a fresh App Password at https://myaccount.google.com/apppasswords")
            print("  3. Copy the 16-character password exactly (no spaces).")
            print("  4. If it still fails, Google may have temporarily blocked the login.")
            print("     Wait a few minutes and try again, or check your Gmail for a security alert.")
            sys.exit(1)

        token = keep.getMasterToken()
        save_token(email, token)
        print("Login successful. Master token saved for future runs.\n")
        keep.sync()

    # ---- Sync & extract ---------------------------------------------------
    print("Syncing with Google Keep...")
    all_notes = list(keep.all())
    print(f"Total notes on server: {len(all_notes)}")

    new_notes = [n for n in all_notes if n.id not in downloaded_ids]
    print(f"New notes since last run: {len(new_notes)}")

    if not new_notes:
        print("\nNothing new to download. You're up to date!")
        state["last_sync"] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        return

    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    saved = 0

    for note in new_notes:
        try:
            md = note_to_markdown(note)
            fname = sanitize_filename(note.title or "untitled")
            section = "trash" if note.trashed else ("archive" if note.archived else "main")
            if section != "main":
                fname = f"{section}_{fname}"

            path = VAULT_DIR / f"{fname}.md"
            ctr = 1
            while path.exists():
                path = VAULT_DIR / f"{fname}_{ctr}.md"
                ctr += 1

            path.write_text(md, encoding="utf-8")
            print(f"  Saved: {path.name}")
            downloaded_ids.add(note.id)
            saved += 1
        except Exception as e:
            print(f"  ERROR saving note '{note.title}': {e}")

    state["downloaded_ids"] = list(downloaded_ids)
    state["last_sync"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

    print(f"\nDone: {saved} new note(s) saved to {VAULT_DIR}")
    print(f"Total tracked: {len(downloaded_ids)} note(s)")


if __name__ == "__main__":
    main()
