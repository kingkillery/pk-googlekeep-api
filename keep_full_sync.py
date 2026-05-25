#!/usr/bin/env python3
"""
Keep Full Sync — Extracts FULL note content from Google Keep via browser automation.
Uses the already-logged-in Chrome profile (no API auth needed).
Opens each note, selects all text, and reads the full content.

Usage:
    python keep_full_sync.py
    python keep_full_sync.py --section main      # only main notes
    python keep_full_sync.py --section archive   # only archived notes
"""

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ERROR: playwright is not installed.")
    print("Run: pip install playwright")
    print("Then: playwright install chromium")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
VAULT_DIR = Path(r"C:\dev\Desktop-Projects\Helpful-Docs-Prompts\VAULTS-OBSIDIAN\Notesandclippings\Notesandclippings\Keep Notes")
STATE_FILE = Path(__file__).parent / "keep_full_sync_state.json"
CHROME_PROFILE = Path(r"C:\Users\prest\keepapi-mcp\chrome_profile")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '_', name).strip()
    name = re.sub(r'^[.\s]+|[.\s]+$', '', name)
    return name[:100] or "untitled"


def note_to_markdown(note: dict) -> str:
    fm = {
        "title": note.get("title", ""),
        "source": "google_keep",
        "source_section": note.get("source_section", "main"),
        "color": note.get("color", ""),
        "pinned": note.get("pinned", False),
        "archived": note.get("archived", False),
        "labels": note.get("labels", []),
        "is_list": note.get("is_list", False),
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
    if fm["title"]:
        md += f"# {fm['title']}\n\n"
    if fm["is_list"] and note.get("items"):
        for txt, checked in note["items"]:
            md += f"- {'[x]' if checked else '[ ]'} {txt}\n"
        md += "\n"
    elif note.get("text"):
        md += f"{note['text']}\n\n"
    md += "---\n*Imported from Google Keep*"
    return md


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"hashes": [], "last_run": None}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def content_hash(title: str, text: str, items: list) -> str:
    payload = f"{title}|{text}|{json.dumps(items, default=str)}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------
def close_editor(page):
    """Close any open note editor."""
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        editor = page.locator('div[role="dialog"]').first
        if editor.is_visible(timeout=500):
            page.mouse.click(10, 10)
            page.wait_for_timeout(300)
    except Exception:
        pass


def get_color(card) -> str:
    colors = ['White', 'Red', 'Orange', 'Yellow', 'Green', 'Teal', 'Blue', 'DarkBlue', 'Purple', 'Pink', 'Brown', 'Gray']
    cls = card.evaluate('el => el.className || ""')
    for c in colors:
        if c in cls:
            return c
    return ""


def is_pinned(card) -> bool:
    return card.locator('[data-tooltip-text*="Unpin"], [aria-label*="Unpin"]').count() > 0


def is_archived(card) -> bool:
    return card.locator('[data-tooltip-text*="Unarchive"], [aria-label*="Unarchive"]').count() > 0


def extract_note_full(page, card, section: str, prior_hashes: set) -> dict | None:
    """Click a card, select all in editor, extract full text, close."""
    try:
        # Get preview for dedupe key and title hint
        preview = card.inner_text(timeout=2000).strip()
        if not preview or preview.startswith("Take a note"):
            return None

        preview_lines = [l.strip() for l in preview.split('\n') if l.strip()]
        preview_title = preview_lines[0][:200] if preview_lines else ""

        # Click to open editor
        card.click(timeout=5000)
        page.wait_for_timeout(1500)

        editor = page.locator('div[role="dialog"]').first
        if not editor.is_visible(timeout=3000):
            print(f"    Editor didn't open — using preview fallback.")
            text = '\n'.join(preview_lines[1:]).strip() if len(preview_lines) > 1 else ""
            h = content_hash(preview_title, text, [])
            if h in prior_hashes:
                return None
            return {
                "title": preview_title,
                "text": text,
                "is_list": False,
                "items": [],
                "color": get_color(card),
                "pinned": is_pinned(card),
                "archived": is_archived(card),
                "labels": [],
                "source_section": section,
            }

        # Focus editor and select all
        editor.click(timeout=3000)
        page.wait_for_timeout(300)
        page.keyboard.press("Control+a")
        page.wait_for_timeout(400)

        # Read full selected text
        full_text = page.evaluate("() => window.getSelection().toString()")
        full_text = full_text.strip() if full_text else ""

        # Extract checklist items from DOM (selection doesn't preserve checkbox state)
        items = []
        cb_locator = editor.locator('input[type="checkbox"]')
        cb_count = cb_locator.count()
        if cb_count > 0:
            for j in range(cb_count):
                cb = cb_locator.nth(j)
                checked = cb.is_checked()
                txt = cb.evaluate(
                    'el => {'
                    '  let row = el.closest("div");'
                    '  if (!row) return "";'
                    '  let t = row.querySelector("span, [contenteditable], .IZ65Hb-YPqjbf");'
                    '  if (!t && row.nextElementSibling) {'
                    '    t = row.nextElementSibling.querySelector("span, [contenteditable], .IZ65Hb-YPqjbf");'
                    '  }'
                    '  return t ? t.innerText.trim() : ""'
                    '}'
                )
                if txt:
                    items.append([txt, checked])

        close_editor(page)

        # Parse title and body from full text
        lines = [l.strip() for l in full_text.split('\n') if l.strip()]
        if not lines:
            return None

        # First line: if it matches the preview title, use as title
        # Otherwise the note might be untitled
        title = ""
        body_lines = lines[:]
        if preview_title and lines[0] == preview_title:
            title = lines[0][:200]
            body_lines = lines[1:]
        elif len(lines) > 1 and len(lines[0]) < 200:
            # Heuristic: if first line is short and distinct, treat as title
            title = lines[0][:200]
            body_lines = lines[1:]
        # else: untitled note, keep all lines as body

        body = '\n'.join(body_lines).strip()
        is_list = len(items) > 0

        # Deduplicate
        h = content_hash(title, body, items)
        if h in prior_hashes:
            return None

        return {
            "title": title,
            "text": body,
            "is_list": is_list,
            "items": items,
            "color": get_color(card),
            "pinned": is_pinned(card),
            "archived": is_archived(card),
            "labels": [],
            "source_section": section,
        }

    except Exception as e:
        print(f"    Error: {e}")
        close_editor(page)
        return None


# ---------------------------------------------------------------------------
# Page-level extraction
# ---------------------------------------------------------------------------
def extract_section(page, section_name: str, prior_hashes: set) -> list:
    url = page.url
    if "accounts.google.com" in url or "signin" in url:
        print(f"  WARNING: Not logged in. Skipping {section_name}.")
        return []

    print(f"\n[{section_name.upper()}] Extracting notes...")
    page.wait_for_timeout(2000)

    # Scroll to load all cards
    print("  Scrolling to load all cards...")
    prev_height = 0
    stable = 0
    for _ in range(50):
        page.evaluate('() => { const m = document.querySelector(\'[role="main"]\') || document.body; m.scrollTop = m.scrollHeight; }')
        page.wait_for_timeout(300)
        curr_height = page.evaluate('() => { const m = document.querySelector(\'[role="main"]\') || document.body; return m.scrollHeight; }')
        if curr_height == prev_height:
            stable += 1
            if stable >= 3:
                break
        else:
            stable = 0
        prev_height = curr_height

    card_locator = page.locator('.IZ65Hb-n0tgWb')
    total = card_locator.count()
    print(f"  Found {total} cards.")

    notes = []
    seen_previews = set()

    for i in range(total):
        card = card_locator.nth(i)
        try:
            preview = card.inner_text(timeout=2000).strip()
        except Exception:
            continue

        if not preview or preview.startswith("Take a note"):
            continue

        key = preview[:60]
        if key in seen_previews:
            continue
        seen_previews.add(key)

        print(f"  [{i+1}/{total}] {preview[:50]}{'...' if len(preview) > 50 else ''}")
        note = extract_note_full(page, card, section_name, prior_hashes)
        if note:
            notes.append(note)
            prior_hashes.add(content_hash(note["title"], note["text"], note["items"]))

    return notes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Full Keep note extraction via browser")
    parser.add_argument("--section", choices=["main", "archive", "trash", "all"], default="all",
                        help="Which section to extract (default: all)")
    parser.add_argument("--vault", default=str(VAULT_DIR), help="Output vault directory")
    args = parser.parse_args()

    vault_dir = Path(args.vault)
    state = load_state()
    prior_hashes = set(state.get("hashes", []))

    print("=" * 60)
    print("Keep Full Sync — Extracts full note content via browser")
    print("=" * 60)
    print(f"Vault: {vault_dir}")
    print(f"Sections: {args.section}")
    print("Launching Chrome with existing profile...")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(CHROME_PROFILE),
            headless=False,
            args=["--disable-background-timer-throttling",
                  "--disable-backgrounding-occluded-windows",
                  "--disable-renderer-backgrounding"]
        )
        page = context.pages[0] if context.pages else context.new_page()

        all_notes = []
        sections = []

        if args.section in ("main", "all"):
            sections.append("main")
        if args.section in ("archive", "all"):
            sections.append("archive")
        if args.section in ("trash", "all"):
            sections.append("trash")

        try:
            for section in sections:
                if section == "main":
                    if "keep.google.com" not in page.url:
                        page.goto("https://keep.google.com", wait_until="domcontentloaded")
                elif section == "archive":
                    page.goto("https://keep.google.com/u/0/#archive", wait_until="domcontentloaded")
                elif section == "trash":
                    page.goto("https://keep.google.com/u/0/#trash", wait_until="domcontentloaded")

                notes = extract_section(page, section, prior_hashes)
                all_notes.extend(notes)
        except Exception as e:
            print(f"\nUnexpected error: {e}")
        finally:
            print("\nClosing Chrome...")
            context.close()

    # Save notes
    vault_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    for note in all_notes:
        md = note_to_markdown(note)
        fname = sanitize_filename(note["title"] or "untitled")
        if note["source_section"] != "main":
            fname = f"{note['source_section']}_{fname}"
        path = vault_dir / f"{fname}.md"
        ctr = 1
        while path.exists():
            path = vault_dir / f"{fname}_{ctr}.md"
            ctr += 1
        path.write_text(md, encoding="utf-8")
        print(f"  Saved: {path.name}")
        saved += 1

    # Update state
    if all_notes:
        new_hashes = [content_hash(n["title"], n["text"], n["items"]) for n in all_notes]
        state["hashes"] = list(prior_hashes | set(new_hashes))
        state["last_run"] = datetime.now(timezone.utc).isoformat()
        save_state(state)

    print(f"\nDone: {saved} new note(s) saved. {len(prior_hashes)} total tracked.")


if __name__ == "__main__":
    main()
