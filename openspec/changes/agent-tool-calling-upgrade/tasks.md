## 1. 前端修复与消息类型升级

- [ ] 1.1 修复 HomeView.vue 消息展示 bug（移除 v-if/v-else 导致的消息消失）
- [ ] 1.2 扩展 types/index.ts 消息类型（Message / ToolCall / ThinkingStep）
- [ ] 1.3 创建 components/MessageCard.vue（统一渲染 user/assistant/tool/thinking）
- [ ] 1.4 创建 components/ToolCallBlock.vue（展示工具调用过程）
- [ ] 1.5 创建 components/ThinkingBlock.vue（展示分析步骤）
- [ ] 1.6 更新 useWebSocket.ts 支持新消息类型

## 2. 后端工具定义与注册

- [ ] 2.1 创建 services/tools/definitions.py（定义工具 Schema）
- [ ] 2.2 创建 services/tools/registry.py（工具注册和执行器）
- [ ] 2.3 实现 get_price 工具（调用 CoinGecko API）
- [ ] 2.4 实现 get_market_cap 工具（调用 CoinGecko API）
- [ ] 2.5 实现 get_funding_rate 工具（调用 OKX/Hyperliquid）
- [ ] 2.6 实现 scrape_binance_square 工具（调用 Binance Square scraper）
- [ ] 2.7 实现 analyze_sentiment 工具（调用 LLM 分析情绪）

## 3. Function Calling 与 Agent 编排

- [ ] 3.1 修改 services/skill_router.py 支持 LLM Function Calling
- [ ] 3.2 创建 services/agent_graph.py（Agent 状态机）
- [ ] 3.3 实现 analyze_intent 节点（LLM 分析意图）
- [ ] 3.4 实现 select_tools 节点（LLM 选择工具）
- [ ] 3.5 实现 execute_tools 节点（并行执行工具）
- [ ] 3.6 实现 summarize 节点（LLM 汇总结果）
- [ ] 3.7 添加错误处理和 fallback 逻辑（LLM 不支持 Function Calling 时 fallback 到关键词匹配）
- [ ] 3.8 实现并行工具超时控制（单个工具 10s，整体 60s）

## 4. WebSocket 流式输出扩展

- [ ] 4.1 修改 api/ws.py 新增 thinking 消息类型
- [ ] 4.2 修改 api/ws.py 新增 tool_call_start 消息类型
- [ ] 4.3 修改 api/ws.py 新增 tool_call_result 消息类型
- [ ] 4.4 修改 api/ws.py 新增 stream 消息类型
- [ ] 4.5 实现消息流式推送（think → tool_call → result → stream）
- [ ] 4.6 添加消息格式标准化（type/data/timestamp）

## 5. Session 会话管理

- [ ] 5.1 修改 database.py 添加 sessions 表
- [ ] 5.2 修改 database.py 添加 messages 表
- [ ] 5.3 创建 services/session.py（Session 管理器）
- [ ] 5.4 实现 WebSocket 连接时创建 session_id
- [ ] 5.5 实现消息持久化存储
- [ ] 5.6 实现上下文注入（发送历史到 LLM prompt）
- [ ] 5.7 添加 Session 过期清理（7 天）

## 6. 集成测试与优化

- [ ] 6.1 测试 Function Calling 流程（analyze_intent → select_tools → execute → summarize）
- [ ] 6.2 测试并行工具调用（asyncio.gather）
- [ ] 6.3 测试 WebSocket 流式输出
- [ ] 6.4 测试 Session 连续对话
- [ ] 6.5 测试错误处理和 fallback
- [ ] 6.6 性能测试（并行调用延迟）
- [ ] 6.7 更新文档和 README

## 7. 移除旧路由（Phase 4 最后）

- [ ] 7.1 移除 skill_router.py 中的关键词路由逻辑
- [ ] 7.2 清理无用代码和测试
- [ ] 7.3 验证所有功能正常
