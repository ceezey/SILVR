# Progress Log

## Project Status

Current phase:

```text
Phase 9.5 Binance demo/testnet readiness implemented
```

Current mode:

```text
No live trading
```

## Completed

- Created master roadmap in `codex-task.json`
- Defined hybrid bot concept
- Selected core strategy: ICT Silver Bullet
- Decided ML will be a filter, not the main trader
- Decided AI agent will be an analyst, not an execution engine
- Defined documentation files for Codex and humans

## In Progress

- Preparing Binance Futures demo/testnet validation while keeping real-money live trading disabled
- Keeping live trading disabled pending backtest, out-of-sample, paper, demo/testnet, risk, kill-switch, Telegram, API-security, and withdrawal-disabled evidence

## Next Recommended Codex Task

Run Phase 9.5 demo/testnet evidence audit only:

```text
demo readiness review
Binance Futures testnet key and endpoint validation
demo-mode dry startup review
```

## Suggested Codex Prompt

```text
Read codex-task.json, AGENTS.md, README.md, ARCHITECTURE.md, STRATEGY_NOTES.md, and RISK_POLICY.md.

Continue Phase 9.5 demo/testnet evidence audit only:
- demo readiness review
- Binance Futures testnet key and endpoint validation
- demo-mode dry startup review

Constraints:
- Do not implement live trading yet.
- Do not place real orders.
- Default mode must be paper or backtest.
- Use Python 3.11+.
- Use clean src/ layout.
- Add type hints and docstrings.
- Add pytest tests.
- Add .env.example.
- Never hardcode API keys.
- Update PROGRESS.md when finished.
- Show changed files and test instructions.
```

## Development Notes

The bot must be built one phase at a time.

Do not ask Codex to build the full bot in one request.

Each Codex task should:

```text
read the documentation
implement a small phase
add tests
avoid live trading
update progress
summarize changes
```

## Live Trading Status

```text
LIVE TRADING IS NOT APPROVED
```

Reason:

```text
Backtesting foundation exists, but out-of-sample validation evidence has not been reviewed
Paper trading implemented in simulated mode only
Risk engine implemented for backtesting and paper trading
Kill switch implemented for risk gating
Live-readiness checker exists, but required evidence has not been supplied
Demo/testnet readiness checker exists, but local demo configuration has not been supplied
```

## Change Log

### Initial Documentation

Created:

```text
README.md
ARCHITECTURE.md
STRATEGY_NOTES.md
RISK_POLICY.md
ML_MODEL.md
DEPLOYMENT.md
PROGRESS.md
TODO.md
AGENTS.md
```
## Phase 1 Foundation Scaffold

- Added Python 3.11+ `src/` package scaffold for `silver_bot`.
- Added safe typed configuration loading from defaults, optional `.env`, optional `config.yaml`, and process environment.
- Enforced fail-closed live trading rules for Phase 1: `LIVE_TRADING=true` and `TRADING_MODE=live` are rejected.
- Added exchange adapter interface and a Binance Futures adapter skeleton with real order placement disabled.
- Added historical OHLCV fetcher interface.
- Added SQLite storage initialization for candles, signals, trades, and logs.
- Added pytest coverage for safe config defaults, unsafe live config rejection, and database initialization.

## Phase 1 Review

- Added the correctly named `RISK_POLICY.md` safety document.
- Added placeholder package boundaries for strategy, risk, execution, backtest, ML, and monitoring without implementing later-phase behavior.
- Hardened config validation for partial Binance credentials, parent-directory database paths, and directory database targets.
- Explicitly disabled exchange order cancellation in addition to order placement.
- Added tests for exchange safety, config validation edge cases, and Phase 1 package imports.

## Phase 2 Strategy Modules

- Added configurable America/New_York Silver Bullet session detection with a DST-aware fallback for Windows environments without IANA tzdata.
- Added causal swing high/low detection that does not use future candles.
- Added buy-side and sell-side liquidity level detection and sweep detection.
- Added bullish and bearish Fair Value Gap detection.
- Added displacement detection using body size, candle range, ATR, and close-location logic.
- Added simple market structure shift detection.
- Added higher-timeframe bias detection.
- Added deterministic Silver Bullet signal generation for `LONG`, `SHORT`, and `NO_TRADE`.
- Added signal quality scoring and synthetic OHLCV tests.
- Kept all outputs as strategy candidates only; no execution, live trading, or ML was introduced.

## Phase 3 Backtesting

- Added an event-driven historical backtester that replays candles one by one.
- Integrated the existing Silver Bullet strategy engine without adding live or paper execution.
- Added simulated limit entries at the strategy FVG midpoint.
- Added stop-loss and take-profit simulation.
- Added conservative same-candle stop-first behavior.
- Added fees, slippage, and spread modeling.
- Added optional partial take-profit and breakeven support.
- Added exports for `trades.csv`, `equity_curve.csv`, `backtest_report.json`, and `rejected_signals.csv`.
- Added metrics for trade counts, win rate, profit factor, expectancy, average R, max drawdown, streaks, fees, net profit, and session performance.
- Added basic chronological validation split structure.
- Added tests for winning trade, losing trade, no-trade scenario, fee impact, slippage impact, and unfilled limit orders.
- Kept live trading, paper trading, ML, and optimization out of scope.

## Phase 4 Risk Management

- Added mandatory risk-management engine.
- Added risk-based position sizing from account equity and configured risk per trade.
- Added stop-loss distance validation and required stop-loss checks.
- Added minimum reward-to-risk validation.
- Added max daily loss validation.
- Added max consecutive losses validation.
- Added max trades per day validation.
- Added max open positions validation.
- Added maximum leverage validation.
- Added file-based kill switch support.
- Integrated risk approval into the backtester before any pending order is created.
- Updated backtesting to use risk-approved position size only.
- Logged risk rejections in rejected signal records.
- Added tests for valid sizing, invalid stop loss, low RR, daily loss lockout, consecutive loss lockout, max trades lockout, max open positions, leverage rejection, kill switch, and backtest risk rejection.
- Kept live trading, paper trading, ML, martingale, and averaging down out of scope.

## Phase 5 Paper Trading

- Added live market-data stream interfaces.
- Added deterministic mock stream for tests and local dry runs.
- Added reconnecting stream wrapper.
- Added Binance Futures polling stream skeleton using the exchange adapter; real network fetching remains unimplemented in the adapter.
- Added paper-only execution engine with simulated limit fills, fees, slippage, spread, stop loss, and take profit.
- Added basic trade management with conservative stop-first behavior.
- Added paper trading orchestrator that consumes stream candles, runs strategy, passes signals through risk, submits simulated orders, and stores lifecycle events.
- Added paper trade and paper event persistence to SQLite.
- Added optional Telegram alert module disabled by default.
- Added alert methods for bot started, signal detected, paper trade opened, paper trade closed, error, and kill switch active.
- Added basic daily paper report helper.
- Added tests with mocked market data and in-memory Telegram.
- Kept live trading, real orders, real API keys, ML, and optimization out of scope.

## Phase 6 ML Foundation

- Added supervised ML dataset creation from deterministic Silver Bullet setup signals.
- Enforced one dataset row per setup, not per candle.
- Added TP-before-SL labels using future candles only for outcomes, with conservative stop-first handling when TP and SL touch in the same candle.
- Added feature engineering that uses only candles and signal fields known at signal time.
- Added future-leakage feature-name validation.
- Added chronological train/validation/test splitting with no random split.
- Added dependency-free baseline logistic regression training.
- Added optional Random Forest and Gradient Boosting training when scikit-learn is available.
- Saved model artifacts, feature list, and validation metrics while leaving the final test split untouched.
- Added a JSON model registry with active model selection and rollback by reactivating an older entry.
- Added tests for feature generation, leakage-column rejection, time-based splitting, model artifact saving, and registry save/load/activation.
- Kept ML offline only; it does not generate signals, place orders, bypass risk, or affect paper/live execution.

## Phase 6 ML Probability Filter Integration

- Added an optional ML probability filter that loads the active model from the model registry.
- Added validated ML config defaults for `ML_FILTER_ENABLED`, `ML_REGISTRY_PATH`, `ML_MIN_PROBABILITY`, and `ML_REDUCE_RISK_THRESHOLD`.
- Added approve, reject, and reduce-risk ML decisions for existing rule-based Silver Bullet signals only.
- Added missing-model and disabled-filter pass-through behavior so the deterministic strategy and risk engine remain usable without ML.
- Integrated ML decisions into backtesting before risk approval, with risk reduction applied only by shrinking an already risk-approved position size.
- Added ML probability and decision fields to backtest trade and rejection records.
- Added ML probability context to paper signal and order lifecycle logs.
- Added SQLite persistence for ML predictions with model version, probability, thresholds, decision, risk multiplier, and feature snapshot.
- Added tests for approved, rejected, reduced-risk, missing-model, disabled-filter, database storage, and backtest reduced-risk behavior.
- Kept live trading disabled and kept ML unable to generate trades, place orders, increase risk, or bypass the risk engine.

## Phase 7 Monitoring and Reporting

- Added structured JSON audit logging with nested secret redaction.
- Added audit events for strategy decisions, rejected signals, risk rejections, ML decisions, simulated trade lifecycle events, bot startup/shutdown, and kill-switch blocks in backtest and paper mode.
- Added Telegram alert methods for bot stopped, signal rejected, risk rejection, ML approval/rejection, and daily report.
- Kept Telegram disabled by default and testable through the in-memory Telegram client.
- Added daily performance reports with trades taken, rejected setups, PnL, drawdown, win rate, average R, best/worst trade, rule failures, and ML decisions.
- Added weekly performance reports with total trades, net PnL, win rate, profit factor, average R, max drawdown, best/worst session, and repeated rejection reasons.
- Added trade journal CSV export.
- Added dashboard data JSON export as the basic dashboard foundation.
- Added tests for structured log generation, secret redaction, daily reports, weekly reports, Telegram disabled behavior, and mocked Telegram sending.
- Kept live trading, real orders, Docker, and deployment out of scope.

## Phase 6 ML Calibration and Promotion

- Added calibration reporting for classification probabilities with Brier score, reliability bins, actual win rate per bin, sample count per bin, and Expected Calibration Error.
- Added exports for `calibration_report.json` and `calibration_bins.csv`.
- Added a configurable offline model-promotion policy using validation score improvement, test-score degradation limits, Brier score limits, minimum sample count, and a final-test optimization guard.
- Added promotion decisions for `promote`, `reject`, and `keep_current`, with JSON audit export.
- Added tests for calibration metrics/exports and promotion approval/rejection cases.
- Kept ML as an offline validator/filter only; it still cannot generate trades, place orders, increase risk, or bypass the risk engine.

## Phase 6 ML Completion Audit

- Verified Phase 6 ML dataset, feature engineering, chronological splits, baseline training, validation metrics, calibration reporting, model registry, rollback support, probability filtering, and promotion policy.
- Tightened promotion policy behavior so a tied validation score cannot hide other rejection reasons such as poor calibration.
- Added direct tests for test-score degradation rejection, `keep_current`, and tied-candidate rejection with failed calibration.
- Confirmed all Phase 6 TODO items remain implemented and tested.

## Phase 8 Deployment Support

- Added Docker containerization with safe paper-mode defaults and no live command as the image default.
- Added `.dockerignore` rules so `.env`, runtime data, logs, models, reports, databases, caches, and local virtual environments are not copied into the image.
- Added Docker Compose services for paper, backtest, and research-safe startup commands with mounted `data`, `logs`, `models`, and `reports` volumes.
- Added a container health check that validates configuration and rejects live trading.
- Added an example systemd service that starts the paper-mode Compose service.
- Added a host preparation script and logrotate example for VPS deployment.
- Updated deployment documentation with safe Docker, Compose, systemd, VPS, secrets, and production checklist guidance.
- Added tests that verify Docker defaults, Docker ignore rules, Compose volume/safety settings, and systemd command safety.
- Kept live trading disabled and real order execution out of scope.

## Phase 9 Live-Readiness Checker

- Added a standalone live-readiness checker that produces `reports/live_readiness_report.json`.
- Added required gates for backtest report, out-of-sample validation report, paper trading report, risk engine enabled, kill switch configured, Telegram tested or disabled, API keys present in process environment, explicit live intent flags, withdrawal-disabled confirmation, and safe risk/leverage limits.
- Added fail-closed readiness validation for an already-active kill-switch file.
- Added CLI support with `python -m silver_bot.readiness --output reports/live_readiness_report.json`.
- Added tests for passing readiness, missing reports, unsafe live flags, missing API keys, missing withdrawal confirmation, unsafe risk limits, Telegram test requirements, and report export.
- Kept live execution unimplemented and live trading blocked unless all readiness checks pass in the report.

## Configuration Checklist

- Added `CONFIGURATION.md` with the actual environment variables, supported `config.yaml` fields, safe defaults, mode-specific settings, ML settings, Telegram settings, deployment settings, and live-readiness requirements.
- Added `config.example.yaml` with safe paper-mode defaults.
- Updated `.env.example` and deployment docs to match implemented variable names.
- Tightened config validation for exchange names, symbols, timeframes, and ML registry paths.
- Improved readiness-checker messages for missing reports, invalid booleans, kill-switch setup, Telegram requirements, API keys, and unsafe risk values.

## Phase 9.5 Binance Demo/Testnet Mode

- Added a separate `demo` mode using `MODE=demo`, `DEMO_TRADING=true`, `BINANCE_TESTNET=true`, `LIVE_TRADING=false`, and `PAPER_TRADING=false`.
- Added strict demo config validation for testnet endpoints, demo API keys, risk engine, kill switch, stop-loss requirement, and safe risk/leverage limits.
- Added Binance Futures adapter endpoint selection with a testnet-only guard for demo mode while keeping real order placement disabled.
- Added `python -m silver_bot.demo_readiness` with output to `reports/demo_readiness_report.json`.
- Added demo readiness checks for API keys, testnet endpoint, risk engine, kill switch, stop-loss requirement, safe limits, `.env` ignore rules, and secret-shaped values outside private runtime files.
- Added Docker Compose `demo` profile that still forces `LIVE_TRADING=false`.
- Updated `.env.example`, `config.example.yaml`, `README.md`, `CONFIGURATION.md`, `ARCHITECTURE.md`, `RISK_POLICY.md`, and `DEPLOYMENT.md`.
- Added tests for safe demo config, unsafe live/testnet flags, production endpoint rejection, demo readiness failures, adapter testnet URL selection, and secret redaction.
