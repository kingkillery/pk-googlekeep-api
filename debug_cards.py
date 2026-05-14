from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp('http://localhost:9333')
    page = browser.contexts[0].pages[0]

    cards = page.locator('.IZ65Hb-n0tgWb').all()
    print(f"Found {len(cards)} cards")

    for i, card in enumerate(cards):
        info = card.evaluate("""
            el => {
                // Get ALL text content recursively
                const allText = el.innerText.trim();
                // Get all child elements with text
                const textElements = Array.from(el.querySelectorAll('*')).map(e => ({
                    tag: e.tagName,
                    cls: e.className ? e.className.split(' ').slice(0,2).join(' ') : '',
                    text: e.innerText.trim(),
                    display: window.getComputedStyle(e).display
                })).filter(e => e.text && e.text.length > 2);

                const rect = el.getBoundingClientRect();
                return {
                    allText,
                    textElements: textElements.slice(0, 8),
                    width: rect.width,
                    height: rect.height,
                    top: rect.top
                };
            }
        """)
        print(f"\n--- Card {i} ---")
        print(f"  Size: {info['width']}x{info['height']} at y={info['top']}")
        print(f"  Full text: {info['allText'][:200]}")
        print(f"  Text elements:")
        for te in info['textElements']:
            print(f"    <{te['tag']} class='{te['cls']}' display='{te['display']}'> {te['text'][:80]}")

    browser.close()
