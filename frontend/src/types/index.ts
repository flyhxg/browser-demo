import type { SourceHint } from '../utils/toolSources'

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
  binance_mode: 'futures' | 'spot'
  trading_enabled: boolean
  max_position_size_usd: number
  tp_percentage: number
  sl_percentage: number
  min_confidence: number
  scan_interval_minutes: number
  arkham_api_key_masked: string
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
  source?: SourceHint
}

export interface ToolCallResultData {
  tool: string
  result: unknown
}

export interface StreamData {
  text: string
}

// (Old monolithic WsMessage interface removed — replaced by the
// discriminated union re-exported from ./ws at the bottom of this file.)

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
  // Short analysis (long-side direction, Phase 1a)
  long_crowdedness?: number
  long_squeeze_risk?: number
  extension_score?: number
  short_risk_rating?: string
  short_grade?: string
  short_opportunity_score?: number
  // Hot tick derivations
  oi_usd?: number
  funding_annualized?: number
  // Warm/cold fields (Phase 1b populates; rendered as 0 for now)
  market_cap?: number
  top10_holders_pct?: number
  gini?: number
  fdv_mcap_ratio?: number
  sector?: string
  consecutive_up_days?: number
  trend_strength?: number
  high_24h?: number
  low_24h?: number
  atr?: number
  rebound_multiple?: number
  low_7d?: number
  stop_loss_price?: number
  take_profit_price?: number
  recommended_leverage?: number
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

export interface ToolCallSource {
  label: string
  url: string
}

export type { SourceHint } from '../utils/toolSources'

export interface ToolCall {
  name: string
  arguments: Record<string, unknown>
  status: 'pending' | 'completed' | 'error'
  result?: unknown
  source?: ToolCallSource
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

// WebSocket chat interactive payload (used by HomeView chat UI)
export interface InteractiveCommand {
  type: string
  message: string
  screenshot: string | null
}

// WebSocket trade execution events
export interface TradeExecutedData {
  order_id: string
  symbol: string
  side: 'buy' | 'sell'
  quantity: number
  price: number
}

export interface TradeClosedData {
  symbol: string
  pnl: number
  closed_at: string
}

// WebSocket analysis:short progress events
export interface AnalysisShortProgress {
  stage: string
  progress: number
}

export interface AnalysisShortComplete {
  report: TokenAnalysisReport
}

// Minimal Signal/Report types — arch-refactor-signal-analyzer will
// produce the full Pydantic-aligned version. We declare the bare
// shape here so the discriminated union compiles.
export interface Signal {
  id: number
  source: string
  symbol: string
  content: string
  sentiment: 'bullish' | 'bearish' | 'neutral' | null
  confidence: number
  created_at: string
}

export interface TokenAnalysisReport {
  symbol: string
  sentiment: 'bullish' | 'bearish' | 'neutral'
  confidence: number
  reasoning: string
  hints?: Record<string, string>
}

// Re-export for convenience — components can keep importing from
// './types' as before. The canonical definition lives in ./ws.
export type { WsMessage, WsMessageType, WsMessageByType } from './ws'
