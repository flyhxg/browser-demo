export interface ProviderConfig {
  model: string
  configured: boolean
}

export interface OpenAIConfig extends ProviderConfig {
  api_key_masked: string
}

export interface AnthropicConfig extends ProviderConfig {
  api_key_masked: string
}

export interface GoogleConfig extends ProviderConfig {
  api_key_masked: string
}

export interface DeepSeekConfig extends ProviderConfig {
  api_key_masked: string
}

export interface GroqConfig extends ProviderConfig {
  api_key_masked: string
}

export interface OllamaConfig extends ProviderConfig {
  url: string
}

export interface AppConfig {
  providers: {
    openai: OpenAIConfig
    anthropic: AnthropicConfig
    google: GoogleConfig
    deepseek: DeepSeekConfig
    groq: GroqConfig
    ollama: OllamaConfig
  }
  browser: {
    mode: 'local' | 'cloud'
    cloud_api_key: string
  }
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

export interface WsMessage {
  type: 'step' | 'result' | 'error' | 'cancelled'
  data: StepData | ResultData | ErrorData | Record<string, never>
}
