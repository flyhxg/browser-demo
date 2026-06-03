## Why

当前 AI Trading Agent 的聊天系统只有简单的关键词意图分类（keyword matching），用户说"查下 BTC 价格"只是返回一句固定文案，没有真正调用 API。用户完全看不到 AI 在分析什么、查了哪些数据源、结果如何汇总。这导致系统缺乏"Agent"的透明度和可信度。引入 Function Calling 和 Agent 编排后，AI 能自动选择工具（查价格、查市值、扫描帖子、情绪分析），并实时展示分析过程。

## What Changes

- **前端**：扩展消息类型，新增 `tool_call`、`thinking` 角色；创建 `ToolCallBlock`、`ThinkingBlock` 组件展示分析过程；修复消息消失 bug
- **后端**：引入 OpenAI Function Calling 模式，定义工具 Schema（get_price、get_market_cap、scrape_binance_square 等）；实现 Agent 编排引擎（analyze_intent → select_tools → execute → summarize）
- **协议**：WebSocket 新增 `thinking`、`tool_call_start`、`tool_call_result`、`stream` 消息类型，支持流式输出
- **Session**：添加 session_id，支持连续对话和上下文记忆

## Capabilities

### New Capabilities
- `tool-calling`: Function Calling 工具调用架构，定义工具 Schema，LLM 自动选择工具并提取参数
- `agent-execution`: Agent 分析执行引擎，支持多步骤编排和并行工具调用
- `message-streaming`: 流式消息输出，实时展示 thinking、tool_call、stream 过程
- `session-management`: Session 会话管理，支持连续对话和上下文记忆

### Modified Capabilities
- `skill-router`: 从关键词匹配升级为 LLM Function Calling 意图分析
- `websocket-protocol`: 扩展消息类型，新增 thinking/tool_call_start/tool_call_result/stream

## Impact

- **Frontend**: `types/index.ts`（扩展消息类型）、`views/HomeView.vue`（修复布局 + 支持新消息）、新增 `components/MessageCard.vue`、`ToolCallBlock.vue`、`ThinkingBlock.vue`
- **Backend**: `services/skill_router.py`（升级为 Function Calling）、新增 `services/tools/definitions.py`、`services/tools/registry.py`、`services/agent_graph.py`、`services/session.py`
- **WebSocket**: `api/ws.py`（扩展消息协议，支持流式推送）
- **Database**: 新增 `sessions`、`messages` 表
