// WebSocket message types — single source of truth for which event
// types the server may broadcast. Adding a new server event means:
//   1. Add the literal to WsMessageType
//   2. Add the data shape to WsMessageByType
//   3. Subscribe via bus.on(<type>, handler) in the relevant component

import type {
  HotToken,
  Signal,
  TokenAnalysisReport,
  StepData,
  ResultData,
  ErrorData,
  LiveUrlData,
  QueueStatusData,
  ThinkingData,
  ToolCallStartData,
  ToolCallResultData,
  StreamData,
  InteractiveCommand,
  TradeExecutedData,
  TradeClosedData,
  AnalysisShortProgress,
  AnalysisShortComplete,
} from './index'

export type WsMessageType =
  | 'hot_tokens_update'
  | 'signal:new'
  | 'signal:analyzed'
  | 'analysis:short'
  | 'analysis:short:complete'
  | 'trade:executed'
  | 'trade:closed'
  | 'step'
  | 'result'
  | 'error'
  | 'history'
  | 'cancelled'
  | 'live_url'
  | 'queue_status'
  | 'thinking'
  | 'tool_call_start'
  | 'tool_call_result'
  | 'interactive'
  | 'stream'

// Discriminated union — when a handler subscribes to a given type,
// TypeScript narrows `data` to the right shape automatically.
export interface WsMessageByType {
  'hot_tokens_update': HotToken[]
  'signal:new': Signal
  'signal:analyzed': { signal: Signal; report: TokenAnalysisReport }
  'analysis:short': AnalysisShortProgress
  'analysis:short:complete': AnalysisShortComplete
  'trade:executed': TradeExecutedData
  'trade:closed': TradeClosedData
  'step': StepData
  'result': ResultData
  'error': ErrorData
  'history': { messages: Array<{ role: 'user' | 'assistant'; content: string; created_at?: string }> }
  'cancelled': null
  'live_url': LiveUrlData
  'queue_status': QueueStatusData
  'thinking': ThinkingData
  'tool_call_start': ToolCallStartData
  'tool_call_result': ToolCallResultData
  'interactive': InteractiveCommand
  'stream': StreamData
}

export interface WsMessage<T extends WsMessageType = WsMessageType> {
  type: T
  data: WsMessageByType[T]
  timestamp?: string
}
