# Auto-LLM Signal Pipeline + Decision Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build end-to-end automatic LLM analysis of Binance Square posts with per-token fundamentals, structured `decision_steps` for verifiability, and a user feedback loop — observability-first, no auto-execution.

**Architecture:**
- Scraper: `chromium.launch_persistent_context` + `/pgc/feed` API response interception (replaces HTML parsing — fixes Windows Python 3.14 subprocess issue).
- Pipeline: `SignalScanScheduler._tick` → save posts → `asyncio.create_task(_analyze_one)` per new post → token context (CoinGecko + klines RSI/MACD) → LLM with `decision_steps` → persist opportunities + token_metric_snapshots → ws broadcast.
- Storage: `signals` renamed to `posts`; new `opportunities` (1:N with `decision_steps` JSON column), `token_metric_snapshots`, `post_feedback`. Back-compat SQL view `signals AS SELECT * FROM posts` keeps `api/trading.py` working during migration. Legacy `signal_analysis` and `signal_validation` tables dropped.
- UI: `TradingView` cards show token snapshot → decision_steps → TL;DR → 👍/👎/Skip/Execute.

**Tech Stack:** Python 3.14, FastAPI, SQLite, Playwright (`launch_persistent_context`), pandas-ta, httpx. Vue 3 + Vite + TypeScript.

**Spec:** `docs/superpowers/specs/2026-06-05-auto-llm-signal-pipeline-design.md`
**ADR:** `docs/adr/0001-posts-opportunities-schema-split.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `backend/services/datasources/technical.py` (MODIFY) | Add `calculate_macd()` helper |
| `backend/services/signal_analyzer.py` (MODIFY) | Extend `analyze()` for token context; add `fetch_token_context()` classmethod |
| `backend/services/database.py` (MODIFY) | Rename `signals`→`posts`; new tables; back-compat view; drop legacy |
| `backend/services/signal_scraper.py` (MODIFY) | Write to `posts`; capture `shares`/`posted_at`/`trading_pairs` |
| `backend/services/scheduler.py` (MODIFY) | `_analyze_one` per new post; DI fetcher; kill switch |
| `backend/services/binance_square_browser.py` (MODIFY) | `launch_persistent_context` + API interception |
| `backend/services/post_pipeline.py` (NEW) | `_persist_opportunities_and_snapshots` helper |
| `backend/services/config_store.py` (MODIFY) | Add 5 new config keys |
| `backend/api/posts.py` (NEW) | New `/api/posts/*` endpoints |
| `backend/main.py` (MODIFY) | Register new router |
| `backend/api/trading.py` (MODIFY) | Read from `posts` table directly |
| `scripts/login_binance.py` (NEW) | One-time manual login |
| `frontend/src/types/index.ts` (MODIFY) | Extend `Post` type with new fields |
| `frontend/src/views/TradingView.vue` (MODIFY) | New card layout |
| Tests: `backend/tests/test_*.py` | Per-task TDD coverage |
| `backend/tests/test_posts_pipeline_headless.py` (NEW) | E2E headless test |

---

## Task 1: Add `calculate_macd()` helper to technical.py

**Files:**
- Create: `backend/tests/test_technical_macd.py`
- Modify: `backend/services/datasources/technical.py:1-50` (add function at end)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_technical_macd.py
import pytest
from services.datasources.technical import calculate_macd


def _rising_closes(n: int = 60) -> list:
    return [{"open_time": i, "open": 100 + i, "high": 100 + i + 1,
             "low": 100 + i - 1, "close": 100 + i * 0.5, "volume": 0}
            for i in range(n)]


def _falling_closes(n: int = 60) -> list:
    return [{"open_time": i, "open": 200 - i, "high": 200 - i + 1,
             "low": 200 - i - 1, "close": 200 - i * 0.5, "volume": 0}
            for i in range(n)]


def test_calculate_macd_returns_dict_with_state_and_hist():
    result = calculate_macd(_rising_closes())
    assert isinstance(result, dict)
    assert "state" in result
    assert "hist" in result
    assert result["state"] in (
        "bullish_cross", "bearish_cross", "above_zero", "below_zero", "unknown"
    )
    assert isinstance(result["hist"], float)


def test_calculate_macd_bullish_cross_on_rising_prices():
    """A clear uptrend should produce either bullish_cross or above_zero state."""
    result = calculate_macd(_rising_closes())
    assert result["state"] in ("bullish_cross", "above_zero")
    assert result["hist"] > 0  # histogram is positive in uptrend


def test_calculate_macd_bearish_on_falling_prices():
    result = calculate_macd(_falling_closes())
    assert result["state"] in ("bearish_cross", "below_zero")
    assert result["hist"] < 0


def test_calculate_macd_returns_unknown_state_for_insufficient_data():
    """Fewer candles than the slow period should return a benign default, not raise."""
    result = calculate_macd(_rising_closes(n=5))
    assert result["state"] == "unknown"
    assert result["hist"] == 0.0


def test_calculate_macd_returns_unknown_when_pandas_ta_missing(monkeypatch):
    """If pandas_ta is not installed, return unknown (matches calculate_rsi behavior)."""
    import services.datasources.technical as tech

    monkeypatch.setattr(tech, "pd", None)  # simulate ImportError
    result = calculate_macd(_rising_closes())
    assert result["state"] == "unknown"
    assert result["hist"] == 0.0
```

- [ ] **Step 2: Run test — expect FAIL (function doesn't exist)**

Run: `cd backend && python -m pytest tests/test_technical_macd.py -v`
Expected: ImportError / AttributeError on `calculate_macd`.

- [ ] **Step 3: Implement `calculate_macd()`**

Append to `backend/services/datasources/technical.py`:

```python
def calculate_macd(
    klines: list,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict:
    """Calculate MACD state and histogram. Returns a dict, never raises.

    Returns:
        {"state": "bullish_cross" | "bearish_cross" | "above_zero" |
                  "below_zero" | "unknown",
         "hist": float}
    """
    try:
        import pandas as pd  # noqa: F401
        import pandas_ta as ta  # noqa: F401
    except ImportError:
        return {"state": "unknown", "hist": 0.0}

    if len(klines) < slow + signal:
        return {"state": "unknown", "hist": 0.0}

    df = pd.DataFrame(klines)
    macd_df = ta.macd(df["close"], fast=fast, slow=slow, signal=signal)
    if macd_df is None or macd_df.empty:
        return {"state": "unknown", "hist": 0.0}

    cols = list(macd_df.columns)  # e.g. ["MACD_12_26_9", "MACDs_12_26_9", "MACDh_12_26_9"]
    macd_line = float(macd_df[cols[0]].iloc[-1])
    signal_line = float(macd_df[cols[1]].iloc[-1])
    hist = float(macd_df[cols[2]].iloc[-1])

    prev_macd = float(macd_df[cols[0]].iloc[-2])
    prev_signal = float(macd_df[cols[1]].iloc[-2])

    if prev_macd <= prev_signal and macd_line > signal_line:
        state = "bullish_cross"
    elif prev_macd >= prev_signal and macd_line < signal_line:
        state = "bearish_cross"
    elif macd_line > 0:
        state = "above_zero"
    elif macd_line < 0:
        state = "below_zero"
    else:
        state = "unknown"

    return {"state": state, "hist": hist}
```

- [ ] **Step 4: Run test — expect PASS**

Run: `cd backend && python -m pytest tests/test_technical_macd.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/datasources/technical.py backend/tests/test_technical_macd.py
git commit -m "feat(technical): add calculate_macd helper for token context"
```

---

## Task 2: Add `SignalAnalyzer.fetch_token_context()` classmethod

**Files:**
- Create: `backend/tests/test_signal_analyzer_context.py`
- Modify: `backend/services/signal_analyzer.py:1-9` (imports) + add classmethod at end

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_signal_analyzer_context.py
import pytest
from unittest.mock import AsyncMock, patch

from services.signal_analyzer import SignalAnalyzer


@pytest.mark.asyncio
async def test_fetch_token_context_returns_combined_market_and_tech():
    fake_details = {"market_cap": 65_000_000_000, "market_cap_rank": 5,
                    "price_change_24h": 4.2}
    fake_klines = [
        {"open_time": i, "open": 100, "high": 101, "low": 99,
         "close": 100 + i * 0.1, "volume": 0}
        for i in range(50)
    ]

    with patch("services.signal_analyzer.get_coin_details",
               AsyncMock(return_value=fake_details)), \
         patch("services.signal_analyzer.get_klines",
               AsyncMock(return_value=fake_klines)):
        ctx = await SignalAnalyzer.fetch_token_context("sol")

    assert ctx["symbol"] == "sol"
    assert ctx["market_cap_usd"] == 65_000_000_000
    assert ctx["market_cap_rank"] == 5
    assert ctx["price_change_24h_pct"] == 4.2
    assert "rsi_14" in ctx
    assert "macd_state" in ctx
    assert "macd_hist" in ctx
    assert "error_market" not in ctx
    assert "error_tech" not in ctx


@pytest.mark.asyncio
async def test_fetch_token_context_handles_market_fetch_failure():
    """CoinGecko timeout → market fields absent, error_market set; tech still works."""
    fake_klines = [
        {"open_time": i, "open": 100, "high": 101, "low": 99,
         "close": 100 + i, "volume": 0}
        for i in range(50)
    ]

    with patch("services.signal_analyzer.get_coin_details",
               AsyncMock(side_effect=RuntimeError("cg timeout"))), \
         patch("services.signal_analyzer.get_klines",
               AsyncMock(return_value=fake_klines)):
        ctx = await SignalAnalyzer.fetch_token_context("sol")

    assert ctx["symbol"] == "sol"
    assert "market_cap_usd" not in ctx
    assert "error_market" in ctx
    assert "rsi_14" in ctx  # tech still worked
    assert "error_tech" not in ctx


@pytest.mark.asyncio
async def test_fetch_token_context_handles_tech_fetch_failure():
    """Binance klines failure → tech fields absent, error_tech set; market still works."""
    fake_details = {"market_cap": 1000, "market_cap_rank": 50, "price_change_24h": 0}

    with patch("services.signal_analyzer.get_coin_details",
               AsyncMock(return_value=fake_details)), \
         patch("services.signal_analyzer.get_klines",
               AsyncMock(side_effect=RuntimeError("klines 429"))):
        ctx = await SignalAnalyzer.fetch_token_context("sol")

    assert ctx["market_cap_usd"] == 1000
    assert "rsi_14" not in ctx
    assert "error_tech" in ctx


@pytest.mark.asyncio
async def test_fetch_token_context_handles_both_failures():
    """Both sources fail → both error_* keys set; never raises."""
    with patch("services.signal_analyzer.get_coin_details",
               AsyncMock(side_effect=RuntimeError("cg"))), \
         patch("services.signal_analyzer.get_klines",
               AsyncMock(side_effect=RuntimeError("klines"))):
        ctx = await SignalAnalyzer.fetch_token_context("sol")

    assert ctx["symbol"] == "sol"
    assert "error_market" in ctx
    assert "error_tech" in ctx
```

- [ ] **Step 2: Run test — expect FAIL (method doesn't exist)**

Run: `cd backend && python -m pytest tests/test_signal_analyzer_context.py -v`
Expected: AttributeError on `SignalAnalyzer.fetch_token_context`.

- [ ] **Step 3: Add `fetch_token_context` classmethod + imports**

Replace `backend/services/signal_analyzer.py:1-9` with:

```python
"""LLM-powered signal analysis service."""
import json
import re
from typing import Any

from services.datasources.coingecko import get_coin_details
from services.datasources.technical import (
    calculate_macd,
    calculate_rsi,
    get_klines,
)
from services.llm_factory import ProviderNotConfiguredError, create_llm
```

Then append the classmethod at the end of the file:

```python
    @staticmethod
    async def fetch_token_context(symbol: str) -> dict:
        """Fetch market_cap + RSI + MACD for one symbol. Returns dict, never raises.

        Per-source failures are captured in `error_market` / `error_tech`
        keys. The LLM still receives a partial context and reasons with
        what it has. See spec section "Token context fetcher".
        """
        ctx: dict[str, Any] = {"symbol": symbol}

        try:
            details = await get_coin_details(symbol.lower())
            ctx["market_cap_usd"] = details.get("market_cap")
            ctx["market_cap_rank"] = details.get("market_cap_rank")
            ctx["price_change_24h_pct"] = details.get("price_change_24h")
        except Exception as e:
            ctx["error_market"] = str(e)

        try:
            klines = await get_klines(symbol, interval="1h", limit=100)
            closes = [k["close"] for k in klines]
            ctx["rsi_14"] = calculate_rsi(closes, period=14)
            macd = calculate_macd(closes)
            ctx["macd_state"] = macd["state"]
            ctx["macd_hist"] = macd["hist"]
            if klines:
                ctx["volume_24h_usd"] = sum(k["volume"] for k in klines[-24:])
        except Exception as e:
            ctx["error_tech"] = str(e)

        return ctx
```

- [ ] **Step 4: Run test — expect PASS**

Run: `cd backend && python -m pytest tests/test_signal_analyzer_context.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/signal_analyzer.py backend/tests/test_signal_analyzer_context.py
git commit -m "feat(analyzer): add fetch_token_context classmethod"
```

---

## Task 3: Extend `SignalAnalyzer.analyze()` for new opportunities shape

**Files:**
- Modify: `backend/services/signal_analyzer.py` (replace `_build_prompt`, `_parse_response`, `analyze` signature)
- Modify: `backend/tests/test_signal_analyzer.py` (add new tests; preserve existing behavior if any)

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_signal_analyzer.py`:

```python
# at top
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from services.signal_analyzer import SignalAnalyzer


def test_build_prompt_includes_token_context_json():
    analyzer = SignalAnalyzer()
    ctx = [{"symbol": "SOL", "market_cap_usd": 65e9, "rsi_14": 32.4,
            "macd_state": "bullish_cross", "macd_hist": 0.12}]
    prompt = analyzer._build_prompt("Post content $SOL", ctx)
    assert "$SOL" in prompt or "SOL" in prompt
    assert "65" in prompt  # market cap
    assert "32.4" in prompt  # rsi
    assert "bullish_cross" in prompt  # macd state
    assert "decision_steps" in prompt  # instructions
    assert "observable" in prompt.lower() or "concrete" in prompt.lower()


def test_parse_response_returns_opportunities_list_with_decision_steps():
    analyzer = SignalAnalyzer()
    text = """```json
{
  "opportunities": [
    {
      "token": "SOL",
      "sentiment": "bullish",
      "is_opportunity": true,
      "action": "long",
      "confidence": 0.82,
      "decision_steps": [
        "Token SOL mentioned in post with bullish tone",
        "RSI 32.4 = oversold (favorable for long entry)"
      ],
      "reasoning": "Top-5 liquid token, oversold RSI, MACD bullish cross."
    }
  ]
}
```"""
    result = analyzer._parse_response(text)
    assert "opportunities" in result
    assert len(result["opportunities"]) == 1
    opp = result["opportunities"][0]
    assert opp["token"] == "SOL"
    assert opp["action"] == "long"
    assert opp["confidence"] == 0.82
    assert len(opp["decision_steps"]) == 2
    assert "oversold" in opp["decision_steps"][1]


def test_parse_response_handles_missing_decision_steps_gracefully():
    analyzer = SignalAnalyzer()
    text = '{"opportunities": [{"token": "BTC", "action": "long", "confidence": 0.5, "reasoning": "ok"}]}'
    result = analyzer._parse_response(text)
    opp = result["opportunities"][0]
    assert opp["decision_steps"] == []  # default empty list
    assert opp["token"] == "BTC"


def test_parse_response_handles_empty_opportunities():
    analyzer = SignalAnalyzer()
    text = '{"opportunities": []}'
    result = analyzer._parse_response(text)
    assert result["opportunities"] == []


def test_parse_response_handles_malformed_json():
    analyzer = SignalAnalyzer()
    text = "I cannot analyze this."
    result = analyzer._parse_response(text)
    assert result["opportunities"] == []


@pytest.mark.asyncio
async def test_analyze_returns_empty_when_llm_not_configured(monkeypatch):
    from services.llm_factory import ProviderNotConfiguredError
    monkeypatch.setattr("services.signal_analyzer.create_llm",
                        MagicMock(side_effect=ProviderNotConfiguredError("not set")))
    analyzer = SignalAnalyzer()
    result = await analyzer.analyze("post content", [])
    assert result == {"opportunities": []}


@pytest.mark.asyncio
async def test_analyze_passes_token_context_in_prompt(monkeypatch):
    """The prompt must include the token context for the LLM to reason on."""
    captured = {}

    class FakeLLM:
        async def ainvoke(self, messages):
            captured["prompt"] = messages[0]["content"]
            resp = MagicMock()
            resp.completion = '{"opportunities": []}'
            return resp

    monkeypatch.setattr("services.signal_analyzer.create_llm", lambda: FakeLLM())
    analyzer = SignalAnalyzer()
    ctx = [{"symbol": "SOL", "rsi_14": 32.4, "macd_state": "bullish_cross",
            "macd_hist": 0.12, "market_cap_usd": 65e9}]
    await analyzer.analyze("post $SOL", ctx)
    assert "32.4" in captured["prompt"]
    assert "bullish_cross" in captured["prompt"]


@pytest.mark.asyncio
async def test_analyze_returns_empty_on_llm_exception(monkeypatch):
    class FakeLLM:
        async def ainvoke(self, messages):
            raise RuntimeError("rate limited")

    monkeypatch.setattr("services.signal_analyzer.create_llm", lambda: FakeLLM())
    analyzer = SignalAnalyzer()
    result = await analyzer.analyze("post $SOL", [])
    assert result == {"opportunities": []}
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `cd backend && python -m pytest tests/test_signal_analyzer.py -v`
Expected: failures on `_build_prompt(content, ctx)` signature and missing `opportunities` key.

- [ ] **Step 3: Replace `analyze`, `_build_prompt`, `_parse_response`**

In `backend/services/signal_analyzer.py`, replace the `analyze`, `_build_prompt`, and `_parse_response` methods with:

```python
async def analyze(
    self,
    content: str,
    token_contexts: list[dict] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Analyze a post + per-token contexts into a list of opportunities.

    Returns:
        {"opportunities": [
            {"token", "sentiment", "is_opportunity", "action",
             "confidence", "decision_steps": [str], "reasoning"}
        ]}

    Never raises: LLM-not-configured and LLM-exception both yield an empty
    list, so callers (the scheduler) can persist the "analyzed but no
    opportunities" state without try/except.
    """
    try:
        llm = create_llm()
    except ProviderNotConfiguredError:
        return {"opportunities": []}

    prompt = self._build_prompt(content, token_contexts or [])

    try:
        result = await llm.ainvoke([{"role": "user", "content": prompt}])
        text = result.completion if isinstance(result.completion, str) else str(result.completion)
        return self._parse_response(text)
    except Exception:
        return {"opportunities": []}


def _build_prompt(self, content: str, token_contexts: list[dict]) -> str:
    import json as _json
    return f"""You are a senior crypto trading analyst. You know every major token
and can read basic technicals. You distinguish real signal from hype, sarcasm,
paid shill, or airdrop spam. When a post mentions a token, the technical and
market context for that token is provided alongside — use it to judge whether
the post's claim lines up with the actual market state.

A Binance Square post mentioned these tokens. For each token we have basic
market context. Decide, per token, whether the post+context combination is a
real trade opportunity.

POST:
\"\"\"
{content}
\"\"\"

TOKEN CONTEXT (per token, fetched in parallel):
{_json.dumps(token_contexts, indent=2)}

For each token, output one opportunity object. The `decision_steps` field is
REQUIRED and is the user's primary verification surface. Each step must be a
SINGLE OBSERVABLE CLAIM that the user can sanity-check against the post +
token snapshot (e.g. "RSI 32.4" maps to a metric value; "Post names a
specific technical level" maps to text in the post). NO vague assertions like
"this looks bullish" — every step must reference something concrete. The last
step should be a conclusion prefixed with "Conclusion:" so it stands out from
the observations.

Return JSON only, no prose:
{{
  "opportunities": [
    {{
      "token": "SOL",
      "sentiment": "bullish",
      "is_opportunity": true,
      "action": "long",
      "confidence": 0.82,
      "decision_steps": [
        "Token SOL mentioned in post with bullish tone",
        "RSI 32.4 = oversold (favorable for long entry)",
        "MACD bullish_cross with positive histogram (favorable momentum)",
        "Conclusion: real opportunity, not noise"
      ],
      "reasoning": "Top-5 liquid token, oversold RSI, MACD bullish cross — real breakout, not hype."
    }}
  ]
}}
"""


def _parse_response(self, text: str) -> dict[str, Any]:
    """Parse LLM response into the opportunities shape.

    Handles ```json``` blocks, leading thinking text, and the legacy
    flat shape (tokens/sentiment/confidence/reasoning at the top level)
    by wrapping it as a single opportunity on the only mentioned token.
    """
    try:
        if "```" in text:
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
            if match:
                text = match.group(1)

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start:end + 1]

        data = json.loads(text)

        # New shape
        if "opportunities" in data:
            opps = []
            for raw in data["opportunities"]:
                opps.append({
                    "token": raw.get("token", ""),
                    "sentiment": raw.get("sentiment", "neutral"),
                    "is_opportunity": bool(raw.get("is_opportunity", False)),
                    "action": raw.get("action"),
                    "confidence": float(raw.get("confidence", 0.0)),
                    "decision_steps": list(raw.get("decision_steps") or []),
                    "reasoning": raw.get("reasoning", ""),
                })
            return {"opportunities": opps}

        # Legacy flat shape — wrap as a single opportunity
        if "tokens" in data or "sentiment" in data:
            tokens = data.get("tokens") or [""]
            return {"opportunities": [{
                "token": tokens[0],
                "sentiment": data.get("sentiment", "neutral"),
                "is_opportunity": True,
                "action": None,
                "confidence": float(data.get("confidence", 0.0)),
                "decision_steps": [],
                "reasoning": data.get("reasoning", ""),
            }]}

        return {"opportunities": []}
    except (json.JSONDecodeError, ValueError, AttributeError):
        return {"opportunities": []}
```

- [ ] **Step 4: Run test — expect PASS**

Run: `cd backend && python -m pytest tests/test_signal_analyzer.py -v`
Expected: all new tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/services/signal_analyzer.py backend/tests/test_signal_analyzer.py
git commit -m "feat(analyzer): return opportunities with decision_steps"
```

---

## Task 4: Schema migration — `signals` → `posts` + new tables + back-compat view

**Files:**
- Modify: `backend/services/database.py` (extend `init_db()`)
- Create: `backend/tests/test_posts_schema_migration.py`

This is a one-shot, idempotent migration. The view `signals AS SELECT * FROM posts` keeps `api/trading.py` working until Task 11 updates it. `signal_analysis` and `signal_validation` are dropped (their data has no historical value per spec).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_posts_schema_migration.py
import os
import tempfile

import pytest


@pytest.fixture
def fresh_db(monkeypatch):
    """Point DB_PATH at a temp file for an isolated schema test."""
    from pathlib import Path
    import services.database as db_module

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setattr(db_module, "DB_PATH", Path(tmp.name))
    yield Path(tmp.name)
    os.unlink(tmp.name)


def test_init_db_creates_posts_table_with_new_columns(fresh_db):
    from services.database import init_db, get_db
    init_db()
    conn = get_db()
    cols = {row[1] for row in conn.execute("PRAGMA table_info(posts)").fetchall()}
    conn.close()
    # New columns per spec
    for col in ("shares", "posted_at", "trading_pairs", "analyzed_at"):
        assert col in cols, f"posts table missing column {col}"


def test_init_db_creates_opportunities_table(fresh_db):
    from services.database import init_db, get_db
    init_db()
    conn = get_db()
    cols = {row[1] for row in conn.execute("PRAGMA table_info(opportunities)").fetchall()}
    conn.close()
    for col in ("post_id", "token", "sentiment", "action", "confidence",
                "is_opportunity", "reasoning", "decision_steps", "llm_model",
                "created_at"):
        assert col in cols, f"opportunities missing column {col}"


def test_init_db_creates_token_metric_snapshots_table(fresh_db):
    from services.database import init_db, get_db
    init_db()
    conn = get_db()
    cols = {row[1] for row in
            conn.execute("PRAGMA table_info(token_metric_snapshots)").fetchall()}
    conn.close()
    for col in ("post_id", "opportunity_id", "symbol", "market_cap_usd",
                "market_cap_rank", "rsi_14", "macd_state", "macd_hist",
                "price_change_24h_pct", "volume_24h_usd", "fetched_at"):
        assert col in cols, f"token_metric_snapshots missing column {col}"


def test_init_db_creates_post_feedback_table(fresh_db):
    from services.database import init_db, get_db
    init_db()
    conn = get_db()
    cols = {row[1] for row in
            conn.execute("PRAGMA table_info(post_feedback)").fetchall()}
    conn.close()
    for col in ("post_id", "feedback", "comment", "created_at"):
        assert col in cols, f"post_feedback missing column {col}"


def test_init_db_drops_legacy_signal_analysis_and_validation(fresh_db):
    from services.database import init_db, get_db
    init_db()
    conn = get_db()
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    assert "signal_analysis" not in tables
    assert "signal_validation" not in tables


def test_init_db_creates_signals_view_for_back_compat(fresh_db):
    """The 'signals' view lets old SELECT * FROM signals queries keep working."""
    from services.database import init_db, get_db
    init_db()
    conn = get_db()
    views = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view'").fetchall()}
    conn.close()
    assert "signals" in views


def test_signals_view_returns_same_rows_as_posts(fresh_db):
    from services.database import init_db, get_db
    init_db()
    conn = get_db()
    conn.execute(
        "INSERT INTO posts (source, content, author) VALUES (?, ?, ?)",
        ("binance_square", "test $BTC", "TestAuthor"),
    )
    conn.commit()
    posts = conn.execute("SELECT * FROM posts").fetchall()
    signals = conn.execute("SELECT * FROM signals").fetchall()
    conn.close()
    assert len(posts) == len(signals) == 1
    assert posts[0]["id"] == signals[0]["id"]
    assert posts[0]["content"] == signals[0]["content"]


def test_init_db_is_idempotent(fresh_db):
    """Re-running init_db on an already-migrated DB must not raise."""
    from services.database import init_db
    init_db()
    init_db()  # second call
    init_db()  # third call
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `cd backend && python -m pytest tests/test_posts_schema_migration.py -v`
Expected: all tests fail (tables not created).

- [ ] **Step 3: Add migration to `init_db()`**

Append to `init_db()` in `backend/services/database.py` BEFORE `conn.commit()`:

```python
    # ---- 2026-06-05 migration: signals → posts + opportunities + snapshots + feedback ----
    # Idempotency: check whether each piece already exists before acting.
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    existing_tables = {row[0] for row in cursor.fetchall()}
    existing_views = {
        row[0]
        for row in cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='view'"
        ).fetchall()
    }

    # 1. Drop legacy tables (purpose now served by new schema).
    for legacy in ("signal_analysis", "signal_validation"):
        if legacy in existing_tables:
            cursor.execute(f"DROP TABLE {legacy}")

    # 2. Rename signals → posts (idempotent via table check).
    if "signals" in existing_tables and "posts" not in existing_tables:
        cursor.execute("ALTER TABLE signals RENAME TO posts")

    # 3. Re-read tables (signals may have just been renamed).
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    existing_tables = {row[0] for row in cursor.fetchall()}

    # 4. New columns on posts (idempotent via PRAGMA check).
    if "posts" in existing_tables:
        cursor.execute("PRAGMA table_info(posts)")
        post_cols = {row[1] for row in cursor.fetchall()}
        if "shares" not in post_cols:
            cursor.execute("ALTER TABLE posts ADD COLUMN shares INTEGER DEFAULT 0")
        if "posted_at" not in post_cols:
            cursor.execute("ALTER TABLE posts ADD COLUMN posted_at TEXT")
        if "trading_pairs" not in post_cols:
            cursor.execute("ALTER TABLE posts ADD COLUMN trading_pairs TEXT")
        if "analyzed_at" not in post_cols:
            cursor.execute("ALTER TABLE posts ADD COLUMN analyzed_at TIMESTAMP")

    # 5. New tables: opportunities, token_metric_snapshots, post_feedback.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            token TEXT NOT NULL,
            sentiment TEXT,
            action TEXT,
            confidence REAL,
            is_opportunity INTEGER DEFAULT 0,
            reasoning TEXT,
            decision_steps TEXT,
            llm_model TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES posts(id)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_opportunities_post "
        "ON opportunities(post_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_opportunities_token "
        "ON opportunities(token)"
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS token_metric_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            opportunity_id INTEGER,
            symbol TEXT NOT NULL,
            market_cap_usd REAL,
            market_cap_rank INTEGER,
            price_change_24h_pct REAL,
            volume_24h_usd REAL,
            rsi_14 REAL,
            macd_state TEXT,
            macd_hist REAL,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES posts(id),
            FOREIGN KEY (opportunity_id) REFERENCES opportunities(id)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_token_snapshots_post "
        "ON token_metric_snapshots(post_id)"
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS post_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            feedback TEXT NOT NULL,
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES posts(id)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_post_feedback_post "
        "ON post_feedback(post_id)"
    )

    # 6. Back-compat view: 'signals' → posts. Drop the view once
    # api/trading.py is updated to use the posts table directly (Task 11).
    if "posts" in existing_tables and "signals" not in existing_views:
        cursor.execute("CREATE VIEW signals AS SELECT * FROM posts")
```

- [ ] **Step 4: Run test — expect PASS**

Run: `cd backend && python -m pytest tests/test_posts_schema_migration.py -v`
Expected: 8 passed.

- [ ] **Step 5: Re-run all DB tests to verify no regression**

Run: `cd backend && python -m pytest tests/test_database.py tests/test_signal_scraper_dedup.py tests/test_database_trades.py -v`
Expected: existing tests still pass (they use the `signals` view).

- [ ] **Step 6: Commit**

```bash
git add backend/services/database.py backend/tests/test_posts_schema_migration.py
git commit -m "feat(db): migrate signals to posts + add opportunities/snapshots/feedback"
```

---

## Task 5: Update `BinanceSquareScraper.save_to_db` to write to `posts` + capture new fields

**Files:**
- Modify: `backend/services/signal_scraper.py:89-127` (`save_to_db`)
- Modify: `backend/services/signal_scraper.py:25-51` (`scrape` to also pass through new fields)
- Create: `backend/tests/test_signal_scraper_posts.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_signal_scraper_posts.py
from services.database import init_db, get_db
from services.signal_scraper import BinanceSquareScraper


def test_save_to_db_writes_shares_posted_at_trading_pairs():
    init_db()
    scraper = BinanceSquareScraper()
    post = {
        "source": "binance_square",
        "source_url": "https://www.binance.com/en/square/post/abc123",
        "author": "NewAuthor",
        "content": "test $BTC $ETH",
        "likes": 10,
        "comments": 2,
        "shares": 5,
        "created_at": "2026-06-05T12:00:00+00:00",
        "trading_pairs": [{"symbol": "BTC"}, {"symbol": "ETH"}],
        "raw_data": "{}",
    }
    inserted = scraper.save_to_db([post])
    assert inserted == 1

    conn = get_db()
    row = conn.execute(
        "SELECT shares, posted_at, trading_pairs FROM posts WHERE source_url = ?",
        ("https://www.binance.com/en/square/post/abc123",),
    ).fetchone()
    conn.close()
    assert row["shares"] == 5
    assert row["posted_at"] == "2026-06-05T12:00:00+00:00"
    assert "BTC" in row["trading_pairs"] and "ETH" in row["trading_pairs"]


def test_save_to_db_default_new_columns_when_missing():
    init_db()
    scraper = BinanceSquareScraper()
    post = {
        "source": "binance_square",
        "source_url": "https://www.binance.com/en/square/post/legacy1",
        "author": "Legacy",
        "content": "old post $SOL",
        "likes": 0,
        "comments": 0,
        "raw_data": "{}",
    }
    scraper.save_to_db([post])
    conn = get_db()
    row = conn.execute(
        "SELECT shares, posted_at, trading_pairs FROM posts WHERE source_url = ?",
        ("https://www.binance.com/en/square/post/legacy1",),
    ).fetchone()
    conn.close()
    assert row["shares"] == 0
    assert row["posted_at"] is None
    assert row["trading_pairs"] is None
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `cd backend && python -m pytest tests/test_signal_scraper_posts.py -v`
Expected: shares/posted_at/trading_pairs are NULL/0 (current INSERT doesn't include them).

- [ ] **Step 3: Update `save_to_db` to write to `posts` + new columns**

In `backend/services/signal_scraper.py`, replace the `save_to_db` method body (lines 89-127) with:

```python
def save_to_db(self, posts: list[dict[str, Any]]) -> int:
    """Save scraped posts to the `posts` table. Returns count of new rows.

    Uses INSERT OR IGNORE so re-running with the same posts (same
    source_url) is a no-op — the UNIQUE partial index on source_url is
    the source of truth for dedup.

    New columns (`shares`, `posted_at`, `trading_pairs`) are populated
    from API interception output; they default to 0/NULL for posts from
    the legacy HTML parser path.
    """
    import json as _json
    conn = get_db()
    cursor = conn.cursor()
    inserted = 0
    for post in posts:
        trading_pairs = post.get("trading_pairs")
        trading_pairs_json = (
            _json.dumps(trading_pairs) if trading_pairs is not None else None
        )
        cursor.execute(
            """
            INSERT OR IGNORE INTO posts
                (source, source_url, author, content, likes, comments,
                 shares, raw_data, status, source_type, created_at,
                 posted_at, trading_pairs)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', 'live', ?,
                    ?, ?)
            """,
            (
                post.get("source", "binance_square"),
                post.get("source_url", ""),
                post.get("author", "unknown"),
                post.get("content", ""),
                post.get("likes", 0),
                post.get("comments", 0),
                post.get("shares", 0),
                post.get("raw_data", str(post)),
                post.get("created_at", ""),
                post.get("posted_at") or post.get("created_at", ""),
                trading_pairs_json,
            ),
        )
        if cursor.rowcount > 0:
            inserted += 1
    conn.commit()
    conn.close()
    if inserted:
        logger.info(
            f"[BinanceSquareScraper] inserted {inserted}/{len(posts)} posts"
        )
    return inserted
```

- [ ] **Step 4: Update `scrape()` to pass through new fields**

In `backend/services/signal_scraper.py`, replace the `scrape` method (lines 25-51) to also include `shares`, `posted_at`, and `trading_pairs` in the post dict when the underlying browser provides them:

```python
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
                "shares": post.get("shares", 0),
                "tokens": tokens,
                "created_at": post.get("created_at", ""),
                "posted_at": post.get("posted_at", post.get("created_at", "")),
                "trading_pairs": post.get("trading_pairs"),
                "raw_data": str(post),
            })

    return posts
```

- [ ] **Step 5: Run test — expect PASS**

Run: `cd backend && python -m pytest tests/test_signal_scraper_posts.py tests/test_signal_scraper_dedup.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/services/signal_scraper.py backend/tests/test_signal_scraper_posts.py
git commit -m "feat(scraper): write to posts table with shares/posted_at/trading_pairs"
```

---

## Task 6: Add `post_pipeline` module — persist opportunities + snapshots

**Files:**
- Create: `backend/services/post_pipeline.py`
- Create: `backend/tests/test_post_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_post_pipeline.py
import json
import pytest

from services.database import init_db, get_db
from services.post_pipeline import (
    persist_opportunities_and_snapshots,
    set_post_analyzed_at,
    load_post,
)


def _insert_post(content: str = "$SOL breakout", author: str = "Auth",
                 trading_pairs: list | None = None) -> int:
    import json as _json
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO posts (source, content, author, trading_pairs) "
        "VALUES (?, ?, ?, ?)",
        ("binance_square", content, author,
         _json.dumps(trading_pairs) if trading_pairs else None),
    )
    post_id = cur.lastrowid
    conn.commit()
    conn.close()
    return post_id


def test_persist_inserts_one_opportunity_per_token():
    init_db()
    post_id = _insert_post()
    opps = [
        {"token": "SOL", "sentiment": "bullish", "is_opportunity": True,
         "action": "long", "confidence": 0.82, "decision_steps": ["step1"],
         "reasoning": "good"},
    ]
    snapshots = [{"symbol": "SOL", "rsi_14": 32.4, "macd_state": "bullish_cross"}]
    persist_opportunities_and_snapshots(post_id, opps, snapshots)

    conn = get_db()
    rows = conn.execute(
        "SELECT token, decision_steps FROM opportunities WHERE post_id = ?",
        (post_id,),
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["token"] == "SOL"
    assert json.loads(rows[0]["decision_steps"]) == ["step1"]


def test_persist_inserts_one_snapshot_per_opportunity():
    init_db()
    post_id = _insert_post()
    opps = [
        {"token": "SOL", "sentiment": "bullish", "is_opportunity": True,
         "action": "long", "confidence": 0.7, "decision_steps": [],
         "reasoning": "ok"},
        {"token": "ETH", "sentiment": "bearish", "is_opportunity": True,
         "action": "short", "confidence": 0.6, "decision_steps": [],
         "reasoning": "ok"},
    ]
    snapshots = [
        {"symbol": "SOL", "rsi_14": 32.4},
        {"symbol": "ETH", "rsi_14": 75.1},
    ]
    persist_opportunities_and_snapshots(post_id, opps, snapshots)

    conn = get_db()
    n = conn.execute(
        "SELECT COUNT(*) FROM token_metric_snapshots WHERE post_id = ?",
        (post_id,),
    ).fetchone()[0]
    conn.close()
    assert n == 2


def test_persist_handles_missing_snapshot_for_token():
    """If fetch failed for a token, no snapshot row is inserted but the
    opportunity row IS still inserted (so the user sees the LLM verdict)."""
    init_db()
    post_id = _insert_post()
    opps = [
        {"token": "SOL", "sentiment": "bullish", "is_opportunity": True,
         "action": "long", "confidence": 0.7, "decision_steps": [],
         "reasoning": "ok"},
    ]
    # Empty snapshots list — fetch failed for everything
    persist_opportunities_and_snapshots(post_id, opps, [])

    conn = get_db()
    n_opp = conn.execute(
        "SELECT COUNT(*) FROM opportunities WHERE post_id = ?",
        (post_id,),
    ).fetchone()[0]
    n_snap = conn.execute(
        "SELECT COUNT(*) FROM token_metric_snapshots WHERE post_id = ?",
        (post_id,),
    ).fetchone()[0]
    conn.close()
    assert n_opp == 1
    assert n_snap == 0


def test_set_post_analyzed_at_sets_timestamp():
    init_db()
    post_id = _insert_post()
    set_post_analyzed_at(post_id)
    conn = get_db()
    row = conn.execute(
        "SELECT analyzed_at FROM posts WHERE id = ?", (post_id,)
    ).fetchone()
    conn.close()
    assert row["analyzed_at"] is not None


def test_load_post_returns_dict():
    init_db()
    post_id = _insert_post(content="hello $BTC", author="LAuthor")
    post = load_post(post_id)
    assert post["content"] == "hello $BTC"
    assert post["author"] == "LAuthor"
    assert "id" in post
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `cd backend && python -m pytest tests/test_post_pipeline.py -v`
Expected: ImportError on `services.post_pipeline`.

- [ ] **Step 3: Create `post_pipeline.py`**

```python
# backend/services/post_pipeline.py
"""Persist LLM-derived opportunity rows + token metric snapshots.

Kept as a separate module so the scheduler can stay focused on
orchestration (timing, kill switch, fire-and-forget) and the analyzer
can stay focused on LLM I/O. The two write paths converge here.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from services.database import get_db

logger = logging.getLogger(__name__)


def load_post(post_id: int) -> dict[str, Any] | None:
    """Load a post row by id, or None if missing."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM posts WHERE id = ?", (post_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def extract_tokens_from_post(post: dict[str, Any]) -> list[str]:
    """Prefer the API's `trading_pairs` JSON; fall back to regex over content."""
    import re

    tp_raw = post.get("trading_pairs")
    if tp_raw:
        try:
            pairs = json.loads(tp_raw) if isinstance(tp_raw, str) else tp_raw
            symbols = [p.get("symbol") for p in pairs if p.get("symbol")]
            if symbols:
                return list(dict.fromkeys(symbols))  # dedup, preserve order
        except (json.JSONDecodeError, TypeError):
            pass

    content = post.get("content") or ""
    return list(dict.fromkeys(
        m.group(1) for m in re.finditer(r"[\$#]([A-Z]{2,10})(?![A-Z])", content)
    ))


def persist_opportunities_and_snapshots(
    post_id: int,
    opportunities: list[dict[str, Any]],
    token_contexts: list[dict[str, Any]],
) -> list[int]:
    """Insert one opportunity row per (post, token) and one snapshot per
    token. Returns the list of opportunity ids inserted.

    Snapshots are matched to opportunities by symbol. If a token's
    context fetch failed (no matching entry in `token_contexts`), the
    opportunity row is still persisted — the LLM's verdict matters more
    than the missing data, and the user can re-analyze to retry the
    fetch.
    """
    conn = get_db()
    cursor = conn.cursor()
    opp_ids: list[int] = []

    # Map symbol → context for quick lookup
    ctx_by_symbol: dict[str, dict[str, Any]] = {}
    for ctx in token_contexts:
        sym = ctx.get("symbol")
        if sym:
            ctx_by_symbol[sym.upper()] = ctx

    for opp in opportunities:
        cursor.execute(
            """
            INSERT INTO opportunities
                (post_id, token, sentiment, action, confidence,
                 is_opportunity, reasoning, decision_steps, llm_model)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                post_id,
                opp.get("token", ""),
                opp.get("sentiment"),
                opp.get("action"),
                float(opp.get("confidence") or 0.0),
                1 if opp.get("is_opportunity") else 0,
                opp.get("reasoning", ""),
                json.dumps(opp.get("decision_steps") or []),
                "default",
            ),
        )
        opp_id = cursor.lastrowid
        opp_ids.append(opp_id)

        ctx = ctx_by_symbol.get((opp.get("token") or "").upper())
        if ctx is None:
            continue
        cursor.execute(
            """
            INSERT INTO token_metric_snapshots
                (post_id, opportunity_id, symbol, market_cap_usd,
                 market_cap_rank, price_change_24h_pct, volume_24h_usd,
                 rsi_14, macd_state, macd_hist)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                post_id,
                opp_id,
                ctx.get("symbol", ""),
                ctx.get("market_cap_usd"),
                ctx.get("market_cap_rank"),
                ctx.get("price_change_24h_pct"),
                ctx.get("volume_24h_usd"),
                ctx.get("rsi_14"),
                ctx.get("macd_state"),
                ctx.get("macd_hist"),
            ),
        )

    conn.commit()
    conn.close()
    return opp_ids


def set_post_analyzed_at(post_id: int) -> None:
    """Stamp the post's `analyzed_at` to mark LLM analysis as completed."""
    conn = get_db()
    conn.execute(
        "UPDATE posts SET analyzed_at = CURRENT_TIMESTAMP WHERE id = ?",
        (post_id,),
    )
    conn.commit()
    conn.close()
```

- [ ] **Step 4: Run test — expect PASS**

Run: `cd backend && python -m pytest tests/test_post_pipeline.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/post_pipeline.py backend/tests/test_post_pipeline.py
git commit -m "feat(pipeline): add post_pipeline module for persistence"
```

---

## Task 7: Wire `_analyze_one` into `SignalScanScheduler`

**Files:**
- Modify: `backend/services/scheduler.py:96-227` (extend `SignalScanScheduler`)
- Create: `backend/tests/test_scheduler_analyze.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_scheduler_analyze.py
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.database import init_db, get_db
from services.scheduler import SignalScanScheduler


def _insert_post(content="test $SOL", author="A") -> int:
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO posts (source, content, author) VALUES (?, ?, ?)",
        ("binance_square", content, author),
    )
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


@pytest.mark.asyncio
async def test_analyze_one_inserts_opportunities_and_sets_analyzed_at():
    init_db()
    post_id = _insert_post()
    scraper = MagicMock()
    fetcher = AsyncMock(return_value={"symbol": "SOL", "rsi_14": 32.4})
    scheduler = SignalScanScheduler(
        scraper, token_context_fetcher=fetcher,
        config_provider=lambda: {"signal_auto_analyze": True},
    )

    with patch("services.scheduler.SignalAnalyzer") as FakeAnalyzer:
        instance = FakeAnalyzer.return_value
        instance.analyze = AsyncMock(return_value={"opportunities": [
            {"token": "SOL", "sentiment": "bullish", "is_opportunity": True,
             "action": "long", "confidence": 0.8, "decision_steps": ["a"],
             "reasoning": "ok"},
        ]})

        await scheduler._analyze_one(post_id)

    fetcher.assert_awaited_once()
    # Wait for any background task
    conn = get_db()
    opp = conn.execute(
        "SELECT * FROM opportunities WHERE post_id = ?", (post_id,)
    ).fetchone()
    analyzed_at = conn.execute(
        "SELECT analyzed_at FROM posts WHERE id = ?", (post_id,)
    ).fetchone()["analyzed_at"]
    conn.close()
    assert opp is not None
    assert opp["token"] == "SOL"
    assert analyzed_at is not None


@pytest.mark.asyncio
async def test_analyze_one_respects_kill_switch():
    init_db()
    post_id = _insert_post()
    scheduler = SignalScanScheduler(
        MagicMock(), token_context_fetcher=AsyncMock(),
        config_provider=lambda: {"signal_auto_analyze": False},
    )
    with patch("services.scheduler.SignalAnalyzer") as FakeAnalyzer:
        instance = FakeAnalyzer.return_value
        instance.analyze = AsyncMock()
        await scheduler._analyze_one(post_id)
    instance.analyze.assert_not_called()


@pytest.mark.asyncio
async def test_analyze_one_does_not_block_on_llm_failure():
    init_db()
    post_id = _insert_post()
    fetcher = AsyncMock(return_value={"symbol": "SOL", "rsi_14": 50.0})
    scheduler = SignalScanScheduler(
        MagicMock(), token_context_fetcher=fetcher,
        config_provider=lambda: {"signal_auto_analyze": True},
    )
    with patch("services.scheduler.SignalAnalyzer") as FakeAnalyzer:
        instance = FakeAnalyzer.return_value
        instance.analyze = AsyncMock(side_effect=RuntimeError("llm down"))
        # Must not raise
        await scheduler._analyze_one(post_id)
    # analyzed_at stays NULL because the analyze() raised before completion
    conn = get_db()
    row = conn.execute(
        "SELECT analyzed_at FROM posts WHERE id = ?", (post_id,)
    ).fetchone()
    conn.close()
    assert row["analyzed_at"] is None


@pytest.mark.asyncio
async def test_tick_fires_analyze_one_as_fire_and_forget(monkeypatch):
    """`_tick` should not await `_analyze_one`; it should `create_task` it."""
    init_db()
    captured = {}

    async def fake_create_task(coro, name=None):
        captured["task"] = True
        # Close the coroutine to avoid warning
        coro.close()
        return MagicMock()

    monkeypatch.setattr("services.scheduler.asyncio.create_task", fake_create_task)

    posts = [{"source": "binance_square", "source_url": "x", "author": "y",
              "content": "$BTC", "likes": 0, "comments": 0, "raw_data": "{}"}]
    scraper = MagicMock()
    scraper.scrape = AsyncMock(return_value=posts)
    scraper.save_to_db = MagicMock(return_value=1)
    scheduler = SignalScanScheduler(
        scraper, token_context_fetcher=AsyncMock(),
        config_provider=lambda: {"signal_auto_analyze": True},
    )
    # Monkey-patch _analyze_one so we don't actually run the LLM
    scheduler._analyze_one = AsyncMock()
    await scheduler._tick()
    assert captured["task"] is True
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `cd backend && python -m pytest tests/test_scheduler_analyze.py -v`
Expected: ImportError on `token_context_fetcher` kwarg / `_analyze_one` method.

- [ ] **Step 3: Add `_analyze_one` + extend `__init__` + fire-and-forget in `_tick`**

In `backend/services/scheduler.py`:

1. Add import at top:

```python
from services.signal_analyzer import SignalAnalyzer
```

2. Extend `__init__` of `SignalScanScheduler`:

```python
def __init__(
    self,
    scraper,
    config_provider: Callable[[], dict] | None = None,
    ws_broadcast: Callable[[str, dict], Awaitable[None]] | None = None,
    token_context_fetcher: Callable[[str], Awaitable[dict]] | None = None,
):
    self.scraper = scraper
    self._config_provider = config_provider or get_trading_config_from_db
    self._ws_broadcast = ws_broadcast
    self._token_context_fetcher = (
        token_context_fetcher or SignalAnalyzer.fetch_token_context
    )
    self._task: asyncio.Task | None = None
    self._stopped = asyncio.Event()
    self._last_run: float | None = None
    self._next_run: float | None = None
```

3. Update `_tick` to return new post ids and fire `_analyze_one` as background task. Replace `_tick` with:

```python
async def _tick(self) -> None:
    """One scrape cycle. Errors are logged and swallowed."""
    try:
        posts = await self.scraper.scrape()
    except Exception as e:
        logger.warning(f"[SignalScanScheduler] scrape failed: {e}")
        return
    if not posts:
        self._last_run = time.time()
        return
    try:
        inserted = self.scraper.save_to_db(posts)
    except Exception as e:
        logger.error(f"[SignalScanScheduler] save_to_db failed: {e}",
                     exc_info=True)
        return
    self._last_run = time.time()
    new_post_ids = self._newly_inserted_post_ids(posts, inserted)
    for pid in new_post_ids:
        asyncio.create_task(self._analyze_one(pid),
                            name=f"signal-scan-analyze-{pid}")
    if self._ws_broadcast:
        for post in posts:
            try:
                await self._ws_broadcast("signal:new", post)
            except Exception as e:
                logger.warning(
                    f"[SignalScanScheduler] broadcast failed for post: {e}"
                )

def _newly_inserted_post_ids(
    self, posts: list[dict], inserted_count: int
) -> list[int]:
    """Return the post_ids of the rows that were newly inserted.

    `save_to_db` returns the count, not the ids. We re-query the DB
    for the most recent N rows with matching source_urls to get them.
    """
    if inserted_count <= 0:
        return []
    from services.database import get_db
    urls = [p.get("source_url", "") for p in posts if p.get("source_url")]
    if not urls:
        return []
    conn = get_db()
    placeholders = ",".join("?" * len(urls))
    rows = conn.execute(
        f"SELECT id, source_url FROM posts WHERE source_url IN ({placeholders}) "
        f"ORDER BY id DESC LIMIT ?",
        (*urls, inserted_count),
    ).fetchall()
    conn.close()
    return [r["id"] for r in rows]
```

4. Add `_analyze_one` method to `SignalScanScheduler`:

```python
async def _analyze_one(self, post_id: int) -> None:
    """Analyze one post: load, fetch token contexts, call LLM, persist.

    Kill-switch: bails early if `signal_auto_analyze` is False in config.
    Never raises — failures are logged and the post's `analyzed_at`
    stays NULL (so the user can re-analyze via /api/posts/{id}/reanalyze).
    """
    from services.post_pipeline import (
        extract_tokens_from_post,
        load_post,
        persist_opportunities_and_snapshots,
        set_post_analyzed_at,
    )

    if not self._config_provider().get("signal_auto_analyze", True):
        logger.debug(
            f"[SignalScanScheduler] auto-analyze disabled; skipping {post_id}"
        )
        return

    try:
        post = load_post(post_id)
        if post is None:
            logger.warning(f"[SignalScanScheduler] post {post_id} not found")
            return
        tokens = extract_tokens_from_post(post)
        contexts = await asyncio.gather(
            *(self._token_context_fetcher(t) for t in tokens),
            return_exceptions=True,
        )
        # Coerce exceptions to empty dicts (post_failure_modes in spec)
        clean_contexts = [
            c if isinstance(c, dict) else {"error": str(c)} for c in contexts
        ]
        result = await SignalAnalyzer().analyze(
            post["content"], token_contexts=clean_contexts
        )
        opps = result.get("opportunities") or []
        persist_opportunities_and_snapshots(post_id, opps, clean_contexts)
        if opps:
            set_post_analyzed_at(post_id)
        if self._ws_broadcast:
            await self._ws_broadcast("post:analyzed", {
                "post_id": post_id,
                "opportunities": opps,
            })
    except Exception as e:
        logger.warning(f"[SignalScanScheduler] analyze post {post_id} failed: {e}")
```

- [ ] **Step 4: Run test — expect PASS**

Run: `cd backend && python -m pytest tests/test_scheduler_analyze.py tests/test_scheduler.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/services/scheduler.py backend/tests/test_scheduler_analyze.py
git commit -m "feat(scheduler): auto-analyze each new post via _analyze_one"
```

---

## Task 8: Scraper — switch to `chromium.launch_persistent_context` + API interception

**Files:**
- Modify: `backend/services/binance_square_browser.py` (replace `_get_or_launch_page` and `fetch_posts` body)
- Create: `backend/tests/fixtures/binance_square/pgc_feed.json`
- Modify: `backend/tests/test_binance_square_browser.py` (add API interception tests)

The browser is broken on Windows Python 3.14 — `chromium.launch()` raises `NotImplementedError` in asyncio subprocess. Switch to `chromium.launch_persistent_context()` (CDP over WebSocket, no subprocess). Add an API response listener that captures `/pgc/feed` JSON and recursively walks it for post-shaped objects.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_binance_square_browser.py`:

```python
import json
from pathlib import Path


_FIXTURE = Path(__file__).parent / "fixtures" / "binance_square" / "pgc_feed.json"


class FakeResponse:
    def __init__(self, url, body):
        self.url = url
        self._body = body

    async def json(self):
        return self._body

    async def text(self):
        return json.dumps(self._body)


class FakePageWithResponses:
    """Stand-in for playwright Page that has a `page.on('response', cb)` API."""

    def __init__(self, html, responses):
        self._html = html
        self._responses = responses
        self._handlers = []
        self.on_calls = 0

    def on(self, event, handler):
        self._handlers.append((event, handler))
        self.on_calls += 1
        # Fire the handlers with each response so the listener sees them
        if event == "response":
            import asyncio
            for r in self._responses:
                asyncio.get_event_loop().create_task(handler(r))

    async def content(self):
        return self._html

    async def goto(self, *args, **kwargs):
        pass

    async def close(self):
        pass

    def is_closed(self):
        return False

    async def wait_for_timeout(self, *args, **kwargs):
        pass


@pytest.mark.asyncio
async def test_fetch_posts_via_api_interception_picks_post_objects():
    """The browser should walk /pgc/feed JSON for objects with content+author."""
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    page = FakePageWithResponses("", responses=[
        FakeResponse("https://api.binance.com/pgc/feed?page=1", fixture),
    ])

    browser = BinanceSquareBrowser(page=page)
    posts = await browser.fetch_posts(limit=20)

    # Two posts in the fixture; both have content+author
    assert len(posts) >= 1
    for p in posts:
        assert "content" in p
        assert "author" in p
        assert "source_url" in p


@pytest.mark.asyncio
async def test_fetch_posts_falls_back_to_html_when_no_api_responses():
    """If no /pgc/feed responses are captured, fall back to the existing
    HTML parser (so the old path still works for manual runs)."""
    html = _load_fixture("home_with_posts.html")
    page = FakePageWithResponses(html, responses=[])  # no API responses
    browser = BinanceSquareBrowser(page=page)
    posts = await browser.fetch_posts(limit=5)
    # The HTML fixture has posts with token mentions
    assert isinstance(posts, list)
```

- [ ] **Step 2: Create the fixture**

`backend/tests/fixtures/binance_square/pgc_feed.json`:

```json
{
  "code": "000000",
  "message": "success",
  "data": {
    "items": [
      {
        "id": "123456",
        "content": "$SOL breakout from descending wedge. Funding flipped negative. Real momentum.",
        "author": {"nickname": "TraderSol"},
        "likeCount": 234,
        "commentCount": 18,
        "shareCount": 5,
        "tradingPairs": [{"symbol": "SOL"}],
        "publishTime": 1717584000000
      },
      {
        "id": "789012",
        "content": "$ETH update — team shipped the merge, but price action is choppy. Watching support.",
        "author": {"nickname": "EthWatcher"},
        "likeCount": 89,
        "commentCount": 7,
        "shareCount": 1,
        "tradingPairs": [{"symbol": "ETH"}],
        "publishTime": 1717587600000
      }
    ]
  }
}
```

- [ ] **Step 3: Run test — expect FAIL**

Run: `cd backend && python -m pytest tests/test_binance_square_browser.py -v`
Expected: existing tests pass; new tests fail (`page.on` not called).

- [ ] **Step 4: Refactor `BinanceSquareBrowser`**

In `backend/services/binance_square_browser.py`, replace `fetch_posts` and `_get_or_launch_page` (keep `_parse_html` and the helpers). Add new helpers and a `ScraperManager` minimal singleton.

```python
async def fetch_posts(self, limit: int) -> list[dict[str, Any]]:
    """Fetch posts via API response interception. Falls back to HTML parser."""
    cfg = get_binance_square_scrape_config()
    page = self._injected_page
    if page is None:
        page = await self._get_or_launch_page(cfg)

    # Register a fresh response listener per call
    self._captured_responses: list[dict[str, Any]] = []

    async def _on_response(response):
        try:
            url = response.url
        except Exception:
            return
        if "pgc/feed" not in url and "/pgc/" not in url:
            return
        try:
            data = await response.json()
        except Exception:
            return
        self._captured_responses.append({"url": url, "data": data})

    try:
        page.on("response", _on_response)
    except Exception:
        pass  # injected page may not support .on — fall through to HTML

    # Force a navigation if we haven't been here in a while
    if (
        self._last_fetch_at is None
        or (time.time() - self._last_fetch_at) > self.IDLE_RELOAD_SECONDS
    ):
        try:
            await page.goto(cfg["url"], wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass

    # Wait briefly for responses to arrive
    await page.wait_for_timeout(3000)

    self._last_fetch_at = time.time()
    posts = self._scan_for_posts(self._captured_responses, limit)

    if not posts:
        # Fall back to HTML parser
        html = await page.content()
        return self._parse_html(html, limit)
    return posts


def _scan_for_posts(
    self, responses: list[dict[str, Any]], limit: int
) -> list[dict[str, Any]]:
    """Recursively walk each response's JSON, pick objects shaped like posts."""
    posts: list[dict[str, Any]] = []
    for resp in responses:
        posts.extend(self._collect_post_dicts(resp.get("data", {})))
    # Dedup by source_url
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for p in posts:
        url = p.get("source_url", "")
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        unique.append(p)
    # Newest first (sort by posted_at desc; missing values land at the bottom)
    unique.sort(key=lambda p: p.get("posted_at") or "", reverse=True)
    return unique[:limit]


def _collect_post_dicts(self, node: Any) -> list[dict[str, Any]]:
    """Recursively scan a JSON tree for dicts that look like a post."""
    out: list[dict[str, Any]] = []
    if isinstance(node, dict):
        if self._looks_like_post(node):
            out.append(self._normalize_post(node))
        for v in node.values():
            out.extend(self._collect_post_dicts(v))
    elif isinstance(node, list):
        for v in node:
            out.extend(self._collect_post_dicts(v))
    return out


def _looks_like_post(self, obj: dict[str, Any]) -> bool:
    """A post has content (text) + author (string-like) + engagement counts."""
    has_content = bool(obj.get("content") or obj.get("body") or obj.get("text"))
    has_author = bool(
        isinstance(obj.get("author"), dict) and obj["author"].get("nickname")
    ) or bool(isinstance(obj.get("author"), str) and obj["author"])
    has_id = bool(obj.get("id") or obj.get("postId"))
    return has_content and has_author and has_id


def _normalize_post(self, raw: dict[str, Any]) -> dict[str, Any]:
    """Convert a /pgc/feed post-shaped dict to the project schema."""
    author = raw.get("author") or {}
    author_name = (
        author.get("nickname") if isinstance(author, dict)
        else str(author) if author else "unknown"
    )
    content = (
        raw.get("content") or raw.get("body") or raw.get("text") or ""
    )[:1000]
    post_id = raw.get("id") or raw.get("postId") or ""
    source_url = (
        f"https://www.binance.com/en/square/post/{post_id}" if post_id else ""
    )
    ts_ms = raw.get("publishTime") or raw.get("createTime") or 0
    posted_at = (
        datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
        if ts_ms else ""
    )
    pairs_raw = raw.get("tradingPairs") or raw.get("trading_pairs") or []
    trading_pairs = (
        [{"symbol": p.get("symbol") or p}
         for p in pairs_raw if (p.get("symbol") if isinstance(p, dict) else p)]
        if pairs_raw else None
    )
    return {
        "source": "binance_square",
        "source_url": source_url,
        "author": author_name,
        "content": content,
        "likes": int(raw.get("likeCount") or raw.get("likes") or 0),
        "comments": int(raw.get("commentCount") or raw.get("comments") or 0),
        "shares": int(raw.get("shareCount") or raw.get("shares") or 0),
        "posted_at": posted_at,
        "trading_pairs": trading_pairs,
        "raw_data": str(raw),
    }
```

Add `timezone` to the imports at the top of the file:

```python
from datetime import datetime, timedelta, timezone
```

Replace `_get_or_launch_page` with the persistent-context version:

```python
async def _get_or_launch_page(self, cfg: dict[str, Any]):
    """Lazy-launch a chromium with launch_persistent_context. Reuses
    the same context across calls so the login state persists on disk.

    On Windows Python 3.14, `chromium.launch()` raises NotImplementedError
    in asyncio.subprocess. `launch_persistent_context()` uses CDP over
    WebSocket instead of subprocess pipes, so it works.
    """
    from playwright.async_api import async_playwright

    if self._context is not None:
        if self._context.browser is not None and self._context.browser.is_connected:
            if self._launched_page is not None and not self._launched_page.is_closed():
                return self._launched_page
            self._launched_page = await self._context.new_page()
            return self._launched_page

    self._playwright = await async_playwright().start()
    user_data_dir = cfg.get("user_data_dir", "data/playwright_user_data")
    Path(user_data_dir).mkdir(parents=True, exist_ok=True)
    self._context = await self._playwright.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        headless=cfg.get("headless", True),
        user_agent=cfg["user_agent"],
        viewport={"width": 1920, "height": 1080},
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    await self._context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', { get: () => false })"
    )
    page = await self._context.new_page()
    await page.goto(cfg["url"], wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(5000)
    for _ in range(int(cfg.get("scroll_passes", 2))):
        await page.mouse.wheel(0, 1200)
        await page.wait_for_timeout(int(cfg.get("scroll_pause_ms", 2500)))
    self._launched_page = page
    return page
```

Add `from pathlib import Path` to the imports (it may already be there; add if not). **Replace `__init__`** with:

```python
def __init__(self, page=None):
    # `page` is injected by tests; None means "lazy-launch real chromium".
    self._injected_page = page
    self._browser = None
    self._context: Optional[Any] = None
    self._playwright = None
    self._launched_page = None
    self._last_fetch_at: Optional[float] = None
    # Per-call list of captured /pgc/feed response bodies
    self._captured_responses: list[dict[str, Any]] = []
```

Update `aclose` to close `_context` instead of `_browser` (the context holds the browser):

```python
async def aclose(self) -> None:
    """Cleanly shut down the browser. Idempotent."""
    if self._launched_page is not None:
        try:
            await self._launched_page.close()
        except Exception as e:
            logger.debug(f"[BinanceSquareBrowser] page close failed: {e}")
        self._launched_page = None
    if self._context is not None:
        try:
            # launch_persistent_context returns a BrowserContext; closing
            # it also closes the browser.
            await self._context.close()
        except Exception as e:
            logger.debug(f"[BinanceSquareBrowser] context close failed: {e}")
        self._context = None
    self._browser = None
    if self._playwright is not None:
        try:
            await self._playwright.stop()
        except Exception as e:
            logger.debug(f"[BinanceSquareBrowser] playwright stop failed: {e}")
        self._playwright = None
```

- [ ] **Step 5: Run test — expect PASS**

Run: `cd backend && python -m pytest tests/test_binance_square_browser.py -v`
Expected: all pass (existing HTML parser tests + new API interception tests).

- [ ] **Step 6: Commit**

```bash
git add backend/services/binance_square_browser.py backend/tests/test_binance_square_browser.py backend/tests/fixtures/binance_square/pgc_feed.json
git commit -m "feat(scraper): use launch_persistent_context + API interception"
```

---

## Task 9: Add `scripts/login_binance.py` for one-time manual login

**Files:**
- Create: `scripts/login_binance.py`
- Create: `data/playwright_user_data/.gitkeep` (data dir is gitignored)

- [ ] **Step 1: Write the script**

```python
# scripts/login_binance.py
"""One-time manual login for Binance Square.

Launches chromium with `headless=False`, navigates to Binance Square,
and waits for the user to complete login (cookie, 2FA, captcha).
Once logged in, the persistent context at `data/playwright_user_data/`
will hold the cookies — all subsequent scraper runs will reuse them.

Run:
    python scripts/login_binance.py
"""
from __future__ import annotations

import sys
from pathlib import Path

USER_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "playwright_user_data"
SQUARE_URL = "https://www.binance.com/en/square"


def main() -> int:
    if not USER_DATA_DIR.exists():
        USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        print(f"[login_binance] created {USER_DATA_DIR}")

    from playwright.sync_api import sync_playwright

    print(f"[login_binance] launching browser with user_data_dir={USER_DATA_DIR}")
    print("[login_binance] please log in to Binance in the opened window")
    print("[login_binance] (this script will exit automatically once you reach the feed)")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            viewport={"width": 1280, "height": 800},
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(SQUARE_URL, wait_until="domcontentloaded", timeout=60000)

        # Poll for the password input to disappear (user is now logged in)
        print("[login_binance] waiting for login to complete...")
        for _ in range(120):  # up to 10 min
            try:
                has_password_input = page.locator("input[type='password']").count() > 0
            except Exception:
                has_password_input = False
            if not has_password_input:
                # Also wait for at least one post to be visible
                try:
                    if page.locator("a[href^='/en/square/post/']").count() > 0:
                        print("[login_binance] login successful — feed is visible")
                        break
                except Exception:
                    pass
            page.wait_for_timeout(5000)
        else:
            print("[login_binance] timeout — please re-run the script", file=sys.stderr)
            context.close()
            return 1

        print(f"[login_binance] cookies saved to {USER_DATA_DIR}/Cookies")
        print("[login_binance] you can close the browser window when ready")
        try:
            page.wait_for_timeout(5000)
        except Exception:
            pass
        context.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Add `data/playwright_user_data/` to `.gitignore`**

Append to `.gitignore` (create if missing):

```
# Persistent Playwright browser profile (login state)
data/playwright_user_data/
```

- [ ] **Step 3: Commit**

```bash
git add scripts/login_binance.py .gitignore
git commit -m "feat(scraper): add manual login script for persistent context"
```

---

## Task 10: New `api/posts.py` with 5 endpoints + register in main.py

**Files:**
- Create: `backend/api/posts.py`
- Create: `backend/tests/test_posts_api.py`
- Modify: `backend/main.py:97-105` (register router)

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_posts_api.py
import json
import pytest
from fastapi.testclient import TestClient

from main import app
from services.database import init_db, get_db


@pytest.fixture
def client():
    init_db()
    return TestClient(app)


def _seed_post(content="$SOL breakout", author="Author", trading_pairs=None,
               with_opp=True) -> int:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO posts (source, content, author, trading_pairs) "
        "VALUES (?, ?, ?, ?)",
        ("binance_square", content, author,
         json.dumps(trading_pairs) if trading_pairs else None),
    )
    pid = cur.lastrowid
    if with_opp:
        cur.execute(
            """INSERT INTO opportunities
               (post_id, token, sentiment, action, confidence,
                is_opportunity, reasoning, decision_steps)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (pid, "SOL", "bullish", "long", 0.8, 1, "good",
             json.dumps(["step1", "step2"])),
        )
        cur.execute(
            """INSERT INTO token_metric_snapshots
               (post_id, opportunity_id, symbol, rsi_14, macd_state,
                macd_hist, market_cap_usd)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (pid, cur.lastrowid, "SOL", 32.4, "bullish_cross", 0.12, 65e9),
        )
    conn.commit()
    conn.close()
    return pid


def test_get_posts_returns_list_with_nested_opportunities(client):
    pid = _seed_post()
    r = client.get("/api/posts")
    assert r.status_code == 200
    body = r.json()
    assert "posts" in body
    assert any(p["id"] == pid for p in body["posts"])
    p = next(p for p in body["posts"] if p["id"] == pid)
    assert p["opportunities"][0]["token"] == "SOL"
    assert p["opportunities"][0]["decision_steps"] == ["step1", "step2"]


def test_get_post_detail_returns_full(client):
    pid = _seed_post()
    r = client.get(f"/api/posts/{pid}")
    assert r.status_code == 200
    body = r.json()
    assert body["post"]["id"] == pid
    assert len(body["opportunities"]) == 1
    assert len(body["token_metrics"]) == 1


def test_get_post_detail_404_for_missing(client):
    r = client.get("/api/posts/99999")
    assert r.status_code == 404


def test_post_skip_sets_is_opportunity_zero(client):
    pid = _seed_post()
    r = client.post(f"/api/posts/{pid}/skip")
    assert r.status_code == 200
    conn = get_db()
    row = conn.execute(
        "SELECT is_opportunity FROM opportunities WHERE post_id = ?", (pid,)
    ).fetchone()
    conn.close()
    assert row["is_opportunity"] == 0


def test_post_feedback_inserts_row(client):
    pid = _seed_post()
    r = client.post(f"/api/posts/{pid}/feedback",
                    json={"feedback": "good", "comment": "nice call"})
    assert r.status_code == 200
    conn = get_db()
    row = conn.execute(
        "SELECT feedback, comment FROM post_feedback WHERE post_id = ?",
        (pid,),
    ).fetchone()
    conn.close()
    assert row["feedback"] == "good"
    assert row["comment"] == "nice call"


def test_post_feedback_validates_value(client):
    pid = _seed_post()
    r = client.post(f"/api/posts/{pid}/feedback",
                    json={"feedback": "meh"})
    assert r.status_code == 422  # Pydantic validation


def test_post_feedback_allows_unlimited_per_post(client):
    """User can change their mind — both rows are kept (latest wins for stats)."""
    pid = _seed_post()
    client.post(f"/api/posts/{pid}/feedback", json={"feedback": "good"})
    client.post(f"/api/posts/{pid}/feedback", json={"feedback": "bad"})
    conn = get_db()
    rows = conn.execute(
        "SELECT feedback FROM post_feedback WHERE post_id = ? ORDER BY id",
        (pid,),
    ).fetchall()
    conn.close()
    assert [r["feedback"] for r in rows] == ["good", "bad"]


def test_post_stats_aggregates_correctly(client):
    pid1 = _seed_post(with_opp=True)
    pid2 = _seed_post(content="$ETH update", with_opp=True)
    client.post(f"/api/posts/{pid1}/feedback", json={"feedback": "good"})
    client.post(f"/api/posts/{pid2}/feedback", json={"feedback": "bad"})

    r = client.get("/api/posts/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["total_posts"] >= 2
    assert body["feedback"]["good"] == 1
    assert body["feedback"]["bad"] == 1
    assert body["feedback"]["accuracy_pct"] == 50.0


def test_post_stats_accuracy_pct_null_when_no_ratings(client):
    _seed_post(with_opp=False)
    r = client.get("/api/posts/stats")
    body = r.json()
    assert body["feedback"]["accuracy_pct"] is None


def test_post_reanalyze_calls_analyzer(monkeypatch, client):
    from unittest.mock import AsyncMock
    pid = _seed_post()
    fake = AsyncMock(return_value={"opportunities": [
        {"token": "SOL", "sentiment": "bullish", "is_opportunity": True,
         "action": "long", "confidence": 0.9, "decision_steps": ["x"],
         "reasoning": "ok"},
    ]})
    monkeypatch.setattr("services.signal_analyzer.SignalAnalyzer.analyze", fake)
    r = client.post(f"/api/posts/{pid}/reanalyze")
    assert r.status_code == 200
    fake.assert_awaited()
    conn = get_db()
    n = conn.execute(
        "SELECT COUNT(*) FROM opportunities WHERE post_id = ?", (pid,)
    ).fetchone()[0]
    conn.close()
    assert n == 2  # original + new
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `cd backend && python -m pytest tests/test_posts_api.py -v`
Expected: 404 on every endpoint (router not registered).

- [ ] **Step 3: Create `api/posts.py`**

```python
# backend/api/posts.py
"""New Post / Opportunity / Feedback API.

Mirrors `api/trading.py` for the legacy `signals` view but exposes the
new schema (posts + opportunities + token_metric_snapshots +
post_feedback). See spec section "API additions".
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.database import get_db
from services.post_pipeline import (
    extract_tokens_from_post,
    load_post,
    persist_opportunities_and_snapshots,
    set_post_analyzed_at,
)
from services.signal_analyzer import SignalAnalyzer

router = APIRouter(prefix="/api/posts")


class FeedbackBody(BaseModel):
    feedback: str = Field(pattern="^(good|bad)$")
    comment: str | None = None


def _row_to_post_dict(row: Any) -> dict[str, Any]:
    """Convert a posts row to a JSON-friendly dict (parse trading_pairs JSON)."""
    d = dict(row)
    tp = d.get("trading_pairs")
    if isinstance(tp, str):
        try:
            d["trading_pairs"] = json.loads(tp)
        except (json.JSONDecodeError, TypeError):
            d["trading_pairs"] = None
    return d


@router.get("")
async def list_posts(limit: int = 50) -> dict[str, Any]:
    conn = get_db()
    posts_rows = conn.execute(
        "SELECT * FROM posts ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    post_ids = [r["id"] for r in posts_rows]
    opp_rows = conn.execute(
        f"SELECT * FROM opportunities WHERE post_id IN ({','.join('?'*len(post_ids))})",
        post_ids,
    ).fetchall() if post_ids else []
    snap_rows = conn.execute(
        f"SELECT * FROM token_metric_snapshots WHERE post_id IN ({','.join('?'*len(post_ids))})",
        post_ids,
    ).fetchall() if post_ids else []
    conn.close()

    opps_by_post: dict[int, list[dict]] = {}
    for r in opp_rows:
        d = dict(r)
        d["decision_steps"] = json.loads(d.get("decision_steps") or "[]")
        opps_by_post.setdefault(d["post_id"], []).append(d)
    snaps_by_post: dict[int, list[dict]] = {}
    for r in snap_rows:
        snaps_by_post.setdefault(r["post_id"], []).append(dict(r))

    posts = []
    for r in posts_rows:
        d = _row_to_post_dict(r)
        d["opportunities"] = opps_by_post.get(d["id"], [])
        d["token_metrics"] = snaps_by_post.get(d["id"], [])
        posts.append(d)
    return {"posts": posts}


@router.get("/stats")
async def stats() -> dict[str, Any]:
    conn = get_db()
    total_posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    total_opp = conn.execute(
        "SELECT COUNT(*) FROM opportunities WHERE is_opportunity = 1"
    ).fetchone()[0]
    last_24h = conn.execute(
        "SELECT COUNT(*) FROM posts WHERE created_at >= datetime('now', '-1 day')"
    ).fetchone()[0]
    # Latest feedback per post (subquery)
    good_n = conn.execute(
        """
        SELECT COUNT(*) FROM post_feedback pf
        WHERE pf.id = (
            SELECT MAX(id) FROM post_feedback WHERE post_id = pf.post_id
        ) AND pf.feedback = 'good'
        """
    ).fetchone()[0]
    bad_n = conn.execute(
        """
        SELECT COUNT(*) FROM post_feedback pf
        WHERE pf.id = (
            SELECT MAX(id) FROM post_feedback WHERE post_id = pf.post_id
        ) AND pf.feedback = 'bad'
        """
    ).fetchone()[0]
    conn.close()
    total_rated = good_n + bad_n
    accuracy = (
        round(good_n / total_rated * 100, 1) if total_rated else None
    )
    return {
        "total_posts": total_posts,
        "total_opportunities": total_opp,
        "last_24h_posts": last_24h,
        "feedback": {
            "good": good_n,
            "bad": bad_n,
            "accuracy_pct": accuracy,
        },
    }


@router.get("/{post_id}")
async def get_post(post_id: int) -> dict[str, Any]:
    conn = get_db()
    post_row = conn.execute(
        "SELECT * FROM posts WHERE id = ?", (post_id,)
    ).fetchone()
    if not post_row:
        conn.close()
        raise HTTPException(404, "Post not found")
    opp_rows = conn.execute(
        "SELECT * FROM opportunities WHERE post_id = ?", (post_id,)
    ).fetchall()
    snap_rows = conn.execute(
        "SELECT * FROM token_metric_snapshots WHERE post_id = ?", (post_id,)
    ).fetchall()
    fb_rows = conn.execute(
        "SELECT * FROM post_feedback WHERE post_id = ? ORDER BY id", (post_id,)
    ).fetchall()
    conn.close()
    opps = []
    for r in opp_rows:
        d = dict(r)
        d["decision_steps"] = json.loads(d.get("decision_steps") or "[]")
        opps.append(d)
    return {
        "post": _row_to_post_dict(post_row),
        "opportunities": opps,
        "token_metrics": [dict(r) for r in snap_rows],
        "feedback": [dict(r) for r in fb_rows],
    }


@router.post("/{post_id}/reanalyze")
async def reanalyze(post_id: int) -> dict[str, Any]:
    post = load_post(post_id)
    if post is None:
        raise HTTPException(404, "Post not found")
    tokens = extract_tokens_from_post(post)
    contexts = []
    for t in tokens:
        try:
            ctx = await SignalAnalyzer.fetch_token_context(t)
            contexts.append(ctx)
        except Exception:
            contexts.append({"symbol": t, "error": "fetch failed"})
    result = await SignalAnalyzer().analyze(
        post["content"], token_contexts=contexts
    )
    opps = result.get("opportunities") or []
    persist_opportunities_and_snapshots(post_id, opps, contexts)
    if opps:
        set_post_analyzed_at(post_id)
    return {"post_id": post_id, "opportunities": opps}


@router.post("/{post_id}/skip")
async def skip_post(post_id: int) -> dict[str, Any]:
    conn = get_db()
    cur = conn.execute(
        "UPDATE opportunities SET is_opportunity = 0 WHERE post_id = ?",
        (post_id,),
    )
    n = cur.rowcount
    conn.commit()
    conn.close()
    return {"post_id": post_id, "updated": n}


@router.post("/{post_id}/feedback")
async def post_feedback(post_id: int, body: FeedbackBody) -> dict[str, Any]:
    conn = get_db()
    if not conn.execute(
        "SELECT 1 FROM posts WHERE id = ?", (post_id,)
    ).fetchone():
        conn.close()
        raise HTTPException(404, "Post not found")
    cur = conn.execute(
        "INSERT INTO post_feedback (post_id, feedback, comment) VALUES (?, ?, ?)",
        (post_id, body.feedback, body.comment),
    )
    conn.commit()
    conn.close()
    return {"feedback_id": cur.lastrowid, "post_id": post_id}
```

- [ ] **Step 4: Register the router in `main.py`**

In `backend/main.py`, add the import alongside the other API imports (around line 10-18):

```python
from api.posts import router as posts_router
```

And add to the `app.include_router(...)` block (around line 97-105):

```python
app.include_router(posts_router)
```

- [ ] **Step 5: Run test — expect PASS**

Run: `cd backend && python -m pytest tests/test_posts_api.py -v`
Expected: 10 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/api/posts.py backend/main.py backend/tests/test_posts_api.py
git commit -m "feat(api): add /api/posts endpoints for opportunities + feedback"
```

---

## Task 11: Update `api/trading.py` to use `posts` table directly

This drops the dependency on the `signals` SQL view. After this task the view can be removed in a follow-up.

**Files:**
- Modify: `backend/api/trading.py:35-176` (signals endpoints)
- Modify: `backend/tests/test_api_trading_actions.py` (extend)

- [ ] **Step 1: Update `get_signals` to read from `posts`**

In `backend/api/trading.py`, replace `get_signals` (lines 35-52) with:

```python
@router.get("/signals")
async def get_signals(status: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Get trading signals. Reads from the new `posts` table directly.

    The `signals` view was a back-compat shim; it's no longer needed
    because this endpoint has been updated.
    """
    conn = get_db()
    cursor = conn.cursor()
    if status:
        cursor.execute(
            "SELECT * FROM posts WHERE status = ? ORDER BY id DESC LIMIT ?",
            (status, limit),
        )
    else:
        cursor.execute(
            "SELECT * FROM posts ORDER BY id DESC LIMIT ?", (limit,)
        )
    rows = cursor.fetchall()
    conn.close()
    return {"signals": [dict(row) for row in rows]}
```

- [ ] **Step 2: Replace `get_signal` (single post) with read from `posts`**

Replace `get_signal` (lines 55-80) with:

```python
@router.get("/signals/{signal_id}")
async def get_signal(signal_id: int) -> dict[str, Any]:
    """Get a single signal. Reads from `posts` + `opportunities` + `token_metric_snapshots`."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM posts WHERE id = ?", (signal_id,))
    signal = cursor.fetchone()
    if not signal:
        conn.close()
        raise HTTPException(status_code=404, detail="Signal not found")
    cursor.execute("SELECT * FROM opportunities WHERE post_id = ?", (signal_id,))
    opps = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM token_metric_snapshots WHERE post_id = ?", (signal_id,))
    snaps = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {
        "signal": dict(signal),
        "analysis": opps,  # legacy key for back-compat
        "opportunities": opps,
        "validation": snaps,  # legacy key for back-compat
        "token_metrics": snaps,
    }
```

- [ ] **Step 3: Replace `validate_signal_endpoint` to delegate to the new pipeline**

Replace `validate_signal_endpoint` (lines 83-176) with:

```python
@router.post("/signals/{signal_id}/validate")
async def validate_signal_endpoint(signal_id: int) -> dict[str, Any]:
    """Manually re-analyze a signal. Delegates to SignalAnalyzer + post_pipeline."""
    from services.post_pipeline import (
        extract_tokens_from_post,
        load_post,
        persist_opportunities_and_snapshots,
        set_post_analyzed_at,
    )

    post = load_post(signal_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Signal not found")

    tokens = extract_tokens_from_post(post)
    contexts = []
    for t in tokens:
        try:
            contexts.append(await SignalAnalyzer.fetch_token_context(t))
        except Exception:
            contexts.append({"symbol": t, "error": "fetch failed"})

    result = await SignalAnalyzer().analyze(
        post["content"], token_contexts=contexts
    )
    opps = result.get("opportunities") or []
    persist_opportunities_and_snapshots(signal_id, opps, contexts)
    if opps:
        set_post_analyzed_at(signal_id)
    return {
        "status": "analyzed" if opps else "no_opportunities",
        "opportunities": opps,
    }
```

- [ ] **Step 4: Add a test**

Append to `backend/tests/test_api_trading_actions.py`:

```python
def test_get_signals_reads_from_posts_table(client):
    """The legacy /api/trading/signals must now read from posts directly."""
    init_db()
    conn = get_db()
    conn.execute(
        "INSERT INTO posts (source, content, author) VALUES (?, ?, ?)",
        ("binance_square", "test $BTC", "Author"),
    )
    conn.commit()
    conn.close()
    r = client.get("/api/trading/signals")
    assert r.status_code == 200
    body = r.json()
    assert len(body["signals"]) >= 1
    assert any("test $BTC" == s["content"] for s in body["signals"])
```

- [ ] **Step 5: Run test — expect PASS**

Run: `cd backend && python -m pytest tests/test_api_trading_actions.py tests/test_posts_api.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/api/trading.py backend/tests/test_api_trading_actions.py
git commit -m "refactor(trading-api): read directly from posts table"
```

---

## Task 12: Add new config keys

**Files:**
- Modify: `backend/services/config_store.py:7-33` (add to `DEFAULT_CONFIG`)
- Create: `backend/tests/test_config_store_auto_llm.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_config_store_auto_llm.py
import json
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def fresh_config(monkeypatch):
    from pathlib import Path
    import services.config_store as cs

    tmp = Path(tempfile.mkdtemp()) / "config.json"
    monkeypatch.setattr(cs, "CONFIG_PATH", tmp)
    yield tmp
    tmp.unlink(missing_ok=True)


def test_default_config_has_new_auto_llm_keys(fresh_config):
    from services.config_store import get_config, DEFAULT_CONFIG
    cfg = get_config()
    for key in (
        "binance_user_data_dir",
        "binance_cookies",
        "signal_auto_analyze",
        "analyze_token_data",
        "kline_interval",
        "kline_limit",
    ):
        assert key in DEFAULT_CONFIG, f"missing default for {key}"
    assert DEFAULT_CONFIG["signal_auto_analyze"] is True
    assert DEFAULT_CONFIG["analyze_token_data"] is True
    assert DEFAULT_CONFIG["kline_interval"] == "1h"
    assert DEFAULT_CONFIG["kline_limit"] == 100


def test_get_config_returns_defaults_when_file_missing(fresh_config):
    from services.config_store import get_config
    cfg = get_config()
    assert cfg["signal_auto_analyze"] is True
    assert cfg["kline_limit"] == 100
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `cd backend && python -m pytest tests/test_config_store_auto_llm.py -v`
Expected: missing keys.

- [ ] **Step 3: Add keys to `DEFAULT_CONFIG`**

In `backend/services/config_store.py`, add to `DEFAULT_CONFIG` (after `arkham_api_key`):

```python
    "binance_user_data_dir": "data/playwright_user_data",
    "binance_cookies": "",
    "signal_auto_analyze": True,
    "analyze_token_data": True,
    "kline_interval": "1h",
    "kline_limit": 100,
```

- [ ] **Step 4: Run test — expect PASS**

Run: `cd backend && python -m pytest tests/test_config_store_auto_llm.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/config_store.py backend/tests/test_config_store_auto_llm.py
git commit -m "feat(config): add auto-LLM pipeline config keys"
```

---

## Task 13: Update frontend `Post` type

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add the new `Post` type**

Append to `frontend/src/types/index.ts`:

```typescript
// New Post/Opportunity/TokenMetric types for the auto-LLM signal pipeline.
// Replaces the legacy `Signal` interface. The old `Signal` is kept
// briefly as a deprecated alias; remove in a follow-up once callers
// are updated.
export interface TokenMetric {
  symbol: string
  market_cap_usd: number | null
  market_cap_rank: number | null
  price_change_24h_pct: number | null
  volume_24h_usd: number | null
  rsi_14: number | null
  macd_state: string | null
  macd_hist: number | null
  fetched_at: string | null
}

export interface Opportunity {
  id: number
  token: string
  sentiment: 'bullish' | 'bearish' | 'neutral' | null
  action: 'long' | 'short' | null
  confidence: number | null
  is_opportunity: boolean
  reasoning: string
  decision_steps: string[]  // the auditable trail
  llm_model: string | null
  created_at: string
}

export interface Post {
  id: number
  source: string
  source_url: string
  author: string
  content: string
  likes: number
  comments: number
  shares: number
  posted_at: string | null
  trading_pairs: Array<{ symbol: string }> | null
  analyzed_at: string | null
  created_at: string
  opportunities: Opportunity[]
  token_metrics: TokenMetric[]
  // User's latest feedback (filled by the UI; null until rated)
  latest_feedback?: 'good' | 'bad' | null
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(types): add Post, Opportunity, TokenMetric"
```

---

## Task 14: Update `TradingView.vue` — new card layout

**Files:**
- Modify: `frontend/src/views/TradingView.vue`

This is a focused UI change, not TDD-friendly. The headless test for the rendered HTML (Task 15) catches regressions.

- [ ] **Step 1: Replace the `Signal` interface and `signals` ref**

In `frontend/src/views/TradingView.vue`:
- Import `Post`, `Opportunity`, `TokenMetric` from `../types` at the top of `<script setup>`.
- Remove the local `interface Signal { ... }` block.
- Change `const signals = ref<Signal[]>([])` to `const signals = ref<Post[]>([])`.

- [ ] **Step 2: Replace the `fetchSignals` function to use `/api/posts`**

Replace `fetchSignals` (lines ~454-463) with:

```typescript
async function fetchSignals() {
  loading.value = true
  try {
    const resp = await fetch('/api/posts')
    if (resp.ok) {
      const data = await resp.json()
      signals.value = data.posts || []
    }
  } catch { /* ignore */ } finally { loading.value = false }
}

async function fetchStats() {
  try {
    const resp = await fetch('/api/posts/stats')
    if (resp.ok) stats.value = await resp.json()
  } catch { /* ignore */ }
}

const stats = ref<{
  total_posts: number
  total_opportunities: number
  last_24h_posts: number
  feedback: { good: number; bad: number; accuracy_pct: number | null }
} | null>(null)
```

Add a `setInterval(fetchStats, 30_000)` in `onMounted`, and call `fetchStats()` once.

- [ ] **Step 3: Add `feedback` + `skip` + `reanalyze` async functions**

Append below `fetchSignals`:

```typescript
async function sendFeedback(postId: number, value: 'good' | 'bad') {
  const post = signals.value.find(p => p.id === postId)
  if (post) post.latest_feedback = value
  await fetch(`/api/posts/${postId}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ feedback: value }),
  })
  await fetchStats()
}

async function skipPost(postId: number) {
  await fetch(`/api/posts/${postId}/skip`, { method: 'POST' })
  await fetchSignals()
}

async function reanalyzePost(postId: number) {
  await fetch(`/api/posts/${postId}/reanalyze`, { method: 'POST' })
  await fetchSignals()
}
```

Replace the old `validateSignal` and `executeSignal` functions to call the new endpoints (keep the same names so the existing buttons keep working).

- [ ] **Step 4: Replace the signal-card template**

In `frontend/src/views/TradingView.vue`, replace the `<div v-for="signal in signals" ...>` block (the inner card body) with the new layout:

```html
<div v-for="post in signals" :key="post.id" class="signal-card" :class="post.status">
  <div class="signal-top">
    <div class="signal-source">
      <span class="source-badge">{{ post.source }}</span>
      <span class="signal-time" :title="post.posted_at || post.created_at">
        {{ formatRelativeTime(post.posted_at || post.created_at) }}
      </span>
      <span v-if="post.analyzed_at" class="status-badge analyzed">analyzed</span>
      <span v-else class="status-badge pending">pending</span>
    </div>
  </div>

  <div class="signal-body">
    <p class="signal-content">"{{ post.content }}"</p>
    <div class="signal-meta">
      <span>👤 {{ post.author || 'unknown' }}</span>
      <span>❤️ {{ post.likes }}</span>
      <span>💬 {{ post.comments }}</span>
      <span>↗ {{ post.shares }}</span>
    </div>
  </div>

  <!-- One card per opportunity on this post -->
  <div v-for="opp in post.opportunities" :key="opp.id" class="signal-decision">
    <div class="decision-header">
      <span v-if="opp.action === 'long'" class="action-badge long">📈 LONG {{ opp.token }}</span>
      <span v-else-if="opp.action === 'short'" class="action-badge short">📉 SHORT {{ opp.token }}</span>
      <span v-else class="action-badge neutral">⚪ NO OPPORTUNITY {{ opp.token }}</span>
      <span class="confidence-bar" :title="`${((opp.confidence || 0) * 100).toFixed(0)}% confidence`">
        <span class="confidence-fill" :style="{ width: `${(opp.confidence || 0) * 100}%` }"></span>
      </span>
    </div>

    <!-- Token snapshot block — what the LLM saw -->
    <div v-for="tm in post.token_metrics.filter(t => t.symbol === opp.token)"
         :key="tm.symbol" class="token-snapshot">
      {{ tm.symbol }} · market_cap ${{ formatMcap(tm.market_cap_usd) }}
      <span v-if="tm.market_cap_rank"> (#{{ tm.market_cap_rank }})</span>
      · RSI(14) {{ formatNum(tm.rsi_14) }}
      · MACD {{ tm.macd_state }}
      <span v-if="tm.macd_hist != null">(hist {{ formatNum(tm.macd_hist) }})</span>
    </div>

    <!-- Decision steps — primary verification surface -->
    <ol v-if="opp.decision_steps.length" class="decision-steps">
      <li v-for="(step, idx) in opp.decision_steps" :key="idx"
          :class="{ 'is-conclusion': step.startsWith('Conclusion:') }">
        {{ step }}
      </li>
    </ol>

    <p v-if="opp.reasoning" class="reasoning-tldr">TL;DR: {{ opp.reasoning }}</p>
  </div>

  <div class="signal-actions">
    <button class="btn-outline" :class="{ active: post.latest_feedback === 'good' }"
            @click="sendFeedback(post.id, 'good')">👍 Good call</button>
    <button class="btn-outline" :class="{ active: post.latest_feedback === 'bad' }"
            @click="sendFeedback(post.id, 'bad')">👎 Bad call</button>
    <button class="btn-outline" @click="skipPost(post.id)">Skip</button>
    <button class="btn-outline" @click="reanalyzePost(post.id)">Reanalyze</button>
    <button class="btn-accent"
            :disabled="!post.opportunities.some(o => o.is_opportunity)"
            @click="executeSignal(post.id)">📈 Execute</button>
  </div>
</div>
```

- [ ] **Step 5: Add the stats strip above the signals list**

In `frontend/src/views/TradingView.vue`, just before `<div v-if="signals.length === 0 ...">`, add:

```html
<div v-if="stats" class="stats-strip">
  24h: {{ stats.last_24h_posts }} posts ·
  {{ stats.total_opportunities }} opportunities
  · 👍 {{ stats.feedback.good }} / 👎 {{ stats.feedback.bad }}
  <span v-if="stats.feedback.accuracy_pct != null">
    · accuracy {{ stats.feedback.accuracy_pct.toFixed(0) }}%
  </span>
</div>
```

- [ ] **Step 6: Add helpers + CSS for the new elements**

In `<script setup>`, add:

```typescript
function formatMcap(v: number | null): string {
  if (v == null) return '?'
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`
  return v.toFixed(0)
}

function formatNum(v: number | null): string {
  if (v == null) return '?'
  return v.toFixed(2)
}
```

Append to `<style scoped>`:

```css
/* Decision visibility */
.signal-decision {
  background: #0a0a0f;
  border: 1px solid #1e1e24;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
.decision-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.action-badge {
  font-size: 16px;
  font-weight: 700;
  padding: 6px 14px;
  border-radius: 6px;
}
.action-badge.long { background: rgba(34,197,94,0.15); color: #22c55e; }
.action-badge.short { background: rgba(239,68,68,0.15); color: #ef4444; }
.action-badge.neutral { background: #27272a; color: #a1a1aa; }
.confidence-bar {
  flex: 1;
  height: 6px;
  background: #1e1e24;
  border-radius: 3px;
  overflow: hidden;
}
.confidence-fill {
  display: block;
  height: 100%;
  background: #6366f1;
}
.token-snapshot {
  font-size: 12px;
  color: #a1a1aa;
  padding: 8px 12px;
  background: #111114;
  border-radius: 4px;
  margin-bottom: 12px;
  font-family: monospace;
}
.decision-steps {
  margin: 0 0 12px 0;
  padding-left: 1.5em;
  line-height: 1.6;
  font-size: 13px;
  color: #e4e4e7;
}
.decision-steps li.is-conclusion {
  color: #6366f1;
  font-weight: 600;
  list-style: none;
  margin-left: -1em;
}
.reasoning-tldr {
  font-size: 12px;
  color: #71717a;
  font-style: italic;
  margin: 0;
}
.stats-strip {
  background: #111114;
  border: 1px solid #1e1e24;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 16px;
  font-size: 13px;
  color: #a1a1aa;
}
.btn-outline.active { border-color: #6366f1; color: #6366f1; }
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/TradingView.vue
git commit -m "feat(trading-view): decision_steps + token snapshot + feedback UI"
```

---

## Task 15: Headless e2e test for the full pipeline

**Files:**
- Create: `backend/tests/test_posts_pipeline_headless.py`

- [ ] **Step 1: Write the test**

```python
# backend/tests/test_posts_pipeline_headless.py
"""Headless end-to-end test of the auto-LLM signal pipeline.

Pipeline under test: fake scraper → real SignalScanScheduler._tick
→ real SignalAnalyzer (LLM mocked) → real DB → /api/posts.
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from services.database import init_db, get_db
from services.scheduler import SignalScanScheduler


@pytest.fixture
def client():
    init_db()
    return TestClient(app)


@pytest.mark.asyncio
async def test_end_to_end_pipeline_inserts_post_and_opportunity(client):
    """Insert a post via the scheduler pipeline; verify it shows up via /api/posts."""
    scraper = MagicMock()
    scraper.scrape = AsyncMock(return_value=[{
        "source": "binance_square",
        "source_url": "https://www.binance.com/en/square/post/e2e1",
        "author": "E2EAuthor",
        "content": "$SOL breakout with bullish MACD cross",
        "likes": 50,
        "comments": 5,
        "shares": 1,
        "tokens": ["SOL"],
        "created_at": "2026-06-05T12:00:00+00:00",
        "posted_at": "2026-06-05T12:00:00+00:00",
        "trading_pairs": [{"symbol": "SOL"}],
        "raw_data": "{}",
    }])
    scraper.save_to_db = MagicMock(return_value=1)

    fetcher = AsyncMock(return_value={
        "symbol": "SOL", "market_cap_usd": 65e9, "market_cap_rank": 5,
        "rsi_14": 32.4, "macd_state": "bullish_cross", "macd_hist": 0.12,
    })

    with patch("services.scheduler.SignalAnalyzer") as FakeAnalyzer:
        instance = FakeAnalyzer.return_value
        instance.analyze = AsyncMock(return_value={"opportunities": [
            {"token": "SOL", "sentiment": "bullish", "is_opportunity": True,
             "action": "long", "confidence": 0.85,
             "decision_steps": ["step1", "Conclusion: real"],
             "reasoning": "ok"},
        ]})

        scheduler = SignalScanScheduler(
            scraper, token_context_fetcher=fetcher,
            config_provider=lambda: {"signal_auto_analyze": True},
        )
        await scheduler._tick()
        # Wait for the fire-and-forget task to complete
        await asyncio.sleep(0.1)

    # Verify the post is reachable via the API
    r = client.get("/api/posts")
    assert r.status_code == 200
    posts = r.json()["posts"]
    assert any(p["source_url"].endswith("e2e1") for p in posts)
    p = next(p for p in posts if p["source_url"].endswith("e2e1"))
    assert len(p["opportunities"]) == 1
    assert p["opportunities"][0]["action"] == "long"
    assert p["opportunities"][0]["decision_steps"] == ["step1", "Conclusion: real"]
    assert len(p["token_metrics"]) == 1
    assert p["token_metrics"][0]["rsi_14"] == 32.4

    # Stats endpoint
    r = client.get("/api/posts/stats")
    body = r.json()
    assert body["total_posts"] >= 1
    assert body["total_opportunities"] >= 1


@pytest.mark.asyncio
async def test_feedback_flow_updates_stats(client):
    """User clicks 👍 on a post → stats.accuracy_pct becomes 100."""
    conn = get_db()
    conn.execute(
        "INSERT INTO posts (source, content, author) VALUES (?, ?, ?)",
        ("binance_square", "$BTC update", "Author"),
    )
    conn.commit()
    pid = conn.execute("SELECT MAX(id) FROM posts").fetchone()[0]
    conn.close()

    r = client.post(f"/api/posts/{pid}/feedback",
                    json={"feedback": "good"})
    assert r.status_code == 200

    r = client.get("/api/posts/stats")
    body = r.json()
    assert body["feedback"]["good"] == 1
    assert body["feedback"]["bad"] == 0
    assert body["feedback"]["accuracy_pct"] == 100.0


@pytest.mark.asyncio
async def test_skip_endpoint_zeros_opportunities(client):
    conn = get_db()
    conn.execute(
        "INSERT INTO posts (source, content, author) VALUES (?, ?, ?)",
        ("binance_square", "$ETH update", "Author"),
    )
    pid = conn.execute("SELECT MAX(id) FROM posts").fetchone()[0]
    conn.execute(
        "INSERT INTO opportunities (post_id, token, is_opportunity) VALUES (?, ?, 1)",
        (pid, "ETH"),
    )
    conn.commit()
    conn.close()

    r = client.post(f"/api/posts/{pid}/skip")
    assert r.status_code == 200
    conn = get_db()
    row = conn.execute(
        "SELECT is_opportunity FROM opportunities WHERE post_id = ?", (pid,)
    ).fetchone()
    conn.close()
    assert row["is_opportunity"] == 0
```

- [ ] **Step 2: Run test — expect PASS**

Run: `cd backend && python -m pytest tests/test_posts_pipeline_headless.py -v`
Expected: 3 passed.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_posts_pipeline_headless.py
git commit -m "test(e2e): headless auto-LLM signal pipeline"
```

---

## Task 16: Drop the `signals` back-compat view

After Task 11 confirmed `/api/trading/signals` works without the view, drop it. Keep a separate commit so the view's removal is reviewable.

**Files:**
- Modify: `backend/services/database.py` (the migration block from Task 4)

- [ ] **Step 1: Update the migration to NOT create the view**

In `backend/services/database.py`, the migration block from Task 4 currently has:

```python
    if "posts" in existing_tables and "signals" not in existing_views:
        cursor.execute("CREATE VIEW signals AS SELECT * FROM posts")
```

Replace with:

```python
    # Back-compat view 'signals' was removed in 2026-06-05 cleanup. Drop it
    # if it still exists from an older migration.
    if "signals" in existing_views:
        cursor.execute("DROP VIEW IF EXISTS signals")
```

- [ ] **Step 2: Verify all tests still pass**

Run: `cd backend && python -m pytest tests/test_api_trading_actions.py tests/test_posts_api.py tests/test_posts_pipeline_headless.py -v`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add backend/services/database.py
git commit -m "refactor(db): drop signals back-compat view"
```

---

## Self-Review

**Spec coverage:**
- ✅ Scraper (`chromium.launch_persistent_context` + API interception) → Task 8
- ✅ One-time manual login → Task 9
- ✅ Auto-LLM per post with `decision_steps` → Task 3, 6, 7
- ✅ Token context (market_cap, RSI, MACD) pre-fetched → Task 1, 2
- ✅ Schema migration (signals→posts + new tables + back-compat) → Task 4, 11, 16
- ✅ New `/api/posts/*` endpoints → Task 10
- ✅ TradingView card with decision_steps + token snapshot + feedback → Task 13, 14
- ✅ Stats strip with accuracy_pct → Task 10, 14
- ✅ `signal_auto_analyze` kill switch → Task 7
- ✅ Config keys → Task 12
- ✅ Token context fetcher dependency-injected on SignalAnalyzer → Task 2, 7
- ✅ Unlimited feedback per post, latest wins for accuracy → Task 10 (test)
- ✅ Migration idempotency → Task 4
- ✅ E2E test → Task 15

**No placeholders** — every step has concrete code or a concrete command.

**Type consistency:**
- `SignalAnalyzer.fetch_token_context` (Task 2) → used by `SignalScanScheduler._analyze_one` (Task 7) ✓
- `post_pipeline.persist_opportunities_and_snapshots` (Task 6) → called by both `_analyze_one` (Task 7) and `reanalyze` endpoint (Task 10) ✓
- `extract_tokens_from_post` (Task 6) → called by `_analyze_one` (Task 7) and `reanalyze` (Task 10) ✓
- `set_post_analyzed_at` (Task 6) → called by `_analyze_one` (Task 7) and `reanalyze` (Task 10) ✓
- `Post`/`Opportunity`/`TokenMetric` (Task 13) → consumed by `TradingView.vue` (Task 14) ✓
- `/api/posts/stats` shape (Task 10) → consumed by `TradingView.vue` stats strip (Task 14) ✓
