## ADDED Requirements

### Requirement: Settings page for LLM and browser configuration
The system SHALL provide a settings page where users can configure API Keys for multiple LLM providers (OpenAI, Claude, Gemini, DeepSeek, Groq) and connection settings for Ollama (URL + model). The page SHALL also allow selecting browser mode (local Chromium or Browser Use Cloud).

#### Scenario: User configures OpenAI API Key
- **WHEN** user enters an OpenAI API Key on the settings page and clicks save
- **THEN** the system validates the Key by calling the OpenAI API, stores it on the backend, and shows a success indicator

#### Scenario: User configures Ollama connection
- **WHEN** user enters an Ollama server URL and clicks connect
- **THEN** the system checks connectivity, auto-detects available models, and populates the model dropdown

#### Scenario: User selects browser mode
- **WHEN** user selects local Chromium or Browser Use Cloud on the settings page
- **THEN** the system saves the browser mode preference and shows relevant additional fields (Cloud API Key for cloud mode)

### Requirement: Main page for task execution
The system SHALL provide a main page with a task input area, model selector dropdown (showing only configured models), an execute button, a real-time execution visualization area, and a result display area.

#### Scenario: User submits a task
- **WHEN** user types a task description, selects a configured model, and clicks execute
- **THEN** the system starts the Agent and begins streaming execution updates to the page

#### Scenario: Model selector shows only configured models
- **WHEN** user opens the model selector dropdown on the main page
- **THEN** only LLM providers with valid configuration (verified API Key or connected Ollama) are shown as available options

### Requirement: Real-time execution visualization
The system SHALL display Agent execution progress in real-time, including step-by-step action logs with status indicators (pending/running/done/error) and browser screenshots captured at each step.

#### Scenario: Agent step updates appear in real-time
- **WHEN** the Agent performs an action (navigate, click, type, etc.)
- **THEN** a new step entry appears in the log with a running indicator, transitioning to done when the action completes

#### Scenario: Browser screenshots update during execution
- **WHEN** the Agent captures a screenshot after each action
- **THEN** the screenshot area updates with the latest browser view

### Requirement: Result display
The system SHALL display the Agent's final result when task execution completes, including extracted data and a summary.

#### Scenario: Task completes successfully
- **WHEN** the Agent finishes execution and returns a result
- **THEN** the result area shows the Agent's final output text and the execution log shows all steps as done

#### Scenario: Task execution fails
- **WHEN** the Agent encounters an error during execution
- **THEN** the result area shows an error message and the failed step shows an error indicator

### Requirement: Task cancellation
The system SHALL allow users to cancel a running task.

#### Scenario: User cancels a running task
- **WHEN** user clicks the cancel button while a task is running
- **THEN** the system stops the Agent execution and shows a "cancelled" status in the log
