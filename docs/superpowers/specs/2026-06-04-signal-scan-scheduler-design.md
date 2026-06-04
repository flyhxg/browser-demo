# Signal Scan Scheduler — Design

> Phase 2.4 of `openspec/changes/ai-trading-system`. Background scheduling
> for the Binance Square signal scraper so we don't have to call the
> scraper manually every time we want fresh data.

**Goal:** Run `BinanceSquareScraper.scrape()` + `save_to_db()` on a
fixed interval in the background, with a kill switch (config flag) and
optional WebSocket broadcast for new signals.

**Architecture:** A single new file `services/scheduler.py` containing
a `SignalScanScheduler` class. The class is wired into FastAPI's
`lifespan` in `main.py`. Configuration is read from
`services/config_store.py` (no new persistence layer).

**Tech Stack:** Python 3.14, `asyncio`, FastAPI lifespan. **No new
dependencies** (Option B from brainstorm — pure asyncio loop).

---

## Why B (asyncio loop), not A (APScheduler) or C (Celery+Redis)

| | B (chosen) | A | C |
|---|---|---|---|
| Deps | 0 | apscheduler | celery + redis |
| Lines | ~80 | ~120 | ~200 + infra |
| Cron expr | ❌ (interval only) | ✅ | ✅ |
| Persistence | ❌ | ✅ | ✅ |
| Multi-process | ❌ | ❌ | ✅ |
| Fit with main.py | ✅ same `lifespan` pattern | OK | ❌ needs worker |

For MVP: scraping every 15 min doesn't need cron expressions, and a
restart losing the schedule is acceptable. The class signature is
deliberately scheduler-agnostic — swap `_loop` for
`apscheduler.AsyncIOScheduler.add_job` later without changing callers.

---

## Components

### `services/scheduler.py` (NEW, ~110 lines)

```python
class SignalScanScheduler:
    """Background scheduler for Binance Square signal scraping.

    Reads interval + enabled flag from config_store. Re-reads on every
    tick so config changes take effect without restart. Never raises
    out of `_tick` — exceptions are logged and swallowed.
    """

    def __init__(
        self,
        scraper: BinanceSquareScraper,
        config_provider: Callable[[], dict] | None = None,
        ws_broadcast: Callable[[str, dict], Awaitable[None]] | None = None,
    ):
        self.scraper = scraper
        self._config_provider = config_provider or get_config
        self._ws_broadcast = ws_broadcast
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def _loop(self) -> None: ...
    async def _tick(self) -> None: ...
    def _is_enabled(self) -> bool: ...
    def _interval_seconds(self) -> float: ...
```

**`start()`** — no-op when `signal_scan_enabled` is `false`; otherwise
creates `asyncio.create_task(self._loop())`. Idempotent: a second
`start()` while the first task is alive is a no-op.

**`stop()`** — sets `_stopped`, cancels the task, awaits it
(CancelledError swallowed), clears the task handle.

**`_loop()`** — runs `_tick()` then `asyncio.wait_for(stopped.wait(),
interval)`. TimeoutError = normal sleep elapsing; stopped event set =
graceful exit. CancelledError propagates (FastAPI shutdown).

**`_tick()`** — `posts = await scraper.scrape()`. If empty, return.
Else `scraper.save_to_db(posts)` then for each post
`await ws_broadcast("signal:new", post)` (only if broadcast was wired).
Each step is wrapped in its own try/except so one failure doesn't
kill the whole tick.

**`_is_enabled()` / `_interval_seconds()`** — re-read config on every
call. Lets the operator toggle the kill switch or change the interval
without restarting the process.

### `main.py` — lifespan integration

Replace the existing `@app.on_event("startup")` pattern with FastAPI's
modern `lifespan` context manager (the `@app.on_event` decorator is
deprecated in FastAPI 0.93+):

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    asyncio.create_task(_warm_sector_classifier())
    await _scheduler.start()
    yield
    # shutdown
    await _scheduler.stop()

app = FastAPI(title="Browser Use Web Demo", lifespan=lifespan)
```

The existing `_warm_sector_classifier` hook is preserved inside the
lifespan; only its trigger changes (was `@app.on_event("startup")`, now
inside `lifespan`).

### `services/config_store.py` — new keys

| key | type | default | meaning |
|---|---|---|---|
| `signal_scan_enabled` | bool | `false` | kill switch; scheduler is a no-op if `false` |
| `signal_scan_interval_minutes` | int | `15` | interval between scrape ticks |

Default `enabled=false` to avoid surprise data ingestion on first
deploy. Flip via `PUT /api/trading/config` after operator confirms the
scraper is ready. Allowed to be added to the existing
`update_trading_config` whitelist in `api/trading.py`.

### WebSocket integration

`SignalScanScheduler` does **not** own the WebSocket — it accepts an
optional `ws_broadcast: Callable[[str, dict], Awaitable[None]]`.
Wiring it to the existing `api/ws.py` hub is a follow-up commit
(out of scope for this design — keeping the scheduler unit-testable
without a live WS). The frontend already handles `signal:*` events
per commit 782f8df.

---

## Data flow

```
main.py lifespan startup
  └── _scheduler.start()
        ├── _is_enabled() == False  → log + return
        └── asyncio.create_task(_loop, name="signal-scan-scheduler")
              └── while not stopped:
                    ├── _tick()
                    │     ├── scraper.scrape()          [1 async call]
                    │     ├── if empty: return
                    │     ├── scraper.save_to_db(posts) [N INSERTs]
                    │     └── for post in posts:
                    │           └── await ws_broadcast("signal:new", post)
                    └── asyncio.wait_for(stopped.wait(), interval):
                          ├── TimeoutError → loop continues
                          └── stopped set  → loop breaks
```

---

## Error handling

| Failure | Behavior | Logged at |
|---|---|---|
| `scraper.scrape()` raises | log warn, skip this tick, continue | WARNING |
| `save_to_db()` raises | log error, skip this tick, continue | ERROR |
| `ws_broadcast()` raises (one post) | log warn for that post, continue with next | WARNING |
| Config key missing | default `False` / `15` | — |
| Config changes mid-run | re-read on next tick (no restart) | — |
| `stop()` during a tick | `cancel()` sets `CancelledError`; current `scrape` call runs to completion (no mid-flight kill) | INFO on stop |
| `start()` called twice | second is a no-op while first task is alive | DEBUG |
| FastAPI process restart | in-memory schedule is lost; restarts cold | — |

The scheduler never crashes the FastAPI process. Persistence across
restarts is in the YAGNI list.

---

## Testing

### `tests/test_scheduler.py` (NEW, 11 tests)

All use `asyncio.sleep` and `asyncio.Event` — no real-time waits.

| # | Test | Verifies |
|---|---|---|
| 1 | `_tick` calls scraper + save | Mock scraper returns 2 posts → `save_to_db` called with 2 posts |
| 2 | `_tick` broadcasts when ws provided | Mock ws → 2× `signal:new` calls |
| 3 | `_tick` no-op on empty posts | Mock scraper returns `[]` → no save, no broadcast |
| 4 | `_tick` survives scraper exception | Mock scraper raises → no exception propagates |
| 5 | `_tick` survives save_to_db exception | Mock save raises → no exception propagates |
| 6 | `_tick` survives ws broadcast exception (per-post) | Mock ws raises on first post → second post still broadcast |
| 7 | `start` no-op when disabled | `enabled=False` → no task created |
| 8 | `start` idempotent | `start()` twice → only 1 task alive |
| 9 | `stop` cancels running task | start, sleep, stop → task `done()` |
| 10 | `_loop` reads interval each tick | interval=0.01s, run 0.05s → ≥ 2 ticks |
| 11 | `_loop` picks up enabled toggle | start disabled, flip to enabled, → next tick runs |

### Integration smoke test (manual, in `docs/`)

After deploy, flip `signal_scan_enabled=true` via the config endpoint
and tail logs for `[SignalScanScheduler]` lines. Should see one `tick`
log per interval. Frontend should see `signal:new` events on the WS
panel.

---

## Scope boundary (YAGNI)

**In scope:** scrape + save + optional broadcast on a fixed interval.

**Out of scope (explicit):**
- LLM analysis per tick (analysis is per-signal, on-demand)
- Cron expressions (use APScheduler if needed)
- Multi-process coordination (single FastAPI process only)
- Job persistence across restarts
- Back-off on errors
- Metrics / Prometheus export
- Per-token scan filtering

**Migration path if any of the above becomes needed:** replace the
`_loop` body with `apscheduler.AsyncIOScheduler.add_job(self._tick,
"interval", ...)` — `SignalScanScheduler`'s public interface
(`start` / `stop` / `_tick`) stays unchanged. Callers in `main.py`
don't need to change.

---

## Self-review checklist

- **Placeholder scan:** no TBD / TODO / "fill in later". ✅
- **Internal consistency:** architecture ↔ components ↔ data flow ↔
  error handling all describe the same single-file scheduler. ✅
- **Scope check:** one new file (~110 lines) + ~10 lines in main.py + 2
  config keys + 11 tests. Single focused PR. ✅
- **Ambiguity check:** "interval" is in minutes (config) → converted to
  seconds in `_interval_seconds()`. "ws_broadcast" is typed as
  `Callable[[str, dict], Awaitable[None]]` — no ambiguity. ✅
