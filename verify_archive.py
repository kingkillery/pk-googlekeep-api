import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp('http://localhost:9333')
    page = browser.contexts[0].pages[0]
    page.goto('https://keep.google.com', wait_until='domcontentloaded')
    time.sleep(3)
    cards = page.locator('.IZ65Hb-n0tgWb').all()
    print(f'Cards remaining on main page: {len(cards)}')
    for i, card in enumerate(cards):
        text = card.evaluate('el => el.innerText.trim().split("\\n")[0]')
        print(f'  [{i}] {text[:60]}')
    browser.close()
