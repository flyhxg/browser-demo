## ADDED Requirements

### Requirement: Multi-provider LLM configuration storage
The system SHALL store configuration for multiple LLM providers, each with provider name, API Key (or Ollama URL), model selection, and validation status. Configuration SHALL persist across server restarts via a local file.

#### Scenario: Store API Key for a provider
- **WHEN** a new API Key is saved for a provider (OpenAI, Claude, Gemini, DeepSeek, Groq)
- **THEN** the Key is stored securely and the provider is marked as configured

#### Scenario: Store Ollama connection settings
- **WHEN** Ollama URL and model are saved
- **THEN** the connection settings are stored and Ollama is marked as configured if the server is reachable

#### Scenario: Configuration persists after restart
- **WHEN** the server is restarted
- **THEN** all previously saved configurations are loaded from the local file

### Requirement: API Key masking
The system SHALL mask API Keys when returning configuration to the frontend. Only the last 4 characters SHALL be visible.

#### Scenario: Masked Key returned in API response
- **WHEN** configuration is retrieved via API
- **THEN** each API Key is displayed as "****xxxx" where xxxx are the last 4 characters

### Requirement: LLM instance factory
The system SHALL provide a factory that creates the correct browser-use LLM client instance (ChatOpenAI, ChatAnthropic, ChatGoogle, ChatOllama, ChatDeepSeek, ChatGroq) based on the configured provider and model. All classes are importable from `browser_use` top-level package.

#### Scenario: Create OpenAI LLM instance
- **WHEN** a task is started with the "openai" provider
- **THEN** the factory creates a ChatOpenAI instance with the stored API Key and selected model

#### Scenario: Create Ollama LLM instance
- **WHEN** a task is started with the "ollama" provider
- **THEN** the factory creates a ChatOllama instance with the stored URL and selected model

#### Scenario: Create DeepSeek LLM instance
- **WHEN** a task is started with the "deepseek" provider
- **THEN** the factory creates a ChatDeepSeek instance with the stored API Key and default base_url "https://api.deepseek.com/v1"

#### Scenario: Provider not configured
- **WHEN** a task is started with a provider that has no valid configuration
- **THEN** the factory returns an error indicating the provider is not configured

### Requirement: Browser mode configuration
The system SHALL store browser mode preference (local Chromium or Browser Use Cloud) and Cloud API Key when applicable.

#### Scenario: Switch to cloud browser mode
- **WHEN** user selects Browser Use Cloud mode and provides a Cloud API Key
- **THEN** the system stores the preference and Key for use when creating Agent sessions
