## ADDED Requirements

### Requirement: Agent execution engine
The system SHALL provide an execution engine that orchestrates the analysis pipeline.

#### Scenario: Simple analysis
- **WHEN** user says "查下 BTC 价格"
- **THEN** the system SHALL execute: analyze_intent → select_tools → execute_tools → summarize

#### Scenario: Complex analysis
- **WHEN** user says "帮我分析 SOL"
- **THEN** the system SHALL execute multiple tools in parallel and summarize results

### Requirement: Parallel tool execution
The system SHALL execute independent tools in parallel using asyncio.

#### Scenario: Parallel execution
- **WHEN** user requests analysis that requires price, market cap, and sentiment
- **THEN** all three tools SHALL execute concurrently

### Requirement: Result summarization
The system SHALL use LLM to summarize tool results into a coherent response.

#### Scenario: Summarize multiple results
- **WHEN** tools return price, market cap, and sentiment data
- **THEN** the system SHALL generate a summary that includes all key findings
