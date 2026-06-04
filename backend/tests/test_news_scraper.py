"""Tests for NewsScraper — the Playwright-based news fetcher."""
import pytest


def test_normalize_post_extracts_mentioned_tokens():
    """_parse_article_html must extract $SYMBOL and #SYMBOL mentions."""
    from services.datasources.news import _parse_article_html

    html = """
    <article>
      <h2>$BTC drops on ETF delay</h2>
      <p>The SEC pushed the decision to Q3, weighing on #Bitcoin markets.</p>
      <time datetime="2026-06-03T14:23:00Z"></time>
    </article>
    """
    evt = _parse_article_html(html, source="CoinDesk", url="https://coindesk.com/x")

    assert evt["title"] == "$BTC drops on ETF delay"
    assert "SEC" in evt["summary"]
    assert "BTC" in evt["mentioned_tokens"]
    assert "BITCOIN" in evt["mentioned_tokens"]  # #bitcoin normalized to BITCOIN
    assert evt["timestamp"] == "2026-06-03T14:23:00+00:00"
    assert evt["source"] == "CoinDesk"
    assert evt["url"] == "https://coindesk.com/x"


def test_filter_by_symbol_includes_cashtags_and_names():
    """matches_symbol must return True for $BTC, #bitcoin, and 'Bitcoin'."""
    from services.datasources.news import matches_symbol

    assert matches_symbol("$BTC surges", "BTC") is True
    assert matches_symbol("#bitcoin news", "BTC") is True
    assert matches_symbol("Bitcoin price update", "BTC") is True
    assert matches_symbol("ETH looking strong", "BTC") is False
    assert matches_symbol("Solana ecosystem", "BTC") is False


def test_top_n_returns_highest_engagement():
    """_top_n_by_engagement must return the N highest-scoring items."""
    from services.datasources.news import _top_n_by_engagement

    items = [
        {"title": "low", "score": 1},
        {"title": "high", "score": 100},
        {"title": "mid", "score": 50},
    ]
    result = _top_n_by_engagement(items, n=2)
    titles = [r["title"] for r in result]
    assert titles == ["high", "mid"]


def test_parse_article_html_handles_missing_optional_fields():
    """_parse_article_html must not crash on minimal HTML."""
    from services.datasources.news import _parse_article_html

    html = "<article><h2>Title only</h2></article>"
    evt = _parse_article_html(html, source="X", url="https://x.com/y")
    assert evt["title"] == "Title only"
    assert evt["summary"] == ""
    assert evt["mentioned_tokens"] == []
    assert evt["timestamp"] is None


@pytest.mark.asyncio
async def test_scraper_handles_site_5xx_returns_from_other_site():
    """When one site fails (FakeBrowser raises), the other site's posts are returned."""
    from services.datasources.news import NewsScraper


    class FakePage:
        def __init__(self, html: str):
            self._html = html
            self._url = ""

        async def goto(self, url: str, timeout: int = 15000):
            self._url = url
            if "coindesk" in url:
                raise RuntimeError("503 Service Unavailable")
            return None

        async def wait_for_selector(self, selector: str, timeout: int = 10000):
            return None

        async def query_selector_all(self, selector: str):
            if "theblock" in self._url:
                html = self._html
                async def inner_html(self, _h=html):
                    return _h
                return [type("E", (), {"inner_html": inner_html})()]
            return []

    class FakeBrowser:
        async def new_context(self):
            class Ctx:
                async def new_page(self_inner):
                    return FakePage("<article><h2>$BTC test</h2></article>")
                async def close(self_inner):
                    pass
            return Ctx()

        async def close(self):
            pass

    class FakeLauncher:
        async def launch(self):
            return FakeBrowser()

    scraper = NewsScraper(browser_launcher=FakeLauncher(), sites=("coindesk", "theblock"))
    events = await scraper.fetch_news("BTC", time_range="24h", top_n_per_site=5)

    # The Block succeeded; CoinDesk failed. The Block's event should be in the result.
    sources = [e["source"] for e in events]
    assert "The Block" in sources or "theblock" in [s.lower() for s in sources]


@pytest.mark.asyncio
async def test_scraper_handles_playwright_launch_failure():
    """If BrowserLauncher.launch() raises, the scraper returns [] without crashing."""
    from services.datasources.news import NewsScraper

    class FailingLauncher:
        async def launch(self):
            raise RuntimeError("browser failed to launch")

    scraper = NewsScraper(browser_launcher=FailingLauncher(), sites=("coindesk", "theblock"))
    events = await scraper.fetch_news("BTC", time_range="24h", top_n_per_site=5)
    assert events == []
