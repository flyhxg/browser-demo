## MODIFIED Requirements

### Requirement: Intent classification
The system SHALL use LLM Function Calling for intent classification instead of keyword matching.

#### Scenario: Intent classification
- **WHEN** user says "帮我分析 BTC"
- **THEN** the system SHALL use LLM to determine that the user wants a comprehensive analysis

## ADDED Requirements

### Requirement: Tool-based intent routing
The system SHALL route user requests based on LLM-selected tools.

#### Scenario: Tool-based routing
- **WHEN** LLM selects tools for a request
- **THEN** the system SHALL execute those tools instead of returning fixed text
