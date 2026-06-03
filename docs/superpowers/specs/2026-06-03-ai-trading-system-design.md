# AI Trading System - Design Document

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Frontend (Vue 3)                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ Signal Feed  │  │  Positions   │  │   Settings   │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │
│  │ /api/signals│  │ /api/trades │  │ /api/config │  │   /ws    │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └──────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌────────────────┐  ┌────────────────┐  ┌────────────────┐
│ Signal Scraper │  │ Signal Analyzer│  │ Trading Engine │
│ (browser-use)  │  │    (LLM)       │  │ (Binance API) │
└────────────────┘  └────────────────┘  └────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌────────────────┐  ┌────────────────┐  ┌────────────────┐
│   CoinGecko    │  │      OKX       │  │  Hyperliquid │
└────────────────┘  └────────────────┘  └────────────────┘
                              │
                              ▼
          ┌───────────────────────────────────────┐
          │   Short-Selling Analytics Engine      │
          │   (做空分析引擎，独立服务)             │
          └───────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌────────────────┐  ┌────────────────┐  ┌────────────────┐
│  Arkham/Whale  │  │    CoinGecko   │  │ Binance Klines │
│   Alert        │  │  (Extended)    │  │   + pandas-ta  │
└────────────────┘  └────────────────┘  └────────────────┘
```

## Data Flow

### 1. Signal Discovery (Cron: every 5 min)
```
Cron Trigger
    │
    ▼
browser-use → Binance Square
    │
    ▼
Extract posts (title, content, likes, comments, author)
    │
    ▼
Filter posts with token mentions ($XXX, #XXX)
    │
    ▼
Store in Signal Queue
```

### 2. Signal Analysis (Async)
```
Signal Queue
    │
    ▼
LLM Analysis (MiniMax-M2.7)
    │
    ├─→ Extract token symbols
    ├─→ Sentiment analysis (bullish/bearish/neutral)
    ├─→ Confidence score (0-1)
    └─→ Reasoning summary
    │
    ▼
Enriched Signal
```

### 3. Market Validation & Short-Selling Analysis

```
Enriched Signal ──or── User Query "分析 BTC 做空"
    │
    ▼
┌──────────────────────────────────────────────────┐
│  Short-Selling Analytics Engine                   │
│  (replaces simple filtering with deep analysis) │
└──────────────────────────────────────────────────┘
    │
    ├── Parallel Data Fetch:
    │   ├─→ Derivatives: Binance Futures
    │   │     (price, funding rate, OI, long/short ratio, liquidations)
    │   ├─→ On-Chain: Arkham Intelligence / Whale Alert
    │   │     (exchange netflow, whale movements, market depth)
    │   ├─→ Unlock Data: CoinGecko / TokenUnlocks
    │   │     (vesting schedule, FDV vs market cap)
    │   ├─→ Technical: Binance Klines + pandas-ta
    │   │     (RSI, divergence, support/resistance)
    │   └─→ Social: Twitter / LunarCrush
    │         (sentiment, keyword monitoring)
    │
    ├── LLM Analysis Pipeline:
    │   ├─→ Layer 2: Predefined functions (single token, single dimension)
    │   │     → Direct API call → immediate result
    │   └─→ Layer 3: Dynamic planning (multi-token, cross-dimension)
    │         → LLM generates data-fetch code → exec → analysis
    │
    ▼
Valid / Invalid Signal  or  Structured Analysis Report
```

### 4. Trade Execution
```
Valid Signal
    │
    ▼
Risk Management
    ├─→ Position sizing (based on balance %)
    ├─→ Max positions check
    └─→ Daily loss limit check
    │
    ▼
Binance API
    ├─→ Place market order (Spot or Futures)
    └─→ Set TP/SL orders
    │
    ▼
Trade Record → Database → WebSocket → Frontend
```

## Database Schema (SQLite)

```sql
-- Signals discovered from Binance Square
CREATE TABLE signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,              -- 'binance_square'
    source_url TEXT,
    author TEXT,
    content TEXT NOT NULL,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    raw_data TEXT,                    -- JSON of original post
    status TEXT DEFAULT 'pending',    -- pending/analyzed/valid/invalid/executed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- LLM Analysis results
CREATE TABLE signal_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL,
    token TEXT NOT NULL,
    sentiment TEXT,                  -- bullish/bearish/neutral
    confidence REAL,                   -- 0.0 - 1.0
    reasoning TEXT,
    llm_model TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (signal_id) REFERENCES signals(id)
);

-- Market data validation
CREATE TABLE signal_validation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL,
    token TEXT NOT NULL,
    cg_market_cap_rank INTEGER,
    cg_price_change_24h REAL,
    okx_funding_rate REAL,
    hyperliquid_funding REAL,
    validation_result TEXT,            -- pass/fail
    fail_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (signal_id) REFERENCES signals(id)
);

-- Trade execution records
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,
    token TEXT NOT NULL,
    side TEXT NOT NULL,                -- buy/sell
    exchange TEXT DEFAULT 'binance',
    market_type TEXT,                  -- spot/futures
    order_id TEXT,
    quantity REAL,
    price REAL,
    tp_price REAL,
    sl_price REAL,
    status TEXT DEFAULT 'pending',     -- pending/filled/cancelled/error
    pnl REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (signal_id) REFERENCES signals(id)
);

-- Trading configuration
CREATE TABLE trading_config (
    id INTEGER PRIMARY KEY,
    binance_api_key TEXT,
    binance_secret_key TEXT,
    use_testnet INTEGER DEFAULT 1,     -- 1 = testnet, 0 = production
    max_position_size_usd REAL DEFAULT 100.0,
    max_positions INTEGER DEFAULT 5,
    tp_percentage REAL DEFAULT 5.0,    -- 5% take profit
    sl_percentage REAL DEFAULT 3.0,    -- 3% stop loss
    min_confidence REAL DEFAULT 0.7,   -- minimum LLM confidence
    max_daily_loss REAL DEFAULT 100.0, -- max daily loss in USD
    scan_interval_minutes INTEGER DEFAULT 5
);

-- Short-selling analysis reports (NEW)
CREATE TABLE analysis_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    dimensions TEXT,                   -- JSON array ["derivatives", "onchain", ...]
    timeframe TEXT DEFAULT '24h',
    request_type TEXT DEFAULT 'single', -- single | compare | event
    raw_data TEXT,                     -- JSON of all fetched metrics
    llm_summary TEXT,
    strengths TEXT,                    -- JSON array
    risks TEXT,                        -- JSON array
    confidence REAL,
    recommendation TEXT,               -- strong_short | weak_short | neutral | weak_long | strong_long
    time_horizon TEXT,                 -- short_term | medium_term | long_term
    version INTEGER DEFAULT 1,         -- analysis versioning
    status TEXT DEFAULT 'completed',   -- pending | completed | failed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Analysis metrics per dimension (NEW)
CREATE TABLE analysis_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL,
    dimension TEXT NOT NULL,           -- derivatives | onchain | unlock | technical | sentiment
    metric_name TEXT NOT NULL,         -- price | funding_rate | netflow | rsi | ...
    metric_value REAL,
    metric_unit TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (report_id) REFERENCES analysis_reports(id)
);

-- Token memories (long-term) (NEW)
CREATE TABLE token_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL UNIQUE,
    first_queried TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_queried TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_interests TEXT,               -- JSON array
    key_levels TEXT,                   -- JSON {"support": [...], "resistance": [...]}
    related_sectors TEXT,              -- JSON array
    notes TEXT,
    analysis_history TEXT              -- JSON array of report_ids
);
```

## API Design

### Signals
- `GET /api/signals` - List all signals with filters
- `GET /api/signals/{id}` - Get single signal with analysis
- `POST /api/signals/{id}/validate` - Manually trigger validation

### Trading
- `POST /api/trades` - Execute manual trade
- `GET /api/trades` - List trade history
- `GET /api/positions` - Current positions
- `POST /api/positions/{id}/close` - Close position

### Configuration
- `GET /api/trading/config` - Get trading configuration
- `PUT /api/trading/config` - Update configuration
- `POST /api/trading/config/test-connection` - Test Binance API

### WebSocket Events
- `signal:new` - New signal discovered
- `signal:analyzed` - Signal analyzed by LLM
- `trade:executed` - Trade executed
- `trade:closed` - Position closed
- **`analysis:short` - Short-selling analysis complete**

## Key Implementation Notes

### Binance Square Scraping
- Use browser-use with stealth mode to avoid detection
- Handle login if required (cookies/session)
- Extract: post content, likes, comments, author, timestamp
- Filter for token mentions using regex: `\$[A-Z]{2,10}` and `#?[A-Z]{2,10}`

### LLM Analysis Prompt
```
Analyze the following social media post about cryptocurrency trading.
Extract the following:
1. Token symbols mentioned (e.g., BTC, ETH, SOL)
2. Sentiment: bullish, bearish, or neutral
3. Confidence score (0.0 - 1.0)
4. Key reasoning points

Post: {content}

Respond in JSON format:
{
    "tokens": ["SOL", "ETH"],
    "sentiment": "bullish",
    "confidence": 0.85,
    "reasoning": "Post mentions..."
}
```

### Filtering Rules (Configurable)
- Token must have market cap rank < 500 (avoid super low-cap)
- 24h price change must be between -30% and +50% (avoid suspicious pumps)
- Funding rate must be < 0.05% (avoid overcrowded longs)
- LLM confidence must be > 0.7

### Risk Management
- Position size = min(balance * 0.02, max_position_size_usd)
- Max 5 concurrent positions
- Daily loss limit enforced
- Auto-cancel conflicting orders

---

## Short-Selling Analytics Engine (Deep Dive)

### 5-Layer Data Pipeline

做空决策不是单一 API 调用，而是**多维度数据的聚合分析**。引擎按以下 5 层组织：

| 层级 | 数据维度 | 已有数据源 | 缺失数据源 | 优先级 |
|------|---------|-----------|-----------|--------|
| L1 | 衍生品市场 | Binance Futures | 清算热力图、历史资金费率 | P0 |
| L2 | 链上流动性 | — | Arkham Intelligence, Whale Alert | P1 |
| L3 | 代币解锁/通胀 | CoinGecko (部分) | TokenUnlocks | P2 |
| L4 | 技术面指标 | — | Binance Klines + pandas-ta | P3 |
| L5 | 社交情绪 | — | Twitter API / LunarCrush | P4 |

### Intent Routing (Layer 2 vs Layer 3)

用户查询进入做空分析引擎时，**不是统一走 LLM 规划**，而是先匹配意图：

```
用户查询
    │
    ├── Layer 2: 固定流程（关键词匹配）
    │   ├── "BTC 价格" → 直接调用 Binance API
    │   ├── "BTC 资金费率" → 直接调用 Binance Funding Rate
    │   └── "分析 BTC 做空" → 调用预定义的做空分析 pipeline
    │       → 并行获取：价格 + 资金费率 + OI + 多空比 + 清算量
    │       → LLM 分析 → 结构化报告
    │
    └── Layer 3: 动态规划（LLM 判断）
        ├── "比较 AI 赛道几个代币的做空性价比"
        │   → LLM 规划：需要获取 [RNDR, TAO, NEAR] 的 5 层数据
        │   → 生成 Python 代码 → exec → 结果给 LLM 分析
        └── "为什么 BTC 今天突然暴跌？"
            → LLM 规划：需要搜索新闻 + 链上大额转账 + 衍生品数据
            → 生成代码 → exec → 结果给 LLM 分析
```

**判断标准**：
- **Layer 2**（固定流程）：单代币 + 预定义维度组合
  - 示例: "BTC 价格"、"BTC 资金费率" → 直接调用单一 API
  - 示例: "分析 BTC 做空" → 调用预定义 pipeline（并行获取 5 个维度 → LLM 分析）
  - 关键特征: pipeline 固定，无需 LLM 规划
- **Layer 3**（动态规划）：多代币、跨赛道、事件驱动、非预定义查询
  - 示例: "比较 AI 赛道几个代币的做空性价比"
  - 示例: "为什么 BTC 今天突然暴跌？"
  - 关键特征: 需要 LLM 判断需要哪些数据、如何组合

### MCP 替代方案：函数即工具

**为什么不用 MCP**：
- JSON Schema 定义成本高，新增数据源需改 Schema
- 工具注册/发现/调用链路长，调试困难
- Agent 编排（选工具 → 填参数 → 执行 → 解析）失败点多

**迁移路径**（从现有 registry 到函数即工具）：

```python
# Phase 1: 保留兼容层（当前）
# registry.py 仍然可用，但不新增工具
from services.tools.registry import registry  # 存量兼容

# Phase 2: 新数据源直接 import（推荐）
from services.datasources.binance import get_24h_ticker
from services.datasources.arkham import get_exchange_netflow

# Phase 3: 逐步迁移存量工具
# 将 registry 中的工具逐步提取为独立函数
# 最终 registry 只保留兼容层，新代码全部直接 import
```

**替代方案**：
```python
# 不用这个 ❌
# registry.register("get_price", _get_price)
# result = await registry.execute("get_price", {"symbol": "BTC"})

# 用这个 ✅
from datasources.binance import get_24h_ticker
from datasources.arkham import get_exchange_netflow
from datasources.technical import calculate_rsi

# 直接并行调用
tasks = [
    get_24h_ticker("BTC"),
    get_exchange_netflow("BTC"),
    calculate_rsi("BTC", timeframe="4h"),
]
results = await asyncio.gather(*tasks)
```

### Memory Management

**文件结构**：
```
backend/memory/
├── sessions/{session_id}.json        # 短期记忆：对话历史
├── tokens/{SYMBOL}.json              # 长期记忆：代币维度
├── sectors/{sector}.json             # 赛道记忆：AI/meme/DeFi
├── insights/general.json             # 通用洞察
└── search_index.json                 # 检索索引
```

**Token Memory 结构**：
```json
{
  "symbol": "LAB",
  "first_queried": "2026-06-01T00:00:00Z",
  "last_queried": "2026-06-03T00:00:00Z",
  "user_interests": ["做空分析", "资金费率", "解锁压力"],
  "key_levels": {
    "support": [8.29, 10.0],
    "resistance": [15.0, 18.0]
  },
  "historical_metrics": [
    {"date": "2026-06-01", "funding_rate": -0.001, "oi": 1000000}
  ],
  "related_sectors": ["ai_tokens"],
  "notes": "用户关注 LAB 的做空机会，FDV 远高于市值"
}
```

**检索机制**：基于文件搜索（非 RAG）
- 按 `tokens/{SYMBOL}.json` 精确读取
- 按 `sectors/{sector}.json` 读取关联代币
- 关键词匹配 `search_index.json`

**触发时机**：
```python
# 1. 分析完成后立即更新
async def after_analysis(symbol: str, report: dict):
    memory = load_token_memory(symbol)
    memory["last_queried"] = now()
    memory["analysis_history"].append(report["id"])
    if report["key_levels"]:
        memory["key_levels"] = report["key_levels"]
    save_token_memory(symbol, memory)

# 2. 用户显式保存
# 前端 "保存到记忆" 按钮触发

# 3. 批量写入（可选）
# 每 5 分钟批量 flush 到磁盘，减少 I/O
```

**并发控制**：
```python
import aiofiles
from filelock import FileLock

async def save_token_memory(symbol: str, data: dict):
    path = f"backend/memory/tokens/{symbol.upper()}.json"
    lock = FileLock(f"{path}.lock")
    with lock:
        async with aiofiles.open(path, "w") as f:
            await f.write(json.dumps(data, indent=2))
```

---

## External Data Source Configuration

### Arkham Intelligence (On-Chain)
- **API**: `https://api.arkhamintelligence.com/v1`
- **Free tier**: 慷慨，未限流
- **覆盖**: EVM 链为主（ETH, ARB, OP 等）
- **Key endpoints**:
  - `/exchanges/{id}/flows` - 交易所净流入/流出
  - `/wallets/{address}` - 巨鲸地址监控
- **API Key**: 需注册，写入 `config.json`

### Whale Alert (On-Chain)
- **API**: `https://api.whale-alert.io`
- **Free tier**: 有限，但够用
- **覆盖**: BTC, ETH, USDT 等主流链
- **Key endpoints**:
  - `/transactions` - 大额转账监控
- **API Key**: 需注册

### TokenUnlocks (Unlock Data)
- **状态**: ❌ 无公开 API，需通过网页抓取或第三方聚合
- **替代方案**: CoinGecko `coins/{id}` 返回 `total_supply`, `circulating_supply`，可计算 FDV
- **手动维护**: 建立 `backend/data/vesting_schedules.json`，手动录入主要代币的解锁时间表
- **覆盖范围**: 仅限用户关注的高频代币（LAB, BTC, ETH 等），不追求全量

### CoinGecko (Extended)
- **已有**: 价格、市值、趋势
- **新增**: `fully_diluted_valuation`, `total_supply`, `circulating_supply`

### Binance Futures (Technical)
- **已有**: 24h ticker, funding rate, OI, liquidations
- **新增**: `fapi/v1/klines` - K 线数据用于 RSI/支撑压力计算

### Twitter / LunarCrush (Social)
- **Twitter API v2**: 付费，$100/月起
- **LunarCrush**: 免费 tier 有限，付费约 $50/月
- **替代方案**: 先用 LLM 对已有文本做情绪分析，后续接入

---

## Frontend Design

### Short-Selling Analysis Dashboard

**组件层级**：
```
ShortAnalysisView.vue
├── TokenSelector.vue          # 代币选择 + 自动完成
├── DimensionToggles.vue       # 5 个维度开关
├── AnalysisReport.vue         # 结构化报告展示
│   ├── DerivativesCard.vue    # 衍生品数据
│   ├── OnChainCard.vue        # 链上数据
│   ├── UnlockCard.vue         # 解锁/FDV 数据
│   ├── TechnicalCard.vue      # 技术指標
│   └── SentimentCard.vue      # 社交情绪
└── ComparisonChart.vue        # 多代币对比图表
```

**TokenSelector.vue**:
- 输入框 + 下拉建议（基于 `CoinGecko search`）
- 支持多选（比较模式）
- 最近查询历史（读取 `memory/tokens/`）

**DimensionToggles.vue**:
```vue
<div class="dimension-toggles">
  <Toggle v-model="active.derivatives" label="衍生品" />
  <Toggle v-model="active.onchain" label="链上" />
  <Toggle v-model="active.unlock" label="解锁/FDV" />
  <Toggle v-model="active.technical" label="技术面" />
  <Toggle v-model="active.sentiment" label="社交情绪" />
</div>
```

**AnalysisReport.vue**:
- 顶部：LLM 分析摘要（自然语言）
- 中部：5 个维度卡片（可展开/折叠）
- 底部：做空建议（强/中/弱，带理由）
- 支持导出 PDF / 分享链接

**分析报告数据结构**：
```json
{
  "recommendation": "weak_short",
  "confidence": 0.72,
  "time_horizon": "short_term",
  "score": 0.68
}
```
- `recommendation`: `strong_short` | `weak_short` | `neutral` | `weak_long` | `strong_long`
- `confidence`: 0.0-1.0，LLM 对分析结果的信心
- `time_horizon`: `short_term` (<7天) | `medium_term` (7-30天) | `long_term` (>30天)
- `score`: -1.0 到 +1.0 的量化打分（负数做空，正数做多，绝对值越大信号越强）

### API Schema (OpenAPI)

**POST /api/analyze/short**

Request:
```json
{
  "symbol": "BTC",
  "dimensions": ["derivatives", "onchain", "technical"],
  "timeframe": "24h",
  "include_recommendation": true
}
```

Response:
```json
{
  "symbol": "BTC",
  "timestamp": "2026-06-03T12:00:00Z",
  "dimensions": {
    "derivatives": {
      "price": 105420.50,
      "price_change_24h_pct": -2.34,
      "funding_rate": -0.0008,
      "open_interest": 15000000000,
      "long_short_ratio": 1.2,
      "liquidations_24h": 50000000,
      "sentiment": "bearish"
    },
    "onchain": {
      "exchange_netflow_24h": -1200.5,
      "whale_movements": [
        {"address": "0x...", "amount": 500, "direction": "out"}
      ],
      "market_depth": {
        "bid_depth_2pct": 8500000,
        "ask_depth_2pct": 12000000
      }
    }
  },
  "llm_analysis": {
    "summary": "BTC 当前做空信号中等偏强...",
    "strengths": ["资金费率极负", "OI 持续攀升"],
    "risks": ["链上净流出减少", "大户正在积累"],
    "confidence": 0.72,
    "recommendation": "weak_short"
  }
}
```

**POST /api/analyze/compare**

Request:
```json
{
  "symbols": ["BTC", "ETH", "SOL"],
  "dimensions": ["derivatives", "technical"],
  "sort_by": "funding_rate"
}
```

Response:
```json
{
  "tokens": [
    {
      "symbol": "BTC",
      "score": 0.72,
      "metrics": { /* ... */ }
    },
    {
      "symbol": "ETH",
      "score": 0.65,
      "metrics": { /* ... */ }
    }
  ],
  "llm_comparison": "从做空性价比来看，BTC > ETH..."
}
```

### 前端状态管理 (Pinia/Vuex)

```typescript
// stores/analysis.ts
export const useAnalysisStore = defineStore('analysis', () => {
  const currentReport = ref<AnalysisReport | null>(null)
  const reports = ref<AnalysisReport[]>([])
  const loading = ref(false)
  const activeDimensions = ref<Record<string, boolean>>({
    derivatives: true,
    onchain: true,
    unlock: false,
    technical: false,
    sentiment: false
  })
  
  async function analyzeShort(symbol: string, dims: string[]) {
    loading.value = true
    const report = await api.post('/api/analyze/short', {
      symbol,
      dimensions: dims
    })
    currentReport.value = report
    reports.value.unshift(report)
    loading.value = false
    return report
  }
  
  // 缓存策略：分析结果缓存到 localStorage
  function cacheReport(report: AnalysisReport) {
    const key = `analysis_${report.symbol}_${report.timestamp}`
    localStorage.setItem(key, JSON.stringify(report))
  }
})
```

### API 故障降级

| 故障场景 | 降级策略 | 用户感知 |
|---------|---------|---------|
| Binance API 限流 | 返回缓存数据 + 提示"数据可能滞后" | 轻微 |
| Arkham API 失败 | 跳过链上分析，其他维度正常 | 中等 |
| LLM 超时 | 返回原始数据 + "AI 分析暂不可用" | 中等 |
| 全部数据源失败 | 返回错误 + 建议稍后重试 | 严重 |

### 缓存策略

```python
# Redis/Memory 缓存（可选，先用内存）
CACHE_TTL = {
    "binance_ticker": 30,      # 30 秒
    "binance_funding": 300,     # 5 分钟
    "binance_oi": 60,           # 1 分钟
    "coingecko": 300,           # 5 分钟
    "arkham": 600,              # 10 分钟
    "llm_analysis": 3600,       # 1 小时（分析结果缓存）
}
```

### 重试机制

```python
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
)
async def fetch_binance_data(symbol: str):
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://fapi.binance.com/...")
        resp.raise_for_status()
        return resp.json()
```

---

## Configuration

### config.json

```json
{
  "llm": {
    "provider": "minimax",
    "model": "MiniMax-M2.7",
    "base_url": "https://api.minimaxi.com/v1",
    "api_key": "..."
  },
  "binance": {
    "api_key": "...",
    "secret_key": "...",
    "use_testnet": true
  },
  "arkham": {
    "api_key": "..."
  },
  "whale_alert": {
    "api_key": "..."
  },
  "cache": {
    "type": "memory",  // or "redis"
    "ttl_seconds": 300
  },
  "analysis": {
    "default_dimensions": ["derivatives", "onchain", "technical"],
    "max_concurrent_tokens": 3,
    "llm_timeout": 25
  }
}
```

---

## Testing Strategy

### Unit Tests
- 每个数据源模块独立测试（mock HTTP）
- 意图路由逻辑测试（Layer 2 vs Layer 3）
- 记忆读写测试

### Integration Tests
- 端到端做空分析（真实 API）
- LLM 分析质量评估（人工抽检）
- 性能测试：多代币并发分析

### Test Fixtures
```python
# tests/fixtures/btc_mock_data.py
BTC_MOCK_DATA = {
    "binance": {"price": 105000, "funding_rate": -0.001, ...},
    "arkham": {"netflow": -1200, "whales": [...]},
    "coingecko": {"fdv": 1000000000, "market_cap": 500000000},
}
```

---

## Deployment Considerations

### 依赖
```bash
# backend
pip install httpx pandas-ta tenacity

# optional for redis cache
pip install redis

# frontend (already in project)
npm install vue-chartjs chart.js
```

### 环境变量
```bash
MINIMAX_API_KEY=...
BINANCE_API_KEY=...
BINANCE_SECRET_KEY=...
ARKHAM_API_KEY=...
WHALE_ALERT_API_KEY=...
```
