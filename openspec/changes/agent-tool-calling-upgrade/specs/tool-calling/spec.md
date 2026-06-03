## ADDED Requirements

### Requirement: Tool definitions
The system SHALL define tools using JSON Schema with name, description, and parameters.

#### Scenario: Tool schema is valid
- **WHEN** a tool is registered with the system
- **THEN** it MUST have a valid JSON Schema with name, description, and parameters

### Requirement: LLM tool selection
The system SHALL send tool definitions to the LLM and receive the selected tool(s) and extracted parameters.

#### Scenario: Single tool selection
- **WHEN** user says "查下 BTC 价格"
- **THEN** LLM SHALL select tool `get_price` with parameter `{"symbol": "BTC"}`

#### Scenario: Multiple tool selection
- **WHEN** user says "帮我分析 SOL"
- **THEN** LLM SHALL select multiple tools: `get_price`, `get_market_cap`, `get_funding_rate`, `scrape_binance_square`

### Requirement: Parameter extraction
The system SHALL extract parameters from user input and validate them against the tool's JSON Schema.

#### Scenario: Valid parameter
- **WHEN** LLM returns parameters `{"symbol": "BTC"}` for `get_price`
- **THEN** the system SHALL validate it and execute the tool

#### Scenario: Invalid parameter
- **WHEN** LLM returns parameters with missing required fields
- **THEN** the system SHALL return an error and ask for clarification

### Requirement: Tool execution
The system SHALL execute selected tools and return results.

#### Scenario: Successful execution
- **WHEN** tool `get_price` is called with `{"symbol": "BTC"}`
- **THEN** the system SHALL return the current price of BTC

#### Scenario: Tool execution failure
- **WHEN** a tool fails (e.g., API timeout)
- **THEN** the system SHALL return an error message and continue with other tools
