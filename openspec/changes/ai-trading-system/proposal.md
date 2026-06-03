# AI-Powered Personal Trading System

## Summary
Build a fully automated personal trading agent that discovers signals from Binance Square social posts, analyzes them with LLM, validates against market data, and executes trades via Binance API.

## Motivation
The user wants a system that continuously monitors social sentiment (Binance Square), uses AI to identify trading opportunities, validates them with multi-source market data, and executes trades automatically.

## Scope
- **In Scope:**
  - Binance Square scraper (browser automation)
  - LLM signal analysis (sentiment + token extraction)
  - Multi-source market data validation (CoinGecko, OKX, Hyperliquid)
  - **Short-selling analytics engine (derivatives, on-chain, unlock data, technical indicators)**
  - Configurable filtering rules engine
  - Binance Spot & Futures trading integration
  - Automatic TP/SL order placement
  - Frontend dashboard for monitoring signals & positions
  - Real-time WebSocket updates

- **Out of Scope:**
  - Multi-user support (single-user personal system)
  - Advanced portfolio management (rebalancing, etc.)
  - Historical backtesting (forward-only)
  - Social media platforms beyond Binance Square (initially)

## Success Criteria
- [ ] System can automatically discover and analyze Binance Square posts every 5 minutes
- [ ] LLM correctly extracts tokens and sentiment with >80% accuracy
- [ ] Trading signals are validated against market data before execution
- [ ] Binance API integration supports both Spot and Futures
- [ ] Frontend displays real-time signals, positions, and trade history
- [ ] System runs end-to-end without manual intervention

## Risks
- **Binance Square scraping:** May break if Binance updates their website structure
- **LLM accuracy:** Sentiment analysis may produce false positives; mitigated by market data validation
- **Trading risk:** Automated trading can lose money; Testnet first, then small amounts
