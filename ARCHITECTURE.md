# Architecture

## Overview

This bot is designed as a modular, testable, and safety-first automated trading system.

The core trading logic is rule-based. Machine learning is optional and may only be used as a filter or risk adjustment layer.

The AI analyst module is optional and must never place trades directly.

## High-Level Flow

```text
Exchange Market Data
    ↓
Data Normalization
    ↓
Session Engine
    ↓
Market Structure Detection
    ↓
Liquidity Detection
    ↓
Fair Value Gap Detection
    ↓
Displacement Detection
    ↓
Higher Timeframe Bias
    ↓
Silver Bullet Strategy Engine
    ↓
Signal Quality Scoring
    ↓
Optional ML Probability Filter
    ↓
Risk Management Engine
    ↓
Execution Engine
    ↓
Trade Management Engine
    ↓
Storage / Logs / Alerts / Dashboard
```

## System Modes

The bot should support four modes:

```text
backtest
demo
paper
live
research
```

### Backtest Mode

Uses historical candles.

Purpose:

- Test strategy logic
- Simulate trade execution
- Generate performance reports
- Validate rules before paper or live trading

Backtest mode must include:

- Fees
- Slippage
- Spread assumptions
- Stop loss
- Take profit
- Partial take profit
- Breakeven logic
- Daily risk limits
- Max trade limits

### Paper Mode

Uses live market data but does not place real orders.

Purpose:

- Validate the bot in live conditions
- Test WebSocket stability
- Test Telegram alerts
- Test execution simulation
- Test monitoring and logs

Paper mode must be the default.

### Demo/Testnet Mode

Uses Binance Futures demo/testnet credentials and testnet endpoints only.

Purpose:

- Validate exchange-facing wiring without real-money live trading
- Confirm API key loading, endpoint selection, risk gates, kill switch, and logs
- Keep execution isolated from production Binance endpoints

Demo/testnet mode must only run if:

```text
MODE=demo
DEMO_TRADING=true
BINANCE_TESTNET=true
LIVE_TRADING=false
PAPER_TRADING=false
```

Demo/testnet mode must reject production Binance URLs, disabled risk controls,
disabled kill switch, disabled stop-loss requirements, and unsafe leverage or
risk limits. Real-money live order placement remains disabled.

### Live Mode

Uses live market data and places real exchange orders.

Live mode must only run if:

```text
LIVE_TRADING=true
PAPER_TRADING=false
READINESS_CHECK_PASSED=true
```

Live mode must block trading if the readiness checklist fails.

### Research Mode

Used for:

- Feature engineering
- ML dataset generation
- Model training
- Strategy analysis
- Report generation

Research mode must never place orders.

## Main Modules

### 1. Config Module

Suggested path:

```text
src/silver_bot/config/
```

Responsibilities:

- Load `.env`
- Load `config.yaml`
- Validate configuration
- Prevent unsafe live settings
- Provide typed configuration objects

Suggested files:

```text
settings.py
schema.py
loader.py
```

### 2. Exchange Module

Suggested path:

```text
src/silver_bot/exchange/
```

Responsibilities:

- Define exchange adapter interface
- Implement Binance Futures adapter
- Fetch candles
- Fetch balance
- Fetch open positions
- Place orders only when live mode is explicitly enabled
- Cancel orders
- Validate symbol precision
- Handle API errors

Suggested files:

```text
base.py
binance_futures.py
models.py
exceptions.py
```

### 3. Data Module

Suggested path:

```text
src/silver_bot/data/
```

Responsibilities:

- Fetch historical OHLCV data
- Normalize candles
- Save candles to Parquet or SQLite
- Load candles for backtesting
- Detect missing candles
- Generate data quality reports

Suggested files:

```text
fetcher.py
normalizer.py
quality.py
repository.py
```

### 4. Strategy Module

Suggested path:

```text
src/silver_bot/strategy/
```

Responsibilities:

- Detect Silver Bullet sessions
- Detect market structure
- Detect liquidity sweeps
- Detect Fair Value Gaps
- Detect displacement
- Determine higher timeframe bias
- Generate long/short/no-trade signals

Suggested files:

```text
sessions.py
structure.py
liquidity.py
fvg.py
displacement.py
bias.py
silver_bullet.py
models.py
```

### 5. Risk Module

Suggested path:

```text
src/silver_bot/risk/
```

Responsibilities:

- Calculate position size
- Validate stop-loss distance
- Validate reward-to-risk
- Enforce max daily loss
- Enforce max consecutive losses
- Enforce max trades per day
- Enforce leverage limits
- Trigger kill switch

Suggested files:

```text
position_sizing.py
limits.py
kill_switch.py
validators.py
models.py
```

### 6. Execution Module

Suggested path:

```text
src/silver_bot/execution/
```

Responsibilities:

- Convert approved signals into orders
- Simulate orders in paper mode
- Place real orders only in live mode
- Manage entries, stop loss, and take profit
- Handle partial fills
- Handle rejected orders
- Cancel stale orders

Suggested files:

```text
executor.py
paper_executor.py
live_executor.py
orders.py
fills.py
trade_management.py
```

### 7. Backtest Module

Suggested path:

```text
src/silver_bot/backtest/
```

Responsibilities:

- Run event-driven backtests
- Simulate execution
- Calculate metrics
- Export trades
- Export equity curve
- Export reports
- Run walk-forward validation
- Run Monte Carlo tests

Suggested files:

```text
engine.py
simulator.py
metrics.py
walk_forward.py
monte_carlo.py
reporting.py
```

### 8. ML Module

Suggested path:

```text
src/silver_bot/ml/
```

Responsibilities:

- Build ML datasets from rule-based setups
- Engineer features
- Train baseline models
- Evaluate models
- Save model artifacts
- Load model for inference
- Approve/reject/downsize signals

Suggested files:

```text
dataset.py
features.py
train.py
evaluate.py
predict.py
registry.py
```

Important:

The ML module must not generate trades independently.

### 9. Storage Module

Suggested path:

```text
src/silver_bot/storage/
```

Responsibilities:

- Store candles
- Store signals
- Store trades
- Store orders
- Store ML predictions
- Store performance metrics
- Store logs and audit records

Suggested files:

```text
database.py
models.py
repositories.py
migrations.py
```

### 10. Monitoring Module

Suggested path:

```text
src/silver_bot/monitoring/
```

Responsibilities:

- Telegram alerts
- Health checks
- Daily reports
- Weekly reports
- Dashboard data
- Error alerts
- Kill switch alerts

Suggested files:

```text
telegram.py
health.py
reports.py
dashboard.py
```

Current implementation:

- Structured JSON audit logs with secret redaction
- Telegram alert facade disabled by default
- Daily and weekly performance report builders
- Trade journal CSV export
- Dashboard data JSON export

## Core Data Models

### Candle

Required fields:

```text
symbol
timeframe
open_time
close_time
open
high
low
close
volume
```

### Signal

Required fields:

```text
signal_id
symbol
timeframe
direction
entry_price
stop_loss
take_profit
risk_reward
session_name
setup_quality_score
ml_probability
status
reason
created_at
```

Direction values:

```text
LONG
SHORT
NONE
```

Status values:

```text
APPROVED
REJECTED
PENDING
EXECUTED
EXPIRED
```

### Trade

Required fields:

```text
trade_id
signal_id
symbol
direction
entry_price
exit_price
stop_loss
take_profit
position_size
risk_amount
realized_pnl
realized_r
fees
slippage
status
entry_time
exit_time
exit_reason
```

### ML Prediction

Required fields:

```text
prediction_id
signal_id
model_version
probability
threshold
decision
features_snapshot
created_at
```

Current local SQLite storage includes an `ml_predictions` table for these filter decisions.

Backtest trade and rejected-signal records include optional:

```text
ml_probability
ml_decision
```

## Safety Design

Live execution should require multiple confirmations:

```text
mode == "live"
LIVE_TRADING == true
PAPER_TRADING == false
READINESS_CHECK_PASSED == true
api_key_has_no_withdrawal_permission == true
kill_switch_active == false
```

If any condition fails, the bot must not place orders.

## Logging Rules

Every decision must be logged.

Log these events:

- Candle received
- Session started
- Liquidity swept
- FVG detected
- MSS detected
- Signal generated
- Signal rejected
- Risk approved
- Risk rejected
- ML approved
- ML rejected
- Order submitted
- Order filled
- Order rejected
- Stop loss hit
- Take profit hit
- Kill switch activated
- Bot started
- Bot stopped
- API error
- WebSocket reconnect

## Testing Requirements

Minimum tests:

- Config validation
- Session time conversion
- FVG detection
- Liquidity sweep detection
- Market structure shift detection
- Position sizing
- Risk rejection
- Kill switch
- Paper execution
- Backtest metrics
- ML feature generation

## Design Principle

The bot must be boring, explainable, and strict.

A profitable-looking bot that cannot explain its trades is not acceptable.

A bot that trades without risk control is not acceptable.

A bot that performs well only because of overfitting is not acceptable.
