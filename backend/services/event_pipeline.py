"""EventPipeline — combines news + social + on-chain + derivatives into a
structured event-causality report.

Architecture (per docs/superpowers/specs/2026-06-04-event-driven-analysis-design.md):

    asyncio.gather(news, social, onchain, derivatives, return_exceptions=True)
        ↓
    normalize + cap at 50 events (drop low-severity first)
        ↓
    cluster_events(events, window_minutes=30)  # assigns cluster_id
        ↓
    llm.synthesize(symbol, time_range, timeline)
        ↓
    {events, llm_summary, overall_confidence, fetched_sources, fetched_at}
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Literal

logger = logging.getLogger(__name__)

MAX_EVENTS = 50
CLUSTER_WINDOW_MINUTES = 30
LLM_TIMEOUT_SECONDS = 20.0


@dataclass
class Event:
    """One event in the timeline. Mirrors the dict shape returned by sources."""
    timestamp: datetime
    type: Literal["news", "social", "whale", "liquidation", "funding_shift"]
    title: str
    source: str
    url: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    severity: int = 1
    cluster_id: int = -1

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        ts_raw = d.get("timestamp")
        if isinstance(ts_raw, str):
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except ValueError:
                ts = datetime.now(timezone.utc)
        elif isinstance(ts_raw, datetime):
            ts = ts_raw if ts_raw.tzinfo else ts_raw.replace(tzinfo=timezone.utc)
        else:
            ts = datetime.now(timezone.utc)
        return cls(
            timestamp=ts,
            type=d.get("type", "news"),
            title=d.get("title", ""),
            source=d.get("source", ""),
            url=d.get("url"),
            payload=d.get("payload", {}),
            severity=d.get("severity", 1),
        )

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "type": self.type,
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "payload": self.payload,
            "severity": self.severity,
            "cluster_id": self.cluster_id,
        }


def _dict_to_event(d: dict) -> Event:
    return Event.from_dict(d)


def cluster_events(events: list[Event], window_minutes: int = CLUSTER_WINDOW_MINUTES) -> list[Event]:
    """Assign cluster_id: events within `window_minutes` of each other get the same id.

    Cluster id is the timestamp (epoch seconds) of the cluster's earliest event,
    so clusters are sortable and unique.
    """
    if not events:
        return events
    sorted_events = sorted(events, key=lambda e: e.timestamp)
    clusters: list[list[Event]] = []
    current: list[Event] = [sorted_events[0]]
    for evt in sorted_events[1:]:
        last = current[-1]
        delta = (evt.timestamp - last.timestamp).total_seconds() / 60.0
        if delta <= window_minutes:
            current.append(evt)
        else:
            clusters.append(current)
            current = [evt]
    clusters.append(current)

    for cluster in clusters:
        cluster_id = int(cluster[0].timestamp.timestamp())
        for evt in cluster:
            evt.cluster_id = cluster_id
    return sorted_events


def cap_events(events: list[Event], max_n: int = MAX_EVENTS) -> list[Event]:
    """Cap event list at max_n, dropping lowest-severity first. Ties broken by timestamp."""
    if len(events) <= max_n:
        return events
    return sorted(events, key=lambda e: (-e.severity, e.timestamp))[:max_n]


class EventPipeline:
    """Orchestrates the 4-source event-causality pipeline. Never raises."""

    def __init__(
        self,
        news=None,
        social=None,
        onchain=None,
        derivatives=None,
        llm_synthesize: Callable[[str, str, list[dict]], Awaitable[str]] | None = None,
    ):
        self.news = news
        self.social = social
        self.onchain = onchain
        self.derivatives = derivatives
        self._llm_synthesize = llm_synthesize or self._default_llm

    async def run(
        self,
        symbol: str,
        time_range: Literal["1h", "4h", "24h", "7d"] = "24h",
    ) -> dict[str, Any]:
        """Fetch → normalize → cap → cluster → synthesize. Returns a dict, never raises."""
        # Fetch in parallel
        results = await asyncio.gather(
            self._safe_fetch(self.news, "fetch_news", symbol, time_range),
            self._safe_fetch(self.social, "scrape_hot", symbol, time_range),
            self._safe_fetch(self.onchain, "fetch", symbol, time_range),
            self._safe_fetch(self.derivatives, "fetch", symbol, time_range),
            return_exceptions=False,
        )

        news_events, social_events, onchain_events, derivatives_events = results
        all_dicts = news_events + social_events + onchain_events + derivatives_events

        # Normalize + cap
        all_events = [_dict_to_event(d) for d in all_dicts]
        all_events = cap_events(all_events, MAX_EVENTS)

        # Cluster
        all_events = cluster_events(all_events)

        # LLM synthesis
        try:
            timeline = [e.to_dict() for e in all_events]
            summary = await asyncio.wait_for(
                self._llm_synthesize(symbol, time_range, timeline),
                timeout=LLM_TIMEOUT_SECONDS,
            )
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"[EventPipeline] LLM synthesis failed: {e}")
            summary = "LLM synthesis unavailable."

        # Confidence: per spec, no decrement logic in this skeleton — covered in Task 9
        confidence = 1.0 if all_events else 0.0

        return {
            "symbol": symbol,
            "time_range": time_range,
            "events": [e.to_dict() for e in all_events],
            "llm_summary": summary,
            "overall_confidence": confidence,
            "fetched_sources": {
                "news": "ok" if news_events else ("failed" if self.news else "skipped"),
                "social": "ok" if social_events else ("failed" if self.social else "skipped"),
                "onchain": "ok" if onchain_events else ("failed" if self.onchain else "skipped"),
                "derivatives": "ok" if derivatives_events else ("failed" if self.derivatives else "skipped"),
            },
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _safe_fetch(self, source, method_name: str, *args) -> list[dict]:
        """Call source.method_name(*args) safely. Returns [] on any error."""
        if source is None:
            return []
        try:
            method = getattr(source, method_name, None)
            if method is None:
                return []
            result = await method(*args)
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.warning(f"[EventPipeline] {method_name} failed: {e}")
            return []

    @staticmethod
    async def _default_llm(symbol: str, time_range: str, timeline: list[dict]) -> str:
        """Default LLM synthesis — placeholder. Real impl in Task 9."""
        if not timeline:
            return "No data available."
        return f"Found {len(timeline)} event(s) for {symbol} in the last {time_range}."
