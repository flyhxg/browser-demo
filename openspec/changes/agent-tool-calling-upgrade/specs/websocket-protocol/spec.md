## MODIFIED Requirements

### Requirement: WebSocket message types
The WebSocket protocol SHALL support `thinking`, `tool_call_start`, `tool_call_result`, and `stream` message types in addition to existing types.

#### Scenario: Thinking message
- **WHEN** the AI starts processing a request
- **THEN** the system SHALL send a WebSocket message with type `thinking`

#### Scenario: Tool call start message
- **WHEN** the AI decides to call a tool
- **THEN** the system SHALL send a WebSocket message with type `tool_call_start`

#### Scenario: Tool call result message
- **WHEN** a tool completes
- **THEN** the system SHALL send a WebSocket message with type `tool_call_result`

#### Scenario: Stream message
- **WHEN** the AI generates text incrementally
- **THEN** the system SHALL send WebSocket messages with type `stream`

## ADDED Requirements

### Requirement: Message format standardization
All WebSocket messages SHALL follow a standard format with type and data fields.

#### Scenario: Standard message format
- **WHEN** any message is sent over WebSocket
- **THEN** it SHALL have fields: `type`, `data`, and optional `timestamp`
