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

- **services/signal_scraper.py** — 信号抓取
- **services/signal_analyzer.py** — 信号分析（LLM）
- **services/hot_tokens_scanner.py** — 热门代币扫描
- **services/square_scraper.py** — Binance Square 帖子抓取
- **services/filter_engine.py** — 信号过滤引擎

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
