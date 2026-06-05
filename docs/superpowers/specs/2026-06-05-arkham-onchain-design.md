# Arkham On-Chain & Prediction Integration — Design

**Date:** 2026-06-05
**Status:** Draft (awaiting user review)
**Source-of-truth for endpoints:** [Vyntral/arkham-intelligence-claude-skill — `ARKHAM_API_DOCUMENTATION.md`](https://github.com/Vyntral/arkham-intelligence-claude-skill/blob/main/ARKHAM_API_DOCUMENTATION.md) (1.0.4, base URL `https://api.arkm.com`)

---

## 1. Context

`ShortSellingEngine._fetch_onchain()` already imports `get_exchange_netflow` and `get_whale_movements` from `datasources/arkham.py`, but that module is **broken**:

| Bug | Existing code | Real Arkham API |
|---|---|---|
| Base URL | `https://api.arkhamintelligence.com/v1` | `https://api.arkm.com` |
| Auth header | `Authorization: Bearer {key}` | `API-Key: {key}` |
| `get_exchange_netflow` calls `/exchanges/flows?token=…` | not a real endpoint | use `/token/top?orderByAgg=netflow` |
| `get_whale_movements` calls `/wallets/transfers?token=…` | wrong path | use `/transfers?tokens=…` |

The API key is also only read from `os.getenv("ARKHAM_API_KEY")` — there is no UI to set it.

This change:
1. Fixes the 2 broken functions (correct base URL, auth, and endpoints)
2. Adds 4 new on-chain capabilities selected by the user: holder concentration, smart money flow, exchange reserves, whale portfolio change
3. Adds 1 bonus function for Arkham's ML entity predictions (the "预测" the user asked about)
4. Wires the API key through `config_store` and the Settings UI

---

## 2. Goals & Non-Goals

**Goals**
- All 5 on-chain functions return real Arkham data (or `{"error": "..."}` on failure)
- Settings UI exposes a masked `arkham_api_key` field; saved value persists in `config.json`
- Existing `ShortSellingEngine` calls keep working (signature unchanged for the 2 original functions)
- 4 new optional dimensions are available via `dimensions=["holder_concentration", …]`
- All endpoints validated against the 1.0.4 docs before merging

**Non-goals (Phase 2)**
- Background refresh / caching of on-chain data (queries stay on-demand)
- Historical backfill of entity_predictions (use it as a one-shot lookup)
- Symbol resolution beyond a hardcoded SYMBOL→CoinGecko-ID map (~50 majors)
- Frontend unit tests for the new Settings card (no headless spec pattern in repo)

---

## 3. Architecture

### 3.1 Files modified

**Production code (5 modified, 0 new):**

```
backend/services/datasources/arkham.py    ← rewrite: base URL, auth, 2 existing fns, 5 new fns
backend/services/config_store.py          ← add arkham_api_key to DEFAULT_CONFIG + masked + allowlist
backend/services/short_selling_engine.py  ← extend dimension_map with 3 new keys
backend/services/datasources/coingecko.py ← export SYMBOL_TO_CG_ID map (already inline in token_analyzer)
frontend/src/types/index.ts               ← add arkham_api_key_masked: string
frontend/src/views/SettingsView.vue       ← add "On-chain / Arkham" card
```

**Tests (1 modified, 1 new):**

```
backend/tests/datasources/test_arkham.py       ← expand from 1 test to 8
backend/tests/test_config_store.py             ← NEW: 2 tests
backend/tests/test_short_selling_engine.py     ← add 1 test for dimension_map
```

No new dependencies (httpx, tenacity, asyncio, respx already in use).

### 3.2 Data flow

```
Settings UI (password input)
   ↓ PUT /api/config { arkham_api_key: "..." }
config_store.update_config()                 ← writes backend/config.json
   ↓
On next ShortSellingEngine call:
   ↓
datasources/arkham.py:_get_api_key()
   ↓ 1. config_store.get_config()["arkham_api_key"]
   ↓ 2. fallback: os.getenv("ARKHAM_API_KEY")
   ↓
get_holder_concentration("ETH")  →  GET /token/holders/ethereum?groupByEntity=true
                                     →  {"top_10_pct": 42.1, "gini": 0.73, "holder_count": 50}
   ↓
ShortSellingEngine._fetch_onchain() aggregates into the LLM prompt
   ↓
LLM sees the metrics → produces short-selling recommendation
```

### 3.3 Error handling policy

Every function returns `dict` — never raises. Patterns:

| Failure | Return value | LLM impact |
|---|---|---|
| `arkham_api_key` empty | `{"error": "ARKHAM_API_KEY not configured"}` | dimension shown as unavailable |
| HTTP 401 / 403 | `{"error": "Invalid API key"}` | same |
| HTTP 404 | `{"error": "Not found", "data_source": "arkham"}` | same |
| HTTP 5xx / network | `{"error": str(exc), "data_source": "arkham"}` | same |
| HTTP 200 unexpected shape | `{"data_source": "arkham", "note": "unexpected response shape"}` | same |

`ShortSellingEngine.analyze()` already wraps each dimension in `try/except` and renders errors as `{"error": str}` in the dimension dict — the LLM prompt compact step (`_compact_dimensions`) keeps the field. No new error plumbing needed.

### 3.4 Symbol → CoinGecko pricing ID

Arkham's `/token/holders/{pricing_id}` and `/token/top?tokenIds=…` use CoinGecko pricing IDs (e.g. `bitcoin`, `ethereum`, `usd-coin`), not Binance USDT-margined symbols.

We add a small constant map in `datasources/arkham.py`:

```python
SYMBOL_TO_CG_ID = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binancecoin",
    "XRP": "ripple", "ADA": "cardano", "DOGE": "dogecoin", "AVAX": "avalanche-2",
    "MATIC": "matic-network", "DOT": "polkadot", "LINK": "chainlink",
    "TON": "the-open-network", "TRX": "tron", "LTC": "litecoin",
    "BCH": "bitcoin-cash", "NEAR": "near", "ATOM": "cosmos", "UNI": "uniswap",
    "APT": "aptos", "ARB": "arbitrum", "OP": "optimism", "INJ": "injective-protocol",
    "SUI": "sui", "SEI": "sei-network", "TIA": "celestia", "WLD": "worldcoin-wld",
    "PEPE": "pepe", "WIF": "dogwifcoin", "BONK": "bonk", "FLOKI": "floki",
    "SHIB": "shiba-inu", "JUP": "jupiter-exchange-solana",
    # Stablecoins
    "USDT": "tether", "USDC": "usd-coin", "DAI": "dai", "FDUSD": "first-digital-usd",
}
# Fallback: assume "ethereum" chain (most ERC-20s) and pass the symbol lowercased —
# Arkham will 404 and the function returns {"error": "Not found"} which is handled.
```

The same map can be extracted from `token_analyzer.py:_coingecko_fallback` (currently inline) to avoid duplication — but that's a refactor; **out of scope here**. Copy for now, leave a `TODO` for the extraction.

---

## 4. Function design (7 total in `datasources/arkham.py`)

| # | Function | Endpoint | Returns |
|---|---|---|---|
| 1 | `get_exchange_netflow(token)` | `GET /token/top?tokenIds={cg_id}&orderByAgg=netflow&timeframe=24h&from=0&size=1` | `{"cex_netflow_24h": float, "data_source": "arkham"}` |
| 2 | `get_whale_movements(token, min_value_usd=1e6)` | `GET /transfers?tokens={cg_id}&timeLast=24h&usdGte={min}&limit=10` | `{"whale_movements": [{from,to,amount_usd,timestamp},…], "data_source": "arkham"}` |
| 3 | `get_holder_concentration(token, top_n=20)` | `GET /token/holders/{cg_id}?groupByEntity=true` | `{"top_10_pct": float, "top_n_pct": float, "gini": float, "holder_count": int, "data_source": "arkham"}` |
| 4 | `get_smart_money_flow(token, days=7)` | parallel `GET /flow/entity/{e}` for 5 known SM entities, sum | `{"smart_money_netflow": float, "by_entity": {e: float}, "data_source": "arkham"}` |
| 5 | `get_exchange_reserves(token)` | parallel `GET /balances/entity/{e}` for 8 exchange entities, sum token balances | `{"exchange_reserves_usd": float, "by_exchange": {e: float}, "data_source": "arkham"}` |
| 6 | `get_whale_portfolio_change(token)` | first `GET /token/holders/{cg_id}` for top 3, then parallel `GET /portfolio/address/{a}?time={ts_now_ms}` and `?time={ts_90d_ago_ms}`, diff per address | `{"top_holders_change": [{address, delta_usd_90d}], "data_source": "arkham"}` |
| 7 | `get_entity_predictions(entity)` | `GET /intelligence/entity_predictions/{entity}` | `{"predictions": [{address, usdBalance}], "data_source": "arkham"}` |

### 4.1 Hardcoded entity lists (with rationale)

```python
SMART_MONEY_ENTITIES = [
    "jump-trading", "wintermute", "cumberland", "galaxy-digital",
    "alameda-research",  # historical reference, still tracked
]
EXCHANGE_ENTITIES = [
    "binance", "coinbase", "kraken", "okx", "bybit", "bitfinex", "htx", "kucoin",
]
```

If Arkham returns 404 for any entity slug, the aggregator skips it and proceeds with the rest. **No runtime entity list discovery** (the `/intelligence/entity_predictions` endpoint is a *unidirectional* one — there's no `/entities` list).

### 4.2 Gini calculation (in `get_holder_concentration`)

Standard formula, computed from `holders.{chain}[].balance`:

```python
def _gini(values: list[float]) -> float:
    if not values or sum(values) == 0:
        return 0.0
    sorted_v = sorted(values)
    n = len(sorted_v)
    cum = sum((i + 1) * v for i, v in enumerate(sorted_v))
    return (2 * cum) / (n * sum(sorted_v)) - (n + 1) / n
```

Returns 0 (perfectly equal) to 1 (one holder owns everything). 0.7+ = concerning concentration.

### 4.3 Async + parallel calls

`get_smart_money_flow`, `get_exchange_reserves`, and `get_whale_portfolio_change` all fan out N+1 async calls. Use `asyncio.gather(…, return_exceptions=True)` and treat exceptions as `{entity: 0.0}` so one bad entity doesn't kill the aggregate.

Standard 10s timeout per request, 3 retries with exponential backoff (`tenacity` decorator, matching existing pattern).

---

## 5. Config store changes

`backend/services/config_store.py`:

```python
DEFAULT_CONFIG = {
    ...
    "arkham_api_key": "",   # NEW
    ...
}

def get_masked_config() -> dict:
    return {
        ...
        "arkham_api_key_masked": mask_key(config.get("arkham_api_key", "")),  # NEW
        ...
    }

def update_config(data: dict) -> dict:
    ...
    # Extend the allowlist prefix tuple to include "arkham_"
    if key in config or key.startswith((..., "arkham_")):  # NEW
        config[key] = data[key]
```

`mask_key()` already exists and matches the binance behavior (`****` + last 4 chars).

---

## 6. ShortSellingEngine integration

Extend `dimension_map` with 3 new keys (the existing 5 stay — 8 total). Note: `get_whale_portfolio_change` and `get_entity_predictions` are implemented in `datasources/arkham.py` but are **not** wired as `analyze()` dimensions in v1 (see rationale at end of section).

```python
self.dimension_map = {
    "derivatives":         self._fetch_derivatives,
    "onchain":             self._fetch_onchain,            # 2 calls (existing)
    "holder_concentration": self._fetch_holder_concentration,  # NEW
    "smart_money":         self._fetch_smart_money,        # NEW
    "exchange_reserves":   self._fetch_exchange_reserves,  # NEW
    "unlock":              self._fetch_unlock,
    "technical":           self._fetch_technical,
    "sentiment":           self._fetch_sentiment,
}
```

New methods (1 line each, thin wrappers over the datasources):

```python
async def _fetch_holder_concentration(self, symbol):
    return await get_holder_concentration(symbol)

async def _fetch_smart_money(self, symbol):
    return await get_smart_money_flow(symbol)

async def _fetch_exchange_reserves(self, symbol):
    return await get_exchange_reserves(symbol)
```

Default `dimensions` list stays at `["derivatives", "onchain", "technical"]` — users opt in to the new ones by passing them in the request.

`get_whale_portfolio_change` is **not** added as a dimension key in v1 (it needs an address, not a symbol). The onchain aggregator can call it inline if the user explicitly asks for "whale portfolio change" in their query (Layer-3 LLM plan can route to it) — that wiring is a Phase 2 follow-up.

---

## 7. Settings UI

`frontend/src/views/SettingsView.vue` — new card after "Trading Configuration":

```vue
<section class="card" style="margin-top: 20px;">
  <h3>On-chain / Arkham Configuration</h3>
  <p class="desc">
    Configure Arkham Intelligence API for on-chain analytics: token holder
    concentration, smart money flow, exchange reserves, whale portfolio change.
  </p>
  <div class="form-row">
    <label>API Key</label>
    <input v-model="arkhamApiKey" type="password" placeholder="Arkham API key" />
    <span v-if="config?.arkham_api_key_masked" class="badge ok">OK</span>
    <span v-else class="badge no">--</span>
  </div>
  <div class="form-actions">
    <button class="btn-primary" @click="saveArkham">Save</button>
    <span v-if="arkhamSaveResult === true" class="valid-text ok">Saved</span>
    <span v-if="arkhamSaveResult === false" class="valid-text err">Save failed</span>
  </div>
</section>
```

Plus a new `saveArkham()` method (mirrors `saveBrowser()`) and a `arkhamApiKey` ref that clears on save (same pattern as binance).

Add `arkham_api_key_masked: string` to `frontend/src/types/index.ts`.

---

## 8. Test plan

| File | Test | Covers |
|---|---|---|
| `tests/datasources/test_arkham.py` | `test_get_exchange_netflow_no_key` | returns `{"error": "not configured"}` when key empty |
| | `test_get_exchange_netflow_happy_path` (httpx_mock) | returns `{"cex_netflow_24h": …}` |
| | `test_get_whale_movements_no_key` | error case |
| | `test_get_holder_concentration_gini_calc` | unit test on the `_gini` helper with known input |
| | `test_get_holder_concentration_no_key` | error case |
| | `test_get_smart_money_flow_aggregates` | mocks 5 entity responses, verifies sum |
| | `test_get_exchange_reserves_aggregates` | mocks 8 entity responses, verifies sum + skips 404 |
| | `test_get_entity_predictions_no_key` | error case |
| `tests/test_config_store.py` **(new)** | `test_arkham_key_round_trip` | save + reload preserves value |
| | `test_arkham_key_mask` | `mask_key("abcd1234")` → `"****1234"` |
| `tests/test_short_selling_engine.py` | `test_dimension_map_has_8_keys` | assert all expected keys present |

httpx mock pattern: use `respx` (already a dev dep) to stub the arkm.com requests. For the existing single test (`test_get_exchange_netflow_returns_dict`), expand it into the 8 new tests above.

---

## 9. Out of scope (Phase 2)

- **Whale portfolio change** as a first-class dimension (needs address, not symbol)
- **Background refresh / caching** of on-chain data
- **Configurable smart-money / exchange entity lists** in the UI
- **Auto-detection of "smart money" entities** via `/intelligence/entity_predictions` (could later be a background job that grows the list)
- **Extracting SYMBOL_TO_CG_ID** out of `token_analyzer._coingecko_fallback` into a shared module
- **Frontend tests** for the new Settings card

---

## 10. Migration / risk

- **Existing callers of `get_exchange_netflow` and `get_whale_movements`**: only `ShortSellingEngine._fetch_onchain()`. The return shape changes for `get_exchange_netflow` (`exchange_netflow_24h` → `cex_netflow_24h`) — update the 1 call site in `_fetch_onchain`. `get_whale_movements` return shape stays identical.
- **No DB migration**, no breaking API changes (the `/api/analyze/short` endpoint signature is unchanged).
- **Backwards-compat**: if `arkham_api_key` is empty, all 7 functions return `{"error": "not configured"}` — engine behavior identical to current (errors are caught and surfaced in the LLM prompt).

---

## 11. Implementation order (5 PRs, can be done in 1 if small)

1. **Config plumbing** — `config_store.py` + `AppConfig` type + `SettingsView.vue` card. Lets user paste the key; nothing uses it yet.
2. **Fix existing 2 functions** — `arkham.py` rewrite: base URL, auth, `get_exchange_netflow`, `get_whale_movements`. Add SYMBOL_TO_CG_ID + `_gini`. Update `ShortSellingEngine._fetch_onchain` to read new key. Tests for #2.
3. **Holder concentration** — `get_holder_concentration` + dimension wrapper + test.
4. **Smart money + exchange reserves** — both fan out to N entities, share the aggregator pattern. One test file, two implementations.
5. **Entity predictions** — `get_entity_predictions` (the "预测" piece). Smallest scope, done last.

Each step is independently mergeable. Steps 2–5 can collapse into a single PR if all stay under ~300 lines.
