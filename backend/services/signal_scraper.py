"""Binance Square signal scraper."""
import asyncio
import re
from typing import Any

from services.database import get_db


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
                    "source_url": post.get("url", ""),
                    "author": post.get("author", "unknown"),
                    "content": content,
                    "likes": post.get("likes", 0),
                    "comments": post.get("comments", 0),
                    "tokens": tokens,
                    "raw_data": str(post),
                })

        return posts

    async def _fetch_posts(self, limit: int) -> list[dict[str, Any]]:
        """Fetch raw posts from Binance Square.

        NOTE: Real implementation requires browser automation.
        For now, returns sample data for testing.
        """
        # Real implementation would use browser-use to:
        # 1. Navigate to https://www.binance.com/en/square
        # 2. Login with credentials
        # 3. Scroll and extract posts
        # 4. Return structured data
        return [
            {
                "url": "https://www.binance.com/en/square/post/1",
                "author": "TraderOne",
                "content": "Just bought $SOL at $140, looking bullish! Target $200. #SOL #crypto",
                "likes": 234,
                "comments": 45,
            },
            {
                "url": "https://www.binance.com/en/square/post/2",
                "author": "CryptoWhale",
                "content": "$ETH breaking out! Massive volume incoming. Don't miss this train! #ETH",
                "likes": 189,
                "comments": 67,
            },
            {
                "url": "https://www.binance.com/en/square/post/3",
                "author": "BearHunter",
                "content": "$BTC looking weak, might dump to 60k. Watch out! #BTC",
                "likes": 123,
                "comments": 89,
            },
        ]

    def _extract_tokens(self, content: str) -> list[str]:
        """Extract token symbols from post content."""
        matches = self.TOKEN_PATTERN.findall(content)
        return list(set(matches))

    def save_to_db(self, posts: list[dict[str, Any]]) -> None:
        """Save scraped posts to database."""
        conn = get_db()
        cursor = conn.cursor()

        for post in posts:
            cursor.execute(
                """
                INSERT INTO signals (source, source_url, author, content, likes, comments, raw_data, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    post["source"],
                    post["source_url"],
                    post["author"],
                    post["content"],
                    post["likes"],
                    post["comments"],
                    post["raw_data"],
                ),
            )

        conn.commit()
        conn.close()

    async def scrape_hot(
        self,
        symbol: str,
        time_range: str = "24h",
        top_n: int = 20,
    ) -> list[dict]:
        """Return the top-N hottest posts mentioning `symbol` within `time_range`.

        Hotness = likes + comments * 2. Posts with no timestamp are excluded
        when a time_range is given. Used by the event-driven analysis pipeline.
        """
        from datetime import datetime, timedelta, timezone

        hours = {"1h": 1, "4h": 4, "24h": 24, "7d": 24 * 7}.get(time_range, 24)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        all_posts = await self.scrape()
        symbol_upper = symbol.upper()
        symbol_name_map = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}
        bare_pattern = re.compile(rf"\b{re.escape(symbol_upper)}\b")

        # Filter: must mention symbol, and be within time range
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
                # try full name
                full_name = symbol_name_map.get(symbol_upper, "")
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

        # Sort by engagement
        filtered.sort(key=lambda p: p.get("likes", 0) + p.get("comments", 0) * 2, reverse=True)
        return filtered[:top_n]
