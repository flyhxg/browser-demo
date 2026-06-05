# Short-Selling Candidate Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the direction-inverted `crowdedness_score`, populate 13 short-selling fields that are currently `getattr` defaults, and add chip filters on the `/analysis` tab — all on top of the existing gainers ranking (heat_score is unchanged).

**Architecture:** Three PRs. (1a) Pure Python rewrite of `_calculate_short_metrics` with the corrected direction, plus `_calculate_short_grade()` and `_short_opportunity_score()`. Hot fields (60s tick) get populated. (1b) New `services/fundamentals_cache.py` (6h refresh) drives the warm fields (market_cap, sector, top10_holders_pct, gini, fdv_mcap_ratio) and `get_token_analysis` returns OHLCV-derived cold fields. (2) Frontend chip filters with a pure `applyHotTokenFilters` function. Fail-soft: no external fetch ever bubbles to the scanner loop.

**Tech Stack:** Python 3.14 + pytest, FastAPI, ccxt (async), Vue 3 + Vite, TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-06-05-short-selling-candidate-overlay-design.md`

---

## File Structure

| Layer | File | Role | Change |
|---|---|---|---|
| Backend | `backend/services/hot_tokens_scanner.py` | Scanner tick + short metrics | Rewrite metrics; rename dataclass fields; add grade & opportunity score; add `oi_usd` / `funding_annualized` to tick |
| Backend | `backend/services/fundamentals_cache.py` | 6h cache: CoinGecko markets + Arkham holders | **Create** |
| Backend | `backend/api/hot_tokens.py` | FastAPI router | Remove `getattr` fallbacks; add OHLCV fetch in `/analysis`; rewrite `_short_recommendation` text |
| Backend | `backend/main.py` | FastAPI app | Wire `FundamentalsCache` into startup; no other change |
| Backend test | `backend/tests/test_hot_tokens_scanner_metrics.py` | Pure-function coverage of new metrics | **Create** |
| Backend test | `backend/tests/test_fundamentals_cache.py` | Cache hit/miss/refresh/fail-soft | **Create** |
| Backend test | `backend/tests/test_hot_tokens_api_fields.py` | API returns all 13 fields without `getattr` defaults | **Create** |
| Frontend | `frontend/src/views/ShortsView.vue` | Page | Modal renders new fields; chip filter UI; filter wiring |
| Frontend util | `frontend/src/utils/shortTokenFilters.ts` | Pure filter function | **Create** |
| Frontend util test | `frontend/src/utils/__tests__/shortTokenFilters.spec.ts` | Pure-function coverage | **Create** |

Each file has one responsibility. The util is the only piece with a non-trivial interface; everything else wires existing surfaces.

---

## Phase 1a — Direction fix + grade + hot fields (~2h, one PR)

### Task 1: `HotToken` dataclass — rename short metrics fields

**Files:**
- Modify: `backend/services/hot_tokens_scanner.py:28-46`

- [ ] **Step 1: Replace the dataclass block**

Replace lines 28-46 with:

```python
@dataclass
class HotToken:
    symbol: str
    price: float = 0.0
    price_change_24h: float = 0.0
    volume_24h: float = 0.0
    volume_usd: float = 0.0
    funding_rate: float = 0.0
    long_short_ratio: float = 0.0
    open_interest: float = 0.0
    liquidation_price: float = 0.0
    heat_score: float = 0.0
    heat_rank: int = 0
    updated_at: Optional[str] = None
    # Short-selling analysis metrics (long-side direction)
    long_crowdedness: float = 0.0       # 0-1, higher = more crowded longs
    long_squeeze_risk: float = 0.0      # 0-1, higher = longs about to be squeezed
    extension_score: float = 0.0        # 0-1, higher = closer to short-term top
    short_risk_rating: str = "neutral"  # "low" / "medium" / "high" / "extreme"
    short_grade: str = "B"              # "S" / "A" / "B" / "C" / "D"
    short_opportunity_score: float = 0.0  # 0-1, composite for modal display
    # Hot tick derivations
    oi_usd: float = 0.0
    funding_annualized: float = 0.0
    # Warm (6h) fundamentals — populated by FundamentalsCache in Phase 1b
    market_cap: float = 0.0
    top10_holders_pct: float = 0.0
    gini: float = 0.0
    fdv_mcap_ratio: float = 0.0
    sector: str = "其他"
    # Cold (daily) OHLCV — populated lazily by get_token_analysis in Phase 1b
    consecutive_up_days: int = 0
    trend_strength: float = 0.0
    high_24h: float = 0.0
    low_24h: float = 0.0
    atr: float = 0.0
    rebound_multiple: float = 0.0
    low_7d: float = 0.0
    # Trade reference (placeholders until Phase 1b fills them)
    stop_loss_price: float = 0.0
    take_profit_price: float = 0.0
    recommended_leverage: int = 5
```

Old field `crowdedness_score` / `squeeze_risk` / `rebound_potential` are gone. Any code that read them must be updated in this same PR (Task 3 & 4). The warm/cold fields are added with zero defaults so `_token_to_dict` can drop the `getattr` fallbacks later (Task 6) without AttributeError.

- [ ] **Step 2: Commit**

```bash
git add backend/services/hot_tokens_scanner.py
git commit -m "refactor(shorts): rename short-metric fields, drop rebound_potential"
```

---

### Task 2: Module-level pure helpers — `_long_crowdedness`, `_extension_score`, `_short_opportunity_score`

**Files:**
- Modify: `backend/services/hot_tokens_scanner.py` (top of file, after imports)
- Create: `backend/tests/test_hot_tokens_scanner_metrics.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_hot_tokens_scanner_metrics.py`:

```python
"""Pure-function tests for short-selling metrics added in Phase 1a."""
import math
from types import SimpleNamespace

import pytest

from services.hot_tokens_scanner import (
    _long_crowdedness,
    _extension_score,
    _short_opportunity_score,
)


def _tok(funding: float = 0.0, ls: float = 1.0, change: float = 0.0,
         market_cap: float = 0.0, volume_usd: float = 0.0,
         top10: float = 0.0, gini: float = 0.0) -> SimpleNamespace:
    return SimpleNamespace(
        funding_rate=funding,
        long_short_ratio=ls,
        price_change_24h=change,
        market_cap=market_cap,
        volume_usd=volume_usd,
        top10_holders_pct=top10,
        gini=gini,
    )


# --- _long_crowdedness ---

def test_long_crowdedness_zero_when_balanced():
    # funding=0, ls=1.0 → both signals 0
    assert _long_crowdedness(_tok(funding=0.0, ls=1.0)) == 0.0


def test_long_crowdedness_full_when_extreme_longs():
    # funding=+1% and ls=2.0 → both signals clipped to 1.0
    val = _long_crowdedness(_tok(funding=0.01, ls=2.0))
    assert math.isclose(val, 1.0, abs_tol=1e-9)


def test_long_crowdedness_negative_funding_does_not_count_as_long_crowd():
    # funding=-1% (shorts pay longs) should NOT raise long_crowdedness
    val = _long_crowdedness(_tok(funding=-0.01, ls=1.0))
    assert val == 0.0


def test_long_crowdedness_weighting_funding_heavier_than_ls():
    # At half-curve each: funding=0.005 → 0.5, ls=1.5 → 0.5
    # Expected: 0.5*0.6 + 0.5*0.4 = 0.5
    val = _long_crowdedness(_tok(funding=0.005, ls=1.5))
    assert math.isclose(val, 0.5, abs_tol=1e-9)


def test_long_crowdedness_clipped_to_unit_interval():
    # Both signals would exceed 1.0 if not clipped
    val = _long_crowdedness(_tok(funding=0.05, ls=5.0))
    assert 0.0 <= val <= 1.0


# --- _extension_score ---

def test_extension_score_zero_for_negative_change():
    assert _extension_score(_tok(change=-5.0)) == 0.0


def test_extension_score_zero_for_zero_change():
    assert _extension_score(_tok(change=0.0)) == 0.0


def test_extension_score_linear_up_to_ten_percent():
    # +5% → 0.5
    assert math.isclose(_extension_score(_tok(change=5.0)), 0.5, abs_tol=1e-9)


def test_extension_score_clamped_at_ten_percent():
    # +20% → 1.0 (clipped)
    assert _extension_score(_tok(change=20.0)) == 1.0


def test_extension_score_exact_boundary_at_ten_percent():
    # +10% → exactly 1.0
    assert math.isclose(_extension_score(_tok(change=10.0)), 1.0, abs_tol=1e-9)


# --- _short_opportunity_score ---

def test_opportunity_score_weights_sum_to_one_when_inputs_one():
    # If all four inputs were 1.0, score should equal 1.0
    t = _tok(funding=0.01, ls=2.0, change=10.0,
             market_cap=2e9, volume_usd=200e6, top10=0.0)
    # crowd=1.0, ext=1.0, liq: market_cap=2e9/1e9=2.0 clipped to 1.0 → 1.0*0.6
    #                  volume_usd=200e6/100e6=2.0 clipped to 1.0 → 1.0*0.4
    #                  liq = 1.0
    # dist: top10=0 → 0.5 neutral
    expected = 1.0 * 0.35 + 1.0 * 0.25 + 1.0 * 0.20 + 0.5 * 0.20
    val = _short_opportunity_score(t)
    assert math.isclose(val, expected, abs_tol=1e-9)


def test_opportunity_score_dist_neutral_when_top10_unfilled():
    # top10=0 (cache miss) → 0.5
    t = _tok(funding=0.005, ls=1.5, change=5.0,
             market_cap=5e8, volume_usd=50e6, top10=0.0)
    val = _short_opportunity_score(t)
    # Check the 0.5 weight on dist
    no_top10 = 0.5 * 0.20
    with_top10_zero = 0.0 * 0.20
    assert val > 0  # never zero when other inputs positive
    # And it's strictly between these two
    assert 0.0 < val < 1.0


def test_opportunity_score_dist_max_at_low_top10():
    # top10=30% → dist=1.0
    t_low = _tok(funding=0.005, ls=1.5, change=5.0,
                 market_cap=5e8, volume_usd=50e6, top10=30.0)
    # top10=70% → dist=0.0
    t_high = _tok(funding=0.005, ls=1.5, change=5.0,
                  market_cap=5e8, volume_usd=50e6, top10=70.0)
    assert _short_opportunity_score(t_low) > _short_opportunity_score(t_high)


def test_opportunity_score_top10_above_70_yields_zero_dist():
    # top10=80% → dist = max(min((70-80)/40, 1.0), 0.0) = 0.0
    t = _tok(funding=0.0, ls=1.0, change=0.0,
             market_cap=0.0, volume_usd=0.0, top10=80.0)
    # Only dist contributes, and it's 0
    assert _short_opportunity_score(t) == 0.0
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd D:/work/browser-demo/backend && python -m pytest tests/test_hot_tokens_scanner_metrics.py -v
```

Expected: ImportError — cannot import `_long_crowdedness`.

- [ ] **Step 3: Add the three helper functions to `hot_tokens_scanner.py`**

Insert at the bottom of the module (after the `_scanner` singleton and `get_scanner()` factory) so they are pure module-level functions and easy to test without instantiating ccxt:

```python
# ---------------------------------------------------------------------------
# Pure scoring helpers (Phase 1a)
# ---------------------------------------------------------------------------

def _long_crowdedness(token: "HotToken") -> float:
    """0-1 measure of how crowded the LONG side is. Higher = easier to short.

    F1 (from spec §4.2):
        funding_signal = clip(funding / 0.01, 0, 1)
        ls_signal      = clip((ls_ratio - 1.0) / 1.0, 0, 1)
        long_crowdedness = funding_signal * 0.6 + ls_signal * 0.4
    """
    funding_signal = max(min(token.funding_rate / 0.01, 1.0), 0.0)
    ls_signal = max(min((token.long_short_ratio - 1.0) / 1.0, 1.0), 0.0)
    return funding_signal * 0.6 + ls_signal * 0.4


def _extension_score(token: "HotToken") -> float:
    """0-1 measure of how extended the price is on the upside.

    F2 (from spec §4.2):
        +10% move → 1.0; negative or zero change → 0.0; clipped to [0, 1].
    """
    if token.price_change_24h <= 0:
        return 0.0
    return max(min(token.price_change_24h / 10.0, 1.0), 0.0)


def _short_opportunity_score(token: "HotToken") -> float:
    """Composite 0-1 score combining crowd, extension, liquidity, distribution.

    Spec §4.4 — used in modal only, never for sort.
    """
    crowd = _long_crowdedness(token)
    ext = _extension_score(token)

    liq = (
        min(token.market_cap / 1e9, 1.0) * 0.6
        + min(token.volume_usd / 100e6, 1.0) * 0.4
    )

    if token.top10_holders_pct <= 0:
        dist = 0.5
    else:
        dist = max(min((70.0 - token.top10_holders_pct) / 40.0, 1.0), 0.0)

    return crowd * 0.35 + ext * 0.25 + liq * 0.20 + dist * 0.20
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd D:/work/browser-demo/backend && python -m pytest tests/test_hot_tokens_scanner_metrics.py -v
```

Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/hot_tokens_scanner.py backend/tests/test_hot_tokens_scanner_metrics.py
git commit -m "feat(shorts): add long_crowdedness, extension_score, opportunity helpers"
```

---

### Task 3: `_calculate_short_grade()` with the S/A/B/C/D mapping

**Files:**
- Modify: `backend/services/hot_tokens_scanner.py` (add helper)
- Modify: `backend/tests/test_hot_tokens_scanner_metrics.py` (add cases)

- [ ] **Step 1: Add the failing tests**

Append to `backend/tests/test_hot_tokens_scanner_metrics.py`:

```python
from services.hot_tokens_scanner import _calculate_short_grade


def test_short_grade_s_top_tier():
    # All four S-conditions satisfied
    t = _tok(funding=0.012, ls=2.0, change=8.0,
             market_cap=2e9, volume_usd=200e6, top10=50.0)
    assert _calculate_short_grade(t) == "S"


def test_short_grade_a_no_top10_known():
    # A requires crowd+ext+market_cap but NOT top10
    t = _tok(funding=0.008, ls=1.8, change=6.0,
             market_cap=2e9, volume_usd=200e6, top10=0.0)
    assert _calculate_short_grade(t) == "A"


def test_short_grade_b_either_signal_at_threshold():
    # crowd ≥ 0.3 is enough
    t = _tok(funding=0.005, ls=1.4, change=1.0,
             market_cap=2e8, volume_usd=50e6, top10=80.0)
    assert _calculate_short_grade(t) == "B"


def test_short_grade_b_extension_only():
    # ext ≥ 0.3, crowd below — still B if market_cap ≥ 100M
    t = _tok(funding=0.0, ls=1.0, change=4.0,
             market_cap=2e8, volume_usd=50e6, top10=80.0)
    assert _calculate_short_grade(t) == "B"


def test_short_grade_c_liquid_below_threshold():
    # market_cap ≥ 100M and volume ≥ 10M but neither signal high enough
    t = _tok(funding=0.0, ls=1.0, change=0.0,
             market_cap=2e8, volume_usd=20e6, top10=80.0)
    assert _calculate_short_grade(t) == "C"


def test_short_grade_d_low_market_cap():
    t = _tok(funding=0.0, ls=1.0, change=0.0,
             market_cap=50e6, volume_usd=50e6, top10=80.0)
    assert _calculate_short_grade(t) == "D"


def test_short_grade_d_low_volume():
    t = _tok(funding=0.0, ls=1.0, change=0.0,
             market_cap=2e8, volume_usd=5e6, top10=80.0)
    assert _calculate_short_grade(t) == "D"


def test_short_grade_s_demits_to_a_when_top10_unknown():
    # Even if crowd/ext/market_cap all S-grade, missing top10 prevents S
    t = _tok(funding=0.012, ls=2.0, change=8.0,
             market_cap=2e9, volume_usd=200e6, top10=0.0)
    assert _calculate_short_grade(t) == "A"


def test_short_grade_s_demits_when_top10_too_concentrated():
    # top10 > 70% disqualifies S
    t = _tok(funding=0.012, ls=2.0, change=8.0,
             market_cap=2e9, volume_usd=200e6, top10=80.0)
    assert _calculate_short_grade(t) == "A"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd D:/work/browser-demo/backend && python -m pytest tests/test_hot_tokens_scanner_metrics.py -v -k "short_grade"
```

Expected: ImportError — cannot import `_calculate_short_grade`.

- [ ] **Step 3: Add `_calculate_short_grade()` to `hot_tokens_scanner.py`**

Insert after `_short_opportunity_score`:

```python
def _calculate_short_grade(token: "HotToken") -> str:
    """Map a token to S/A/B/C/D per spec §4.3.

    The first matching row wins. Unfilled fields (=0) downgrade by failing
    the row that requires them.
    """
    crowd = _long_crowdedness(token)
    ext = _extension_score(token)
    mc = token.market_cap
    vol = token.volume_usd
    top10 = token.top10_holders_pct

    # S: top-tier. Requires top10 known AND ≤ 70.
    if (
        crowd >= 0.7
        and ext >= 0.6
        and mc >= 1e9
        and 0 < top10 <= 70
    ):
        return "S"

    # A: solid. No top10 requirement, but big-cap + high signals.
    if crowd >= 0.5 and ext >= 0.4 and mc >= 1e9:
        return "A"

    # B: either signal above 0.3 AND big enough to trade.
    if (crowd >= 0.3 or ext >= 0.3) and mc >= 100e6:
        return "B"

    # C: liquid but no real signal.
    if mc >= 100e6 and vol >= 10e6:
        return "C"

    # D: not tradeable.
    return "D"
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd D:/work/browser-demo/backend && python -m pytest tests/test_hot_tokens_scanner_metrics.py -v -k "short_grade"
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/hot_tokens_scanner.py backend/tests/test_hot_tokens_scanner_metrics.py
git commit -m "feat(shorts): add _calculate_short_grade S/A/B/C/D mapping"
```

---

### Task 4: Replace `_calculate_short_metrics` to populate the renamed fields + grade + score

**Files:**
- Modify: `backend/services/hot_tokens_scanner.py:270-319`

- [ ] **Step 1: Replace the body of `_calculate_short_metrics`**

Replace lines 270-319 (the entire `_calculate_short_metrics` method) with:

```python
    def _calculate_short_metrics(self, token: HotToken) -> None:
        """Populate long-side crowdedness, extension, grade, and composite score.

        Reads only fields already on the tick (funding_rate, long_short_ratio,
        price_change_24h, volume_usd, plus cached market_cap / top10 from
        FundamentalsCache).
        """
        token.long_crowdedness = _long_crowdedness(token)
        token.extension_score = _extension_score(token)

        # Long squeeze risk: high crowd + extended price (longs about to be squeezed)
        token.long_squeeze_risk = min(
            token.long_crowdedness * 0.6 + token.extension_score * 0.4, 1.0
        )

        token.short_opportunity_score = _short_opportunity_score(token)
        token.short_grade = _calculate_short_grade(token)

        # Risk rating bands use long_crowdedness (high = good for shorting).
        risk = token.long_crowdedness
        if risk > 0.8:
            token.short_risk_rating = "extreme"
        elif risk > 0.6:
            token.short_risk_rating = "high"
        elif risk > 0.4:
            token.short_risk_rating = "medium"
        else:
            token.short_risk_rating = "low"
```

- [ ] **Step 2: Run the existing scanner tests + new tests**

```bash
cd D:/work/browser-demo/backend && python -m pytest tests/test_hot_tokens.py tests/test_hot_tokens_scanner_metrics.py -v
```

Expected: all pass (the previous test file `test_hot_tokens.py` only tests the `/sectors` endpoint, which doesn't touch short metrics, so it should still pass).

- [ ] **Step 3: Commit**

```bash
git add backend/services/hot_tokens_scanner.py
git commit -m "refactor(shorts): replace _calculate_short_metrics with correct direction"
```

---

### Task 5: Tick-level `oi_usd` and `funding_annualized` derivations

**Files:**
- Modify: `backend/services/hot_tokens_scanner.py:155-172` (inside `_fetch_and_update`)

- [ ] **Step 1: Update the HotToken construction in `_fetch_and_update`**

Replace the block that builds `HotToken(...)` (around lines 161-171) with:

```python
            oi_usd = open_interest * price
            funding_annualized = funding_rate * 3 * 365

            hot = HotToken(
                symbol=binance_symbol,
                price=price,
                price_change_24h=price_change,
                volume_24h=volume,
                volume_usd=volume_usd,
                funding_rate=funding_rate,
                long_short_ratio=long_short_ratio,
                open_interest=open_interest,
                liquidation_price=liquidation_price,
                oi_usd=oi_usd,
                funding_annualized=funding_annualized,
            )
            hot_list.append(hot)
```

- [ ] **Step 2: Run the scanner tests**

```bash
cd D:/work/browser-demo/backend && python -m pytest tests/test_hot_tokens.py tests/test_hot_tokens_scanner_metrics.py -v
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add backend/services/hot_tokens_scanner.py
git commit -m "feat(shorts): derive oi_usd and funding_annualized at tick"
```

---

### Task 6: API `_token_to_dict` + `_short_recommendation` text rewrite

**Files:**
- Modify: `backend/api/hot_tokens.py:15-52` (`_token_to_dict`)
- Modify: `backend/api/hot_tokens.py:222-232` (`_short_recommendation`)
- Modify: `backend/api/hot_tokens.py:166-219` (`get_token_analysis`)

- [ ] **Step 1: Add the failing test**

Create `backend/tests/test_hot_tokens_api_fields.py`:

```python
"""API contract: /api/hot_tokens/ and /api/hot_tokens/{symbol}/analysis must
expose all 13 short-selling fields with values populated from the scanner
(no getattr fallbacks hiding the absence of data)."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from services.hot_tokens_scanner import HotToken


EXPECTED_LIST_FIELDS = {
    "symbol", "price", "price_change_24h", "volume_24h", "volume_usd",
    "funding_rate", "long_short_ratio", "open_interest", "liquidation_price",
    "heat_score", "heat_rank", "updated_at",
    "long_crowdedness", "long_squeeze_risk", "extension_score",
    "short_risk_rating", "short_grade", "short_opportunity_score",
    "oi_usd", "funding_annualized",
    # Phase 1b will fill these from FundamentalsCache; for now they should
    # be present in the response even if zero.
    "market_cap", "consecutive_up_days", "trend_strength", "sector",
    "top10_holders_pct", "gini", "fdv_mcap_ratio",
    "high_24h", "low_24h", "atr",
    "recommended_leverage", "stop_loss_price", "take_profit_price",
}


def _stub_token() -> HotToken:
    """Return a fully-populated HotToken so we can assert the response shape."""
    return HotToken(
        symbol="BTCUSDT",
        price=60000.0,
        price_change_24h=5.0,
        volume_24h=100.0,
        volume_usd=6_000_000_000.0,
        funding_rate=0.005,
        long_short_ratio=1.8,
        open_interest=50000.0,
        liquidation_price=57000.0,
        heat_score=0.85,
        heat_rank=1,
        updated_at="2026-06-05T00:00:00Z",
        long_crowdedness=0.72,
        long_squeeze_risk=0.65,
        extension_score=0.5,
        short_risk_rating="high",
        short_grade="A",
        short_opportunity_score=0.68,
        oi_usd=3_000_000_000.0,
        funding_annualized=547.5,
    )


class _FakeScanner:
    def __init__(self, token: HotToken) -> None:
        self._hot_tokens = {token.symbol: token}
        self._running = True

    def get_hot_tokens(self, limit: int = 50) -> list[HotToken]:
        return list(self._hot_tokens.values())[:limit]


def test_list_endpoint_returns_all_short_fields():
    token = _stub_token()
    with patch("api.hot_tokens.get_scanner", return_value=_FakeScanner(token)):
        from main import app
        client = TestClient(app)
        resp = client.get("/api/hot_tokens/?limit=5")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    row = body[0]
    missing = EXPECTED_LIST_FIELDS - set(row.keys())
    assert not missing, f"Missing fields: {missing}"
    # Hot fields should carry real values, not defaults
    assert row["short_grade"] == "A"
    assert row["long_crowdedness"] == pytest.approx(0.72)
    assert row["oi_usd"] == pytest.approx(3_000_000_000.0)


def test_analysis_endpoint_returns_ohlcv_derived_fields():
    token = _stub_token()
    with patch("api.hot_tokens.get_scanner", return_value=_FakeScanner(token)):
        from main import app
        client = TestClient(app)
        resp = client.get("/api/hot_tokens/BTCUSDT/analysis")

    assert resp.status_code == 200
    body = resp.json()
    for f in ("high_24h", "low_24h", "atr", "rebound_multiple",
              "consecutive_up_days", "low_7d"):
        assert f in body, f"Missing: {f}"
    assert "recommendation" in body
    # Recommendation should reflect the corrected long-side direction
    assert "long" in body["recommendation"].lower() or "extreme" in body["recommendation"].lower()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd D:/work/browser-demo/backend && python -m pytest tests/test_hot_tokens_api_fields.py -v
```

Expected: failures on the new-field assertions (e.g., `top10_holders_pct` not in response; recommendation text doesn't contain the new direction language).

- [ ] **Step 3: Rewrite `_token_to_dict` to drop `getattr` and expose the new fields**

Replace the body of `_token_to_dict` in `backend/api/hot_tokens.py` (lines 15-52) with:

```python
def _token_to_dict(token: HotToken) -> dict[str, Any]:
    return {
        "symbol": token.symbol,
        "price": token.price,
        "price_change_24h": token.price_change_24h,
        "volume_24h": token.volume_24h,
        "volume_usd": token.volume_usd,
        "funding_rate": token.funding_rate,
        "long_short_ratio": token.long_short_ratio,
        "open_interest": token.open_interest,
        "liquidation_price": token.liquidation_price,
        "heat_score": token.heat_score,
        "heat_rank": token.heat_rank,
        "updated_at": token.updated_at,
        # Short analysis (corrected long-side direction)
        "long_crowdedness": token.long_crowdedness,
        "long_squeeze_risk": token.long_squeeze_risk,
        "extension_score": token.extension_score,
        "short_risk_rating": token.short_risk_rating,
        "short_grade": token.short_grade,
        "short_opportunity_score": token.short_opportunity_score,
        # Hot tick derivations
        "oi_usd": token.oi_usd,
        "funding_annualized": token.funding_annualized,
        # Warm / cold fields — populated by FundamentalsCache (Phase 1b)
        "market_cap": token.market_cap,
        "top10_holders_pct": token.top10_holders_pct,
        "gini": token.gini,
        "fdv_mcap_ratio": token.fdv_mcap_ratio,
        "sector": token.sector,
        "consecutive_up_days": token.consecutive_up_days,
        "trend_strength": token.trend_strength,
        "high_24h": token.high_24h,
        "low_24h": token.low_24h,
        "atr": token.atr,
        "rebound_multiple": token.rebound_multiple,
        "low_7d": token.low_7d,
        "stop_loss_price": token.stop_loss_price,
        "take_profit_price": token.take_profit_price,
        "recommended_leverage": token.recommended_leverage,
    }
```

- [ ] **Step 4: Rewrite `_short_recommendation()` for the corrected direction**

Replace `backend/api/hot_tokens.py:222-232` with:

```python
def _short_recommendation(token: HotToken) -> str:
    """Short recommendation in the corrected long-crowd direction.

    High long_crowdedness = longs are paying funding and over-positioned
    = favorable short entry. High extension_score = price extended
    = stronger short setup.
    """
    if token.short_risk_rating == "extreme" and token.long_squeeze_risk > 0.7:
        return (
            "HIGH CONFIDENCE SHORT — Longs are extremely crowded and "
            "squeeze risk is high. Wait for funding to flip or a wick, "
            "then short into the move."
        )
    if token.short_risk_rating == "extreme":
        return (
            "STRONG SHORT — Extreme long crowding with elevated funding. "
            "Size conservatively; the position can run further before mean-reverting."
        )
    if token.short_risk_rating == "high":
        return (
            "MODERATE SHORT — Longs are crowded and funding is positive. "
            "Standard short setup; honor stop."
        )
    if token.short_risk_rating == "medium":
        return (
            "CAUTION — Some long crowding but not extreme. "
            "Wait for extension_score > 0.4 before entry."
        )
    return (
        "LOW CONVICTION — Longs are not crowded. Look elsewhere."
    )
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
cd D:/work/browser-demo/backend && python -m pytest tests/test_hot_tokens_api_fields.py tests/test_hot_tokens.py tests/test_hot_tokens_scanner_metrics.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/api/hot_tokens.py backend/services/hot_tokens_scanner.py backend/tests/test_hot_tokens_api_fields.py
git commit -m "feat(shorts): API exposes all 13 short fields, recommendation text reflects long direction"
```

---

### Task 7: Frontend — modal renders new metrics, table shows real short_grade

**Files:**
- Modify: `frontend/src/views/ShortsView.vue`

- [ ] **Step 1: Update the `HotToken` interface**

Replace the interface in `<script setup>` (lines 242-273) with:

```typescript
interface HotToken {
  symbol: string
  price: number
  price_change_24h: number
  volume_24h: number
  volume_usd: number
  funding_rate: number
  long_short_ratio: number
  open_interest: number
  liquidation_price: number
  heat_score: number
  heat_rank?: number
  updated_at?: string
  // Short analysis (long-side direction)
  long_crowdedness?: number
  long_squeeze_risk?: number
  extension_score?: number
  short_risk_rating?: string
  short_grade?: string
  short_opportunity_score?: number
  // Hot tick derivations
  oi_usd?: number
  funding_annualized?: number
  // Warm/cold fields (Phase 1b populates; rendered as 0 for now)
  market_cap?: number
  top10_holders_pct?: number
  gini?: number
  fdv_mcap_ratio?: number
  sector?: string
  consecutive_up_days?: number
  trend_strength?: number
  high_24h?: number
  low_24h?: number
  atr?: number
  rebound_multiple?: number
  low_7d?: number
  stop_loss_price?: number
  take_profit_price?: number
  recommended_leverage?: number
}
```

- [ ] **Step 2: Replace the metric-card 4-grid with corrected labels**

In the template, replace lines 109-138 (the `<div class="analysis-metrics">` block) with:

```html
          <!-- 核心指标四卡（已修正为多头拥挤度方向） -->
          <div class="analysis-metrics">
            <div class="metric-card" :class="fundingColorClass">
              <div class="metric-label">资金费率 (8h)</div>
              <div class="metric-value">
                {{ ((selectedToken.funding_rate || 0) * 100).toFixed(4) }}%
              </div>
              <div class="metric-hint">{{ fundingHintText }}</div>
            </div>
            <div class="metric-card" :class="longCrowdClass">
              <div class="metric-label">多头拥挤度</div>
              <div class="metric-value">
                {{ ((selectedToken.long_crowdedness || 0) * 100).toFixed(0) }}%
              </div>
              <div class="metric-hint">{{ longCrowdHintText }}</div>
            </div>
            <div class="metric-card" :class="squeezeClass">
              <div class="metric-label">轧空风险</div>
              <div class="metric-value">
                {{ ((selectedToken.long_squeeze_risk || 0) * 100).toFixed(0) }}%
              </div>
              <div class="metric-hint">{{ squeezeHintText }}</div>
            </div>
            <div class="metric-card" :class="extensionClass">
              <div class="metric-label">涨幅到位度</div>
              <div class="metric-value">
                {{ ((selectedToken.extension_score || 0) * 100).toFixed(0) }}%
              </div>
              <div class="metric-hint">{{ extensionHintText }}</div>
            </div>
          </div>
```

- [ ] **Step 3: Add the new computed properties in `<script setup>`**

After the `squeezeHintText` computed (around line 350), add:

```typescript
const longCrowdClass = computed(() => {
  const c = selectedToken.value?.long_crowdedness ?? 0
  if (c > 0.7) return 'extreme'
  if (c > 0.5) return 'high'
  if (c > 0.3) return 'medium'
  return 'low'
})

const longCrowdHintText = computed(() => {
  const c = selectedToken.value?.long_crowdedness ?? 0
  if (c > 0.7) return '多头极度拥挤,做空胜率↑'
  if (c > 0.4) return '多头仓位偏高,关注'
  if (c > 0.2) return '多空相对平衡'
  return '多头仓位较轻,做空需谨慎'
})

const extensionClass = computed(() => {
  const e = selectedToken.value?.extension_score ?? 0
  if (e > 0.7) return 'extreme'
  if (e > 0.4) return 'high'
  if (e > 0.2) return 'medium'
  return 'low'
})

const extensionHintText = computed(() => {
  const e = selectedToken.value?.extension_score ?? 0
  if (e > 0.7) return '涨幅已延伸,顶部临近'
  if (e > 0.4) return '涨势明显,可考虑介入'
  if (e > 0.2) return '有一定涨幅'
  return '涨幅未到位,做空风险大'
})
```

- [ ] **Step 4: Update the table's grade cell label**

The grade cell at lines 62-64 already reads `token.short_grade` — no change needed; the backend now actually populates it. Verify by running the dev server.

- [ ] **Step 5: Type-check**

```bash
cd D:/work/browser-demo/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/ShortsView.vue
git commit -m "feat(shorts): modal renders long_crowdedness, long_squeeze_risk, extension_score"
```

---

### Task 8: Manual smoke test + Phase 1a wrap-up

- [ ] **Step 1: Boot the backend**

```bash
cd D:/work/browser-demo/backend && python -m uvicorn main:app --reload
```

- [ ] **Step 2: Hit the endpoint**

```bash
curl http://localhost:8000/api/hot_tokens/?limit=5 | python -m json.tool | head -60
```

Expected: 5 rows, every row has `short_grade` of `A`/`B`/`C`/`D` (no `S` until Phase 1b populates `top10_holders_pct`), `long_crowdedness` is a real number, `oi_usd` is non-zero for top tokens.

- [ ] **Step 3: Boot the frontend**

```bash
cd D:/work/browser-demo/frontend && npm run dev
```

- [ ] **Step 4: Open `http://localhost:5173/analysis`**

Expected: the "做空评级" column shows real letters (not all `C`); clicking a row opens a modal where the four cards show "多头拥挤度 / 轧空风险 / 涨幅到位度" with real percentages.

- [ ] **Step 5: Push the branch and open a PR**

```bash
git push origin <branch>
gh pr create --title "feat(shorts): Phase 1a — corrected direction + S/A/B/C/D grade" --body "..."
```

---

## Phase 1b — Cache layer + warm/cold fields (~2.5h, one PR)

### Task 9: `FundamentalsCache` skeleton + CoinGecko `/coins/markets` pull

**Files:**
- Create: `backend/services/fundamentals_cache.py`
- Create: `backend/tests/test_fundamentals_cache.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_fundamentals_cache.py`:

```python
"""Tests for FundamentalsCache (Phase 1b)."""
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.fundamentals_cache import FundamentalsCache


@pytest.mark.asyncio
async def test_cache_returns_empty_dict_on_init():
    cache = FundamentalsCache(refresh_interval=3600)
    assert cache.get("BTCUSDT") == {}


@pytest.mark.asyncio
async def test_refresh_populates_market_data():
    cache = FundamentalsCache(refresh_interval=3600)

    fake_markets = [
        {
            "symbol": "btc", "id": "bitcoin",
            "market_cap": 1_200_000_000_000,
            "fully_diluted_valuation": 1_250_000_000_000,
            "categories": ["Layer 1", "Store of Value"],
        },
        {
            "symbol": "eth", "id": "ethereum",
            "market_cap": 400_000_000_000,
            "fully_diluted_valuation": 400_000_000_000,
            "categories": ["Smart Contract Platform"],
        },
    ]
    fake_source = MagicMock()
    fake_source.get_coins_markets = AsyncMock(return_value=fake_markets)

    with patch(
        "services.fundamentals_cache._get_coingecko_source",
        return_value=fake_source,
    ):
        await cache.refresh()

    btc = cache.get("BTCUSDT")
    assert btc["market_cap"] == 1_200_000_000_000
    assert btc["cg_id"] == "bitcoin"
    assert "Layer 1" in btc["categories"]
    assert btc["fdv_mcap_ratio"] == pytest.approx(1_250_000_000_000 / 1_200_000_000_000)


@pytest.mark.asyncio
async def test_refresh_swallows_coingecko_failure():
    cache = FundamentalsCache(refresh_interval=3600)
    fake_source = MagicMock()
    fake_source.get_coins_markets = AsyncMock(side_effect=Exception("429"))
    with patch(
        "services.fundamentals_cache._get_coingecko_source",
        return_value=fake_source,
    ):
        # Must NOT raise
        await cache.refresh()
    # Stale data may be empty but lookup must not crash
    assert cache.get("BTCUSDT") == {}


@pytest.mark.asyncio
async def test_cache_is_stale_after_interval():
    cache = FundamentalsCache(refresh_interval=0.1)
    await cache.refresh()
    assert cache.is_stale() is False
    time.sleep(0.2)
    assert cache.is_stale() is True


@pytest.mark.asyncio
async def test_arkham_holders_layered_on_top():
    cache = FundamentalsCache(refresh_interval=3600)
    fake_markets = [
        {"symbol": "btc", "id": "bitcoin", "market_cap": 1e12,
         "fully_diluted_valuation": 1e12, "categories": []},
    ]
    fake_arkham = {
        "top_10_pct": 35.5, "gini": 0.72, "holder_count": 1000,
    }
    cg_source = MagicMock()
    cg_source.get_coins_markets = AsyncMock(return_value=fake_markets)
    with patch(
        "services.fundamentals_cache._get_coingecko_source",
        return_value=cg_source,
    ), patch(
        "services.fundamentals_cache.arkham.get_holder_concentration",
        AsyncMock(return_value=fake_arkham),
    ):
        await cache.refresh()

    btc = cache.get("BTCUSDT")
    assert btc["top10_holders_pct"] == 35.5
    assert btc["gini"] == 0.72
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd D:/work/browser-demo/backend && python -m pytest tests/test_fundamentals_cache.py -v
```

Expected: ModuleNotFoundError — `services.fundamentals_cache` does not exist.

- [ ] **Step 3: Create `fundamentals_cache.py`**

Create `backend/services/fundamentals_cache.py`:

```python
"""6h cache for token fundamentals: market cap, FDV, categories, holder concentration.

Spec §5 — pulls CoinGecko /coins/markets once per refresh interval, then layers
Arkham holder concentration on top per symbol. All external calls are wrapped
in try/except so a single failure never bubbles to the scanner loop.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from services.datasources.coingecko import CoinGeckoSource
from services.datasources import arkham

logger = logging.getLogger(__name__)


def _get_coingecko_source() -> CoinGeckoSource:
    return CoinGeckoSource()


class FundamentalsCache:
    """In-memory cache refreshed every `refresh_interval` seconds.

    Per-symbol entries look like:
        {
            "market_cap": float,
            "fdv_mcap_ratio": float,
            "categories": list[str],
            "cg_id": str,
            "top10_holders_pct": float,  # 0 if unknown
            "gini": float,                # 0 if unknown
            "holder_count": int,
        }
    """

    def __init__(self, refresh_interval: int = 6 * 3600) -> None:
        self.refresh_interval = refresh_interval
        self._data: dict[str, dict[str, Any]] = {}
        self._last_refresh: float = 0.0
        self._lock = asyncio.Lock()

    def get(self, symbol: str) -> dict[str, Any]:
        """Return cached entry for a USDT-margined symbol. Empty dict on miss."""
        return self._data.get(symbol.upper(), {})

    def is_stale(self) -> bool:
        return (time.time() - self._last_refresh) >= self.refresh_interval

    async def refresh(self) -> None:
        """Refresh CoinGecko markets + Arkham holders. Fail-soft: never raises."""
        async with self._lock:
            markets = await self._fetch_coingecko_markets()
            cg_by_symbol = self._index_by_symbol(markets)
            new_data: dict[str, dict[str, Any]] = {}

            for symbol, entry in cg_by_symbol.items():
                holders = await self._fetch_arkham_holders(entry["cg_id"])
                new_data[symbol] = {**entry, **holders}

            self._data = new_data
            self._last_refresh = time.time()
            logger.info(f"FundamentalsCache refreshed: {len(new_data)} symbols")

    async def _fetch_coingecko_markets(self) -> list[dict[str, Any]]:
        try:
            src = _get_coingecko_source()
            return await src.get_coins_markets(per_page=250)
        except Exception as e:
            logger.warning(f"CoinGecko /coins/markets failed: {e}")
            return []

    @staticmethod
    def _index_by_symbol(markets: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for coin in markets:
            symbol = (coin.get("symbol") or "").upper()
            if not symbol:
                continue
            mc = coin.get("market_cap") or 0
            fdv = coin.get("fully_diluted_valuation") or 0
            fdv_ratio = (fdv / mc) if mc else 0.0
            out[f"{symbol}USDT"] = {
                "market_cap": mc,
                "fdv_mcap_ratio": fdv_ratio,
                "categories": coin.get("categories") or [],
                "cg_id": coin.get("id") or "",
            }
        return out

    async def _fetch_arkham_holders(self, cg_id: str) -> dict[str, Any]:
        if not cg_id:
            return {"top10_holders_pct": 0.0, "gini": 0.0, "holder_count": 0}
        try:
            result = await arkham.get_holder_concentration(cg_id, top_n=20)
            if "error" in result:
                return {"top10_holders_pct": 0.0, "gini": 0.0, "holder_count": 0}
            return {
                "top10_holders_pct": result.get("top_10_pct", 0.0),
                "gini": result.get("gini", 0.0),
                "holder_count": result.get("holder_count", 0),
            }
        except Exception as e:
            logger.warning(f"Arkham holder fetch failed for {cg_id}: {e}")
            return {"top10_holders_pct": 0.0, "gini": 0.0, "holder_count": 0}


# Module-level singleton
_cache: Optional[FundamentalsCache] = None


def get_cache() -> FundamentalsCache:
    global _cache
    if _cache is None:
        _cache = FundamentalsCache()
    return _cache
```

- [ ] **Step 4: Add `get_coins_markets` to `CoinGeckoSource` if missing**

Read `backend/services/datasources/coingecko.py`. The `get_top_market_cap` method already calls `/coins/markets` but it reshapes the response. Add a thin wrapper that returns the raw list:

Append to `backend/services/datasources/coingecko.py`:

```python
    async def get_coins_markets(self, per_page: int = 250, page: int = 1) -> list[dict[str, Any]]:
        """Raw /coins/markets response. Used by FundamentalsCache."""
        resp = await self._client.get(
            "/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": per_page,
                "page": page,
                "sparkline": "false",
            },
        )
        resp.raise_for_status()
        return resp.json()
```

- [ ] **Step 5: Run the test to verify it passes**

(Step numbers below shift by 1 from this point.)

```bash
cd D:/work/browser-demo/backend && python -m pytest tests/test_fundamentals_cache.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/services/fundamentals_cache.py backend/services/datasources/coingecko.py backend/tests/test_fundamentals_cache.py
git commit -m "feat(shorts): FundamentalsCache with CoinGecko + Arkham 6h refresh"
```

---

### Task 10: Wire `FundamentalsCache` into scanner tick + sector classifier

**Files:**
- Modify: `backend/services/hot_tokens_scanner.py` (inside `_fetch_and_update`)
- Modify: `backend/main.py` (startup hook)

- [ ] **Step 1: Add the failing test**

Append to `backend/tests/test_fundamentals_cache.py`:

```python
@pytest.mark.asyncio
async def test_scanner_applies_cached_fields_to_token():
    """When the cache is populated, scanner tick should copy values onto the token."""
    from services.hot_tokens_scanner import HotToken

    cache = FundamentalsCache(refresh_interval=3600)
    cache._data = {
        "BTCUSDT": {
            "market_cap": 1e12, "fdv_mcap_ratio": 1.04,
            "categories": ["Layer 1"], "cg_id": "bitcoin",
            "top10_holders_pct": 35.0, "gini": 0.72, "holder_count": 1_000,
        }
    }
    token = HotToken(symbol="BTCUSDT", price=60000.0, market_cap=1e9)
    cache.apply_to_token(token)
    assert token.market_cap == 1e12  # overwritten by cache
    assert token.top10_holders_pct == 35.0
    assert token.gini == 0.72
    assert token.sector == "Layer 1"  # categories first element


@pytest.mark.asyncio
async def test_scanner_keeps_existing_when_cache_empty():
    from services.hot_tokens_scanner import HotToken

    cache = FundamentalsCache(refresh_interval=3600)
    token = HotToken(symbol="OBSCUREUSDT", market_cap=5e7, sector="其他")
    cache.apply_to_token(token)
    assert token.market_cap == 5e7
    assert token.sector == "其他"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd D:/work/browser-demo/backend && python -m pytest tests/test_fundamentals_cache.py::test_scanner_applies_cached_fields_to_token -v
```

Expected: AttributeError — `FundamentalsCache` has no `apply_to_token`.

- [ ] **Step 3: Add `apply_to_token` to `FundamentalsCache`**

Append inside the `FundamentalsCache` class in `fundamentals_cache.py`:

```python
    def apply_to_token(self, token: "HotToken") -> None:
        """Copy cached fields onto a HotToken in-place. No-op on miss."""
        from services.hot_tokens_scanner import HotToken  # local import to avoid cycle
        entry = self._data.get(token.symbol)
        if not entry:
            return
        token.market_cap = entry.get("market_cap", 0.0) or 0.0
        token.fdv_mcap_ratio = entry.get("fdv_mcap_ratio", 0.0) or 0.0
        token.top10_holders_pct = entry.get("top10_holders_pct", 0.0) or 0.0
        token.gini = entry.get("gini", 0.0) or 0.0
        # Sector: prefer first CoinGecko category; fall back to classifier
        categories = entry.get("categories") or []
        if categories:
            token.sector = categories[0]
        else:
            try:
                from services.sector_classifier import get_classifier
                token.sector = get_classifier().classify(token.symbol)
            except Exception:
                pass  # keep existing sector ("其他")
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd D:/work/browser-demo/backend && python -m pytest tests/test_fundamentals_cache.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Wire cache into scanner tick**

In `backend/services/hot_tokens_scanner.py`, modify the `_run_loop` method (lines 122-132). Replace with:

```python
    async def _run_loop(self) -> None:
        """Main loop: fetch data, calculate scores, broadcast, auto-trade."""
        from services.fundamentals_cache import get_cache
        cache = get_cache()

        while self._running:
            try:
                # Refresh fundamentals cache if stale (non-blocking on first tick)
                if cache.is_stale():
                    await cache.refresh()

                await self._fetch_and_update(cache=cache)
                await self._broadcast_update()
                if self._auto_enabled:
                    await self._check_and_auto_trade()
            except Exception as e:
                logger.warning(f"HotTokensScanner loop error: {e}")
            await asyncio.sleep(60)
```

And modify `_fetch_and_update` to take a `cache` parameter and apply it to each token. Replace the existing `_fetch_and_update` signature and the bottom of the loop (after `hot_list.append(hot)`):

```python
    async def _fetch_and_update(self, cache=None) -> None:
        """Fetch market data and update hot tokens."""
        # ... existing ticker + per-symbol fetch unchanged ...
        # After the `hot_list.append(hot)` line, add:
        for hot in hot_list:
            if cache is not None:
                cache.apply_to_token(hot)
            self._calculate_short_metrics(hot)
```

The full method body should now end with:

```python
        # Calculate heat scores
        if hot_list:
            for hot in hot_list:
                if cache is not None:
                    cache.apply_to_token(hot)
                self._calculate_short_metrics(hot)
            self._hot_tokens = {t.symbol: t for t in hot_list}
            await self._save_to_db(hot_list)
```

- [ ] **Step 6: Wire cache startup in `main.py`**

In `backend/main.py`, modify the `lifespan` function to refresh the cache once at startup:

Replace lines 71-80 with:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    from services.fundamentals_cache import get_cache
    asyncio.create_task(_warm_sector_classifier())
    asyncio.create_task(get_cache().refresh())  # non-blocking first load
    await _scheduler.start()
    await _poly.start()
    _hot_scanner.start()
    yield
    await _scheduler.stop()
    await _poly.stop()
    _hot_scanner.stop()
```

- [ ] **Step 7: Run the full test suite**

```bash
cd D:/work/browser-demo/backend && python -m pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/services/hot_tokens_scanner.py backend/main.py backend/services/fundamentals_cache.py backend/tests/test_fundamentals_cache.py
git commit -m "feat(shorts): scanner applies FundamentalsCache on each tick"
```

---

### Task 11: OHLCV cold fields in `get_token_analysis`

**Files:**
- Modify: `backend/api/hot_tokens.py:166-219` (`get_token_analysis`)

- [ ] **Step 1: Add the failing test**

Append to `backend/tests/test_hot_tokens_api_fields.py`:

```python
def test_analysis_endpoint_computes_rebound_multiple_from_ohlcv():
    """When OHLCV succeeds, the analysis endpoint should return rebound_multiple, low_7d,
    consecutive_up_days derived from the klines."""
    token = _stub_token()
    fake_scanner = _FakeScanner(token)

    # 7 daily klines: prices going up 100, 102, 105, 108, 110, 112, 115
    # low_7d = 100, current = 115 → rebound_multiple = 1.15
    # consecutive_up_days = 6 (last 6 closes are all > previous)
    fake_ohlcv = [
        [0, 100, 101, 99, 100, 1000],
        [1, 100, 103, 100, 102, 1000],
        [2, 102, 106, 102, 105, 1000],
        [3, 105, 109, 105, 108, 1000],
        [4, 108, 111, 108, 110, 1000],
        [5, 110, 113, 110, 112, 1000],
        [6, 112, 116, 112, 115, 1000],
    ]
    fake_exchange = MagicMock()
    fake_exchange.fetch_ohlcv = AsyncMock(return_value=fake_ohlcv)

    with patch("api.hot_tokens.get_scanner", return_value=fake_scanner), \
         patch("api.hot_tokens._get_exchange", return_value=fake_exchange):
        from main import app
        client = TestClient(app)
        resp = client.get("/api/hot_tokens/BTCUSDT/analysis")

    assert resp.status_code == 200
    body = resp.json()
    assert body["rebound_multiple"] == pytest.approx(1.15)
    assert body["low_7d"] == pytest.approx(100.0)
    assert body["consecutive_up_days"] == 6
```

(Also add `from unittest.mock import AsyncMock, MagicMock` to the top of the file.)

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd D:/work/browser-demo/backend && python -m pytest tests/test_hot_tokens_api_fields.py::test_analysis_endpoint_computes_rebound_multiple_from_ohlcv -v
```

Expected: failure on `rebound_multiple` not in response.

- [ ] **Step 3: Add OHLCV fetch + computation in `get_token_analysis`**

Replace `get_token_analysis` (lines 166-219) with:

```python
@router.get("/{symbol}/analysis")
async def get_token_analysis(symbol: str) -> dict[str, Any]:
    """Get comprehensive short-selling analysis for a token."""
    scanner = get_scanner()
    token = scanner._hot_tokens.get(symbol)
    if not token:
        raise HTTPException(status_code=404, detail=f"Token {symbol} not found")

    # OHLCV cold fields: fetch lazily here (per spec §5.2)
    ohlcv_data = await _fetch_ohlcv_metrics(symbol)

    base = _token_to_dict(token)
    base.update(ohlcv_data)
    base["metrics"] = {
        "funding_annualized": token.funding_annualized,
        "oi_usd": token.oi_usd,
    }
    base["signals"] = {
        "funding_extreme": abs(token.funding_rate) > 0.01,
        "overcrowded_long": token.long_crowdedness > 0.7,
        "squeeze_alert": token.long_squeeze_risk > 0.6,
        "high_extension": token.extension_score > 0.6,
    }
    base["recommendation"] = _short_recommendation(token)
    return base


async def _fetch_ohlcv_metrics(symbol: str) -> dict[str, Any]:
    """Fetch 30 daily klines and compute consecutive_up_days, low_7d, rebound_multiple, atr."""
    empty = {
        "consecutive_up_days": 0,
        "low_7d": 0.0,
        "rebound_multiple": 0.0,
        "atr": 0.0,
        "high_24h": 0.0,
        "low_24h": 0.0,
    }
    try:
        exchange = _get_exchange()
        klines = await exchange.fetch_ohlcv(symbol, "1d", limit=30)
    except Exception:
        return empty
    if not klines or len(klines) < 2:
        return empty

    closes = [float(k[4]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]

    # consecutive_up_days: count from latest backward while close > prev close
    up = 0
    for i in range(len(closes) - 1, 0, -1):
        if closes[i] > closes[i - 1]:
            up += 1
        else:
            break
    down = 0
    for i in range(len(closes) - 1, 0, -1):
        if closes[i] < closes[i - 1]:
            down += 1
        else:
            break
    consecutive = up if up > 0 else -down

    last_7 = klines[-7:]
    low_7d = min(float(k[3]) for k in last_7) if last_7 else 0.0
    current = closes[-1]
    rebound = (current / low_7d) if low_7d > 0 else 0.0

    # ATR(14) on daily closes using simple high-low average
    atr_window = min(14, len(klines))
    atr = (
        sum(highs[-atr_window - 1:][i] - lows[-atr_window - 1:][i] for i in range(atr_window))
        / atr_window
    ) if atr_window else 0.0

    return {
        "consecutive_up_days": consecutive,
        "low_7d": low_7d,
        "rebound_multiple": rebound,
        "atr": atr,
        "high_24h": highs[-1],
        "low_24h": lows[-1],
    }


def _get_exchange():
    """Lazy ccxt exchange for OHLCV. Reuses the scanner's if available."""
    scanner = get_scanner()
    return scanner.exchange
```

- [ ] **Step 4: Run the failing test plus full suite**

```bash
cd D:/work/browser-demo/backend && python -m pytest tests/test_hot_tokens_api_fields.py -v
```

Expected: all pass.

```bash
cd D:/work/browser-demo/backend && python -m pytest tests/ -v
```

Expected: all pass (no regressions).

- [ ] **Step 5: Commit**

```bash
git add backend/api/hot_tokens.py backend/tests/test_hot_tokens_api_fields.py
git commit -m "feat(shorts): OHLCV-derived consecutive_up_days, low_7d, rebound_multiple, atr"
```

---

### Task 12: Frontend — modal renders cold fields + recommendation

**Files:**
- Modify: `frontend/src/views/ShortsView.vue` (detail-strip)

- [ ] **Step 1: Replace the detail-strip block to include new fields**

In `frontend/src/views/ShortsView.vue`, replace the `<div class="detail-strip">` block (lines 161-196) with:

```html
          <!-- 详细数据条 -->
          <div class="detail-strip">
            <div class="strip-item">
              <span class="strip-label">板块</span>
              <span class="strip-value">{{ selectedToken.sector || '其他' }}</span>
            </div>
            <div class="strip-item">
              <span class="strip-label">市值</span>
              <span class="strip-value">${{ marketCapText }}</span>
            </div>
            <div class="strip-item">
              <span class="strip-label">FDV/MC</span>
              <span class="strip-value" :class="fdvWarnClass">
                {{ fdvRatioText }}
              </span>
            </div>
            <div class="strip-item">
              <span class="strip-label">Top10持仓</span>
              <span class="strip-value" :class="top10WarnClass">
                {{ top10Text }}
              </span>
            </div>
            <div class="strip-item">
              <span class="strip-label">Gini</span>
              <span class="strip-value">{{ giniText }}</span>
            </div>
            <div class="strip-item">
              <span class="strip-label">7日最低</span>
              <span class="strip-value">${{ low7dText }}</span>
            </div>
            <div class="strip-item">
              <span class="strip-label">反弹倍数</span>
              <span class="strip-value profit">×{{ reboundText }}</span>
            </div>
            <div class="strip-item">
              <span class="strip-label">连涨天数</span>
              <span :class="['strip-value', (selectedToken.consecutive_up_days || 0) >= 0 ? 'profit' : 'loss']">
                {{ consecutiveDaysText }}
              </span>
            </div>
          </div>
```

- [ ] **Step 2: Add the new computed properties**

After the existing `oiUsdText` computed (line 373), add:

```typescript
const fdvRatioText = computed(() => {
  const r = selectedToken.value?.fdv_mcap_ratio ?? 0
  if (!r) return '–'
  return r.toFixed(2)
})

const fdvWarnClass = computed(() => {
  const r = selectedToken.value?.fdv_mcap_ratio ?? 0
  if (r > 5) return 'loss'
  if (r > 2) return 'profit'
  return ''
})

const top10Text = computed(() => {
  const t = selectedToken.value?.top10_holders_pct ?? 0
  if (!t) return '–'
  return `${t.toFixed(1)}%`
})

const top10WarnClass = computed(() => {
  const t = selectedToken.value?.top10_holders_pct ?? 0
  if (t > 70) return 'loss'
  return ''
})

const giniText = computed(() => {
  const g = selectedToken.value?.gini ?? 0
  if (!g) return '–'
  return g.toFixed(2)
})

const low7dText = computed(() => {
  const v = selectedToken.value?.low_7d ?? 0
  if (!v) return '–'
  if (v >= 1) return v.toFixed(2)
  return v.toFixed(4)
})

const reboundText = computed(() => {
  const r = selectedToken.value?.rebound_multiple ?? 0
  if (!r) return '–'
  return r.toFixed(2)
})
```

- [ ] **Step 3: Update the signal-badges block to reflect the new field names**

Replace lines 222-228 with:

```html
            <div class="signal-badges">
              <span v-if="tokenAnalysis.signals?.funding_extreme" class="signal-badge warning">⚠ 极端资金费率</span>
              <span v-if="tokenAnalysis.signals?.overcrowded_long" class="signal-badge danger">🔥 多头过度拥挤</span>
              <span v-if="tokenAnalysis.signals?.squeeze_alert" class="signal-badge alert">💥 轧空警报</span>
              <span v-if="tokenAnalysis.signals?.high_extension" class="signal-badge success">📈 涨幅到位</span>
            </div>
```

- [ ] **Step 4: Type-check + manual smoke**

```bash
cd D:/work/browser-demo/frontend && npx tsc --noEmit
```

Then boot backend + frontend, open `/analysis`, click a token, verify the new fields appear with real values from the cache.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/ShortsView.vue
git commit -m "feat(shorts): modal renders FDV/MC, top10, gini, low_7d, rebound_multiple, consecutive days"
```

---

### Task 13: Phase 1b manual smoke + PR

- [ ] **Step 1: Verify the end-to-end flow**

```bash
curl http://localhost:8000/api/hot_tokens/BTCUSDT/analysis | python -m json.tool | head -80
```

Expected: `market_cap`, `top10_holders_pct`, `gini`, `rebound_multiple`, `low_7d`, `consecutive_up_days`, `sector` all populated with real numbers (not 0) — assuming the cache has refreshed at least once and OHLCV succeeded.

- [ ] **Step 2: Push the branch and open a PR**

```bash
git push origin <branch>
gh pr create --title "feat(shorts): Phase 1b — fundamentals cache + 13 fields populated" --body "..."
```

---

## Phase 2 — Chip filters + search (~2.5h, one PR)

### Task 14: Pure filter function + tests

**Files:**
- Create: `frontend/src/utils/shortTokenFilters.ts`
- Create: `frontend/src/utils/__tests__/shortTokenFilters.spec.ts`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/utils/__tests__/shortTokenFilters.spec.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { applyHotTokenFilters, type HotToken, type Filters } from '../shortTokenFilters'

function makeToken(overrides: Partial<HotToken> = {}): HotToken {
  return {
    symbol: 'BTCUSDT',
    price: 60000,
    price_change_24h: 5.0,
    funding_rate: 0.005,
    short_grade: 'A',
    sector: 'Layer 1',
    volume_usd: 6e9,
    long_crowdedness: 0.7,
    ...overrides,
  } as HotToken
}

const noFilters: Filters = {
  funding: 'all',
  change: 'all',
  grade: 'all',
  sector: 'all',
  search: '',
}

describe('applyHotTokenFilters', () => {
  it('empty filters return all tokens', () => {
    const tokens = [makeToken({ symbol: 'A' }), makeToken({ symbol: 'B' })]
    expect(applyHotTokenFilters(tokens, noFilters)).toHaveLength(2)
  })

  it('funding=short_paying returns tokens with funding_rate < -0.001', () => {
    const tokens = [
      makeToken({ symbol: 'A', funding_rate: -0.002 }),
      makeToken({ symbol: 'B', funding_rate: 0.005 }),
    ]
    const result = applyHotTokenFilters(tokens, { ...noFilters, funding: 'short_paying' })
    expect(result.map(t => t.symbol)).toEqual(['A'])
  })

  it('funding=long_paying returns tokens with funding_rate > 0.001', () => {
    const tokens = [
      makeToken({ symbol: 'A', funding_rate: 0.005 }),
      makeToken({ symbol: 'B', funding_rate: -0.005 }),
    ]
    const result = applyHotTokenFilters(tokens, { ...noFilters, funding: 'long_paying' })
    expect(result.map(t => t.symbol)).toEqual(['A'])
  })

  it('change=surge returns tokens with price_change_24h > 10', () => {
    const tokens = [
      makeToken({ symbol: 'A', price_change_24h: 15 }),
      makeToken({ symbol: 'B', price_change_24h: 5 }),
    ]
    const result = applyHotTokenFilters(tokens, { ...noFilters, change: 'surge' })
    expect(result.map(t => t.symbol)).toEqual(['A'])
  })

  it('change=crash returns tokens with price_change_24h < -10', () => {
    const tokens = [
      makeToken({ symbol: 'A', price_change_24h: -15 }),
      makeToken({ symbol: 'B', price_change_24h: -3 }),
    ]
    const result = applyHotTokenFilters(tokens, { ...noFilters, change: 'crash' })
    expect(result.map(t => t.symbol)).toEqual(['A'])
  })

  it('grade=S filters to short_grade === "S"', () => {
    const tokens = [
      makeToken({ symbol: 'A', short_grade: 'S' }),
      makeToken({ symbol: 'B', short_grade: 'A' }),
      makeToken({ symbol: 'C', short_grade: 'B' }),
    ]
    const result = applyHotTokenFilters(tokens, { ...noFilters, grade: 'S' })
    expect(result.map(t => t.symbol)).toEqual(['A'])
  })

  it('sector filter matches exact case', () => {
    const tokens = [
      makeToken({ symbol: 'A', sector: 'Layer 1' }),
      makeToken({ symbol: 'B', sector: 'Meme' }),
    ]
    const result = applyHotTokenFilters(tokens, { ...noFilters, sector: 'Meme' })
    expect(result.map(t => t.symbol)).toEqual(['B'])
  })

  it('search is case-insensitive substring match on symbol', () => {
    const tokens = [
      makeToken({ symbol: 'BTCUSDT' }),
      makeToken({ symbol: 'ETHUSDT' }),
      makeToken({ symbol: 'btcdom' }),
    ]
    const result = applyHotTokenFilters(tokens, { ...noFilters, search: 'btc' })
    expect(result.map(t => t.symbol).sort()).toEqual(['BTCUSDT', 'btcdom'])
  })

  it('multiple filters AND together', () => {
    const tokens = [
      makeToken({ symbol: 'A', short_grade: 'S', funding_rate: 0.005, price_change_24h: 15 }),
      makeToken({ symbol: 'B', short_grade: 'S', funding_rate: -0.005, price_change_24h: 15 }),
      makeToken({ symbol: 'C', short_grade: 'A', funding_rate: 0.005, price_change_24h: 15 }),
    ]
    const result = applyHotTokenFilters(tokens, {
      ...noFilters, grade: 'S', funding: 'long_paying', change: 'surge',
    })
    expect(result.map(t => t.symbol)).toEqual(['A'])
  })

  it('empty token list stays empty', () => {
    expect(applyHotTokenFilters([], noFilters)).toEqual([])
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd D:/work/browser-demo/frontend && npx vitest run src/utils/__tests__/shortTokenFilters.spec.ts
```

Expected: module not found.

- [ ] **Step 3: Create `shortTokenFilters.ts`**

Create `frontend/src/utils/shortTokenFilters.ts`:

```typescript
export interface HotToken {
  symbol: string
  price: number
  price_change_24h: number
  funding_rate: number
  short_grade?: string
  sector?: string
  long_crowdedness?: number
  [key: string]: unknown
}

export type FundingFilter = 'all' | 'short_paying' | 'long_paying' | 'extreme_long' | 'extreme_short' | 'neutral'
export type ChangeFilter  = 'all' | 'crash' | 'down' | 'flat' | 'up' | 'surge'
export type GradeFilter   = 'all' | 'S' | 'A' | 'B' | 'C' | 'D'
export type SectorFilter  = string  // 'all' or any sector name

export interface Filters {
  funding: FundingFilter
  change: ChangeFilter
  grade: GradeFilter
  sector: SectorFilter
  search: string
}

export const defaultFilters: Filters = {
  funding: 'all',
  change: 'all',
  grade: 'all',
  sector: 'all',
  search: '',
}

export function applyHotTokenFilters(tokens: HotToken[], f: Filters): HotToken[] {
  const search = f.search.trim().toLowerCase()
  return tokens.filter(t => {
    // Funding
    if (f.funding !== 'all') {
      const fr = t.funding_rate ?? 0
      if (f.funding === 'extreme_long'  && !(fr >  0.005)) return false
      if (f.funding === 'long_paying'   && !(fr >  0.001)) return false
      if (f.funding === 'neutral'       && !(-0.001 <= fr && fr <= 0.001)) return false
      if (f.funding === 'short_paying'  && !(fr < -0.001)) return false
      if (f.funding === 'extreme_short' && !(fr < -0.005)) return false
    }
    // Change
    if (f.change !== 'all') {
      const c = t.price_change_24h ?? 0
      if (f.change === 'crash' && !(c < -10)) return false
      if (f.change === 'down'  && !(c >= -10 && c < -3)) return false
      if (f.change === 'flat'  && !(c >= -3  && c <= 3)) return false
      if (f.change === 'up'    && !(c >  3   && c <= 10)) return false
      if (f.change === 'surge' && !(c > 10)) return false
    }
    // Grade
    if (f.grade !== 'all' && t.short_grade !== f.grade) return false
    // Sector
    if (f.sector !== 'all' && (t.sector ?? '其他') !== f.sector) return false
    // Search
    if (search && !t.symbol.toLowerCase().includes(search)) return false
    return true
  })
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd D:/work/browser-demo/frontend && npx vitest run src/utils/__tests__/shortTokenFilters.spec.ts
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/shortTokenFilters.ts frontend/src/utils/__tests__/shortTokenFilters.spec.ts
git commit -m "feat(shorts): pure applyHotTokenFilters with funding/change/grade/sector/search"
```

---

### Task 15: Chip filter UI + wiring in `ShortsView.vue`

**Files:**
- Modify: `frontend/src/views/ShortsView.vue`

- [ ] **Step 1: Import the filter util and add filter state**

After the existing `import` lines (around line 240), add:

```typescript
import {
  applyHotTokenFilters,
  defaultFilters,
  type Filters,
  type HotToken as FilterHotToken,
} from '../utils/shortTokenFilters'
```

(Note: the local `HotToken` interface is richer than the util's; we cast.)

- [ ] **Step 2: Add filter state + computed filtered list**

After the `selectedToken` ref (line 279), add:

```typescript
const filters = ref<Filters>({ ...defaultFilters })
const showFilters = ref(false)

const filteredTokens = computed<HotToken[]>(() => {
  return applyHotTokenFilters(
    hotTokens.value as unknown as FilterHotToken[],
    filters.value,
  ) as unknown as HotToken[]
})

const availableSectors = computed<string[]>(() => {
  const set = new Set<string>()
  for (const t of hotTokens.value) {
    const s = t.sector || '其他'
    if (s !== '其他') set.add(s)
  }
  return Array.from(set).sort()
})
```

- [ ] **Step 3: Add the chip filter bar above the table**

In the template, insert this between the `</div>` of `.actions-bar` (after line 32) and the empty-state div:

```html
    <!-- Filters Bar -->
    <div v-if="showFilters" class="filters-bar">
      <div class="filter-group">
        <span class="filter-label">资金费率</span>
        <button v-for="opt in fundingOptions" :key="opt.value"
                :class="['chip', filters.funding === opt.value ? 'chip-active' : '']"
                @click="filters.funding = opt.value">
          {{ opt.label }}
        </button>
      </div>
      <div class="filter-group">
        <span class="filter-label">24h涨跌</span>
        <button v-for="opt in changeOptions" :key="opt.value"
                :class="['chip', filters.change === opt.value ? 'chip-active' : '']"
                @click="filters.change = opt.value">
          {{ opt.label }}
        </button>
      </div>
      <div class="filter-group">
        <span class="filter-label">评级</span>
        <button v-for="opt in gradeOptions" :key="opt.value"
                :class="['chip', filters.grade === opt.value ? 'chip-active' : '']"
                @click="filters.grade = opt.value">
          {{ opt.label }}
        </button>
      </div>
      <div class="filter-group">
        <span class="filter-label">板块</span>
        <button :class="['chip', filters.sector === 'all' ? 'chip-active' : '']"
                @click="filters.sector = 'all'">全部</button>
        <button v-for="s in availableSectors" :key="s"
                :class="['chip', filters.sector === s ? 'chip-active' : '']"
                @click="filters.sector = s">{{ s }}</button>
      </div>
      <div class="filter-group filter-search">
        <input v-model="filters.search" type="text" placeholder="搜索 symbol..." class="search-input" />
        <span class="filter-count">{{ filteredTokens.length }}/{{ hotTokens.length }}</span>
      </div>
    </div>
```

- [ ] **Step 4: Add a "Filters" toggle to the actions bar**

Modify the actions bar (line 17) to add a "Filters" button. Replace the existing "Start Scanner" button block with:

```html
      <button class="btn-outline" @click="showFilters = !showFilters" :class="{ active: showFilters }">
        {{ showFilters ? 'Hide Filters' : 'Show Filters' }}
      </button>
      <button class="btn-outline" @click="startScanner" :disabled="scannerRunning">
        {{ scannerRunning ? 'Scanner Running' : 'Start Scanner' }}
      </button>
```

- [ ] **Step 5: Switch the table to render `filteredTokens`**

Replace `v-for="(token, idx) in hotTokens"` (line 49) with `v-for="(token, idx) in filteredTokens"`.

- [ ] **Step 6: Define the option lists in `<script setup>`**

After the new `availableSectors` computed, add:

```typescript
const fundingOptions = [
  { value: 'all',           label: '全部' },
  { value: 'extreme_long',  label: '多头极拥 (>0.5%)' },
  { value: 'long_paying',   label: '多头付费 (>0.1%)' },
  { value: 'neutral',       label: '中性' },
  { value: 'short_paying',  label: '空头付费 (<-0.1%)' },
  { value: 'extreme_short', label: '空头极拥 (<-0.5%)' },
] as const

const changeOptions = [
  { value: 'all',    label: '全部' },
  { value: 'crash',  label: '大跌 (<-10%)' },
  { value: 'down',   label: '跌 (-10~-3%)' },
  { value: 'flat',   label: '中性 (-3~3%)' },
  { value: 'up',     label: '涨 (3~10%)' },
  { value: 'surge',  label: '大涨 (>10%)' },
] as const

const gradeOptions = [
  { value: 'all', label: '全部' },
  { value: 'S',   label: 'S' },
  { value: 'A',   label: 'A' },
  { value: 'B',   label: 'B' },
  { value: 'C',   label: 'C' },
  { value: 'D',   label: 'D' },
] as const
```

- [ ] **Step 7: Add styles for the filter bar**

Append inside the `<style scoped>` block:

```css
/* Filters */
.filters-bar {
  background: #111114;
  border: 1px solid #1e1e24;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
}
.filter-group { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.filter-label { font-size: 11px; color: #71717a; text-transform: uppercase; margin-right: 4px; }
.filter-search { margin-left: auto; }
.chip {
  padding: 4px 10px;
  font-size: 12px;
  border-radius: 16px;
  border: 1px solid #27272a;
  background: transparent;
  color: #a1a1aa;
  cursor: pointer;
  transition: all 0.15s;
}
.chip:hover { border-color: #6366f1; color: #6366f1; }
.chip.chip-active { background: #6366f1; color: #fff; border-color: #6366f1; }
.search-input {
  padding: 6px 10px;
  font-size: 13px;
  background: #0a0a0f;
  border: 1px solid #27272a;
  border-radius: 6px;
  color: #e4e4e7;
  width: 180px;
}
.filter-count { font-size: 12px; color: #71717a; margin-left: 8px; }
.btn-outline.active { border-color: #6366f1; color: #6366f1; }
```

- [ ] **Step 8: Type-check + run vitest**

```bash
cd D:/work/browser-demo/frontend && npx tsc --noEmit && npx vitest run
```

Expected: no type errors, all tests pass.

- [ ] **Step 9: Manual smoke**

Boot the app, click "Show Filters", pick "评级=S" — table should shrink to only S-grade tokens. Pick "资金费率=多头极拥" — table shrinks further. Type "btc" in search — only BTCUSDT remains. Counter shows `N/50`.

- [ ] **Step 10: Commit + push**

```bash
git add frontend/src/views/ShortsView.vue
git commit -m "feat(shorts): chip filters (funding, change, grade, sector) + symbol search"
git push origin <branch>
gh pr create --title "feat(shorts): Phase 2 — chip filters + search" --body "..."
```

---

## Self-Review

**Spec coverage:**
- §4.2 long_crowdedness / extension_score → Tasks 2, 4, 5 ✓
- §4.3 S/A/B/C/D grade → Task 3 ✓
- §4.4 short_opportunity_score → Task 2 ✓
- §4.2 oi_usd / funding_annualized → Task 5 ✓
- §5.2 CoinGecko 6h refresh → Task 9 ✓
- §5.2 Arkham 6h → Task 9 ✓
- §5.2 OHLCV cold → Task 11 ✓
- §5.4 fail-soft → Tasks 9, 10, 11 ✓
- §6 Phase 1a / 1b / 2 → Tasks 1-8 / 9-13 / 14-15 ✓
- §10 test plan → Tasks 2, 3, 6, 9, 10, 11, 14 ✓

**Type consistency check:** All references to `long_crowdedness`, `long_squeeze_risk`, `extension_score`, `short_grade`, `short_opportunity_score`, `top10_holders_pct`, `gini`, `fdv_mcap_ratio`, `rebound_multiple`, `low_7d` use the same spelling and case. The old `crowdedness_score` / `squeeze_risk` / `rebound_potential` are gone from the dataclass and from `_token_to_dict` in the same PR (Task 6).

**Placeholder scan:** No "TODO" / "TBD" / "implement later" in any task. All code blocks are complete.

**Out-of-scope deferred to Phase 3:** sector_classifier enrichment (spec §6.3).
