# 做空决策数据架构与 MCP 替代方案

> 文档类型: 架构设计
> 更新日期: 2026-06-03

---

## 1. 当前数据覆盖度

### 1.1 已实现的 Binance Futures 数据

| 数据项 | 来源 API | 状态 |
|--------|---------|------|
| 实时价格 & 24h 涨跌幅 | `fapi/v1/ticker/24hr` | ✅ |
| 24h 成交量 | `fapi/v1/ticker/24hr` | ✅ |
| 资金费率 | `fapi/v1/fundingRate` | ✅ |
| 多空比 | `futures/data/topLongShortAccountRatio` | ✅ |
| 持仓量 (OI) | `fapi/v1/openInterest` | ✅ |
| 24h 清算量 | `fapi/v1/allForceOrders` | ✅ |

### 1.2 现有数据源模块

- **CoinGecko** (`datasources/coingecko.py`) — 价格、市值、趋势
- **OKX** (`datasources/okx.py`) — 资金费率、行情
- **Hyperliquid** (`datasources/hyperliquid.py`) — 巨鲸、资金费率、持仓
- **Binance Futures** — 实时价格、合约数据（直接在 `token_analyzer.py` 中调用）

---

## 2. 做空决策五大维度

### 2.1 衍生品市场数据（核心）

**已有数据**：
- 资金费率 ✅
- 持仓量 ✅
- 多空比 ✅
- 24h 清算量 ✅

**缺失数据**：
- 清算热力图 (Liquidation Heatmap) — 需 Binance K 线 + 清算分布计算
- 历史资金费率趋势 — 需聚合多期数据
- 合约持仓变化率 — 需对比多时段 OI

### 2.2 链上流动性与筹码分布

**缺失数据**：
- 交易所净流入 (Exchange Netflow)
- 巨鲸持仓变动（前 100 地址）
- 流动性深度 (Market Depth)
- DEX/CEX 买盘深度

**获取方案**：
- 交易所净流入: **Arkham Intelligence API** (免费 tier) / **Glassnode** (付费)
- 巨鲸变动: **Whale Alert API** / **Etherscan API** + 地址标签
- 流动性深度: **Binance 深度 API** `fapi/v1/depth` / **CoinGecko 深度数据**
- DEX 深度: **Uniswap/Curve 子图** (The Graph)

### 2.3 代币解锁与通胀压力

**缺失数据**：
- 解锁时间表 (Vesting Schedule)
- FDV (Fully Diluted Valuation) vs 市值比
- 通胀率 / 质押解锁量

**获取方案**：
- 解锁数据: **TokenUnlocks API** / **CoinGecko** (部分覆盖)
- FDV: **CoinGecko** `fully_diluted_valuation`
- 通胀: **Messari** (需订阅) / 手动维护解锁日历

### 2.4 技术面指标

**缺失数据**：
- RSI (相对强弱指数)
- 背离信号 (Divergence)
- 支撑/压力位
- 清算热力图

**获取方案**：
- K 线数据: **Binance Futures** `fapi/v1/klines`
- 指标计算: Python `pandas-ta` / `ta-lib`
- 清算热力图: 基于 K 线 + 清算订单聚合（或第三方 API: CoinGlass）

### 2.5 社交情绪与舆论监控

**缺失数据**：
- Twitter/X 实时情绪
- 项目方动态
- "操纵"/"跑路"/"黑客" 关键词监控

**获取方案**：
- 情绪分析: 已有 `analyze_sentiment` 工具（基于 LLM）
- Twitter 抓取: **Twitter API v2** (付费) / 第三方聚合
- 社区监控: **LunarCrush** / **Santiment** (付费)

---

## 3. MCP 替代方案: 代码优先，命令行执行

### 3.1 为什么不用 MCP

MCP 的问题：
- **强结构化**: 每个工具必须预定义 JSON Schema，新增数据源成本高
- **强显式绑定**: 工具注册、发现、调用链全部显式编排
- **强编排成本**: Agent 的工具选择 → 参数填充 → 执行 → 结果解析，每一步都有失败点

### 3.2 替代方案: 函数即工具

**核心原则**: 需要哪个数据源，直接 import 函数调用。不需要注册、不需要 Schema、不需要 Agent 编排。

```python
# 不用这个 ❌
# registry.register("get_price", _get_price)
# result = await registry.execute("get_price", {"symbol": "BTC"})

# 用这个 ✅
from datasources.binance import get_24h_ticker
from datasources.okx import get_funding_rate
from datasources.arkham import get_exchange_netflow

# 直接并行调用
tasks = [
    get_24h_ticker("BTC"),
    get_funding_rate("BTC"),
    get_exchange_netflow("BTC"),
]
results = await asyncio.gather(*tasks)
```

### 3.3 Agent 设计: 规划 → 代码生成 → 执行

**不是**: Agent 选工具 → Agent 填参数 → Agent 执行 → Agent 总结

**而是**: 
1. **规划**: LLM 根据用户问题，输出一个 "数据获取计划" (Python 代码)
2. **执行**: 直接执行生成的代码（或预定义的函数）
3. **分析**: LLM 分析原始数据，输出做空决策建议

```
用户: "分析下 BTC 做空机会"
      ↓
LLM 规划: 需要以下数据 → [价格、资金费率、OI、净流入、RSI]
      ↓
代码生成: 调用 binance.get_ticker(), arkham.get_netflow(), rsi.calculate()
      ↓
并行执行: asyncio.gather() 获取所有数据
      ↓
LLM 分析: 基于原始数据生成做空决策报告
```

---

## 4. 记忆管理方案

### 4.1 文件结构

```
backend/memory/
├── sessions/           # 按 session 隔离的短期记忆
│   ├── {session_id}.json
│   └── ...
├── tokens/            # 按代币聚合的长期记忆
│   ├── BTC.json
│   ├── ETH.json
│   └── LAB.json
├── strategies/        # 策略级别的长期记忆
│   └── short_selling_framework.json
└── search_index.json  # 记忆检索索引
```

### 4.2 短期记忆 (Session Memory)

每个对话 session 的上下文，包括：
- 对话历史
- 用户提到的代币和关注维度
- 当前分析进度

存储格式: `sessions/{session_id}.json`

### 4.3 长期记忆 (Token Memory)

按代币聚合的历史数据和用户关注记录：

```json
{
  "symbol": "LAB",
  "first_queried": "2026-06-01T00:00:00Z",
  "last_queried": "2026-06-03T00:00:00Z",
  "user_interests": [
    "做空分析", "资金费率", "解锁压力"
  ],
  "key_levels": {
    "support": [8.29, 10.0],
    "resistance": [15.0, 18.0]
  },
  "historical_metrics": [
    {"date": "2026-06-01", "funding_rate": -0.001, "oi": 1000000}
  ],
  "notes": "用户关注 LAB 的做空机会，FDV 远高于市值"
}
```

### 4.4 检索机制

**不依赖 RAG，基于文件搜索**：

```python
import json
from pathlib import Path

class MemoryStore:
    def __init__(self, base_path: str = "backend/memory"):
        self.base = Path(base_path)
        self.base.mkdir(parents=True, exist_ok=True)

    def get_token_memory(self, symbol: str) -> dict:
        """读取代币的长期记忆"""
        path = self.base / "tokens" / f"{symbol.upper()}.json"
        if path.exists():
            return json.loads(path.read_text())
        return {}

    def update_token_memory(self, symbol: str, data: dict):
        """更新代币记忆"""
        path = self.base / "tokens" / f"{symbol.upper()}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = self.get_token_memory(symbol)
        existing.update(data)
        path.write_text(json.dumps(existing, indent=2, default=str))

    def search_memory(self, query: str) -> list[dict]:
        """基于关键词搜索记忆索引"""
        index_path = self.base / "search_index.json"
        if not index_path.exists():
            return []
        index = json.loads(index_path.read_text())
        # 简单的关键词匹配
        return [item for item in index if query.lower() in item.get("keywords", "")]
```

---

## 5. 实施优先级

| 阶段 | 内容 | 预计工作量 | 数据价值 |
|------|------|-----------|---------|
| P0 | 优化现有 Binance 数据分析质量 | 1-2 天 | 高 |
| P1 | 接入 K 线数据 + RSI/支撑压力计算 | 2-3 天 | 高 |
| P2 | 接入链上数据 (Arkham/Whale Alert) | 3-5 天 | 高 |
| P3 | 代币解锁/FDV 数据 (CoinGecko 补充) | 2-3 天 | 中 |
| P4 | 清算热力图 | 3-5 天 | 中 |
| P5 | 社交情绪 (Twitter/LunarCrush) | 3-5 天 | 低 |
| P6 | 记忆系统实现 | 2-3 天 | 高 |

---

## 6. 技术决策记录

### 6.1 不用 MCP 的理由

| MCP 特性 | 问题 | 替代方案 |
|---------|------|---------|
| JSON Schema 定义 | 新增数据源需改 Schema，成本高 | 直接写 Python 函数 |
| 工具注册/发现 | 运行时绑定，调试困难 | import 直接调用 |
| Agent 编排 | 工具选择 → 参数填充 → 执行，链路长 | LLM 规划 → 代码执行 → 分析 |
| 显式绑定 | 耦合度高 | 函数解耦，按需组合 |

### 6.2 不用 RAG 的理由

| RAG 特性 | 问题 | 替代方案 |
|---------|------|---------|
| 向量数据库 | 引入额外依赖 (pinecone/chroma) | 文件系统 + JSON |
| Embedding 模型 | 需要额外模型，增加延迟 | 关键词匹配 + 文件路径 |
| 召回精度 | 对专业术语召回不稳定 | 按代币/维度分文件，精确读取 |
| 成本 | Embedding + 存储 + 查询 | 文件 I/O，几乎零成本 |
