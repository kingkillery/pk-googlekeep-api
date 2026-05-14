#!/usr/bin/env python3
"""
Extract ALL Google Keep notes: Main, Archive, and Trash.
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


def log_observation(record: dict):
    OBS_FILE = Path(__file__).with_name("observations.jsonl")
    with open(OBS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def load_manifest() -> dict:
    MANIFEST_FILE = Path(__file__).with_name("manifest.json")
    if MANIFEST_FILE.exists():
        return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    return {"hashes": [], "last_run": None, "version": "1.0.0"}


def save_manifest(manifest: dict):
    MANIFEST_FILE = Path(__file__).with_name("manifest.json")
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
    source_section = note.get("source_section", "main")

    fm = {
        "title": title,
        "source": "google_keep",
        "source_section": source_section,
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
    print("  Scrolling to load all notes...")
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
    return prev_height


def extract_from_section(page, section_name: str, vault_dir: Path, prior_hashes: set):
    """Extract notes from the current page section."""
    url = page.url
    print(f"  Current URL: {url}")

    if "accounts.google.com" in url or "signin" in url:
        print(f"  WARNING: Not logged in on {section_name}. Skipping.")
        return [], 0

    time.sleep(3)
    scroll_height = scroll_to_load_all(page)

    selectors = [
        ".IZ65Hb-n0tgWb",
        "[data-test-id='note']",
        "[data-note-id]",
        ".brCWhc",
    ]

    best_selector = None
    best_count = 0
    for sel in selectors:
        count = page.locator(sel).count()
        if count > best_count:
            best_count = count
            best_selector = sel

    if not best_selector:
        print(f"  No notes found in {section_name}.")
        return [], 0

    print(f"  Found {best_count} raw cards in {section_name} with {best_selector}")

    notes = page.evaluate(f"""
        () => {{
            const notes = [];
            const cards = document.querySelectorAll('{best_selector}');
            const seenTexts = new Set();

            cards.forEach(card => {{
                try {{
                    const fullText = card.innerText.trim();
                    if (!fullText || fullText.startsWith('Take a note')) return;

                    const key = fullText.substring(0, 200);
                    if (seenTexts.has(key)) return;
                    seenTexts.add(key);

                    const title = fullText.split('\\n').find(l => l.trim())?.substring(0, 200) || '';

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

                    const lines = fullText.split('\\n');
                    const titleIdx = lines.findIndex(l => l.trim());
                    const bodyLines = lines.slice(titleIdx + 1);
                    let text = bodyLines.join('\\n').trim();
                    if (!text) text = fullText;

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

                    notes.push({{ title, text, is_list: isList, items, color, pinned, archived, labels, source_section: '{section_name}' }});
                }} catch(e) {{}}
            }});
            return notes;
        }}
    """)
    return notes, scroll_height


def save_notes(notes, vault_dir: Path, prior_hashes: set):
    vault_dir.mkdir(parents=True, exist_ok=True)
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

        section = note.get("source_section", "main")
        fname = sanitize_filename(note.get("title", "untitled"))
        if section != "main":
            fname = f"{section}_{fname}"
        path = vault_dir / f"{fname}.md"
        ctr = 1
        while path.exists():
            path = vault_dir / f"{fname}_{ctr}.md"
            ctr += 1
        path.write_text(note_to_markdown(note), encoding="utf-8")
        saved += 1
        print(f"    Saved: {path.name}")

    return saved, skipped, new_hashes


def main():
    parser = argparse.ArgumentParser(description="Extract ALL Google Keep notes")
    parser.add_argument("--vault", default=DEFAULT_VAULT, help="Target Obsidian vault directory")
    parser.add_argument("--port", type=int, default=9333, help="Chrome remote debugging port")
    args = parser.parse_args()

    vault_dir = Path(args.vault)
    start_time = time.time()
    observation = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "skill_version": "1.1.0",
        "success": False,
        "sections": {},
        "total_saved": 0,
        "total_skipped": 0,
        "vault_dir": str(vault_dir),
        "chrome_port": args.port,
        "errors": [],
        "warnings": [],
        "duration_seconds": 0.0,
    }

    print("="*60)
    print("Google Keep FULL Extraction (Main + Archive + Trash)")
    print("="*60)

    manifest = load_manifest()
    prior_hashes = set(manifest.get("hashes", []))

    cdp_url = f"http://localhost:{args.port}"
    browser = None
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.connect_over_cdp(cdp_url)
            except Exception as e:
                print(f"WARNING: CDP connection failed: {e}")
                print("Running self-healing cleanup...")
                import subprocess
                cleanup_script = Path(__file__).with_name("cleanup-chrome.ps1")
                if cleanup_script.exists():
                    subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(cleanup_script)],
                                   capture_output=True)
                else:
                    # Fallback: kill chrome on port directly
                    subprocess.run(["powershell", "-Command",
                                    f"Get-NetTCPConnection -LocalPort {args.port} -ErrorAction SilentlyContinue | "
                                    "ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}"],
                                   capture_output=True)
                time.sleep(3)
                print("Retrying CDP connection...")
                try:
                    browser = p.chromium.connect_over_cdp(cdp_url)
                    print("Reconnected successfully after cleanup.")
                except Exception as e2:
                    observation["errors"].append(f"CDP connection failed after cleanup: {e2}")
                    print(f"ERROR: Could not connect to Chrome at {cdp_url} even after cleanup.")
                    print("Please run .\\cleanup-chrome.ps1 manually, then try again.")
                    log_observation(observation)
                    sys.exit(1)

            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()

            all_notes = []

            # Section 1: Main Notes
            print("\n[1/3] Extracting MAIN notes...")
            if "keep.google.com" not in page.url:
                page.goto("https://keep.google.com", wait_until="domcontentloaded")
            notes, scroll_h = extract_from_section(page, "main", vault_dir, prior_hashes)
            all_notes.extend(notes)
            observation["sections"]["main"] = {"found": len(notes), "scroll_height": scroll_h}

            # Section 2: Archive
            print("\n[2/3] Extracting ARCHIVED notes...")
            page.goto("https://keep.google.com/u/0/#archive", wait_until="domcontentloaded")
            time.sleep(2)
            notes, scroll_h = extract_from_section(page, "archive", vault_dir, prior_hashes)
            all_notes.extend(notes)
            observation["sections"]["archive"] = {"found": len(notes), "scroll_height": scroll_h}

            # Section 3: Trash
            print("\n[3/3] Extracting TRASHED notes...")
            page.goto("https://keep.google.com/u/0/#trash", wait_until="domcontentloaded")
            time.sleep(2)
            notes, scroll_h = extract_from_section(page, "trash", vault_dir, prior_hashes)
            all_notes.extend(notes)
            observation["sections"]["trash"] = {"found": len(notes), "scroll_height": scroll_h}

            # Save all unique notes
            if all_notes:
                saved, skipped, new_hashes = save_notes(all_notes, vault_dir, prior_hashes)
                observation["total_saved"] = saved
                observation["total_skipped"] = skipped
                observation["success"] = True

                manifest["hashes"] = list(prior_hashes | set(new_hashes))
                manifest["last_run"] = datetime.now(timezone.utc).isoformat()
                manifest["version"] = "1.1.0"
                save_manifest(manifest)
            else:
                print("\nNo notes found in any section.")
                observation["warnings"].append("No notes found in any section")

    except Exception as e:
        observation["errors"].append(str(e))
        print(f"Unexpected error: {e}")
    finally:
        observation["duration_seconds"] = round(time.time() - start_time, 2)
        log_observation(observation)
        # Always close browser to avoid interfering with user's normal Chrome
        if browser:
            try:
                browser.close()
                print("Browser closed.")
            except Exception:
                pass

    if observation["success"]:
        print(f"\nDone: {observation['total_saved']} saved, {observation['total_skipped']} skipped across all sections.")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
