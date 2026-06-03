## ADDED Requirements

### Requirement: Agent execution engine
The system SHALL wrap browser-use Agent to execute tasks, accepting a task description, LLM instance, and browser session configuration. It SHALL use `register_new_step_callback` to receive step events and capture screenshots from `BrowserStateSummary.screenshot`.

#### Scenario: Execute a task with local browser
- **WHEN** a task is started with local browser mode
- **THEN** the engine creates a BrowserSession with local Chromium, initializes an Agent with the given LLM and task, and starts execution

#### Scenario: Execute a task with cloud browser
- **WHEN** a task is started with Browser Use Cloud mode
- **THEN** the engine creates a cloud browser session using `Browser(use_cloud=True)`

### Requirement: Step event emission via callback
The system SHALL use browser-use's `register_new_step_callback` to receive step events. The callback receives `(BrowserStateSummary, AgentOutput, step_number)`. The `BrowserStateSummary.screenshot` field contains the base64-encoded screenshot.

#### Scenario: Step event received via callback
- **WHEN** the Agent completes a step
- **THEN** the callback is invoked with BrowserStateSummary (containing screenshot), AgentOutput (containing actions), and step number

#### Scenario: WebSocket message sent for each step
- **WHEN** a step callback is triggered
- **THEN** the engine sends a WebSocket message with type "step", including action type, target, status, and base64 screenshot from BrowserStateSummary

### Requirement: Task result capture
The system SHALL use `register_done_callback` to capture the Agent's final result when execution completes, including the output text and execution metadata (total steps, duration).

#### Scenario: Successful task completion
- **WHEN** the Agent signals task completion
- **THEN** the done callback is invoked with AgentHistoryList, the engine sends a WebSocket "result" message with the output and metadata, and closes the browser session

#### Scenario: Task execution error
- **WHEN** the Agent encounters an unrecoverable error
- **THEN** the engine captures the error message, sends a WebSocket "error" message, and cleans up resources

### Requirement: Task cancellation via stop()
The system SHALL support cancelling a running Agent task by calling `agent.stop()`.

#### Scenario: Cancel running task
- **WHEN** a cancel signal is received
- **THEN** the engine calls `agent.stop()`, sends a WebSocket "cancelled" message, and closes the browser session

### Requirement: Single concurrent task limit
The system SHALL enforce a limit of one running Agent task at a time.

#### Scenario: Attempt to start task while another is running
- **WHEN** a new task is requested while a task is already running
- **THEN** the system rejects the request with a "task already running" error
