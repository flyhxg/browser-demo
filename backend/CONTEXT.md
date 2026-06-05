# 领域上下文：Backend (FastAPI)

## 概述

Backend 是基于 FastAPI 构建的 Python 服务层，负责意图分析、工具调用、数据聚合和会话管理。

## 核心模块

### API 层

- **api/ws.py** — WebSocket 连接管理，消息收发
- **api/tasks.py** — 任务启停控制
- **api/interactive.py** — 交互式命令处理
- **api/polymarket.py** — Polymarket 预测市场接口
- **api/workflow.py** — 工作流配置

### 服务层

- **services/skill_router.py** — 关键词/LLM 意图分类路由
- **services/agent_runner.py** — browser-use agent 执行器
- **services/llm_factory.py** — LLM 实例创建与管理
- **services/config_store.py** — 配置持久化
- **services/database.py** — SQLite 数据存储

### 数据源

- **services/datasources/** — CoinGecko / OKX / Hyperliquid 数据获取
- **services/polymarket_data_api.py** — Polymarket Data API 客户端
- **services/polymarket_trader.py** — Polymarket 交易执行
- **services/polymarket_monitor.py** — Polymarket 持仓监控
- **services/polymarket_poller.py** — Polymarket Top 用户轮询

### 信号与分析

- **services/signal_scraper.py** — Binance Square 帖子抓取（保存为 `posts` 表；历史表名 signals 保留兼容）
- **services/signal_analyzer.py** — LLM 分析服务：输入 Post，输出 Opportunity 候选
- **services/hot_tokens_scanner.py** — 热门代币扫描
- **services/square_scraper.py** — Binance Square 帖子抓取（API 拦截实现）
- **services/filter_engine.py** — Opportunity 过滤引擎（cg/okx/hyperliquid 数据校验）

### 交易引擎

- **services/trading_engine.py** — 交易执行与风险管理
- **services/binance_trader.py** — Binance 交易接口

## 数据流

```
WebSocket 消息 → api/ws.py → skill_router.py → 工具选择/执行 → 结果汇总 → WebSocket 推送
```

## 术语

| 术语 | 说明 |
|------|------|
| skill_router | 意图路由，决定调用哪个工具 |
| agent_runner | browser-use agent 的执行环境 |
| tool_call | LLM 选择工具并传参的过程 |
| session | 一次对话上下文，含消息历史 |
| dry_run | 模拟运行，不真正下单 |

## 风险模块 / Risk Module

`backend/services/risk.py` 统一管理所有风险参数。`TradingEngine` 和 Polymarket 代码都从该模块导入，避免在业务代码中硬编码百分比。

### `RiskConfig` (frozen dataclass)

字段：`max_position_pct`（可用余额的占比，例如 `0.02 = 2%`）、`max_position_usd`（单仓绝对上限）、`max_open_positions`（最大并发持仓数）、`tp_pct` / `sl_pct`（止盈 / 止损以**小数**表示，例如 `0.05 = 5%`、`0.03 = 3%`；dataclass 默认值分别为 `0.05` 和 `0.03`）、`min_position_usd`（默认 `10.0`；低于该阈值的信号会被拒绝）。

### 两种构造方式

- `RiskConfig.from_config_store(config: dict | None = None) -> RiskConfig` — 通过 `services/config_store.get_config()` 从 `config.json` 读取 `position_pct` / `max_position_size_usd` / `max_open_positions` / `tp_percentage` / `sl_percentage`。`tp_percentage` / `sl_percentage` 在 config 中以**百分点**存储（`5.0 = 5%`、`3.0 = 3%`），在构造方法内部通过除以 `100` 转换为小数；这两个键的 `from_config_store` fallback 默认值分别为 `5.0` 和 `3.0`。每次调用都会重新读取配置，因此对 `config.json` 的修改在下次调用时即可生效，无需重启进程（hot-reload）。接受可选的 `config` dict 便于测试。
- `RiskConfig.polymarket() -> RiskConfig` — 预测市场的硬编码常量（`max_position_pct=1.0`、`max_position_usd=10_000.0`、`max_open_positions=10`、`tp_pct=0.05`、`sl_pct=0.15`）。Polymarket 风险参数**不**走 DB。

### 三个纯函数（模块级）

均以 `RiskConfig` 为参数。无全局状态、无 DB、无 I/O，可在任意上下文中安全调用。

- `position_size(available: float, risk: RiskConfig) -> float` — 返回 `min(available * risk.max_position_pct, risk.max_position_usd)`。若结果小于 `risk.min_position_usd`，调用方（如 `TradingEngine.execute_signal`）会跳过该信号并返回 `{"status": "skipped", "reason": "Position size too small"}`（见 `services/trading_engine.py:40-41`）。
- `take_profit_price(entry: float, sentiment: str, risk: RiskConfig) -> float` — `sentiment` 取值 `'bullish'`（做多）或 `'bearish'`（做空）。Bullish：`entry * (1 + risk.tp_pct)`。Bearish：`entry * (1 - risk.tp_pct)`。
- `stop_loss_price(entry: float, sentiment: str, risk: RiskConfig) -> float` — Bullish：`entry * (1 - risk.sl_pct)`。Bearish：`entry * (1 + risk.sl_pct)`。

### 接入 `TradingEngine`

`TradingEngine.__init__` 将 `risk` 声明为**仅关键字**参数（位于签名 `*` 之后：`def __init__(self, api_key, secret_key, use_testnet=False, proxy_url="", *, risk: RiskConfig)`），调用方必须显式传入。已知调用点：

- `api/hot_tokens.py` 和 `services/hot_tokens_scanner.py` 传入 `RiskConfig.from_config_store()`。
- `api/polymarket.py` 传入 `RiskConfig.polymarket()`。

### 新增风险字段

1. 向 `RiskConfig` dataclass 添加字段（若非总是传入则提供默认值）。
2. 添加到 `from_config_store` 的映射中（通过 `cfg.get(...)` 提供默认值）。
3. 在 `tests/test_risk.py` 中补充单元测试。
4. 若 Polymarket 语义不同，需在 `polymarket()` classmethod 中覆盖该值。
