# Event-Driven Analysis — Design

> Phase 2.2.3 of `openspec/changes/ai-trading-system`. Adds a specialized
> "why did X move" sub-pipeline that combines news, social media,
> on-chain flows, and derivatives into a structured event-causality
> report.

**Goal:** Answer "why did BTC drop 5% in the last 24h?" with a
chronological event timeline + a short LLM-written causal narrative,
not a free-form LLM paragraph.

**Architecture:** A new `EventPipeline` class that orchestrates 4
parallel datasource fetches, clusters the events by timestamp window,
and asks the LLM to synthesize the most likely causes. Exposed via
`POST /api/analyze/events`. `IntentRouter` is updated so event-shaped
queries ("why did X drop", "what happened to Y") route to the new
pipeline instead of the generic Layer 3 plan-then-synthesize path.

**Tech Stack:** Python 3.14, `asyncio`, Playwright (already a project
dep via `services/signal_scraper.py`), existing datasources
(`arkham`, `whale_alert`, `binance_futures`, `okx`).

---

## Why a separate pipeline, not just an LLM-prompt tweak

The existing `IntentRouter._route_layer3` (commit 07f47d5) does
plan-then-synthesize: it asks the LLM to pick which (symbol,
dimension) fetches to run, then writes a free-form paragraph. That
works for cross-token comparison ("ETH vs SOL for shorting") but
gives weak answers for **event causality** because:

1. It never correlates events across sources by timestamp
2. The output is a paragraph, not a structured timeline the frontend
   can render
3. There's no notion of confidence — the user can't tell when the
   answer is based on thin data

`EventPipeline` fixes all three: it gathers from 4 sources in
parallel, clusters by 30-min windows, and returns a structured
response with a confidence score.

---

## Components

### `services/datasources/news.py` (NEW, ~180 lines)

Playwright-based news scraper. Scrapes **2 sites** (CoinDesk + The
Block) and returns normalized posts.

```python
class NewsScraper:
    """Scrape crypto news sites for posts mentioning a symbol.

    Returns a list of normalized news events, filtered to those
    mentioning the target symbol within the time range.
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
    ) -> list[NewsEvent]:
        """Returns up to `top_n_per_site` most recent articles per site
        that mention `symbol` in title or summary."""

class BrowserLauncher(Protocol):
    """Seam for tests — production uses Playwright, tests inject a fake."""
    async def launch(self) -> Browser: ...

class PlaywrightLauncher:
    """Production launcher. One context per call, closed in finally."""
    async def launch(self) -> Browser: ...
```

**Key methods:**
- `_scrape_site(site: str, symbol: str) -> list[NewsEvent]` — Playwright
  `goto(site_url)`, `wait_for_selector("article")`, extract title /
  url / timestamp / summary, filter to those mentioning `symbol`.
- `fetch_news` runs all `_scrape_site` calls in parallel via
  `asyncio.gather(return_exceptions=True)`, flattens, sorts by
  timestamp DESC, slices to `top_n_per_site * len(sites)`.

**Symbol matching:** a post matches if it contains `$SYMBOL`,
`#SYMBOL`, or the full name (e.g. "Bitcoin" / "BTC"). Case-insensitive.

### `services/event_pipeline.py` (NEW, ~250 lines)

Orchestrator. The core class.

```python
@dataclass
class Event:
    timestamp: datetime          # UTC
    type: Literal["news", "social", "whale", "liquidation", "funding_shift"]
    title: str
    source: str                  # "CoinDesk", "BinanceSquare", "Arkham", etc.
    url: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    severity: int = 1            # 1-5, source-provided or computed

class EventPipeline:
    """Combines news + social + on-chain + derivatives into a
    structured event-causality report."""

    def __init__(
        self,
        news: NewsScraper | None = None,
        social: BinanceSquareScraper | None = None,
        onchain: OnchainAggregator | None = None,
        derivatives: DerivativesAggregator | None = None,
        llm_factory: Callable | None = None,
    ): ...

    async def run(
        self,
        symbol: str,
        time_range: Literal["1h", "4h", "24h", "7d"] = "24h",
    ) -> dict[str, Any]:
        """Fetch → cluster → synthesize. Never raises."""
```

**`run()` algorithm:**
1. `asyncio.gather(news, social, onchain, derivatives, return_exceptions=True)` — all 4 in parallel.
2. Flatten into a single `list[Event]`. Failed fetches decrement confidence.
3. `cluster_events(events, window_minutes=30)` — group by 30-min window per type. NOT used as a single timeline; kept as a sorted list with cluster-id metadata.
4. `build_timeline(events)` — chronological list, capped at 50 events.
5. `llm.synthesize(symbol, time_range, timeline)` — 20s timeout, returns `(summary_text, confidence_delta)`.
6. Compute `overall_confidence = max(0.0, 1.0 - sum(decrements))`.
7. Return response dict.

**Per-source sampling rules:**
- `news`: top 5 most recent per site (10 total max)
- `social`: top 20 hottest Binance Square posts (engagement = likes + comments × 2)
- `whale`: only transfers ≥ $5M
- `liquidation`: only liquidations ≥ $1M
- `funding_shift`: only points where `|funding_rate|` exceeded 0.1% within the window

**Hard cap: 50 events.** If exceeded, the lowest-severity events are dropped first.

### `services/datasources/binance_square.py` (MODIFY)

Add `scrape_hot(symbol, time_range, top_n=20)` method to
`BinanceSquareScraper`. Returns posts sorted by engagement (likes +
comments × 2), filtered to those mentioning `symbol` in `time_range`.

The existing `scrape()` method is unchanged — scheduler still uses it.

### `services/datasources/aggregators.py` (NEW, ~80 lines)

Two thin aggregator classes that fan out to the underlying single-source
classes. They keep `EventPipeline`'s call sites simple.

```python
class OnchainAggregator:
    def __init__(self):
        self.arkham = Arkham()
        self.whale = WhaleAlert()
    async def fetch(self, symbol: str, time_range: str) -> list[Event]:
        # Combine arkham + whale_alert results, normalize to Event
        ...

class DerivativesAggregator:
    def __init__(self):
        self.binance = BinanceFutures()
        self.okx = OKXSource()
    async def fetch(self, symbol: str, time_range: str) -> list[Event]:
        # Combine funding + OI + liquidations, normalize to Event
        ...
```

### `api/analysis.py` (MODIFY)

Add new endpoint:

```python
class AnalyzeEventsRequest(BaseModel):
    symbol: str
    time_range: Literal["1h", "4h", "24h", "7d"] = "24h"

@router.post("/events")
async def analyze_events(req: AnalyzeEventsRequest):
    pipeline = EventPipeline()
    return await pipeline.run(req.symbol, req.time_range)
```

### `services/intent_router.py` (MODIFY)

Add a hook so event-shaped queries route to `EventPipeline`. Detection
heuristic: message contains `why`, `为什么`, `what happened`, `发生了什么`,
`drop`, `pump`, `crash`, `暴涨`, `暴跌`. These get dispatched to the new
endpoint; everything else keeps the current Layer 2/3 path.

```python
EVENT_QUERY_KEYWORDS = (
    "why", "为什么", "what happened", "发生了什么",
    "drop", "pump", "crash", "暴涨", "暴跌", "plunge", "rally",
)

@staticmethod
def classify(message: str | None, ...) -> Literal["layer2", "layer3", "event"]:
    if message and any(kw in message.lower() for kw in EVENT_QUERY_KEYWORDS):
        return "event"
    ...
```

Add `route_event()` method that calls `EventPipeline` and wraps the
result in the existing `{layer, report, ...}` shape.

---

## Data flow

```
POST /api/analyze/events {symbol: "BTC", time_range: "24h"}
        ↓
EventPipeline.run(symbol, time_range)
        ├── asyncio.gather(
        │     news.fetch_news(symbol, time_range),         # Playwright × 2 sites
        │     social.scrape_hot(symbol, time_range),        # BinanceSquare top 20
        │     onchain.fetch(symbol, time_range),            # arkham + whale_alert
        │     derivatives.fetch(symbol, time_range),        # binance + okx
        │   , return_exceptions=True)
        ↓
   normalize → list[Event] (cap 50, drop low-severity first)
        ↓
   build_timeline(events) — chronological, each tagged with cluster_id
        ↓
   llm.synthesize(symbol, time_range, timeline)   [20s timeout]
        ↓
Response:
{
  "symbol": "BTC",
  "time_range": "24h",
  "events": [
    {
      "timestamp": "2026-06-03T14:23:00Z",
      "type": "news",
      "title": "SEC delays spot ETH ETF decision",
      "source": "CoinDesk",
      "url": "https://...",
      "payload": {},
      "severity": 3,
      "cluster_id": 1
    },
    {
      "timestamp": "2026-06-03T14:30:00Z",
      "type": "whale",
      "title": "50,000 BTC transferred to Binance",
      "source": "WhaleAlert",
      "payload": {"amount_usd": 3250000000, "from": "unknown", "to": "binance"},
      "severity": 5,
      "cluster_id": 1
    },
    ...
  ],
  "llm_summary": "BTC dropped 5% after a $3.25B whale transfer to Binance coincided with the SEC ETF delay, triggering a long-liquidation cascade of ~$120M.",
  "overall_confidence": 0.72,
  "fetched_sources": {"news": "ok", "social": "ok", "onchain": "ok", "derivatives": "ok"},
  "fetched_at": "2026-06-04T10:00:00Z"
}
```

`events` is sorted by timestamp ascending. `cluster_id` groups events
within the same 30-min window — the frontend can use it to render
clusters as connected groups.

---

## Error handling

| Failure | Behavior | `confidence` impact |
|---|---|---|
| News Playwright fails to launch | Skip news, `fetched_sources.news = "failed"` | `-0.2` |
| One news site 5xx / timeout | Skip that site only, log warning | `-0.1` per failed site |
| BinanceSquare `scrape_hot` returns [] | OK — empty social events | `0` |
| Arkham / Whale Alert API down | Skip on-chain, log | `-0.2` |
| Binance / OKX derivatives timeout | Skip derivatives, log | `-0.2` |
| LLM timeout (20s) | Return events without summary, `llm_summary = "LLM synthesis unavailable"` | `-0.3` |
| LLM returns unparseable text | Same as timeout | `-0.3` |
| All 4 sources fail | Return `events=[]`, `llm_summary="No data available"`, `confidence=0` | n/a |
| `symbol` not found in CoinGecko | Return 400 from endpoint | n/a |
| `time_range` not in `{1h, 4h, 24h, 7d}` | Return 422 from Pydantic | n/a |

**Implementation patterns:**
- `EventPipeline.run()` never raises. All exceptions caught at the
  boundary, converted to `fetched_sources` entries.
- `asyncio.gather(*tasks, return_exceptions=True)` is the only safe way
  to run 4 sources in parallel; one slow source cannot block the others.
- `confidence` is `max(0.0, 1.0 - sum(decrement))`. Floor at 0.0.
- Playwright uses one `BrowserContext` per `run()` call, closed in
  `finally`. No persistent pool for MVP.
- Per-source timeout: 15s (Playwright `goto(timeout=15000)`).

---

## Testing

### `tests/test_event_pipeline.py` (NEW, 10 tests)

All use fake datasources. No real network, no real LLM.

| # | Test | Verifies |
|---|---|---|
| 1 | `test_pipeline_clusters_events_by_30min_window` | Events within 30min of each other get the same `cluster_id` |
| 2 | `test_pipeline_orders_timeline_chronologically` | Output events are sorted by `timestamp` ASC |
| 3 | `test_pipeline_truncates_to_top_n_per_source` | news ≤ 5/site, social = 20, whale ≥ $5M, liq ≥ $1M |
| 4 | `test_pipeline_calls_llm_with_timeline` | Mock LLM, prompt contains all events |
| 5 | `test_pipeline_returns_summary_and_confidence_from_llm` | LLM summary returned verbatim, confidence in [0, 1] |
| 6 | `test_pipeline_handles_single_source_failure` | One source raises, response still has events + summary, `confidence` lowered |
| 7 | `test_pipeline_handles_all_sources_failure` | All raise → `events=[]`, summary="No data available", `confidence=0` |
| 8 | `test_pipeline_runs_fetches_in_parallel` | Use a slow fake (asyncio.sleep(0.1)); total elapsed < 0.2s proves parallelism |
| 9 | `test_pipeline_caps_at_50_events` | 100 fake events → output ≤ 50, severity-descending kept |
| 10 | `test_pipeline_never_raises` | All sources raise unexpected exception types → response is 200-shaped, no exception |

### `tests/test_news_scraper.py` (NEW, 5 tests)

| # | Test | Verifies |
|---|---|---|
| 1 | `test_normalize_post_extracts_mentioned_tokens` | Raw HTML → post with `mentioned_tokens=["BTC"]` |
| 2 | `test_filter_by_symbol_includes_cashtags_and_names` | `$BTC`, `#bitcoin`, `"Bitcoin"` all match |
| 3 | `test_top_n_returns_highest_engagement` | 50 posts → top 5 by engagement |
| 4 | `test_scraper_handles_site_5xx` | One site 503, the other succeeds → returns from the OK site only |
| 5 | `test_scraper_handles_playwright_launch_failure` | `BrowserLauncher.launch()` raises → returns [], no exception |

**Seam:** `BrowserLauncher` Protocol. Production wires `PlaywrightLauncher`.
Tests inject `FakeBrowserLauncher` returning canned HTML.

### `tests/test_binance_square_hot.py` (NEW or extend `test_signal_scraper.py`, 3 tests)

| # | Test | Verifies |
|---|---|---|
| 1 | `test_scrape_hot_returns_top_n_by_engagement` | 30 posts, `top_n=10` → 10 with highest likes+comments |
| 2 | `test_scrape_hot_filters_by_time_range` | Posts older than `time_range` excluded |
| 3 | `test_scrape_hot_filters_by_symbol_mention` | Posts not mentioning symbol excluded |

### Integration smoke (manual, in `docs/`)

After deploy:
```bash
curl -X POST http://localhost:8000/api/analyze/events \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTC","time_range":"24h"}'
```

Expected: 200 response, events list with ≥ 3 distinct `type` values,
`llm_summary` non-empty, `overall_confidence` ≥ 0.5. Frontend renders
the timeline.

---

## Scope boundary (YAGNI)

**In scope:**
- News scraping from 2 sites (CoinDesk + The Block) via Playwright
- Reuse `BinanceSquareScraper` (add `scrape_hot` method)
- On-chain from existing arkham + whale_alert
- Derivatives from existing binance_futures + okx
- LLM synthesis into a 2-3 sentence summary
- Single endpoint `POST /api/analyze/events`
- `IntentRouter` hook so event queries route to the new pipeline
- 18 new unit tests

**Out of scope (explicit):**
- Persistent event store (in-memory per request)
- Cross-token event correlation ("did BTC drop *cause* ETH to drop?")
- Real-time streaming (this is request/response only)
- WebSocket push for new events as they happen
- Multi-language news sources
- Twitter/X integration
- News source rotation / failover beyond per-site try/except
- Historical replay (only the configured `time_range`)
- Confidence calibration (we just decrement on failure; no ground truth)

**Migration path:** if event correlation becomes needed later, add a
new method `EventPipeline.cluster_causal_chains()` that uses a small
LLM call to group clusters into A→B causal chains. No change to the
public `run()` signature needed.

---

## Self-review checklist

- **Placeholder scan:** no TBD / TODO / "fill in later". All methods have
  signatures, error tables are concrete, test names + assertions are
  spelled out.
- **Internal consistency:** the data flow matches the components
  section. `cluster_id` appears in both the response example and the
  test descriptions. `confidence` decrement math is consistent across
  the error table and the algorithm description.
- **Scope check:** 1 new datasource (news.py), 1 new pipeline
  (event_pipeline.py), 1 new aggregator file (aggregators.py), 1
  modified scraper, 1 new endpoint, 1 small IntentRouter hook, 18
  tests. Single focused PR.
- **Ambiguity check:**
  - "hottest" defined explicitly as `likes + comments × 2`
  - "30-min window" — explicit in the clustering section
  - "symbol" — exact strings (BTC, ETH, etc.), case-insensitive
  - "time_range" — Pydantic Literal pins the values
  - "confidence" — math is `max(0.0, 1.0 - sum(decrement))`, floor 0.0
