# Binance Hot Tokens Scanner 开发文档

## 1. 概述

### 目标
为 AI Trading Desk 新增「热门代币扫描器」功能，自动发现币安 USDT 永续合约中交易最活跃的代币，支持可视化展示和手动/自动交易。

### 复用现有能力
- **CCXT + Binance USDM**: 复用 `services/binance_trader.py` 中的 CCXT 初始化逻辑
- **SignalAnalyzer**: 复用 `services/signal_analyzer.py` 的 LLM 分析能力
- **TradingEngine**: 复用 `services/trading_engine.py` 的交易执行和风险管理
- **SQLite + Database**: 复用 `services/database.py` 的表结构和连接管理
- **WebSocket**: 复用 `api/ws.py` 的广播机制，新增 `hot_tokens_update` 消息类型

### 新增模块
| 模块 | 文件 | 说明 |
|------|------|------|
| HotTokensScanner | `services/hot_tokens_scanner.py` | 扫描、评分、推送 |
| Hot Tokens API | `api/hot_tokens.py` | REST 接口 |
| WebSocket广播 | 复用 `api/ws.py` | 新增消息类型 |
| 前端热榜 | `TradingView.vue` 新增 Tab | 实时榜单、分析、交易 |

---

## 2. 架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              前端 (Vue - TradingView)                        │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │ Crypto Tab                                                           │    │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────────────────────────┐ │    │
│  │  │Signals Feed │  │ Positions  │  │ 🔥 Hot Tokens (新增)           │ │    │
│  │  └────────────┘  └────────────┘  │ ┌──────────────────────────┐   │ │    │
│  │                                   │ │ 综合热度排行榜            │   │ │    │
│  │                                   │ │ ┌────┬───────┬──────┐   │   │ │    │
│  │                                   │ │ │Rank│Symbol │Heat  │...│   │ │    │
│  │                                   │ │ └────┴───────┴──────┘   │   │ │    │
│  │                                   │ │ [Analyze] → LLM分析      │   │ │    │
│  │                                   │ │ [Execute] → 下单       │   │ │    │
│  │                                   │ └──────────────────────────┘   │ │    │
│  │                                   └────────────────────────────────┘ │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                              ↑ WebSocket (hot_tokens_update)                 │
│                              ↑ REST (/api/hot_tokens/*)                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                          │
┌─────────────────────────────────────────┼────────────────────────────────────┐
│                              后端 (FastAPI)                                   │
│  ┌────────────────────────────────────────┼──────────────────────────────┐  │
│  │ HotTokensScanner                       │                              │  │
│  │  ┌─────────────────────────────┐      │                              │  │
│  │  │ _fetch_and_update()          │      │                              │  │
│  │  │  ├ fetch_tickers()           │      │                              │  │
│  │  │  ├ fetch_funding_rate()      │      │                              │  │
│  │  │  ├ fetch_long_short_ratio()  │      │                              │  │
│  │  │  └ _calculate_heat_score()  │      │                              │  │
│  │  └─────────────────────────────┘      │                              │  │
│  │  ┌─────────────────────────────┐      │                              │  │
│  │  │ _broadcast_update()         │ ───────→ manager.broadcast()      │  │
│  │  └─────────────────────────────┘      │      (复用 ws_manager.py)    │  │
│  └────────────────────────────────────────┘                              │  │
│  ┌──────────────────────────────────────────────────────────────────┐   │  │
│  │ API Layer (api/hot_tokens.py)                                    │   │  │
│  │  GET  /api/hot_tokens          → 查询热榜列表                    │   │  │
│  │  POST /api/hot_tokens/:symbol/analyze → LLM分析该代币            │   │  │
│  │  POST /api/hot_tokens/:symbol/execute   → 执行交易               │   │  │
│  │  POST /api/hot_tokens/start      → 启动扫描器                    │   │  │
│  │  POST /api/hot_tokens/stop       → 停止扫描器                    │   │  │
│  └──────────────────────────────────────────────────────────────────┘   │  │
│  ┌──────────────────────────────────────────────────────────────────┐   │  │
│  │ Reuse Layer                                                      │   │  │
│  │  ├ signal_analyzer.analyze()   (复用 LLM 分析)                    │   │  │
│  │  ├ trading_engine.execute_signal() (复用 交易执行)               │   │  │
│  │  └ binance_trader.*            (复用 CCXT 连接)                  │   │  │
│  └──────────────────────────────────────────────────────────────────┘   │  │
└───────────────────────────────────────────────────────────────────────────┘
                                          │
                                    ┌─────┴─────┐
                                    │ Binance   │
                                    │ Futures   │
                                    │ API       │
                                    └───────────┘
```

---

## 3. 信号流（扫描 → 分析 → 交易）

### 3.1 扫描流程

```
Step 1: 定时触发 (每60秒)
  │
  ▼
Step 2: 获取所有 USDT 永续合约行情
  │   GET /fapi/v1/ticker/24hr (CCXT fetch_tickers)
  │   返回: symbol, price, volume, priceChange, priceChangePercent
  │
  ▼
Step 3: 对每个代币，获取附加数据
  │   GET /fapi/v1/fundingRate (CCXT fetch_funding_rate)
  │   GET /futures/data/globalLongShortAccountRatio
  │   GET /fapi/v1/openInterest
  │
  ▼
Step 4: 计算热度得分
  │   heat_score = volume_score * 0.5 + change_score * 0.3 + funding_score * 0.2
  │
  ▼
Step 5: 排序，取前50名
  │
  ▼
Step 6: 保存到 hot_tokens 表 + WebSocket广播
```

### 3.2 热度计算公式 (MVP)

```python
def calculate_heat_score(token):
    # 归一化各指标 (0-1)
    volume_score = token.volume_usd / max_volume
    change_score = abs(token.price_change_24h_pct) / max_change
    funding_score = abs(token.funding_rate) / max_funding

    # 加权计算
    heat_score = (
        volume_score * 0.5 +    # 交易量权重最高
        change_score * 0.3 +     # 价格变动次之
        funding_score * 0.2     # 资金费率最低
    )
    return heat_score
```

---

## 4. 数据库 Schema

### 4.1 hot_tokens — 热币快照表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| symbol | TEXT | 代币符号 (如 BTCUSDT) |
| price | REAL | 当前价格 |
| price_change_24h | REAL | 24h 价格变动百分比 |
| volume_24h | REAL | 24h 交易量 |
| volume_usd | REAL | 24h 交易额 (USD) |
| funding_rate | REAL | 当前资金费率 |
| long_short_ratio | REAL | 多空持仓比 |
| open_interest | REAL | 持仓量 |
| liquidation_price | REAL | 预估爆仓价格 |
| heat_score | REAL | 热度得分 |
| created_at | TIMESTAMP | 记录时间 |

---

## 5. API 端点

### 5.1 查询端点

| 方法 | 路径 | 说明 | 参数 |
|------|------|------|------|
| GET | `/api/hot_tokens` | 热榜列表 | `limit=50`, `sort=heat_score` |
| GET | `/api/hot_tokens/:symbol` | 单个代币详情 | `symbol` |

### 5.2 操作端点

| 方法 | 路径 | 说明 | Body |
|------|------|------|------|
| POST | `/api/hot_tokens/:symbol/analyze` | LLM分析该代币 | — |
| POST | `/api/hot_tokens/:symbol/execute` | 执行交易 | `{side, quantity, leverage}` |
| POST | `/api/hot_tokens/start` | 启动扫描器 | — |
| POST | `/api/hot_tokens/stop` | 停止扫描器 | — |

---

## 6. WebSocket 消息协议

### 6.1 服务端 → 客户端

```json
{
  "type": "hot_tokens_update",
  "data": [
    {
      "symbol": "BTCUSDT",
      "price": 64320.5,
      "price_change_24h": 2.3,
      "volume_24h": 150000,
      "funding_rate": 0.0001,
      "long_short_ratio": 1.25,
      "heat_score": 0.89
    },
    ...
  ]
}
```

---

## 7. 前端集成

### 7.1 TradingView Crypto Tab 改造

在现有「Signals Feed」和「Positions」子标签旁新增「🔥 Hot Tokens」子标签。

```
Crypto Tab
├── Signals Feed (已有)
├── Positions (已有)
└── 🔥 Hot Tokens (新增)
    ├── 热度排行榜 (表格)
    │   ├── Rank
    │   ├── Symbol
    │   ├── Price
    │   ├── 24h Change
    │   ├── Volume (24h)
    │   ├── Funding Rate
    │   ├── L/S Ratio
    │   └── Heat Score
    │
    └── 操作列
        ├── [Analyze] → 调用 LLM 分析 → 显示分析结果弹窗
        └── [Trade] → 打开交易面板 → 确认下单
```

### 7.2 数据绑定

| 前端组件 | API / WebSocket | 数据字段 |
|---------|----------------|---------|
| 热度排行榜 | WebSocket `hot_tokens_update` | symbol, price, heat_score, ... |
| 分析弹窗 | POST `/hot_tokens/:symbol/analyze` | sentiment, confidence, reasoning |
| 交易面板 | POST `/hot_tokens/:symbol/execute` | order_id, status |
| 扫描器控制 | POST `/hot_tokens/start` / `stop` | status |

---

## 8. 配置管理

在 `config.json` 中新增字段（复用现有 `config_store.py`）：

```json
{
  "hot_tokens_enabled": false,
  "hot_tokens_scan_interval": 60,
  "hot_tokens_max_results": 50,
  "hot_tokens_auto_execute": false,
  "hot_tokens_auto_threshold": 0.8
}
```

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| hot_tokens_enabled | false | 是否启用热币扫描 |
| hot_tokens_scan_interval | 60 | 扫描间隔（秒） |
| hot_tokens_max_results | 50 | 热榜最大显示数量 |
| hot_tokens_auto_execute | false | 是否自动交易 |
| hot_tokens_auto_threshold | 0.8 | 自动交易置信度阈值 |

---

## 9. 与现有系统的关系

### 9.1 复用的模块

| 模块 | 复用方式 | 说明 |
|------|---------|------|
| `services/binance_trader.py` | 复用 CCXT 连接 | HotTokensScanner 直接使用 ccxt.binanceusdm |
| `services/signal_analyzer.py` | 复用 LLM 分析 | 分析热币时调用 analyze() |
| `services/trading_engine.py` | 复用交易执行 | 下单时调用 execute_signal() |
| `services/database.py` | 复用 SQLite 连接 | 新增 hot_tokens 表 |
| `services/ws_manager.py` | 复用广播机制 | 新增 hot_tokens_update 消息 |

### 9.2 新增 vs 复用

- **新增**: HotTokensScanner 类、hot_tokens API 路由、前端 Hot Tokens 标签页
- **复用**: CCXT 连接、LLM 分析、交易执行、数据库、WebSocket广播

---

## 10. 实现顺序

1. **Step 1**: 新增 `hot_tokens` 表到 `database.py`
2. **Step 2**: 创建 `services/hot_tokens_scanner.py` (扫描 + 评分 + 广播)
3. **Step 3**: 创建 `api/hot_tokens.py` (REST API)
4. **Step 4**: 注册路由到 `main.py`
5. **Step 5**: 前端 TradingView.vue 新增 Hot Tokens 标签页
6. **Step 6**: 测试完整链路
