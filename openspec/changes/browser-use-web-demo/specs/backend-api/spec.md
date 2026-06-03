## ADDED Requirements

### Requirement: Configuration management API
The system SHALL provide REST API endpoints for reading and updating LLM provider configurations. API Keys SHALL NOT be returned in full; only a masked version (e.g., "sk-***xxx") and a configured status flag SHALL be returned.

#### Scenario: Get current configuration
- **WHEN** a GET request is made to the configuration endpoint
- **THEN** the system returns all LLM provider configurations with masked API Keys and status flags indicating whether each provider is configured

#### Scenario: Update LLM provider configuration
- **WHEN** a PUT request is made with a provider name and API Key
- **THEN** the system stores the Key, validates it, and returns the updated configuration with a masked Key and validation status

#### Scenario: Validate existing configuration
- **WHEN** a POST request is made to the validate endpoint with a provider name
- **THEN** the system tests the stored Key by making a minimal API call and returns success or failure

### Requirement: Task execution API
The system SHALL provide a REST API endpoint to start a task and a WebSocket endpoint at `/ws` for streaming execution updates.

#### Scenario: Start a task via REST API
- **WHEN** a POST request is made to `/api/tasks` with a task description and model selection
- **THEN** the system creates and starts an Agent execution, returning a task ID

#### Scenario: Stream execution updates via WebSocket
- **WHEN** a WebSocket connection is established to `/ws`
- **THEN** the system pushes step updates (action type, status, screenshot) and final results as JSON messages with type field ("step", "result", "error", "cancelled")

#### Scenario: Cancel a running task
- **WHEN** a POST request is made to `/api/tasks/cancel`
- **THEN** the system stops the running Agent and sends a WebSocket "cancelled" message

### Requirement: Ollama connectivity check API
The system SHALL provide an API endpoint to check Ollama server connectivity and list available models.

#### Scenario: Check Ollama connectivity
- **WHEN** a GET request is made to the Ollama check endpoint with a URL parameter
- **THEN** the system attempts to connect to the Ollama server and returns connection status and available model list

#### Scenario: Ollama server is unreachable
- **WHEN** the Ollama server URL is unreachable
- **THEN** the system returns a connection error with a descriptive message
