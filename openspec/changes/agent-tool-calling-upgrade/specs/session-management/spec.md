## ADDED Requirements

### Requirement: Session creation
The system SHALL create a new session when a user connects via WebSocket.

#### Scenario: New session
- **WHEN** a user opens the chat page
- **THEN** the system SHALL create a new session with a unique ID

### Requirement: Session persistence
The system SHALL persist session messages to the database.

#### Scenario: Message persistence
- **WHEN** a message is sent or received
- **THEN** the system SHALL store it in the database with session_id

### Requirement: Context injection
The system SHALL inject session history into LLM prompts.

#### Scenario: Context injection
- **WHEN** a user sends a message in an existing session
- **THEN** the system SHALL include recent messages in the LLM prompt

### Requirement: Session expiration
The system SHALL clean up expired sessions after 7 days.

#### Scenario: Session cleanup
- **WHEN** a session has been inactive for 7 days
- **THEN** the system SHALL mark it as expired
