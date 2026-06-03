# Agent Tool Calling Upgrade Design Spec

## Overview

Upgrade the AI Trading Agent from keyword-based routing to LLM-driven Function Calling with real-time analysis visualization.

## Context

Current system uses simple keyword matching for intent classification. When user says "check BTC price", the system returns static text instead of calling actual APIs. Users cannot see what the AI is analyzing, which data sources are queried, or how results are aggregated.

## Goals

1. Implement Function Calling architecture with tool schema definitions
2. Real-time visualization of AI analysis process (thinking → tool_call → result)
3. Support parallel multi-tool execution with result aggregation
4. Fix frontend message display bugs and support multiple message types
5. Add session management for continuous conversation context

## Non-Goals

- Replace existing browser-use agent (kept as one of the tools)
- Implement fully autonomous trading decisions (user confirmation required)
- Add external LLM providers (uses existing llm_factory)

## Architecture

### Backend

```
services/
  tools/
    definitions.py    # Tool schemas (get_price, get_market_cap, etc.)
    registry.py       # Tool registration and executor
  agent_graph.py      # Agent state machine
  session.py          # Session management
  skill_router.py     # Upgraded to Function Calling
```

### Frontend

```
components/
  MessageCard.vue     # Unified message rendering
  ToolCallBlock.vue   # Tool call visualization
  ThinkingBlock.vue   # Analysis step display
composables/
  useWebSocket.ts     # Extended for new message types
```

### WebSocket Protocol

New message types:
- `thinking` - Analysis step
- `tool_call_start` - Tool invocation beginning
- `tool_call_result` - Tool result
- `stream` - Streaming text output

## Design Decisions

### 1. Function Calling over Keyword Matching
- **Why**: Keywords cannot handle complex intents (e.g., "analyze SOL" needs price + market cap + sentiment)
- **Benefit**: LLM selects multiple tools automatically; no code changes when adding tools

### 2. WebSocket Streaming over HTTP Polling
- **Why**: Existing WebSocket infrastructure; unified communication
- **Benefit**: Real-time tool call visualization

### 3. Message Type Extension
- **Why**: Tool calls are part of AI response, should bind to assistant message
- **Benefit**: Unified rendering in MessageCard component

### 4. Parallel Tool Execution
- **Why**: "Analyze BTC" can query price, market cap, funding rate, and scrape posts simultaneously
- **Implementation**: `asyncio.gather()` with individual 10s timeout and overall 60s timeout

### 5. SQLite for Session Storage
- **Why**: Existing infrastructure; single-user personal tool
- **Benefit**: No new dependencies

## Streaming Granularity

- **thinking**: Complete object pushed once
- **tool_call_start/tool_call_result**: Complete object pushed once
- **stream**: Character-by-character streaming (per token)

## Timeout Strategy

- Individual tool: 10s timeout → skip and continue
- Overall execution: 60s timeout → return completed results + timeout notice
- Fallback: If LLM doesn't support Function Calling, fall back to keyword matching

## Message Type Fallback

- Frontend silently ignores unknown message types via `v-if` conditional rendering
- No errors thrown for unrecognized types

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| LLM selects wrong tool or extracts invalid params | Clear tool descriptions; pydantic validation; fallback to generic response |
| Streaming increases backend complexity | Unified AgentState; independently testable nodes |
| Frontend compatibility with new types | Conditional rendering; optional fields |

## Migration Plan

1. **Phase 1**: Fix frontend message display bug
2. **Phase 2**: Add Function Calling backend (parallel with existing routing)
3. **Phase 3**: Add ToolCallBlock/ThinkingBlock components
4. **Phase 4**: Remove keyword routing, switch fully to Function Calling
5. **Phase 5**: Add session management

## Open Questions

1. LLM Function Calling compatibility with MiniMax-M2.7 → fallback to keyword matching if unsupported
2. Tool result length for Binance Square scraping → truncate to top 10 posts + statistics
3. Session cleanup frequency → 7-day expiration
