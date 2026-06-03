# AI Trading Agent 技术升级计划（结合本地项目）

## 一、本地项目现状

### 当前架构
```
Frontend (Vue 3 + Vite + WebSocket)
  ├── HomeView.vue        ← 聊天界面（问题：消息发送后消失/布局崩溃）
  ├── TradingView.vue     ← 交易面板
  ├── WorkflowView.vue    ← 工作流设置
  └── composables/
      ├── useAgent.ts     ← 状态管理
      └── useWebSocket.ts ← WebSocket 连接

Backend (FastAPI)
  ├── api/ws.py           ← WebSocket 入口
  ├── api/tasks.py        ← 任务启停
  ├── services/skill_router.py     ← 关键词意图分类（太简单）
  ├── services/agent_runner.py     ← browser-use agent
  ├── services/llm_factory.py     ← LLM 创建
  ├── services/datasources/         ← CoinGecko/OKX/Hyperliquid
  └── services/signal_*.py         ← 信号分析
```

### 当前问题
1. **前端**：发消息后消息消失、布局崩溃（flex 嵌套问题）
2. **后端意图**：只有关键词匹配，无法处理复杂需求
3. **工具调用**：只有"直接返回文案"，没有真正的 Function Calling
4. **分析过程**：用户看不到 AI 在查什么、怎么分析
5. **会话管理**：无 Session，每次请求独立

---

## 二、参考项目分析

### 1. Vercel AI SDK（前端参考）

**核心概念**：
- `useChat()` — React hook，管理消息流、loading、错误状态
- `Message` 类型 — 区分 user / assistant / tool / thinking 角色
- `ToolCall` 组件 — 展示"调用 get_price(BTC)"的过程
- `createDataStreamResponse` — 后端流式输出，前端实时渲染

**本地适配**：
- Vue 版 `useChat`：管理 `messages` 数组 + `status`（idle/streaming/tool_call/error）
- `MessageCard` 组件：根据 `role` 渲染不同样式
- `ToolCallBlock`：展示工具调用过程（名称、参数、结果）

```typescript
// 消息类型扩展（参考 Vercel AI SDK）
interface Message {
  id: string
  role: 'user' | 'assistant' | 'tool' | 'thinking'
  content: string
  tool_calls?: ToolCall[]      // 工具调用记录
  thinking_steps?: Step[]    // 思考步骤
  created_at: Date
}

interface ToolCall {
  id: string
  name: string                 // e.g. "get_price"
  arguments: Record<string, any>  // e.g. { symbol: "BTC" }
  status: 'pending' | 'running' | 'done' | 'error'
  result?: any                // 工具返回结果
  duration_ms?: number
}

interface Step {
  step: number
  action: string             // e.g. "分析用户意图"
  status: string
  timestamp: Date
}
```

### 2. OpenAI Function Calling（后端参考）

**核心概念**：
- 工具定义 = `name + description + parameters(schema)`
- LLM 根据用户输入自动选择工具、提取参数
- 多轮调用：call → result → call → result → final_answer

**本地适配**：

```python
# tools/definitions.py
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_price",
            "description": "获取加密货币的实时价格",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "币种符号，如 BTC、ETH、SOL"
                    }
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_cap",
            "description": "获取加密货币的市值排名和数据",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "币种符号"
                    }
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_funding_rate",
            "description": "获取资金费率",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": { "type": "string" },
                    "exchange": {
                        "type": "string",
                        "enum": ["okx", "hyperliquid"],
                        "description": "交易所"
                    }
                },
                "required": ["symbol", "exchange"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scrape_binance_square",
            "description": "扫描 Binance Square 帖子，提取信号",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": { "type": "integer", "default": 20 },
                    "token_filter": { "type": "string", "description": "只关注某个代币" }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_sentiment",
            "description": "对文本进行情绪分析",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": { "type": "string" }
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_trade",
            "description": "执行交易（需要用户确认）",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": { "type": "string" },
                    "side": { "type": "string", "enum": ["buy", "sell"] },
                    "amount": { "type": "number" }
                },
                "required": ["symbol", "side", "amount"]
            }
        }
    }
]
```

### 3. LangChain/LangGraph（Agent 编排参考）

**核心概念**：
- `StateGraph` — 状态机，节点 = 步骤，边 = 流转
- `Memory` — 会话历史管理
- `Agent` — ReAct 模式（Thought → Action → Observation）

**本地适配**（简化版 StateGraph）：

```python
# services/agent_graph.py
from typing import TypedDict, List, Any, Optional
from dataclasses import dataclass

class AgentState(TypedDict):
    """Agent 状态机"""
    messages: List[dict]           # 对话历史
    user_input: str                # 当前输入
    intent: Optional[str]         # 识别出的意图
    tool_calls: List[dict]        # 要执行的工具
    tool_results: List[dict]      # 工具返回结果
    final_answer: Optional[str]   # 最终回复
    status: str                   # 当前状态

# 节点 1: 意图分析
def analyze_intent(state: AgentState) -> AgentState:
    """用 LLM 分析用户意图"""
    ...

# 节点 2: 工具选择
ndef select_tools(state: AgentState) -> AgentState:
    """根据意图选择要调用的工具"""
    ...

# 节点 3: 并行执行工具
def execute_tools(state: AgentState) -> AgentState:
    """并发调用多个工具"""
    ...

# 节点 4: 汇总结果
def summarize(state: AgentState) -> AgentState:
    """用 LLM 汇总工具结果，生成最终回复"""
    ...

# 构建图
graph = StateGraph(AgentState)
graph.add_node("analyze_intent", analyze_intent)
graph.add_node("select_tools", select_tools)
graph.add_node("execute_tools", execute_tools)
graph.add_node("summarize", summarize)

graph.set_entry_point("analyze_intent")
graph.add_edge("analyze_intent", "select_tools")
graph.add_edge("select_tools", "execute_tools")
graph.add_edge("execute_tools", "summarize")
```

---

## 三、升级实施计划

### Phase 1: 修复前端 + 消息类型升级（1 天）

**目标**：让聊天正常显示，支持多种消息类型

**文件清单**：
- `frontend/src/types/index.ts` — 扩展 Message 类型
- `frontend/src/views/HomeView.vue` — 修复布局 + 支持新消息类型
- `frontend/src/components/MessageCard.vue` — 新组件
- `frontend/src/components/ToolCallBlock.vue` — 工具调用展示
- `frontend/src/components/ThinkingBlock.vue` — 思考过程展示

**关键改动**：
1. 消息类型从 `ChatMessage = { role, text, timestamp }` 升级
2. 移除 `v-if/v-else` 导致的消息消失 bug
3. `messages` 数组不再由前端生成，由 WebSocket 消息驱动
4. 添加 `status` 管理：idle / streaming / tool_calling / complete / error

**前端消息流**：
```
用户输入 → sendCommand(text) → WebSocket 发送
  ↓
WebSocket 接收 ← 服务端推送
  ↓
根据 msg.type 决定渲染方式：
  - 'thinking' → ThinkingBlock（灰色、可折叠）
  - 'tool_call' → ToolCallBlock（显示工具名、参数、执行结果）
  - 'stream' → MessageBubble（流式输出，逐字显示）
  - 'result' → MessageBubble（最终回复）
```

### Phase 2: 后端工具架构 + Function Calling（2-3 天）

**目标**：LLM 自动选择工具，真正调用 API

**文件清单**：
- `backend/services/tools/definitions.py` — 工具定义
- `backend/services/tools/registry.py` — 工具注册和执行
- `backend/services/tools/__init__.py` — 导出
- `backend/services/agent_graph.py` — Agent 状态机
- `backend/services/tool_executor.py` — 并行工具执行
- `backend/api/ws.py` — 修改 WebSocket 消息协议

**后端消息流（WebSocket）**：
```
用户发送消息
  ↓
skill_router.route() — 改为 LLM 意图分析
  ↓
AgentState 初始化
  ↓
analyze_intent() — LLM 分析意图
  ↓
select_tools() — 选择工具（可能有多个）
  ↓
发送 tool_call_start → WebSocket → 前端显示 ToolCallBlock
  ↓
并行 execute_tools() — 真正调用 CoinGecko/OKX/Hyperliquid
  ↓
发送 tool_call_result → WebSocket → 前端更新 ToolCallBlock
  ↓
summarize() — LLM 汇总结果
  ↓
发送 stream → WebSocket → 前端流式显示
  ↓
发送 result → WebSocket → 最终回复
```

**WebSocket 消息协议扩展**：
```python
# 服务端 → 客户端
{
    "type": "thinking",
    "data": {
        "step": 1,
        "action": "分析用户意图",
        "detail": "用户想查询 BTC 的价格和市值"
    }
}

{
    "type": "tool_call_start",
    "data": {
        "tool_call_id": "call_123",
        "name": "get_price",
        "arguments": {"symbol": "BTC"}
    }
}

{
    "type": "tool_call_result",
    "data": {
        "tool_call_id": "call_123",
        "name": "get_price",
        "result": {"symbol": "BTC", "price": 64320, "change_24h": 2.3}
    }
}

{
    "type": "stream",
    "data": {
        "chunk": "BTC 当前价格为 $64,320",
        "is_final": false
    }
}

{
    "type": "result",
    "data": {
        "output": "BTC 当前价格为 $64,320，24小时涨幅 +2.3%...",
        "tools_used": ["get_price", "get_market_cap"],
        "steps": 3,
        "duration_ms": 2450
    }
}
```

### Phase 3: Session 会话管理（1-2 天）

**目标**：支持连续对话

**文件清单**：
- `backend/services/session.py` — Session 管理
- `backend/services/database.py` — 添加 messages 表
- `frontend/src/composables/useWebSocket.ts` — 添加 session_id

**Session 结构**：
```python
@dataclass
class Session:
    id: str                    # UUID
    created_at: datetime
    updated_at: datetime
    messages: List[Message]    # 对话历史
    context: dict              # 上下文（用户偏好、持仓等）

@dataclass
class Message:
    role: str                  # user / assistant / tool
    content: str
    tool_calls: Optional[List]
    created_at: datetime
```

### Phase 4: Agent 编排优化（3-5 天）

**目标**：复杂任务自动编排

**示例**：用户说"帮我分析 BTC"

```
Agent 自动执行：
1. 意图分析 → "综合分析请求"
2. 工具选择 → get_price, get_market_cap, get_funding_rate, scrape_binance_square
3. 并行执行 →
   - get_price(BTC) → $64,320
   - get_market_cap(BTC) → $1.2T
   - get_funding_rate(BTC, okx) → 0.01%
   - scrape_binance_square(token_filter="BTC") → [帖子1, 帖子2]
4. 情绪分析 → analyze_sentiment(帖子内容)
5. 汇总 → LLM 生成综合分析报告
```

---

## 四、关键改造点

### 前端改造

```vue
<!-- HomeView.vue -->
<template>
  <div class="chat-app">
    <div class="messages-wrapper">
      <div v-for="msg in messages" :key="msg.id" class="message">
        <MessageCard :message="msg" />
      </div>
    </div>
    <div class="chat-footer">
      <textarea v-model="inputText" @keydown="handleKeydown" />
    </div>
  </div>
</template>
```

```vue
<!-- MessageCard.vue -->
<template>
  <div :class="['message-card', message.role]">
    <!-- 用户消息 -->
    <template v-if="message.role === 'user'">
      <div class="user-bubble">{{ message.content }}</div>
    </template>

    <!-- AI 回复 -->
    <template v-if="message.role === 'assistant'">
      <div class="assistant-bubble">
        <!-- 思考过程 -->
        <ThinkingBlock v-if="message.thinking_steps" :steps="message.thinking_steps" />

        <!-- 工具调用 -->
        <ToolCallBlock v-if="message.tool_calls" :tools="message.tool_calls" />

        <!-- 内容 -->
        <div class="content">{{ message.content }}</div>
      </div>
    </template>
  </div>
</template>
```

```vue
<!-- ToolCallBlock.vue -->
<template>
  <div class="tool-call-block">
    <div v-for="tool in tools" :key="tool.id" class="tool-call">
      <div class="tool-header">
        <span class="tool-icon">🔧</span>
        <span class="tool-name">{{ tool.name }}</span>
        <span :class="['tool-status', tool.status]">{{ tool.status }}</span>
      </div>
      <div class="tool-args">{{ JSON.stringify(tool.arguments) }}</div>
      <div v-if="tool.result" class="tool-result">
        <pre>{{ JSON.stringify(tool.result, null, 2) }}</pre>
      </div>
    </div>
  </div>
</template>
```

### 后端改造

```python
# api/ws.py
@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    session_id = generate_session_id()
    session = SessionManager.get_or_create(session_id)

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            user_input = msg["command"]

            # 1. 发送 thinking 开始
            await ws.send_json({
                "type": "thinking",
                "data": {"step": 1, "action": "分析意图..."}
            })

            # 2. LLM 分析意图 + 选择工具
            intent, tools = await analyze_intent_with_llm(user_input)

            # 3. 发送 tool_call_start
            for tool in tools:
                await ws.send_json({
                    "type": "tool_call_start",
                    "data": tool
                })

            # 4. 执行工具
            results = await execute_tools_parallel(tools)

            # 5. 发送 tool_call_result
            for result in results:
                await ws.send_json({
                    "type": "tool_call_result",
                    "data": result
                })

            # 6. LLM 汇总
            final_answer = await summarize_with_llm(user_input, results)

            # 7. 发送最终回复
            await ws.send_json({
                "type": "result",
                "data": {"output": final_answer}
            })

    except WebSocketDisconnect:
        pass
```

---

## 五、实施顺序

### 第 1 步：修复前端 bug（当天完成）
- [ ] 修复 `HomeView.vue` flex 布局
- [ ] 移除 `v-if/v-else` 导致的消息消失
- [ ] 确保 `messages` 数组正确渲染

### 第 2 步：扩展消息类型（当天完成）
- [ ] 扩展 `types/index.ts` 添加 `ToolCall`、`ThinkingStep`
- [ ] 创建 `MessageCard.vue`、`ToolCallBlock.vue`、`ThinkingBlock.vue`

### 第 3 步：后端工具定义（1-2 天）
- [ ] 创建 `tools/definitions.py` 定义所有工具 schema
- [ ] 创建 `tools/registry.py` 实现工具注册和执行
- [ ] 测试工具单独调用

### 第 4 步：Function Calling（1-2 天）
- [ ] 修改 `skill_router.py` 用 LLM 做意图分析
- [ ] 实现工具选择和参数提取
- [ ] 并行工具执行

### 第 5 步：WebSocket 流式输出（1 天）
- [ ] 扩展 WebSocket 消息协议
- [ ] 实现 thinking → tool_call → result 的流式推送
- [ ] 前端实时渲染

### 第 6 步：Session 管理（1-2 天）
- [ ] 添加 session_id
- [ ] 消息历史存储
- [ ] 上下文注入 LLM

### 第 7 步：Agent 编排优化（3-5 天）
- [ ] 实现 StateGraph 状态机
- [ ] 复杂任务自动编排
- [ ] 并行工具调用优化

---

## 六、参考资源

| 项目 | 链接 | 学习重点 |
|------|------|----------|
| Vercel AI SDK | https://github.com/vercel/ai | useChat、ToolCall UI、流式输出 |
| OpenAI Function Calling | https://platform.openai.com/docs/guides/function-calling | Tool Schema、参数提取 |
| LangGraph | https://github.com/langchain-ai/langgraph | StateGraph、Agent 编排 |
| LangChain Tools | https://python.langchain.com/docs/modules/agents/tools/ | 工具定义和调用 |

---

## 七、下一步

现在开始实施 **第 1 步**（修复前端 bug + 扩展消息类型）？
