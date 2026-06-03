## ADDED Requirements

### Requirement: Thinking message type
The system SHALL support a `thinking` message type to show the AI's reasoning process.

#### Scenario: Show thinking
- **WHEN** the AI starts analyzing user intent
- **THEN** the system SHALL send a `thinking` message with step number and description

### Requirement: Tool call message types
The system SHALL support `tool_call_start` and `tool_call_result` message types.

#### Scenario: Tool call start
- **WHEN** the AI decides to call a tool
- **THEN** the system SHALL send a `tool_call_start` message with tool name and arguments

#### Scenario: Tool call result
- **WHEN** a tool completes execution
- **THEN** the system SHALL send a `tool_call_result` message with the result

### Requirement: Stream message type
The system SHALL support a `stream` message type for partial text output.

#### Scenario: Streaming response
- **WHEN** the AI generates a long response
- **THEN** the system SHALL send `stream` messages with text chunks

### Requirement: Frontend message type rendering
The frontend SHALL render different message types with appropriate UI components.

#### Scenario: Tool call rendering
- **WHEN** a `tool_call_start` message is received
- **THEN** the frontend SHALL show a ToolCallBlock with tool name, arguments, and loading spinner

#### Scenario: Thinking rendering
- **WHEN** a `thinking` message is received
- **THEN** the frontend SHALL show a ThinkingBlock with step description
