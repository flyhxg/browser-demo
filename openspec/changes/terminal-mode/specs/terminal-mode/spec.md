## ADDED Requirements

### Requirement: Command queuing
The system SHALL accept multiple commands via the WebSocket connection and execute them sequentially. Each command SHALL reset the browser page context before executing.

#### Scenario: Single command execution
- **WHEN** user sends a single command "go to example.com" via WebSocket
- **THEN** the system executes it and sends a `result` event when complete

#### Scenario: Multiple commands queued
- **WHEN** user sends "go to example.com" then immediately sends "click the first link"
- **THEN** the second command is queued and executes only after the first command completes

#### Scenario: Command resets page context
- **WHEN** a command is executing
- **THEN** the page context is reset (navigated to about:blank) before the command runs to ensure clean state

### Requirement: Persistent browser session
The system SHALL reuse the same BrowserSession instance across all commands in the queue. The browser SHALL NOT close between commands.

#### Scenario: Browser persists across commands
- **WHEN** two commands "go to google.com" and "search for ai" are queued and executed sequentially
- **THEN** the browser session started for the first command is reused for the second command

#### Scenario: Idle timeout closes browser
- **WHEN** the command queue is empty and 5 minutes pass with no new commands
- **THEN** the browser session is closed automatically

### Requirement: Bidirectional WebSocket messaging
The system SHALL allow the frontend to send commands over the WebSocket connection at any time, and the backend SHALL push step, result, live_url, and queue_status events to the frontend.

#### Scenario: Frontend sends command while agent is running
- **WHEN** user sends a command while the agent is currently executing a previous command
- **THEN** the new command is added to the queue and a `queue_status` event is sent to the frontend

#### Scenario: Frontend receives live_url event on cloud browser start
- **WHEN** the agent starts a cloud browser session and receives the cdp_url
- **THEN** a `live_url` event is sent to the frontend with the live preview URL

### Requirement: Live URL iframe display
The system SHALL display the live preview URL in an iframe within the Browser View area when running in cloud mode. When running in local mode, the existing base64 screenshot display SHALL be used.

#### Scenario: Cloud mode renders live URL iframe
- **WHEN** a `live_url` event is received by the frontend in cloud browser mode
- **THEN** the ScreenshotView component renders an iframe with the live preview URL instead of a static screenshot

#### Scenario: Local mode renders base64 screenshot
- **WHEN** the agent is running in local browser mode
- **THEN** the ScreenshotView component renders base64 screenshots from step events (existing behavior)

### Requirement: Command history display
The system SHALL maintain a scrollable history of command results. The latest result SHALL remain visible by default and the user SHALL be able to scroll up to see previous results.

#### Scenario: Results accumulate in history
- **WHEN** multiple commands complete sequentially
- **THEN** each result is added to the history panel and the latest result is visible at the bottom

#### Scenario: User scrolls up to view past results
- **WHEN** the user scrolls up in the result history panel
- **THEN** previous results are visible without being dismissed

### Requirement: Queue status display
The system SHALL show the current queue depth (number of pending commands) in the frontend so users know how many tasks are queued.

#### Scenario: Queue depth shown while commands are pending
- **WHEN** there are 2 commands in the queue waiting to execute
- **THEN** the frontend displays a queue status indicator showing "2 pending"

#### Scenario: Queue depth updates after command completes
- **WHEN** a running command completes and the queue has one remaining command
- **THEN** the queue status updates to show "1 pending"