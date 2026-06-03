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
