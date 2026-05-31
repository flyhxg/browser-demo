export interface AppConfig {
  api_key_masked: string
  base_url: string
  model: string
  protocol: 'openai' | 'anthropic'
  configured: boolean
  browser_mode: 'local' | 'cloud'
  browser_use_api_key_masked: string
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

export interface WsMessage {
  type: 'step' | 'result' | 'error' | 'cancelled' | 'interactive' | 'live_url' | 'queue_status'
  data: StepData | ResultData | ErrorData | LiveUrlData | QueueStatusData | Record<string, never>
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

export interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
  timestamp: Date
}
