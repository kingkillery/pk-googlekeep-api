#!/usr/bin/env python3
"""
Keep Live Extractor — Full Note Edition
Opens a visible Chrome window on Google Keep, injects a "Save to Vault" button,
and writes FULL note contents (by opening each note editor) directly to disk.

Usage:
    python keep_live_extractor.py
"""

import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# Output directory
VAULT_DIR = Path(__file__).parent


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


def save_notes(notes: list) -> int:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    saved = 0
    for note in notes:
        md = note_to_markdown(note)
        fname = sanitize_filename(note.get("title", "untitled"))
        section = note.get("source_section", "main")
        if section != "main":
            fname = f"{section}_{fname}"
        path = VAULT_DIR / f"{fname}.md"
        ctr = 1
        while path.exists():
            path = VAULT_DIR / f"{fname}_{ctr}.md"
            ctr += 1
        path.write_text(md, encoding="utf-8")
        print(f"  Saved: {path.name}")
        saved += 1
    return saved


def detect_section(page) -> str:
    url = page.url
    if "#archive" in url:
        return "archive"
    if "#trash" in url:
        return "trash"
    return "main"


def get_color_from_card(card) -> str:
    colors = ['White', 'Red', 'Orange', 'Yellow', 'Green', 'Teal', 'Blue', 'DarkBlue', 'Purple', 'Pink', 'Brown', 'Gray']
    cls = card.evaluate('el => el.className || ""')
    for c in colors:
        if c in cls:
            return c
    return ""


def is_pinned_card(card) -> bool:
    return card.locator('[data-tooltip-text*="Unpin"], [aria-label*="Unpin"]').count() > 0


def is_archived_card(card) -> bool:
    return card.locator('[data-tooltip-text*="Unarchive"], [aria-label*="Unarchive"]').count() > 0


def close_editor(page):
    """Press Escape and/or click outside to close any open note editor."""
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        # If still open, click outside
        editor = page.locator('div[role="dialog"]').first
        if editor.is_visible(timeout=500):
            page.mouse.click(10, 10)
            page.wait_for_timeout(300)
    except Exception:
        pass


def extract_full_note(page, card) -> dict | None:
    """Click a card, extract full content from the editor, close editor."""
    try:
        # Click card to open editor
        card.click(timeout=5000)
        page.wait_for_timeout(1200)

        # Wait for editor dialog
        editor = page.locator('div[role="dialog"]').first
        if not editor.is_visible(timeout=3000):
            print("    Editor did not open — using card preview fallback.")
            preview = card.inner_text().strip()
            lines = [l.strip() for l in preview.split('\n') if l.strip()]
            title = lines[0][:200] if lines else ''
            text = '\n'.join(lines[1:]).strip() if len(lines) > 1 else ''
            return {
                'title': title,
                'text': text,
                'is_list': False,
                'items': [],
            }

        # Extract clean content from contenteditable areas inside the editor
        # Google Keep puts note text in [contenteditable="true"] divs
        editables = editor.locator('[contenteditable="true"]').all()
        texts = []
        for el in editables:
            txt = el.inner_text().strip()
            if txt:
                texts.append(txt)

        # Determine title and body
        if len(texts) >= 2:
            title = texts[0][:200]
            body = '\n'.join(texts[1:]).strip()
        elif len(texts) == 1:
            # Could be untitled note with only body
            title = ''
            body = texts[0]
        else:
            # Fallback to editor innerText (may include UI labels)
            full = editor.inner_text().strip()
            lines = [l.strip() for l in full.split('\n') if l.strip()]
            # Filter known UI labels
            ui_labels = {'Close', 'Delete note', 'Make a copy', 'Copy to Google Docs',
                         'Show tick boxes', 'Hide tick boxes', 'Pin note', 'Unpin note',
                         'Archive', 'Unarchive', 'Change color', 'Add label', 'Add drawing',
                         'Add image', 'Remind me', 'Collaborator', 'Send', 'More'}
            filtered = [l for l in lines if l not in ui_labels]
            title = filtered[0][:200] if filtered else ''
            body = '\n'.join(filtered[1:]).strip() if len(filtered) > 1 else ''

        # Extract checkboxes from the editor
        items = []
        cb_locator = editor.locator('input[type="checkbox"]')
        cb_count = cb_locator.count()
        if cb_count > 0:
            for j in range(cb_count):
                cb = cb_locator.nth(j)
                checked = cb.is_checked()
                # Try to find associated text via JS
                item_text = cb.evaluate(
                    'el => {'
                    '  let row = el.closest("div");'
                    '  if (!row) return "";'
                    '  let txt = row.querySelector("span, [contenteditable], .IZ65Hb-YPqjbf");'
                    '  if (!txt && row.nextElementSibling) {'
                    '    txt = row.nextElementSibling.querySelector("span, [contenteditable], .IZ65Hb-YPqjbf");'
                    '  }'
                    '  return txt ? txt.innerText.trim() : ""'
                    '}'
                )
                if item_text:
                    items.append([item_text, checked])

        close_editor(page)

        return {
            'title': title,
            'text': body,
            'is_list': len(items) > 0,
            'items': items,
        }

    except Exception as e:
        print(f"    Error extracting note: {e}")
        close_editor(page)
        return None


def extract_all_notes_from_page(page) -> list:
    """Extract all notes from the current Keep view by opening each card."""
    section = detect_section(page)
    notes = []
    seen_keys = set()

    card_locator = page.locator('.IZ65Hb-n0tgWb')
    total_cards = card_locator.count()
    print(f"  Found {total_cards} cards on page. Opening each to extract full content...")

    for i in range(total_cards):
        card = card_locator.nth(i)
        try:
            preview = card.inner_text(timeout=2000).strip()
        except Exception:
            continue

        if not preview or preview.startswith('Take a note'):
            continue

        key = preview[:60]
        if key in seen_keys:
            continue
        seen_keys.add(key)

        print(f"  [{i+1}/{total_cards}] Extracting: {preview[:50]}{'...' if len(preview) > 50 else ''}")
        note_data = extract_full_note(page, card)

        if note_data:
            # Enrich with card metadata
            note_data['color'] = get_color_from_card(card)
            note_data['pinned'] = is_pinned_card(card)
            note_data['archived'] = is_archived_card(card)
            note_data['labels'] = []  # Best-effort; editor labels are tricky
            note_data['source_section'] = section
            notes.append(note_data)

    return notes


INJECT_JS = r"""
(function() {
    const BTN_ID = 'keep-vault-export-btn';
    if (document.getElementById(BTN_ID)) return;

    const btn = document.createElement('button');
    btn.id = BTN_ID;
    btn.innerText = '💾 Save to Vault';
    btn.style.cssText = 'position:fixed;top:16px;right:16px;z-index:99999;padding:12px 20px;background:#1a73e8;color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:bold;cursor:pointer;box-shadow:0 4px 12px rgba(0,0,0,0.3);font-family:system-ui,-apple-system,sans-serif;';
    btn.onclick = async () => {
        btn.innerText = '⏳ Extracting...';
        btn.style.background = '#f9ab00';
        try {
            if (typeof pyExportNotes === 'function') {
                const result = await pyExportNotes({trigger: true});
                const saved = result?.saved || 0;
                btn.innerText = saved > 0 ? '✅ Saved ' + saved : '✅ Up to date';
                btn.style.background = '#188038';
            } else {
                btn.innerText = '❌ Not connected';
                btn.style.background = '#d93025';
            }
        } catch(e) {
            btn.innerText = '❌ Error';
            btn.style.background = '#d93025';
            console.error(e);
        }
        setTimeout(() => {
            btn.innerText = '💾 Save to Vault';
            btn.style.background = '#1a73e8';
        }, 3000);
    };
    document.body.appendChild(btn);

    // Keep-alive re-injection
    const observer = new MutationObserver(() => {
        if (!document.getElementById(BTN_ID)) {
            document.body.appendChild(btn);
        }
    });
    observer.observe(document.body, { childList: true, subtree: true });
})();
"""


def main():
    print("=" * 60)
    print("Keep Live Extractor — Full Note Edition")
    print("=" * 60)
    print(f"Vault output: {VAULT_DIR}")
    print("Launching Chrome...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        saved_count = {"total": 0}

        def handle_export(source, data):
            print("\n  Button clicked — extracting full notes from current view...")
            notes = extract_all_notes_from_page(page)
            if notes:
                count = save_notes(notes)
                saved_count["total"] += count
                print(f"  Total this session: {saved_count['total']} note(s) saved.")
                return {"saved": count}
            print("  No new notes found.")
            return {"saved": 0}

        page.expose_binding("pyExportNotes", handle_export)
        page.goto("https://keep.google.com")

        page.wait_for_selector("body", timeout=30000)
        page.add_script_tag(content=INJECT_JS)

        print("\nChrome is open. A blue 'Save to Vault' button is in the top-right.")
        print("Navigate to Main, Archive, or Trash and click the button.")
        print("Each note card will be opened to extract the FULL content.")
        print("Close the browser window when done.")
        print("=" * 60)

        try:
            while True:
                time.sleep(1)
                if not browser.is_connected():
                    break
                try:
                    has_btn = page.evaluate("() => !!document.getElementById('keep-vault-export-btn')")
                    if not has_btn:
                        page.add_script_tag(content=INJECT_JS)
                except Exception:
                    pass
        except KeyboardInterrupt:
            print("\nInterrupted by user.")
        finally:
            if browser.is_connected():
                browser.close()
            print(f"\nDone. Total notes saved this session: {saved_count['total']}")


if __name__ == "__main__":
    main()
