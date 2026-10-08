# TODO

## Phase 1: Foundation

- [x] Create Python project scaffold
- [x] Create `src/` layout
- [x] Add `pyproject.toml` or `requirements.txt`
- [x] Add `.env.example`
- [x] Add config loader
- [x] Add config validation
- [x] Add exchange adapter interface
- [x] Add Binance Futures adapter skeleton
- [x] Add historical data fetcher
- [x] Add local storage layer
- [x] Add basic tests

## Phase 2: Strategy Engine

- [x] Add Silver Bullet session engine
- [x] Add timezone handling
- [x] Add swing high/low detection
- [x] Add liquidity level detection
- [x] Add liquidity sweep detection
- [x] Add Fair Value Gap detection
- [x] Add displacement detection
- [x] Add market structure shift detection
- [x] Add higher timeframe bias
- [x] Add full Silver Bullet signal engine
- [x] Add signal quality score

## Phase 3: Backtesting

- [x] Add event-driven backtester
- [x] Add fee simulation
- [x] Add slippage simulation
- [x] Add spread simulation
- [x] Add stop-loss simulation
- [x] Add take-profit simulation
- [x] Add partial TP simulation
- [x] Add breakeven simulation
- [x] Export trades.csv
- [x] Export equity_curve.csv
- [x] Export backtest_report.json
- [x] Add performance metrics

## Phase 4: Risk Management

- [x] Add position sizing
- [x] Add max daily loss
- [x] Add max consecutive losses
- [x] Add max trades per day
- [x] Add max open positions
- [x] Add leverage validation
- [x] Add minimum RR validation
- [x] Add kill switch
- [x] Add emergency shutdown logic

## Phase 5: Paper Trading

- [x] Add live market stream
- [x] Add WebSocket reconnect
- [x] Add REST fallback
- [x] Add paper executor
- [x] Add simulated fills
- [x] Add paper trade logs
- [x] Add Telegram alerts
- [x] Add daily paper report

## Phase 6: ML Filter

- [x] Build ML dataset from detected setups
- [x] Add feature engineering
- [x] Add time-based split
- [x] Train baseline model
- [x] Evaluate model
- [x] Add calibration report
- [x] Add model promotion rules
- [x] Add model registry
- [x] Add ML probability filter
- [x] Add model rollback support

## Phase 7: Monitoring

- [x] Add structured logging
- [x] Add trade journal
- [x] Add Telegram status alerts
- [x] Add Telegram error alerts
- [x] Add daily report
- [x] Add weekly report
- [x] Add dashboard

## Phase 8: Deployment

- [x] Add Dockerfile
- [x] Add docker-compose.yaml
- [x] Add deployment script
- [x] Add systemd service example
- [x] Add log rotation
- [x] Add VPS setup instructions
- [x] Add production safety checklist

## Phase 9: Live Readiness

- [x] Add live readiness checker
- [x] Add complete configuration checklist
- [ ] Backtest passes
- [ ] Out-of-sample validation passes
- [ ] Paper trading stable
- [ ] Risk engine tested
- [ ] Kill switch tested
- [ ] Telegram alerts tested
- [ ] API key secured
- [ ] Withdrawals disabled
- [ ] Live readiness checklist passes

## Phase 9.5: Binance Demo/Testnet

- [x] Add demo/testnet mode config
- [x] Add Binance Futures testnet endpoint validation
- [x] Add demo readiness checker
- [x] Add demo readiness report export
- [x] Add demo/testnet documentation
- [x] Add demo/testnet tests

## Never Do

- [ ] Do not enable live trading by default
- [ ] Do not hardcode API keys
- [ ] Do not use martingale
- [ ] Do not average down
- [ ] Do not trade without stop loss
- [ ] Do not let ML place trades directly
- [ ] Do not bypass the risk engine
