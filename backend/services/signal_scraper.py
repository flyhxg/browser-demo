"""Binance Square signal scraper."""
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from services.database import get_db

logger = logging.getLogger(__name__)

# Full-name map for symbol-to-name expansion in scrape_hot (matches plan spec).
SYMBOL_FULL_NAMES = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}

# time_range string → hours. Unknown values fall back to 24h.
TIME_RANGE_HOURS = {"1h": 1, "4h": 4, "24h": 24, "7d": 24 * 7}


class BinanceSquareScraper:
    """Scraper for Binance Square social posts."""

    # Token mention patterns: $SOL, #BTC, etc.
    TOKEN_PATTERN = re.compile(r"[\$#]([A-Z]{2,10})")

    async def scrape(self, limit: int = 20) -> list[dict[str, Any]]:
        """Scrape Binance Square for posts with token mentions.

        Returns:
            List of post dicts with token mentions.
        """
        posts = []
        raw_posts = await self._fetch_posts(limit)

        for post in raw_posts:
            content = post.get("content", "")
            tokens = self._extract_tokens(content)

            if tokens:
                posts.append({
                    "source": "binance_square",
                    "source_url": post.get("source_url", ""),
                    "author": post.get("author", "unknown"),
                    "content": content,
                    "likes": post.get("likes", 0),
                    "comments": post.get("comments", 0),
                    "tokens": tokens,
                    "raw_data": str(post),
                })

        return posts

    async def _fetch_posts(self, limit: int) -> list[dict[str, Any]]:
        """Fetch real Binance Square posts via the singleton browser.

        The browser swallows nothing — the four `BrowserError` subclasses
        (LoginWall / Captcha / RateLimit / Parse) are caught here and
        converted to an empty list so the scheduler tick is a no-op
        instead of an error. Any other exception is allowed to propagate
        so the scheduler's existing error-handling path still fires.
        """
        from services.binance_square_browser import (
            CaptchaError,
            LoginWallError,
            ParseError,
            RateLimitError,
            get_browser,
        )

        browser = get_browser()
        try:
            raw = await browser.fetch_posts(limit)
        except (LoginWallError, CaptchaError, RateLimitError) as e:
            logger.warning(f"[BinanceSquareScraper] {type(e).__name__}: {e}")
            return []
        except ParseError as e:
            logger.error(
                f"[BinanceSquareScraper] parse failed: {e} "
                f"(screenshot: {e.screenshot_path})"
            )
            return []
        return raw

    def _extract_tokens(self, content: str) -> list[str]:
        """Extract token symbols from post content."""
        matches = self.TOKEN_PATTERN.findall(content)
        return list(set(matches))

    def save_to_db(self, posts: list[dict[str, Any]]) -> int:
        """Save scraped posts to the database. Returns the count of rows actually inserted.

        Uses INSERT OR IGNORE so re-running with the same posts (same
        source_url) is a no-op — the UNIQUE partial index on source_url
        (created in init_db) is the source of truth for dedup.
        """
        conn = get_db()
        cursor = conn.cursor()
        inserted = 0
        for post in posts:
            cursor.execute(
                """
                INSERT OR IGNORE INTO signals
                    (source, source_url, author, content, likes, comments, raw_data, status, source_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 'live')
                """,
                (
                    post.get("source", "binance_square"),
                    post.get("source_url", ""),
                    post.get("author", "unknown"),
                    post.get("content", ""),
                    post.get("likes", 0),
                    post.get("comments", 0),
                    post.get("raw_data", str(post)),
                ),
            )
            if cursor.rowcount > 0:
                inserted += 1
        conn.commit()
        conn.close()
        if inserted:
            logger.info(f"[BinanceSquareScraper] inserted {inserted}/{len(posts)} posts")
        return inserted

    async def scrape_hot(
        self,
        symbol: str,
        time_range: str = "24h",
        top_n: int = 20,
    ) -> list[dict]:
        """Return the top-N hottest posts mentioning `symbol` within `time_range`.

        Hotness = likes + comments * 2. Posts without a timestamp pass the
        time filter (we can't tell if they're stale). Used by the
        event-driven analysis pipeline.
        """
        hours = TIME_RANGE_HOURS.get(time_range, 24)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Request enough raw posts from scrape() to populate top_n after filtering.
        all_posts = await self.scrape(limit=top_n)
        symbol_upper = symbol.upper()
        bare_pattern = re.compile(rf"\b{re.escape(symbol_upper)}\b")

        filtered = []
        for p in all_posts:
            content = p.get("content", "")
            upper = content.upper()
            has_symbol = (
                f"${symbol_upper}" in upper
                or f"#{symbol_upper}" in upper
                or bare_pattern.search(upper) is not None
            )
            if not has_symbol:
                full_name = SYMBOL_FULL_NAMES.get(symbol_upper, "")
                if full_name and full_name not in content.lower():
                    continue
            ts_str = p.get("timestamp")
            if ts_str and time_range:
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts < cutoff:
                        continue
                except (ValueError, AttributeError):
                    continue
            filtered.append(p)

        filtered.sort(
            key=lambda p: p.get("likes", 0) + p.get("comments", 0) * 2,
            reverse=True,
        )
        for p in filtered:
            p.setdefault("type", "social")
        return filtered[:top_n]
