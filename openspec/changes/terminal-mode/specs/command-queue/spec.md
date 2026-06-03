## ADDED Requirements

### Requirement: Command queue management
The AgentRunner SHALL maintain an in-memory queue of command strings. Commands SHALL be dequeued and executed one at a time in FIFO order.

#### Scenario: Command added to queue
- **WHEN** a `command` WebSocket message is received and no command is currently running
- **THEN** the command is executed immediately (not queued)

#### Scenario: Command queued when busy
- **WHEN** a `command` WebSocket message is received while a command is currently executing
- **THEN** the command is added to the queue and a `queue_status` event `{ type: "queue_status", data: { pending: N } }` is sent to the frontend

#### Scenario: Queue drains automatically
- **WHEN** the currently executing command calls its done_callback
- **THEN** the next command is dequeued and executed automatically

#### Scenario: CDP connection recovered after idle
- **WHEN** a command starts but the cloud browser CDP connection has dropped due to prior idle time
- **THEN** the system recreates the BrowserSession automatically and executes the command

### Requirement: Queue capacity limit
The command queue SHALL have a maximum capacity of 50 commands. Commands beyond this limit SHALL be rejected with an error event.

#### Scenario: Queue rejects when full
- **WHEN** the queue already has 50 pending commands and a new command is received
- **THEN** an error event `{ type: "error", data: { message: "Queue is full (max 50 commands)", step: 0 } }` is sent to the frontend

### Requirement: Queue status events
The system SHALL send a `queue_status` event to the frontend whenever the queue depth changes.

#### Scenario: Queue status sent on enqueue
- **WHEN** a command is added to the queue
- **THEN** a `queue_status` event with `pending: N` is sent to the frontend

#### Scenario: Queue status sent on dequeue
- **WHEN** a command finishes and the queue becomes empty
- **THEN** a `queue_status` event with `pending: 0` is sent to the frontend

### Requirement: Queue cleared on cancel
The system SHALL clear all pending commands from the queue when the user cancels the current task.

#### Scenario: Cancel clears queue
- **WHEN** user sends a cancel request while commands are queued
- **THEN** all pending commands are removed from the queue and the browser session is closed