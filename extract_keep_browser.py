#!/usr/bin/env python3
"""
Extract Google Keep notes via browser automation using Playwright.
Assumes the user is already logged into Google in Chrome.
"""

import hashlib
import json
import os
import re
import time
import tempfile
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

VAULT_DIR = Path(r"C:\dev\Desktop-Projects\Helpful-Docs-Prompts\VAULTS-OBSIDIAN\Notesandclippings\Notesandclippings\Untitled")
CHROME_USER_DATA = Path(r"C:\Users\prest\AppData\Local\Google\Chrome\User Data")


def sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    if not name:
        name = "untitled"
    return name[:100]


def note_to_markdown(note_data: dict) -> str:
    """Convert a Keep note dict to Obsidian markdown."""
    title = note_data.get("title", "Untitled")
    text = note_data.get("text", "")
    color = note_data.get("color", "")
    pinned = note_data.get("pinned", False)
    archived = note_data.get("archived", False)
    labels = note_data.get("labels", [])
    is_list = note_data.get("is_list", False)
    items = note_data.get("items", [])
    created = note_data.get("created", "")
    updated = note_data.get("updated", "")

    frontmatter = {
        "title": title,
        "source": "google_keep",
        "color": color,
        "pinned": pinned,
        "archived": archived,
        "labels": labels,
        "is_list": is_list,
    }
    if created:
        frontmatter["created"] = created
    if updated:
        frontmatter["updated"] = updated

    md = "---\n"
    for k, v in frontmatter.items():
        if isinstance(v, list):
            md += f"{k}:\n"
            for item in v:
                md += f"  - {item}\n"
        elif isinstance(v, bool):
            md += f"{k}: {str(v).lower()}\n"
        else:
            md += f"{k}: {v}\n"
    md += "---\n\n"

    if title:
        md += f"# {title}\n\n"

    if is_list and items:
        for item_text, checked in items:
            checkbox = "[x]" if checked else "[ ]"
            md += f"- {checkbox} {item_text}\n"
        md += "\n"
    elif text:
        md += f"{text}\n\n"

    md += "---\n*Imported from Google Keep*\n"
    return md


def extract_notes_from_browser() -> list:
    """Use Playwright to extract notes from keep.google.com."""
    notes = []

    # Copy Chrome profile to temp dir to avoid lock conflicts with running Chrome
    temp_profile = Path(tempfile.mkdtemp(prefix="keep_chrome_"))
    print(f"Using temp profile: {temp_profile}")

    # Copy cookies and login state
    source_default = CHROME_USER_DATA / "Default"
    if source_default.exists():
        import shutil
        dest_default = temp_profile / "Default"
        # Only copy essential files (cookies, login data, etc.)
        dest_default.mkdir(parents=True, exist_ok=True)
        essential_files = ["Cookies", "Login Data", "Preferences", "Network", "Local State"]
        for fname in essential_files:
            src = source_default / fname
            if src.exists():
                if src.is_dir():
                    shutil.copytree(src, dest_default / fname, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dest_default / fname)
        # Also copy Local State from parent
        src_local = CHROME_USER_DATA / "Local State"
        if src_local.exists():
            shutil.copy2(src_local, temp_profile / "Local State")

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(temp_profile),
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )

        page = browser.new_page()
        print("Navigating to keep.google.com...")
        page.goto("https://keep.google.com", wait_until="networkidle")

        # Debug: save screenshot and HTML
        debug_dir = Path("C:\\Users\\prest\\keepapi-mcp\\debug")
        debug_dir.mkdir(exist_ok=True)
        page.screenshot(path=str(debug_dir / "keep_page.png"), full_page=True)
        (debug_dir / "keep_page.html").write_text(page.content(), encoding="utf-8")
        print(f"Debug saved to {debug_dir}")

        # Check for login state
        url = page.url
        print(f"Current URL: {url}")
        if "accounts.google.com" in url or "signin" in url:
            print("ERROR: Not logged into Google. Please log in first via Chrome.")
            browser.close()
            return []

        # Try multiple selectors for notes
        selectors = [
            "[role='listitem']",
            "[data-test-id='note']",
            "div[role='main'] [role='listitem']",
            "[data-note-id]",
            ".IZ65Hb-YPqjbf",
        ]

        found_selector = None
        for selector in selectors:
            try:
                page.wait_for_selector(selector, timeout=5000)
                found_selector = selector
                print(f"Found notes using selector: {selector}")
                break
            except Exception:
                continue

        if not found_selector:
            print("Could not find notes on the page.")
            print("The page may have a different structure or no notes exist.")
            browser.close()
            return []

        # Extract note data via JavaScript
        raw_notes = page.evaluate("""
            () => {
                const notes = [];
                const items = document.querySelectorAll('[role="listitem"]');
                items.forEach(item => {
                    try {
                        const titleEl = item.querySelector('div[role="heading"]');
                        const title = titleEl ? titleEl.innerText.trim() : '';

                        const contentEl = item.querySelector('[contenteditable="true"]');
                        const text = contentEl ? contentEl.innerText.trim() : '';

                        // Check for checkboxes (list items)
                        const checkboxes = item.querySelectorAll('input[type="checkbox"]');
                        const isList = checkboxes.length > 0;
                        const listItems = [];
                        if (isList) {
                            // Try to find list item text near each checkbox
                            const allDivs = item.querySelectorAll('div');
                            allDivs.forEach(div => {
                                const cb = div.querySelector('input[type="checkbox"]');
                                if (cb) {
                                    // Find text sibling
                                    let textNode = div.querySelector('span');
                                    if (!textNode) textNode = div.querySelector('div[contenteditable]');
                                    if (textNode) {
                                        listItems.push([textNode.innerText.trim(), cb.checked]);
                                    }
                                }
                            });
                        }

                        // Try to get color from classes
                        let color = '';
                        const classStr = item.className || '';
                        const colors = ['White','Red','Orange','Yellow','Green','Teal','Blue','DarkBlue','Purple','Pink','Brown','Gray'];
                        for (const c of colors) {
                            if (classStr.includes(c)) { color = c; break; }
                        }

                        const pinned = !!item.querySelector('[aria-label*="Unpin"], [data-tooltip*="Unpin"]');
                        const archived = !!item.querySelector('[aria-label*="Unarchive"]');

                        const labelEls = item.querySelectorAll('[data-tooltip*="Label"]');
                        const labels = Array.from(labelEls).map(el => el.innerText.trim()).filter(Boolean);

                        notes.push({
                            title,
                            text,
                            is_list: isList,
                            items: listItems,
                            color,
                            pinned,
                            archived,
                            labels
                        });
                    } catch (e) {
                        console.error('Error extracting note:', e);
                    }
                });
                return notes;
            }
        """)

        browser.close()
        return raw_notes


def save_notes_to_vault(notes: list):
    """Save extracted notes to Obsidian vault, skipping duplicates."""
    VAULT_DIR.mkdir(parents=True, exist_ok=True)

    seen_hashes = set()
    saved = 0
    skipped = 0

    for note in notes:
        content_key = (note.get("title", "") + "|" + note.get("text", "") + "|" + json.dumps(note.get("items", [])))
        content_hash = hashlib.sha256(content_key.encode()).hexdigest()[:16]

        if content_hash in seen_hashes:
            skipped += 1
            continue
        seen_hashes.add(content_hash)

        filename = sanitize_filename(note.get("title", "untitled"))
        filepath = VAULT_DIR / f"{filename}.md"

        counter = 1
        original_filepath = filepath
        while filepath.exists():
            filepath = VAULT_DIR / f"{filename}_{counter}.md"
            counter += 1

        markdown = note_to_markdown(note)
        filepath.write_text(markdown, encoding="utf-8")
        saved += 1
        print(f"  Saved: {filepath.name}")

    print(f"\nDone: {saved} saved, {skipped} duplicates skipped, {len(notes)} total")


if __name__ == "__main__":
    print("Extracting Google Keep notes via browser...")
    notes = extract_notes_from_browser()
    print(f"Found {len(notes)} notes")
    if notes:
        save_notes_to_vault(notes)
    else:
        print("No notes found.")
