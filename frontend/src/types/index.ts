export interface AppConfig {
  api_key_masked: string
  base_url: string
  model: string
  protocol: 'openai' | 'anthropic'
  configured: boolean
  browser_mode: 'local' | 'cloud'
  browser_use_api_key_masked: string
  // Trading config
  binance_api_key_masked: string
  binance_testnet: boolean
  binance_mode: 'futures' | 'spot'
  trading_enabled: boolean
  max_position_size_usd: number
  tp_percentage: number
  sl_percentage: number
  min_confidence: number
  scan_interval_minutes: number
}

export interface StepData {
  step: number
  action: string
  target: string
  status: 'running' | 'done' | 'error'
  screenshot: string | null
}

export interface ResultData {
  output: string
  steps: number
  duration_ms: number
}

export interface ErrorData {
  message: string
  step: number
}

export interface LiveUrlData {
  url: string
}

export interface QueueStatusData {
  pending: number
}

export interface ThinkingData {
  step: number
  description: string
}

export interface ToolCallStartData {
  tool: string
  arguments: Record<string, unknown>
}

export interface ToolCallResultData {
  tool: string
  result: unknown
}

export interface StreamData {
  text: string
}

export interface WsMessage {
  type: 'step' | 'result' | 'error' | 'cancelled' | 'interactive' | 'live_url' | 'queue_status' | 'thinking' | 'tool_call_start' | 'tool_call_result' | 'stream' | 'hot_tokens_update'
  data: StepData | ResultData | ErrorData | LiveUrlData | QueueStatusData | ThinkingData | ToolCallStartData | ToolCallResultData | StreamData | HotToken[] | Record<string, never>
  timestamp?: string
}

// Task configuration options
export interface TaskOptions {
  task: string
  sensitive_data?: Record<string, string | Record<string, string>>
  initial_actions?: Array<Record<string, Record<string, any>>>
  use_vision?: boolean
  headless?: boolean
  max_failures?: number
  max_actions_per_step?: number
  step_timeout?: number
}

export interface HotToken {
  symbol: string
  price: number
  price_change_24h: number
  volume_24h: number
  volume_usd: number
  funding_rate: number
  long_short_ratio: number
  open_interest: number
  liquidation_price: number
  heat_score: number
  heat_rank?: number
  updated_at?: string
}

export interface HotTokensUpdateData {
  type: 'hot_tokens_update'
  data: HotToken[]
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
  timestamp: Date
}

export interface ToolCall {
  name: string
  arguments: Record<string, unknown>
  status: 'pending' | 'completed' | 'error'
  result?: unknown
}

export interface ThinkingStep {
  step: number
  description: string
}

export interface ExtendedChatMessage {
  role: 'user' | 'assistant'
  text: string
  timestamp: Date
  toolCalls?: ToolCall[]
  thinkingSteps?: ThinkingStep[]
}
