# Binance Hot Tokens Scanner

## Summary
为 AI Trading Desk 新增「热门代币扫描器」功能，自动发现币安 USDT 永续合约中交易最活跃的代币，支持可视化展示和手动/自动交易。

## Motivation
用户希望 Trading Desk 能主动扫描币安市场，发现交易最热的代币，然后接入 LLM 分析 → 交易闭环。目前系统只支持被动接收信号（来自 Binance Square 社交媒体或 Polymarket），缺少主动市场扫描能力。

## Scope
- **In Scope:**
  - 币安 USDT 永续合约市场扫描器（24h ticker, 资金费率, 多空比）
  - 热度综合评分算法（交易量 + 价格变动 + 资金费率）
  - 热门代币榜单实时展示（WebSocket 推送）
  - LLM 分析热门代币（复用 SignalAnalyzer）
  - 手动/自动交易执行（复用 TradingEngine）
  - WebSocket 实时更新热榜数据
  - 前端 TradingView 新增 Hot Tokens 标签页

- **Out of Scope:**
  - 现货市场扫描（只扫描合约）
  - 链上数据（代币市值、鲸鱼动向等）
  - 多交易所对比（只支持币安）
  - 复杂的策略回测

## Success Criteria
- [ ] 扫描器每 60 秒自动更新热榜数据
- [ ] 热榜展示价格、24h涨跌、交易量、资金费率、多空比、热度得分
- [ ] WebSocket 实时推送热榜更新到前端
- [ ] 用户可点击「分析」按钮，LLM 分析代币并给出建议
- [ ] 用户可点击「交易」按钮，执行买入/做空操作
- [ ] 支持自动模式（置信度超过阈值自动执行交易）

## Risks
- **币安 API 限制**: CCXT 请求可能触发 rate limit，需控制频率
- **WebSocket 连接**: 大量代币同时推送可能造成前端性能问题
- **自动交易风险**: 自动模式下需严格控制仓位和止损
