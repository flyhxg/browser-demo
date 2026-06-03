## ADDED Requirements

### Requirement: live_url event emission
The system SHALL emit a `live_url` event to the frontend via WebSocket when a cloud browser session starts and the cdp_url is available.

#### Scenario: live_url sent on cloud browser start
- **WHEN** BrowserSession.start() completes successfully in cloud mode
- **THEN** the AgentRunner SHALL extract session.cdp_url, construct the live preview URL as `https://live.browser-use.com/?wss={cdp_url}`, and send a WebSocket message `{ type: "live_url", data: { url: "<live_url>" } }`

#### Scenario: No live_url event in local mode
- **WHEN** BrowserSession is running in local (non-cloud) mode
- **THEN** no live_url event is emitted

### Requirement: live_url event format
The live_url event SHALL conform to the following format:

```json
{
  "type": "live_url",
  "data": {
    "url": "https://live.browser-use.com/?wss=wss%3A%2F%2F..."
  }
}
```

#### Scenario: Frontend receives valid live_url event
- **WHEN** frontend receives a message with type "live_url"
- **THEN** it SHALL parse data.url and render it in an iframe in the ScreenshotView component