#!/usr/bin/env python3
"""
Extract Google Keep notes by connecting to a RUNNING Chrome instance via CDP.

USAGE:
    # Manual Chrome launch:
    chrome --remote-debugging-port=9333
    # Then run:
    python extract_keep_cdp.py

    # Or use the automation wrapper:
    .\\keep_automation.ps1
"""

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

DEFAULT_VAULT = r"C:\dev\Desktop-Projects\Helpful-Docs-Prompts\VAULTS-OBSIDIAN\Notesandclippings\Notesandclippings\Untitled"
CDP_URL = "http://localhost:9333"
OBSERVATION_FILE = Path(__file__).with_name("observations.jsonl")
MANIFEST_FILE = Path(__file__).with_name("manifest.json")


def log_observation(record: dict):
    """Append structured observation to JSONL file."""
    with open(OBSERVATION_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def load_manifest() -> dict:
    """Load cross-run manifest of previously extracted note hashes."""
    if MANIFEST_FILE.exists():
        return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    return {"hashes": [], "last_run": None, "version": "1.0.0"}


def save_manifest(manifest: dict):
    """Save manifest with extracted note hashes."""
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    return name[:100] or "untitled"


def note_to_markdown(note: dict) -> str:
    title = note.get("title", "")
    text = note.get("text", "")
    color = note.get("color", "")
    pinned = note.get("pinned", False)
    archived = note.get("archived", False)
    labels = note.get("labels", [])
    is_list = note.get("is_list", False)
    items = note.get("items", [])

    fm = {
        "title": title,
        "source": "google_keep",
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
    if is_list and items:
        for txt, checked in items:
            md += f"- {'[x]' if checked else '[ ]'} {txt}\n"
        md += "\n"
    elif text:
        md += f"{text}\n\n"
    md += "---\n*Imported from Google Keep*\n"
    return md


def scroll_to_load_all(page):
    """Scroll the main content area to trigger lazy loading of all notes."""
    print("Scrolling to load all notes...")
    prev_height = 0
    stable_count = 0
    for _ in range(50):
        page.evaluate("""
            () => {
                const main = document.querySelector('[role="main"]') || document.body;
                main.scrollTop = main.scrollHeight;
            }
        """)
        time.sleep(0.3)
        curr_height = page.evaluate("""
            () => {
                const main = document.querySelector('[role="main"]') || document.body;
                return main.scrollHeight;
            }
        """)
        if curr_height == prev_height:
            stable_count += 1
            if stable_count >= 3:
                break
        else:
            stable_count = 0
        prev_height = curr_height
    print(f"Finished scrolling (height stabilized at {prev_height}px).")
    return prev_height


def extract_notes(page, vault_dir: Path):
    """Extract notes from the Keep page using class-agnostic selectors."""
    url = page.url
    print(f"Current URL: {url}")
    if "accounts.google.com" in url or "signin" in url:
        print("\n" + "="*60)
        print("SESSION EXPIRED - FIRST-RUN SETUP REQUIRED")
        print("="*60)
        print("You are not logged into Google in this Chrome instance.")
        print("Please log in to keep.google.com in the Chrome window,")
        print("then re-run this script.")
        print("="*60 + "\n")
        return [], False, 0, None

    print("Waiting for notes to load...")
    time.sleep(3)
    scroll_height = scroll_to_load_all(page)

    # Class-agnostic fallback selectors (ordered by specificity)
    selectors = [
        ".IZ65Hb-n0tgWb",           # Current known class
        "[data-test-id='note']",    # Semantic test ID (may exist)
        "[data-note-id]",           # Data attribute
        ".brCWhc",                   # Alternative card class
    ]

    best_selector = None
    best_count = 0
    for sel in selectors:
        count = page.locator(sel).count()
        if count > best_count:
            best_count = count
            best_selector = sel

    if not best_selector:
        print("Could not find notes with any selector. Saving debug screenshot...")
        debug_file = vault_dir / "keep_debug.png"
        try:
            page.screenshot(path=str(debug_file))
            print(f"Debug screenshot saved to {debug_file}")
        except Exception:
            pass
        return [], True, scroll_height, None

    print(f"Found {best_count} raw cards with selector: {best_selector}")

    print("Extracting note data...")
    raw_notes = page.evaluate(f"""
        () => {{
            const notes = [];
            const cards = document.querySelectorAll('{best_selector}');
            const seenTexts = new Set();

            cards.forEach(card => {{
                try {{
                    const fullText = card.innerText.trim();
                    if (!fullText || fullText.startsWith('Take a note')) return;

                    // Deduplicate masonry duplicates by first 200 chars
                    const key = fullText.substring(0, 200);
                    if (seenTexts.has(key)) return;
                    seenTexts.add(key);

                    // Title = first non-empty line, capped at 200 chars
                    const title = fullText.split('\\n').find(l => l.trim())?.substring(0, 200) || '';

                    // List items
                    const cbs = card.querySelectorAll('input[type="checkbox"]');
                    const isList = cbs.length > 0;
                    const items = [];
                    if (isList) {{
                        cbs.forEach(cb => {{
                            let row = cb.closest('div');
                            let textEl = null;
                            if (row) {{
                                textEl = row.querySelector('.IZ65Hb-YPqjbf, span, [contenteditable]');
                                if (!textEl && row.nextElementSibling) {{
                                    textEl = row.nextElementSibling.querySelector('.IZ65Hb-YPqjbf, span, [contenteditable]');
                                }}
                            }}
                            if (textEl) {{
                                items.push([textEl.innerText.trim(), cb.checked]);
                            }}
                        }});
                    }}

                    // Body text: full text minus title line
                    const lines = fullText.split('\\n');
                    const titleIdx = lines.findIndex(l => l.trim());
                    const bodyLines = lines.slice(titleIdx + 1);
                    let text = bodyLines.join('\\n').trim();
                    if (!text) text = fullText;

                    // Color
                    let color = '';
                    const cls = card.className || '';
                    const colors = ['White','Red','Orange','Yellow','Green','Teal','Blue','DarkBlue','Purple','Pink','Brown','Gray'];
                    for (const c of colors) {{
                        if (cls.includes(c)) {{ color = c; break; }}
                    }}

                    const pinned = !!card.querySelector('[data-tooltip-text*="Unpin"], [aria-label*="Unpin"]');
                    const archived = !!card.querySelector('[data-tooltip-text*="Unarchive"], [aria-label*="Unarchive"]');
                    const labelEls = card.querySelectorAll('[data-tooltip-text*="Label"]');
                    const labels = Array.from(labelEls).map(e => e.innerText.trim()).filter(Boolean);

                    notes.push({{ title, text, is_list: isList, items, color, pinned, archived, labels }});
                }} catch(e) {{}}
            }});
            return notes;
        }}
    """)
    return raw_notes, True, scroll_height, best_selector


def save_notes(notes, vault_dir: Path):
    vault_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    prior_hashes = set(manifest.get("hashes", []))

    seen = set()
    saved = 0
    skipped = 0
    new_hashes = []

    for note in notes:
        key = hashlib.sha256(
            (note.get("title", "") + "|" + note.get("text", "") + "|" + json.dumps(note.get("items", []))).encode()
        ).hexdigest()[:16]

        if key in seen or key in prior_hashes:
            skipped += 1
            continue
        seen.add(key)
        new_hashes.append(key)

        fname = sanitize_filename(note.get("title", "untitled"))
        path = vault_dir / f"{fname}.md"
        ctr = 1
        while path.exists():
            path = vault_dir / f"{fname}_{ctr}.md"
            ctr += 1
        path.write_text(note_to_markdown(note), encoding="utf-8")
        saved += 1
        print(f"  Saved: {path.name}")

    # Update manifest
    manifest["hashes"] = list(prior_hashes | set(new_hashes))
    manifest["last_run"] = datetime.now(timezone.utc).isoformat()
    manifest["version"] = "1.0.0"
    save_manifest(manifest)

    print(f"\nDone: {saved} saved, {skipped} skipped (already in vault), {len(notes)} total unique")
    return saved, skipped


def main():
    parser = argparse.ArgumentParser(description="Extract Google Keep notes via Chrome CDP")
    parser.add_argument("--vault", default=DEFAULT_VAULT, help="Target Obsidian vault directory")
    parser.add_argument("--port", type=int, default=9333, help="Chrome remote debugging port")
    args = parser.parse_args()

    vault_dir = Path(args.vault)
    start_time = time.time()
    observation = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "skill_version": "1.0.0",
        "success": False,
        "notes_found": 0,
        "notes_extracted": 0,
        "notes_saved": 0,
        "notes_skipped": 0,
        "vault_dir": str(vault_dir),
        "chrome_port": args.port,
        "chrome_reused": False,
        "session_valid": False,
        "scroll_height_px": 0,
        "card_selector_used": None,
        "errors": [],
        "warnings": [],
        "duration_seconds": 0.0,
    }

    print("="*60)
    print("Google Keep to Obsidian Vault Extractor")
    print("="*60)

    cdp_url = f"http://localhost:{args.port}"
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.connect_over_cdp(cdp_url)
                observation["chrome_reused"] = True
            except Exception as e:
                observation["errors"].append(f"CDP connection failed: {e}")
                print(f"ERROR: Could not connect to Chrome at {cdp_url}")
                print(f"       {e}")
                print(f"\nMake sure Chrome is running with: --remote-debugging-port={args.port}")
                log_observation(observation)
                sys.exit(1)

            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()

            if "keep.google.com" not in page.url:
                print("Navigating to keep.google.com...")
                page.goto("https://keep.google.com", wait_until="domcontentloaded")
            else:
                print("Already on keep.google.com.")

            notes, session_valid, scroll_height, card_selector = extract_notes(page, vault_dir)
            observation["session_valid"] = session_valid
            observation["scroll_height_px"] = scroll_height
            observation["card_selector_used"] = card_selector

            if not session_valid:
                observation["errors"].append("Session expired or not logged in")
                log_observation(observation)
                sys.exit(1)

            observation["notes_found"] = len(notes)
            observation["notes_extracted"] = len(notes)

            if notes:
                saved, skipped = save_notes(notes, vault_dir)
                observation["notes_saved"] = saved
                observation["notes_skipped"] = skipped
                observation["success"] = True
            else:
                print("No notes extracted.")
                observation["warnings"].append("No notes found after scrolling")

    except Exception as e:
        observation["errors"].append(str(e))
        print(f"Unexpected error: {e}")
    finally:
        observation["duration_seconds"] = round(time.time() - start_time, 2)
        log_observation(observation)

    if not observation["success"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
