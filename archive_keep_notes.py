#!/usr/bin/env python3
"""
Archive all notes in the Google Keep MAIN view.
Uses Chrome CDP to click the Archive action on each note card.
"""

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

CDP_URL = "http://localhost:9333"


def archive_notes():
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"WARNING: Could not connect to Chrome at {CDP_URL}")
            print(f"         {e}")
            print("Running self-healing cleanup...")
            import subprocess
            cleanup_script = Path(__file__).with_name("cleanup-chrome.ps1")
            if cleanup_script.exists():
                subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(cleanup_script)],
                               capture_output=True)
            else:
                subprocess.run(["powershell", "-Command",
                                "Get-NetTCPConnection -LocalPort 9333 -ErrorAction SilentlyContinue | "
                                "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"],
                               capture_output=True)
            time.sleep(3)
            print("Retrying CDP connection...")
            try:
                browser = p.chromium.connect_over_cdp(CDP_URL)
                print("Reconnected successfully after cleanup.")
            except Exception as e2:
                print(f"ERROR: Could not connect to Chrome at {CDP_URL} even after cleanup.")
                print("       {e2}")
                print("\nMake sure Chrome is running with: --remote-debugging-port=9333")
                return 0

        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()

        if "keep.google.com" not in page.url:
            print("Navigating to keep.google.com...")
            page.goto("https://keep.google.com", wait_until="domcontentloaded")
        else:
            print("Already on keep.google.com.")

        url = page.url
        if "accounts.google.com" in url or "signin" in url:
            print("ERROR: Not logged into Google. Please log in first.")
            return 0

        print("Waiting for notes to load...")
        time.sleep(3)

        # Find note cards
        card_selector = ".IZ65Hb-n0tgWb"
        cards = page.locator(card_selector).all()
        print(f"Found {len(cards)} raw cards.")

        archived = 0
        skipped = 0

        for i, card in enumerate(cards):
            # Check if this is the composer bar
            is_composer = card.evaluate("el => el.innerText.trim().startsWith('Take a note')")
            if is_composer:
                print(f"  [{i}] Skipping composer bar")
                skipped += 1
                continue

            # Check if already archived
            is_archived = card.evaluate("""
                el => !!el.querySelector('[data-tooltip-text*="Unarchive"], [aria-label*="Unarchive"]')
            """)
            if is_archived:
                print(f"  [{i}] Already archived")
                skipped += 1
                continue

            # Get title for logging
            title = card.evaluate("""
                el => {
                    const text = el.innerText.trim();
                    const firstLine = text.split('\\n').find(l => l.trim());
                    return firstLine ? firstLine.substring(0, 60) : '(no title)';
                }
            """)

            # Find and click the Archive button
            # Strategy: look for the more-actions menu (three dots) and click Archive
            # OR look for a direct archive button with tooltip
            archive_clicked = card.evaluate("""
                el => {
                    // Try direct archive button first
                    let btn = el.querySelector('[data-tooltip-text="Archive note"]');
                    if (btn) { btn.click(); return true; }

                    // Try aria-label
                    btn = el.querySelector('[aria-label="Archive note"]');
                    if (btn) { btn.click(); return true; }

                    // Try the more-actions menu (three dots)
                    const moreBtn = el.querySelector('[data-tooltip-text="More"]') ||
                                      el.querySelector('[aria-label="More"]');
                    if (moreBtn) {
                        moreBtn.click();
                        // Wait for menu to appear, then click Archive
                        setTimeout(() => {
                            const menuItems = document.querySelectorAll('[role="menuitem"]');
                            for (const item of menuItems) {
                                if (item.innerText.includes('Archive')) {
                                    item.click();
                                    return true;
                                }
                            }
                        }, 300);
                        return true;
                    }
                    return false;
                }
            """)

            if archive_clicked:
                print(f"  [{i}] Archiving: {title}")
                archived += 1
                time.sleep(0.8)  # Wait for UI animation
            else:
                print(f"  [{i}] Could not find archive button for: {title}")

        browser.close()
        return archived


if __name__ == "__main__":
    print("="*60)
    print("Archiving Google Keep Main Notes")
    print("="*60)
    count = archive_notes()
    print(f"\nDone: {count} notes archived.")
    if count == 0:
        sys.exit(1)
    # Always close automation Chrome to avoid interfering with user's browser
    print("Closing automation Chrome...")
    import subprocess
    subprocess.run(['powershell', '-Command',
        'Get-Process chrome -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*chrome_profile*" } | Stop-Process -Force'],
        capture_output=True)
