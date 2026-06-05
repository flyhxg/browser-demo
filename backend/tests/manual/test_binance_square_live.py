"""Live smoke test for BinanceSquareBrowser.

Launches real chromium and hits binance.com/en/square. Skipped in
CI. Run with: `pytest tests/manual/test_binance_square_live.py --no-header -v`
or just `python -m pytest tests/manual -v` after removing the skip.
"""
import asyncio
from pathlib import Path

import pytest

from services.binance_square_browser import (
    BinanceSquareBrowser,
    BrowserError,
    get_browser,
)


OUTPUT_DIR = Path(__file__).parent.parent / "output"


@pytest.mark.skip(reason="manual live smoke — needs network + chromium")
@pytest.mark.asyncio
async def test_live_fetch_returns_posts():
    OUTPUT_DIR.mkdir(exist_ok=True)
    browser = get_browser()
    try:
        posts = await browser.fetch_posts(limit=10)
    except BrowserError as e:
        # On error, dump the page so we can debug selectors
        if browser._browser is not None:
            try:
                pages = browser._browser.contexts[0].pages if browser._browser.contexts else []
                if pages:
                    shot = OUTPUT_DIR / "live_failure.png"
                    await pages[0].screenshot(path=str(shot))
                    print(f"  screenshot: {shot}")
            except Exception:
                pass
        raise

    print(f"  fetched {len(posts)} posts")
    for p in posts[:5]:
        print(f"    [{p['author']}] {p['content'][:80]}")
    assert len(posts) > 0, "no posts returned from live Square"
    assert all(p["tokens"] for p in posts), "expected token-mentioning posts only"

    await browser.aclose()
