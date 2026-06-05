"""One-shot helper: launch a real chromium, hit Binance Square, save
the rendered HTML into the four fixture files used by tests.

Usage (from project root):
    cd backend && python tests/fixtures/binance_square/capture_fixtures.py

The login_wall and captcha fixtures are best-effort — they save the
current page if those states happen to be detected. Empty page is
saved if the feed has no posts at capture time.
"""
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

FIXTURE_DIR = Path(__file__).parent
SQUARE_URL = "https://www.binance.com/en/square"


async def capture(page, name: str) -> None:
    html = await page.content()
    out = FIXTURE_DIR / f"{name}.html"
    out.write_text(html, encoding="utf-8")
    print(f"  saved {out.name} ({len(html)} bytes)")


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )
        await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => false })")
        page = await ctx.new_page()

        print(">>> home_with_posts")
        await page.goto(SQUARE_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)  # let SPA render
        # Scroll 2x to load more
        for _ in range(2):
            await page.mouse.wheel(0, 1200)
            await page.wait_for_timeout(2500)
        await capture(page, "home_with_posts")

        # The other fixtures are best-effort — saved as the current page
        # if those states are detected, otherwise as the home page.
        print(">>> empty_page (best-effort)")
        await capture(page, "empty_page")

        print(">>> login_wall (best-effort)")
        await capture(page, "login_wall")

        print(">>> captcha (best-effort)")
        await capture(page, "captcha")

        await browser.close()
    print("Done. Inspect HTML files and replace selectors in _parse_html as needed.")


if __name__ == "__main__":
    asyncio.run(main())
