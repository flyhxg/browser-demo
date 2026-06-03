"""Binance Square scraper using browser automation.

Scrapes Binance Square (feed/social) posts and extracts token mentions.
Designed to work with the existing browser-use agent in browser-demo.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SquarePost:
    """Represents a Binance Square post."""
    post_id: str
    author: str
    content: str
    created_at: str
    likes: int = 0
    comments: int = 0
    shares: int = 0
    # Extracted tokens mentioned in the post
    tokens: List[str] = field(default_factory=list)
    # Sentiment score: -1.0 (bearish) to 1.0 (bullish)
    sentiment: float = 0.0
    # Raw HTML/text from the post
    raw: str = ""


@dataclass
class SquareScrapeResult:
    """Result of scraping Binance Square."""
    posts: List[SquarePost]
    total_posts: int
    tokens_mentioned: Dict[str, int]  # token -> mention count
    scrape_time: str


class BinanceSquareScraper:
    """Scraper for Binance Square posts.

    This is designed to be used with the browser-use Agent in browser-demo.
    The agent navigates to Binance Square, scrolls through posts, and extracts content.
    """

    # Binance Square URLs
    SQUARE_URL = "https://www.binance.com/en/square"
    FEED_URL = "https://www.binance.com/en/square/feed/all"

    # Token regex patterns
    TOKEN_PATTERNS = [
        # $TOKEN or #TOKEN patterns
        r"\$[A-Z]{2,10}",
        r"#[A-Z]{2,10}",
        # Common token names mentioned in text
        r"\b(BTC|ETH|SOL|XRP|ADA|DOT|AVAX|LINK|UNI|AAVE|SNX|CRV|MKR|COMP|YFI|SUSHI|BAL|LRC|GRT|1INCH|MATIC|ALGO|VET|FIL|ATOM|XTZ|EGLD|NEAR|FTM|ONE|ROSE|CELO|ANKR|CHZ|ENJ|MANA|SAND|GALA|APE|SHIB|DOGE|PEPE|FLOKI|BONK|SUI|SEI|TIA|INJ|RNDR|AR|ICP|STX|ORDI|SATS)\b",
    ]

    def __init__(self, page: Optional[Any] = None) -> None:
        """Initialize scraper.

        Args:
            page: Playwright page object (optional, for direct use)
        """
        self.page = page
        self._posts: List[SquarePost] = []

    async def scrape_with_agent(
        self,
        agent: Any,
        max_posts: int = 50,
        min_likes: int = 5,
    ) -> SquareScrapeResult:
        """Scrape Binance Square using the browser-use Agent.

        Args:
            agent: The browser-use Agent instance
            max_posts: Maximum number of posts to scrape
            min_likes: Minimum likes filter

        Returns:
            SquareScrapeResult with extracted posts and token mentions
        """
        logger.info(f"Starting Binance Square scrape (max_posts={max_posts})")

        # Navigate to Binance Square
        await agent.browser_use(
            f"Navigate to {self.SQUARE_URL} and wait for the page to load. "
            "Scroll down to load posts. Extract the following from each post:\n"
            "1. Post ID or URL\n"
            "2. Author username\n"
            "3. Post content (text)\n"
            "4. Like count\n"
            "5. Comment count\n"
            "6. Timestamp\n\n"
            f"Continue scrolling and extracting until you have collected up to {max_posts} posts. "
            f"Only include posts with at least {min_likes} likes."
        )

        # For now, return empty result (actual extraction would parse agent output)
        # In practice, the agent would need to return structured data
        return SquareScrapeResult(
            posts=[],
            total_posts=0,
            tokens_mentioned={},
            scrape_time=datetime.now().isoformat(),
        )

    @staticmethod
    def extract_tokens_from_text(text: str) -> List[str]:
        """Extract token mentions from text.

        Args:
            text: Post content text

        Returns:
            List of token symbols (uppercase)
        """
        tokens = set()

        for pattern in BinanceSquareScraper.TOKEN_PATTERNS:
            matches = re.findall(pattern, text.upper())
            for match in matches:
                # Remove $ or # prefix
                clean = match.lstrip("$#")
                if len(clean) >= 2:
                    tokens.add(clean)

        # Also extract common crypto keywords
        crypto_keywords = re.findall(
            r"\b(bitcoin|ethereum|solana|cardano|polkadot|avalanche|chainlink|matic|ripple)\b",
            text.lower(),
        )
        keyword_map = {
            "bitcoin": "BTC",
            "ethereum": "ETH",
            "solana": "SOL",
            "cardano": "ADA",
            "polkadot": "DOT",
            "avalanche": "AVAX",
            "chainlink": "LINK",
            "matic": "MATIC",
            "ripple": "XRP",
        }
        for kw in crypto_keywords:
            tokens.add(keyword_map.get(kw, kw.upper()))

        return sorted(tokens)

    @staticmethod
    def analyze_sentiment(text: str) -> float:
        """Simple sentiment analysis for crypto posts.

        Returns a score from -1.0 (bearish) to 1.0 (bullish).
        """
        text_lower = text.lower()

        bullish_keywords = [
            "bullish", "pump", "moon", "breakout", "rally", "surge",
            " ATH", "all time high", "buy", "long", "hodl", "hold",
            "up only", "green", "rocket", "to the moon", "lambo",
            "100x", "10x", "gem", "alpha", "bull run", "uptrend",
        ]
        bearish_keywords = [
            "bearish", "dump", "crash", "correction", "sell", "short",
            "down", "red", "rug pull", "scam", "bear market", "downtrend",
            "correction", "rekt", "liquidation", "panic sell", "fud",
        ]

        bullish_score = sum(1 for kw in bullish_keywords if kw in text_lower)
        bearish_score = sum(1 for kw in bearish_keywords if kw in text_lower)

        total = bullish_score + bearish_score
        if total == 0:
            return 0.0

        # Normalize to -1.0 to 1.0
        return (bullish_score - bearish_score) / total

    def parse_posts_from_html(self, html: str) -> List[SquarePost]:
        """Parse Square posts from HTML content.

        This is a fallback when using direct HTML scraping instead of the agent.
        """
        posts = []
        # This would use BeautifulSoup or similar to parse actual HTML
        # For now, return empty list
        return posts


class SquareSignalExtractor:
    """Extracts trading signals from scraped Square posts."""

    def __init__(self, posts: List[SquarePost]) -> None:
        self.posts = posts

    def get_trending_tokens(self, min_mentions: int = 3) -> Dict[str, dict]:
        """Get tokens mentioned most frequently with sentiment.

        Args:
            min_mentions: Minimum number of mentions to be considered trending

        Returns:
            Dict of token -> {"mentions": int, "avg_sentiment": float, "latest_post": str}
        """
        token_stats: Dict[str, dict] = {}

        for post in self.posts:
            for token in post.tokens:
                if token not in token_stats:
                    token_stats[token] = {
                        "mentions": 0,
                        "sentiments": [],
                        "latest_post": post.content[:200],
                    }
                token_stats[token]["mentions"] += 1
                token_stats[token]["sentiments"].append(post.sentiment)

        # Filter and compute averages
        result = {}
        for token, stats in token_stats.items():
            if stats["mentions"] >= min_mentions:
                avg_sentiment = sum(stats["sentiments"]) / len(stats["sentiments"])
                result[token] = {
                    "mentions": stats["mentions"],
                    "avg_sentiment": round(avg_sentiment, 2),
                    "latest_post": stats["latest_post"],
                }

        return result

    def get_high_confidence_signals(self, threshold: float = 0.5) -> List[dict]:
        """Get posts with high sentiment confidence for trading signals.

        Args:
            threshold: Minimum absolute sentiment score

        Returns:
            List of signal dicts with token, sentiment, and post info
        """
        signals = []
        for post in self.posts:
            if abs(post.sentiment) >= threshold and post.tokens:
                for token in post.tokens:
                    signals.append({
                        "token": token,
                        "sentiment": post.sentiment,
                        "likes": post.likes,
                        "author": post.author,
                        "content": post.content[:300],
                        "timestamp": post.created_at,
                    })
        return signals


# ---------------------------------------------------------------------------
# Convenience functions for use with the existing agent_runner
# ---------------------------------------------------------------------------

def create_scrape_task(max_posts: int = 50, min_likes: int = 5) -> str:
    """Create a task description for the browser agent to scrape Binance Square.

    Returns a task string that can be passed to the agent.
    """
    return (
        f"Go to https://www.binance.com/en/square and scrape the latest posts. "
        f"Scroll through the feed and collect up to {max_posts} posts. "
        f"For each post, record: author, content, likes, comments, and timestamp. "
        f"Only include posts with at least {min_likes} likes. "
        f"After collecting, extract any mentioned cryptocurrency tokens (like BTC, ETH, SOL) "
        f"and note the sentiment of each post (bullish, bearish, or neutral). "
        f"Return the data in a structured JSON format."
    )


def parse_agent_output(output: str) -> SquareScrapeResult:
    """Parse the browser agent's output into a structured result.

    This attempts to extract JSON from the agent's response.
    """
    posts: List[SquarePost] = []
    tokens_mentioned: Dict[str, int] = {}

    # Try to find JSON in the output
    json_match = re.search(r"```json\n(.*?)\n```", output, re.DOTALL)
    if not json_match:
        json_match = re.search(r"\{.*\"posts\".*\}", output, re.DOTALL)

    if json_match:
        try:
            data = json.loads(json_match.group(1) if json_match.lastindex == 1 else json_match.group(0))
            for post_data in data.get("posts", []):
                post = SquarePost(
                    post_id=post_data.get("id", ""),
                    author=post_data.get("author", ""),
                    content=post_data.get("content", ""),
                    created_at=post_data.get("timestamp", ""),
                    likes=post_data.get("likes", 0),
                    comments=post_data.get("comments", 0),
                    tokens=post_data.get("tokens", []),
                    sentiment=post_data.get("sentiment", 0.0),
                )
                posts.append(post)
                for token in post.tokens:
                    tokens_mentioned[token] = tokens_mentioned.get(token, 0) + 1
        except json.JSONDecodeError:
            logger.warning("Failed to parse agent output as JSON")

    return SquareScrapeResult(
        posts=posts,
        total_posts=len(posts),
        tokens_mentioned=tokens_mentioned,
        scrape_time=datetime.now().isoformat(),
    )
