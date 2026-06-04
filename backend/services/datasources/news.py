"""Playwright-based news scraper for CoinDesk + The Block.

Fetches articles mentioning a target symbol within a time range.
The `BrowserLauncher` Protocol is the seam for tests — production
uses `PlaywrightLauncher`, tests inject `FakeBrowserLauncher` returning
canned HTML.
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

logger = logging.getLogger(__name__)

SYMBOL_FULL_NAMES = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binance coin",
}

TOKEN_MENTION_RE = re.compile(r"\$([A-Z]{2,10})|#([A-Za-z]{2,15})")


def matches_symbol(text: str, symbol: str) -> bool:
    """Return True if `text` mentions `symbol` via $tag, #tag, or full name."""
    if not text:
        return False
    upper_text = text.upper()
    if f"${symbol.upper()}" in upper_text:
        return True
    if f"#{symbol.upper()}" in upper_text:
        return True
    full_name = SYMBOL_FULL_NAMES.get(symbol.upper(), "")
    if full_name and full_name in text.lower():
        return True
    return False


def _parse_article_html(html: str, source: str, url: str) -> dict[str, Any]:
    """Parse one article's HTML into a normalized news event dict.

    Uses regex (no BeautifulSoup dependency) — robust enough for the
    article structures on CoinDesk / The Block.
    """
    # Title
    title_match = re.search(r"<h2[^>]*>(.*?)</h2>", html, re.DOTALL | re.IGNORECASE)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""

    # First <p> as summary
    p_match = re.search(r"<p[^>]*>(.*?)</p>", html, re.DOTALL | re.IGNORECASE)
    summary = re.sub(r"<[^>]+>", "", p_match.group(1)).strip() if p_match else ""
    summary = re.sub(r"\s+", " ", summary)[:500]

    # Timestamp from <time datetime="...">
    time_match = re.search(r'<time[^>]+datetime="([^"]+)"', html, re.IGNORECASE)
    timestamp: str | None = None
    if time_match:
        raw = time_match.group(1)
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            timestamp = dt.isoformat()
        except ValueError:
            timestamp = None

    # Token mentions
    mentioned: set[str] = set()
    for m in TOKEN_MENTION_RE.finditer(html):
        token = (m.group(1) or m.group(2) or "").upper()
        if token:
            mentioned.add(token)

    return {
        "title": title,
        "summary": summary,
        "mentioned_tokens": sorted(mentioned),
        "timestamp": timestamp,
        "source": source,
        "url": url,
    }


def _top_n_by_engagement(items: list[dict], n: int) -> list[dict]:
    """Return the N items with the highest `score` field."""
    return sorted(items, key=lambda x: x.get("score", 0), reverse=True)[:n]


# --- BrowserLauncher seam ---


class BrowserLauncher(Protocol):
    """Seam for tests — production uses PlaywrightLauncher."""
    async def launch(self) -> Any: ...


class PlaywrightLauncher:
    """Production launcher. One context per call, closed in finally."""
    async def launch(self) -> Any:
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True)
        return _PlaywrightHandle(pw, browser)


class _PlaywrightHandle:
    """Wraps the Playwright objects so launcher.launch() returns a single value."""
    def __init__(self, pw, browser):
        self.pw = pw
        self.browser = browser


SITE_URLS = {
    "coindesk": "https://www.coindesk.com/",
    "theblock": "https://www.theblock.co/",
}
SITE_NAMES = {
    "coindesk": "CoinDesk",
    "theblock": "The Block",
}


class NewsScraper:
    """Scrape crypto news sites for posts mentioning a symbol.

    The `BrowserLauncher` is the test seam — production uses
    `PlaywrightLauncher`, tests inject a fake that returns canned HTML
    or raises on goto to simulate failures.
    """

    def __init__(
        self,
        browser_launcher: BrowserLauncher | None = None,
        sites: tuple[str, ...] = ("coindesk", "theblock"),
    ):
        self._launcher = browser_launcher or PlaywrightLauncher()
        self._sites = sites

    async def fetch_news(
        self,
        symbol: str,
        time_range: str = "24h",
        top_n_per_site: int = 5,
    ) -> list[dict[str, Any]]:
        """Scrape all configured sites in parallel, return normalized events."""
        results = await asyncio.gather(
            *[self._scrape_site(site, symbol) for site in self._sites],
            return_exceptions=True,
        )

        all_events: list[dict] = []
        for site, result in zip(self._sites, results):
            if isinstance(result, Exception):
                logger.warning(f"[NewsScraper] {site} failed: {result}")
                continue
            all_events.extend(result)

        # Filter by time range
        hours = {"1h": 1, "4h": 4, "24h": 24, "7d": 24 * 7}.get(time_range, 24)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        filtered = []
        for evt in all_events:
            ts_str = evt.get("timestamp")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts < cutoff:
                        continue
                except ValueError:
                    pass
            if not matches_symbol(evt.get("title", "") + " " + evt.get("summary", ""), symbol):
                continue
            filtered.append(evt)

        # Sort by timestamp DESC, take top N
        filtered.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
        return filtered[: top_n_per_site * len(self._sites)]

    async def _scrape_site(self, site: str, symbol: str) -> list[dict[str, Any]]:
        """Scrape one site. Returns a list of normalized event dicts.

        Production: launches a browser, navigates to the site, extracts articles.
        Tests: a fake launcher can simulate the navigation returning HTML or raising.
        """
        url = SITE_URLS[site]
        source_name = SITE_NAMES[site]
        handle = await self._launcher.launch()
        events: list[dict] = []
        try:
            context = await handle.new_context()
            try:
                page = await context.new_page()
                await page.goto(url, timeout=15000)
                # Try multiple selectors — different sites use different markup
                articles = await page.query_selector_all("article")
                for art in articles[:20]:  # cap raw articles
                    try:
                        html = await art.inner_html()
                        evt = _parse_article_html(html, source=source_name, url=url)
                        if evt["title"]:
                            events.append(evt)
                    except Exception as e:
                        logger.debug(f"[NewsScraper] article parse error: {e}")
            finally:
                await context.close()
        finally:
            await handle.close()
            # For PlaywrightLauncher, the underlying pw instance also needs stopping.
            if hasattr(handle, "pw"):
                try:
                    await handle.pw.stop()
                except Exception:
                    pass
        return events
