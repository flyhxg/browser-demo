## Context

当前 AI Trading Agent 的聊天系统使用简单的关键词匹配（keyword matching）进行意图分类，用户输入"查下 BTC 价格"时，系统只是返回一句固定文案，没有真正调用任何数据源 API。用户完全无法看到 AI 的"思考过程"和"工具调用过程"，导致系统缺乏透明度和可信度。

我们需要引入 OpenAI Function Calling 模式，让 LLM 自动选择工具、提取参数、调用 API，并实时展示分析过程。同时参考 Vercel AI SDK 的消息流式输出和 LangGraph 的 Agent 编排模式，构建一个可观测、可扩展的工具调用架构。

## Goals / Non-Goals

**Goals:**
1. 实现 Function Calling 工具调用架构，LLM 自动选择工具并提取参数
2. 实时展示 AI 的分析过程（thinking → tool_call → result）
3. 支持多工具并行调用和结果汇总
4. 修复前端消息展示 bug，支持多种消息类型
5. 添加 Session 会话管理，支持连续对话

**Non-Goals:**
- 不替换现有的 browser-use agent（作为工具之一保留）
- 不实现真正的"自主决策交易"（需要用户确认）
- 不接入外部 LLM 提供商（使用现有 llm_factory）

## Decisions

### 1. Function Calling 模式而非关键词匹配
**选择**：使用 OpenAI Function Calling 模式（Tool Schema + LLM 选择）
**替代方案**：继续使用关键词匹配，或基于规则的分类器
**原因**：
- 关键词匹配无法处理复杂意图（如"帮我分析下 SOL 最近的情况"涉及价格+市值+情绪多个维度）
- LLM 可以一次性识别多个工具调用需求
- 未来新增工具不需要修改分类逻辑

### 2. WebSocket 流式输出而非 HTTP 轮询
**选择**：扩展 WebSocket 协议，新增 thinking/tool_call/stream 消息类型
**替代方案**：HTTP SSE（Server-Sent Events）
**原因**：
- 已有 WebSocket 基础设施，无需引入新协议
- 工具调用结果需要多次推送（start → result → next tool → ...）
- 保持前后端通信统一

### 3. 前端消息类型扩展（Vue reactive）
**选择**：扩展 `Message` 类型，添加 `tool_calls`、`thinking_steps` 字段
**替代方案**：单独维护 tool_call 状态，不与消息绑定
**原因**：
- 工具调用是 AI 回复的一部分，应该与 assistant 消息绑定展示
- 参考 Vercel AI SDK 的 Message 类型设计
- 便于前端组件（MessageCard）统一渲染

### 4. 并行工具调用
**选择**：`asyncio.gather()` 并行执行多个工具
**替代方案**：串行执行
**原因**：
- 用户说"分析 BTC"时，可以同时查价格、市值、资金费率、扫描帖子
- 串行执行会增加总延迟
- LangGraph 等框架也推荐并行执行独立工具

### 5. Session 存储在 SQLite 而非 Redis
**选择**：使用现有 SQLite 数据库
**替代方案**：引入 Redis 或内存存储
**原因**：
- 项目已有 SQLite 基础设施
- Session 数据量小（单用户个人使用），SQLite 足够
- 避免引入新依赖

## Risks / Trade-offs

**[风险] LLM Function Calling 可靠性**
- 问题：LLM 可能选错工具、参数提取错误
- 缓解：
  - 工具描述要非常明确
  - 添加参数验证（pydantic schema）
  - 失败后 fallback 到通用回复

**[风险] 流式输出增加后端复杂度**
- 问题：需要维护多个消息类型和状态机
- 缓解：
  - 使用统一的 AgentState 管理状态
  - 每个节点（intent → tools → execute → summarize）独立测试

**[风险] 前端兼容性**
- 问题：扩展消息类型后，旧版本前端可能无法正确渲染
- 缓解：
  - 前端组件使用 `v-if` 条件渲染（不认识的 type 不报错）
  - tool_calls 和 thinking_steps 为可选字段

**[Trade-off] 实时性 vs. 完整性**
- 思考过程实时展示会增加网络传输
- 但用户的等待体验更好（知道 AI 在做什么）

## Migration Plan

1. **Phase 1**：前端修复消息展示 bug（不影响现有功能）
2. **Phase 2**：后端添加 Function Calling 架构（并行运行，旧的关键词路由保留为 fallback）
3. **Phase 3**：前端添加 ToolCallBlock、ThinkingBlock 组件
4. **Phase 4**：移除旧的关键词路由，全面切换到 Function Calling
5. **Phase 5**：添加 Session 管理

## Open Questions

1. **工具调用的超时时间**：并行调用多个工具时，一个工具超时怎么办？
   - 暂定：单个工具超时 10s，整体超时 60s
2. **工具结果太长**：扫描 Binance Square 返回 50 条帖子，LLM 上下文装不下怎么办？
   - 暂定：工具返回结果做摘要（取前 10 条 + 统计）
3. **Session 过期时间**：多久清理一次？
   - 暂定：7 天过期

## Design Decisions

### 6. 流式推送粒度
**选择**：按步骤推 + stream 按字符推（方案3）
- thinking 完整推送（一次性）
- tool_call_start/tool_call_result 完整推送（一次性）
- stream 按字符流推送（逐 token）

### 7. 并行工具超时策略
**选择**：部分失败不影响整体
- 单个工具超时（10s）→ 跳过该工具，继续执行其他工具
- 整体超时（60s）→ 返回已完成的工具结果 + 超时提示

### 8. 消息类型 fallback
**选择**：前端静默忽略不认识的消息类型
- 收到未知的 `type` → 不渲染，不报错
- 通过 `v-if` 条件渲染实现

### 9. LLM Function Calling 兼容性
**选择**：检测 LLM 能力，不支持时 fallback 到关键词匹配
- LLM 返回 `tool_calls` → 走 Function Calling 流程
- LLM 不支持 → fallback 到现有 `skill_router.py` 关键词匹配
- 前端无需感知差异
