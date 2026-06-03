# Polymarket 预测市场集成方案

## 1. 概述

基于 Polymarket Agent 项目中的核心逻辑，将预测市场（Prediction Market）交易能力集成到现有 Browser Demo 项目中。

### 核心能力
- **信号发现**：每 60 秒轮询 Polymarket Top 200 交易员，聚合交易数据，检测集群信号
- **自动交易**：信号通过过滤后自动下单（市价单）
- **持仓监控**：实时检查持仓价格，自动触发止盈止损
- **数据持久化**：信号、持仓、交易记录全部存入 SQLite

---

## 2. 架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              前端 (Vue)                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ Signals  │  │ Positions│  │  Trades  │  │  Config  │  │  Status  │      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘      │
│       │             │             │             │             │              │
│       └─────────────┴─────────────┴─────────────┴─────────────┘              │
│                                          │                                   │
└──────────────────────────────────────────┼────────────────────────────────────┘
                                          │ HTTP
┌──────────────────────────────────────────┼────────────────────────────────────┐
│                              后端 (FastAPI)│                                   │
│                                          │                                     │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                        API Layer                                        │  │
│  │  GET  /api/polymarket/signals      →  查询信号列表                       │  │
│  │  GET  /api/polymarket/signals/:id  →  查询单个信号                       │  │
│  │  GET  /api/polymarket/positions    →  查询持仓                         │  │
│  │  GET  /api/polymarket/trades       →  查询交易历史                       │  │
│  │  GET  /api/polymarket/config       →  查询配置                         │  │
│  │  PUT  /api/polymarket/config       →  更新配置                         │  │
│  │  POST /api/polymarket/start        →  启动轮询                         │  │
│  │  POST /api/polymarket/stop         →  停止轮询                         │  │
│  │  GET  /api/polymarket/status       →  查询服务状态                     │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                          │                                     │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                      Services Layer                                     │  │
│  │                                                                         │  │
│  │   ┌───────────────┐    ┌───────────────┐    ┌───────────────┐        │  │
│  │   │ TopUsersPoller│───▶│ SignalHandler │───▶│   Trader      │        │  │
│  │   │ (轮询Top200)   │    │ (过滤+保存)   │    │ (下单执行)    │        │  │
│  │   └───────────────┘    └───────────────┘    └───────┬───────┘        │  │
│  │                                                     │                   │  │
│  │                                        ┌────────────┘                   │  │
│  │                                        ▼                                │  │
│  │                              ┌───────────────┐                        │  │
│  │                              │PositionMonitor│                        │  │
│  │                              │(止盈止损监控)  │                        │  │
│  │                              └───────────────┘                        │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                          │                                     │
└──────────────────────────────────────────┼────────────────────────────────────┘
                                          │ HTTP
┌──────────────────────────────────────────┼────────────────────────────────────┐
│                         Polymarket API   │                                     │
│  ┌───────────────────────────────────────┴────────────────────────────────┐   │
│  │  Data API:  https://data-api.polymarket.com                          │   │
│  │  CLOB API:  https://clob.polymarket.com                                │   │
│  │                                                                         │   │
│  │  Endpoints used:                                                       │   │
│  │  GET /api/v1/leaderboard    → Top 200 交易员                           │   │
│  │  GET /api/v1/activity       → 用户最近交易                              │   │
│  │  GET /api/v1/market         → 市场信息                                  │   │
│  │  POST /order                → 创建订单 (需要 API Key)                   │   │
│  └────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 信号流（核心逻辑）

### 3.1 信号发现流程

```
Step 1: 轮询触发 (每60秒)
  │
  ▼
Step 2: 获取 Top 200 交易员
  │   GET /api/v1/leaderboard?limit=50&offset={page*50}
  │   分页获取，默认取200人
  │
  ▼
Step 3: 获取每个交易员最近交易
  │   GET /api/v1/activity?user={proxyWallet}&start={timestamp}&limit=20
  │   并发请求，Semaphore限制20个同时请求
  │
  ▼
Step 4: 聚合交易
  │   按 (market_slug, side, outcome) 分组
  │   计算每组的总金额、平均价格、参与人数
  │
  ▼
Step 5: 计算净流入
  │   对每个 market_slug + outcome:
  │   net_inflow = BUY_value - SELL_value
  │
  ▼
Step 6: 集群检测
  │   过滤条件:
  │   - 参与用户数 >= cluster_min_users (默认3)
  │   - 净流入绝对值 >= cluster_min_value (默认$1000)
  │   - 平均价格在 [min_price, max_price] 范围内 (默认0.01-0.99)
  │   - ⚠️ 到期时间过滤 (market_expiry_hours) — 暂未完成
  │
  ▼
Step 7: 信号去重
  │   5分钟内同一市场同一方向的信号不重复发送
  │
  ▼
Step 8: 发射信号
  ▼
Step 9: 信号处理
  │   保存到 DB (polymarket_signals 表)
  │   如果 confidence >= auto_execute_threshold (默认0.7，可配置) → 自动执行
  │   否则 → 保持 pending 状态
  │
  ▼
Step 10: 执行交易
   │   ⚠️ dry_run=true: 仅记录到数据库，不执行真实市价单
   │   dry_run=false: 调用 PolymarketTrader.create_market_order() 创建 FOK 市价单
   │   记录到 polymarket_trades 表
   │   创建持仓到 polymarket_positions 表 (含 SL/TP 价格)
   │
   ▼
Step 11: 持仓监控 (每30秒)
    随 /api/polymarket/start 一起启动
    获取当前价格 → 比较 SL/TP → 触发平仓
```

### 3.2 信号数据结构

```python
class ClusterSignal:
    market_slug: str       # 市场标识符 (如 "will-btc-hit-100k")
    side: str              # "BUY" 或 "SELL"
    outcome: str           # "YES" 或 "NO"
    token_id: str          # 代币ID (0x...)
    condition_id: str      # 条件ID (0x...)
    total_amount: float    # 交易数量
    total_value: float     # 交易金额 (USDC)
    unique_users: int      # 参与用户数
    avg_price: float       # 平均价格 (即概率)
    confidence: float      # 置信度 (0-1)
    net_inflow: float      # 净流入金额
    direction: str         # 信号方向 "BUY" / "SELL"
```

---

## 4. 数据库 Schema

### 4.1 polymarket_signals — 信号表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| signal_id | TEXT UNIQUE | 信号唯一标识 |
| market_slug | TEXT | 市场slug |
| question | TEXT | 问题描述 |
| outcome | TEXT | 结果方向 (YES/NO) |
| side | TEXT | 交易方向 (BUY/SELL) |
| token_id | TEXT | 代币ID |
| condition_id | TEXT | 条件ID |
| avg_price | REAL | 平均价格 |
| total_value | REAL | 总交易金额 |
| unique_users | INTEGER | 参与用户数 |
| confidence | REAL | 置信度 0-1 |
| net_inflow | REAL | 净流入 |
| status | TEXT | pending / executed / rejected |
| executed_at | TIMESTAMP | 执行时间 |
| created_at | TIMESTAMP | 创建时间 |

### 4.2 polymarket_positions — 持仓表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| position_id | TEXT UNIQUE | 持仓唯一标识 |
| signal_id | TEXT | 关联信号 |
| token_id | TEXT | 代币ID |
| condition_id | TEXT | 条件ID |
| market_slug | TEXT | 市场slug |
| question | TEXT | 问题描述 |
| outcome | TEXT | 结果方向 |
| side | TEXT | 持仓方向 |
| entry_price | REAL | 入场价格 |
| current_price | REAL | 当前价格 |
| size | REAL | 持仓数量 |
| entry_amount | REAL | 入场金额 |
| highest_price | REAL | 历史最高价 |
| lowest_price | REAL | 历史最低价 |
| stop_loss_price | REAL | 止损价格 |
| take_profit_price | REAL | 止盈价格 |
| status | TEXT | open / closed |
| pnl | REAL | 盈亏金额 |
| pnl_pct | REAL | 盈亏百分比 |
| close_price | REAL | 平仓价格 |
| close_reason | TEXT | 平仓原因 |
| opened_at | TIMESTAMP | 开仓时间 |
| closed_at | TIMESTAMP | 平仓时间 |

### 4.3 polymarket_trades — 交易记录表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| trade_id | TEXT UNIQUE | 交易唯一标识 |
| signal_id | TEXT | 关联信号 |
| position_id | TEXT | 关联持仓 |
| token_id | TEXT | 代币ID |
| condition_id | TEXT | 条件ID |
| market_slug | TEXT | 市场slug |
| outcome | TEXT | 结果方向 |
| side | TEXT | 交易方向 |
| price | REAL | 成交价格 |
| size | REAL | 成交数量 |
| amount | REAL | 成交金额 |
| fee | REAL | 手续费 |
| status | TEXT | pending / filled / failed |
| order_id | TEXT | 订单ID |
| filled_at | TIMESTAMP | 成交时间 |
| created_at | TIMESTAMP | 创建时间 |

### 4.4 polymarket_config — 配置表

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| id | INTEGER PK | 1 | 主键 |
| api_key | TEXT | null | CLOB API Key |
| api_secret | TEXT | null | CLOB API Secret |
| api_passphrase | TEXT | null | CLOB Passphrase |
| private_key | TEXT | null | 钱包私钥 |
| dry_run | INTEGER | 1 | 是否只模拟不真下单 |
| poll_interval | INTEGER | 60 | 轮询间隔(秒) |
| cluster_min_users | INTEGER | 3 | 最小参与用户数 |
| cluster_min_value | REAL | 1000.0 | 最小净流入金额 |
| min_price | REAL | 0.01 | 最低价格 |
| max_price | REAL | 0.99 | 最高价格 |
| sl_percentage | REAL | 0.15 | 止损百分比 |
| tp_percentage | REAL | 0.05 | 止盈百分比 |
| enabled | INTEGER | 0 | 是否启用 |

---

## 5. 核心模块设计

### 5.1 PolymarketDataApiClient

**职责**: 封装 Polymarket Data API 调用

**方法**:
- `get_leaderboard(limit, offset, ...)` — 获取排行榜
- `get_user_activity(user, limit, start, ...)` — 获取用户交易
- `get_market_info(slug)` — 获取市场信息
- `get_market_price(token_id)` — 获取市场价格

### 5.2 TopUsersPoller

**职责**: 轮询Top交易员，检测集群信号

**配置参数**:
| 参数 | 默认值 | 说明 |
|------|--------|------|
| poll_interval | 60 | 轮询间隔(秒) |
| leaderboard_limit | 200 | 取Top N交易员 |
| positions_limit | 20 | 每人取最近N条交易 |
| cluster_min_users | 3 | 最小参与用户数 |
| cluster_min_value | 1000.0 | 最小净流入金额 |
| market_expiry_hours | 6 | 忽略超过N小时到期的市场 |
| min_price | 0.01 | 最低价格 |
| max_price | 0.99 | 最高价格 |

**内部流程**:
1. `start()` → 启动轮询循环
2. `_refresh_leaderboard()` → 获取Top 200
3. `_poll_all_trades()` → 并发获取交易
4. `_process_trades()` → 聚合+检测
5. `_emit_signal()` → 触发回调

### 5.3 PolymarketTrader

**职责**: 执行交易订单

**方法**:
- `create_market_order(token_id, side, amount, max_slippage)` — 创建市价单
- `cancel_all_orders()` — 取消所有挂单
- `get_stats()` — 获取统计

**注意**: 当前为dry_run模式，实际交易需配置API Key

### 5.4 PositionMonitor

**职责**: 监控持仓，触发止盈止损

**监控逻辑**:
```
每30秒:
  获取所有 status='open' 的持仓
  对每个持仓:
    获取当前价格
    如果 current_price <= stop_loss_price → 平仓(reason=stop_loss)
    如果 current_price >= take_profit_price → 平仓(reason=take_profit)
    更新 highest_price / lowest_price
```

---

## 6. API 端点

### 6.1 查询端点

| 方法 | 路径 | 说明 | 参数 |
|------|------|------|------|
| GET | `/api/polymarket/signals` | 信号列表 | status, limit |
| GET | `/api/polymarket/signals/:id` | 单个信号 | signal_id |
| GET | `/api/polymarket/positions` | 持仓列表 | — |
| GET | `/api/polymarket/trades` | 交易历史 | limit |
| GET | `/api/polymarket/config` | 配置信息 | — |
| GET | `/api/polymarket/status` | 服务状态 | — |

### 6.2 控制端点

| 方法 | 路径 | 说明 | Body |
|------|------|------|------|
| PUT | `/api/polymarket/config` | 更新配置 | { poll_interval, cluster_min_users, ... } |
| POST | `/api/polymarket/start` | 启动轮询 | — |
| POST | `/api/polymarket/stop` | 停止轮询 | — |

---

## 7. 前端集成

### 7.1 TradingView Prediction Tab 改造

当前 Prediction Tab 是占位符，需要替换为功能面板：

```
┌─────────────────────────────────────────────────────────────────┐
│                    Prediction Markets                           │
├─────────────────────────────────────────────────────────────────┤
│  Status: [Running]  [Start] [Stop]                             │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Stats Row: Open Positions | Signals | P&L             │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│  │ Signals  │  │ Positions│  │  Trades  │                   │
│  │  Feed    │  │  List    │  │  History │                   │
│  └──────────┘  └──────────┘  └──────────┘                   │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 数据绑定

| 前端组件 | API 端点 | 数据字段 |
|---------|---------|---------|
| 信号列表 | GET /api/polymarket/signals | market_slug, side, confidence, net_inflow, created_at |
| 持仓列表 | GET /api/polymarket/positions | market_slug, entry_price, current_price, pnl, status |
| 交易历史 | GET /api/polymarket/trades | market_slug, side, price, size, status, created_at |
| 服务控制 | POST /api/polymarket/{start,stop} | status |

---

## 8. 配置管理

### 8.1 默认配置（首次启动）

```json
{
  "dry_run": true,
  "poll_interval": 60,
  "cluster_min_users": 3,
  "cluster_min_value": 1000.0,
  "min_price": 0.01,
  "max_price": 0.99,
  "sl_percentage": 0.15,
  "tp_percentage": 0.05,
  "enabled": false
}
```

### 8.2 关键配置说明

- **dry_run**: true 时只模拟交易，不真正下单。测试阶段建议保持 true
- **poll_interval**: 轮询间隔，单位秒。60秒适合实时追踪
- **cluster_min_users**: 触发信号的最小参与用户数，太低会噪音多
- **cluster_min_value**: 触发信号的最小净流入金额(USD)，过滤小额交易
- **sl_percentage**: 止损百分比，默认15%（Polymarket价格波动较大）
- **tp_percentage**: 止盈百分比，默认5%

---

## 9. 与 Binance 交易的区别

| 特性 | Binance Futures | Polymarket |
|------|----------------|------------|
| 标的 | 加密货币永续合约 | 预测市场合约 |
| 价格 | 连续波动 | 0-1 (概率) |
| 杠杆 | 支持 | 不支持 |
| 爆仓 | 有 | 无 |
| 最大亏损 | 保证金全部 | 持仓金额 |
| 订单类型 | 限价/市价/条件单 | 限价/市价 |
| SL/TP | 交易所原生支持 | 需自行监控 |
| 结算 | 随时平仓 | 事件到期结算 |

---

## 10. 后续扩展

### 10.1 待实现功能
1. **真实交易**: 配置 CLOB API Key 后执行真实下单
2. **WebSocket 推送**: 用 WebSocket 实时推送信号到前端
3. **策略参数动态调整**: 运行时修改 cluster_min_users 等参数
4. **多策略支持**: 除 TopUsers 外，增加 Consensus、Sports 等策略
5. **历史分析**: 信号胜率统计、P&L 分析

### 10.2 风险点
- **API Rate Limit**: Polymarket Data API 有速率限制，需控制并发
- **Dry Run 模式**: 默认关闭真实交易，避免误操作
- **价格获取**: `get_market_price` 依赖 Polymarket API，可能不稳定
- **并发控制**: `asyncio.Semaphore(20)` 限制同时请求数
