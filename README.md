# ICT Silver Bullet Trading Bot

A Python-based automated trading bot focused on the ICT Silver Bullet strategy for crypto futures trading.

This bot is designed as a hybrid system:

- Rule-based ICT Silver Bullet strategy engine
- Deterministic risk management
- Event-driven backtesting
- Paper trading before live trading
- Binance Futures demo/testnet validation before live trading
- Optional ML probability filter
- Optional AI analyst/reporting module
- Telegram monitoring and alerts
- VPS/Docker deployment for 24/7 operation

## Important Warning

This project is for research, backtesting, paper trading, and carefully controlled live experimentation.

Trading crypto futures is high risk. Leverage can quickly liquidate an account. This bot must never be treated as guaranteed profitable.

Default mode must always be:

```text
PAPER_TRADING=true
LIVE_TRADING=false
DEMO_TRADING=false
```

Live trading should only be enabled after:

1. The strategy passes backtesting.
2. The strategy passes out-of-sample validation.
3. Paper trading is stable.
4. Risk controls are working.
5. Kill switch is enabled.
6. API withdrawals are disabled.
7. The user accepts the risk.

## Core Strategy

Main strategy:

```text
ICT Silver Bullet
```

The bot looks for setups during configured Silver Bullet time windows.

General long idea:

1. Price enters a Silver Bullet session window.
2. Sell-side liquidity is swept.
3. Bullish displacement appears.
4. Market structure shifts bullish.
5. A bullish Fair Value Gap forms.
6. Price retraces into the FVG.
7. Entry is placed inside the FVG.
8. Stop loss is placed beyond the sweep or invalidation level.
9. Take profit targets opposing liquidity.

General short idea:

1. Price enters a Silver Bullet session window.
2. Buy-side liquidity is swept.
3. Bearish displacement appears.
4. Market structure shifts bearish.
5. A bearish Fair Value Gap forms.
6. Price retraces into the FVG.
7. Entry is placed inside the FVG.
8. Stop loss is placed beyond the sweep or invalidation level.
9. Take profit targets opposing liquidity.

## Target Market

Initial target:

```text
Binance Futures
```

Recommended initial symbols:

```text
BTCUSDT
ETHUSDT
```

Recommended testing order:

```text
Backtest first
Paper trading second
Binance Futures demo/testnet third
Live trading last
```

## Project Philosophy

This bot must be built around survival first.

Priorities:

1. Protect capital.
2. Avoid unsafe live execution.
3. Avoid overfitting.
4. Log every decision.
5. Prove performance before live trading.
6. Use ML only as a filter, not as the main trader.
7. Never use martingale.
8. Never trade without a stop loss.

## Planned Architecture

```text
Market Data
    ↓
Session Engine
    ↓
Market Structure Engine
    ↓
Liquidity Detection
    ↓
Fair Value Gap Detection
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
Trade Management
    ↓
Logging / Dashboard / Telegram Alerts
```

## Development Phases

### Phase 1: Foundation

- Project scaffold
- Configuration system
- Exchange adapter interface
- Historical data fetcher
- Local storage layer
- Basic tests

### Phase 2: ICT Silver Bullet Engine

- Session window engine
- Swing high/low detection
- Liquidity sweep detection
- Market structure shift detection
- Fair Value Gap detection
- Displacement detection
- Higher timeframe bias
- Strategy signal engine

### Phase 3: Backtesting

- Event-driven backtester
- Fee and slippage simulation
- Trade journal
- Equity curve
- Performance metrics
- Walk-forward validation

### Phase 4: Risk Management

- Position sizing
- Max daily loss
- Max consecutive losses
- Max trades per day
- Leverage validation
- Minimum reward-to-risk validation
- Kill switch

### Phase 5: Paper Trading

- Real-time market data
- Simulated execution
- Realistic fees and slippage
- Telegram alerts
- Dashboard

### Phase 5.5: Binance Demo/Testnet

- `MODE=demo`
- `DEMO_TRADING=true`
- `BINANCE_TESTNET=true`
- `LIVE_TRADING=false`
- `PAPER_TRADING=false`
- Binance Futures testnet endpoints only
- Demo readiness report

### Phase 6: ML Filter

- ML dataset builder
- Feature engineering
- Baseline model
- Probability filter
- Model registry
- No direct ML trade execution

### Phase 7: Deployment

- Docker
- VPS setup
- systemd or supervisor
- Monitoring
- Logs
- Emergency controls

### Phase 8: Live Trading

Live trading is only allowed after the live readiness checklist passes.

## Suggested Repository Structure

```text
ict_silver_bullet_bot/
├── src/
│   └── silver_bot/
│       ├── config/
│       ├── data/
│       ├── exchange/
│       ├── strategy/
│       ├── risk/
│       ├── execution/
│       ├── backtest/
│       ├── ml/
│       ├── monitoring/
│       ├── storage/
│       └── utils/
├── tests/
├── data/
│   ├── raw/
│   ├── processed/
│   └── backtests/
├── models/
├── logs/
├── reports/
├── docker/
├── codex-task.json
├── AGENTS.md
├── README.md
├── ARCHITECTURE.md
├── STRATEGY_NOTES.md
├── RISK_POLICY.md
├── ML_MODEL.md
├── DEPLOYMENT.md
├── PROGRESS.md
├── TODO.md
├── .env.example
├── pyproject.toml
└── main.py
```

## Safe Defaults

The bot must default to safe values:

```text
LIVE_TRADING=false
PAPER_TRADING=true
DEMO_TRADING=false
MAX_RISK_PER_TRADE=0.005
MAX_DAILY_LOSS=0.02
MAX_CONSECUTIVE_LOSSES=3
MAX_TRADES_PER_DAY=3
USE_ML_FILTER=false
ALLOW_MARKET_ORDERS=false
REQUIRE_STOP_LOSS=true
```

## Basic Setup

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it:

```bash
# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Copy the environment file:

```bash
cp .env.example .env
```

Review the complete configuration checklist:

```text
CONFIGURATION.md
```

Optional YAML configuration example:

```bash
cp config.example.yaml config.yaml
```

Run tests:

```bash
pytest
```

Run backtest:

```bash
TRADING_MODE=backtest PAPER_TRADING=false python main.py
```

Run paper trading:

```bash
TRADING_MODE=paper PAPER_TRADING=true python main.py
```

Run demo/testnet readiness without placing orders:

```bash
python -m silver_bot.demo_readiness
```

Start demo/testnet mode safely only after configuring demo API keys and passing
demo readiness:

```bash
MODE=demo DEMO_TRADING=true BINANCE_TESTNET=true LIVE_TRADING=false PAPER_TRADING=false python main.py
```

Safe Docker demo/testnet flow:

```bash
docker compose build
docker compose --profile demo run --rm demo python -m silver_bot.demo_readiness
docker compose --profile demo run --rm demo
```

The demo profile forces `LIVE_TRADING=false`, `BINANCE_TESTNET=true`, the
Binance Futures testnet URL, risk limits, stop-loss requirement, and a
container kill-switch path at `/app/data/KILL_SWITCH`. If `data/KILL_SWITCH`
exists on the host, demo readiness is intentionally blocked.

Live trading should not be available until the readiness checklist is implemented and passed.

## Docker Deployment

Deployment defaults to paper mode:

```bash
docker compose build
docker compose up bot
```

Safe one-off commands:

```bash
docker compose --profile backtest run --rm backtest
docker compose --profile paper run --rm paper
docker compose --profile demo run --rm demo
docker compose --profile research run --rm research
```

The Docker image does not copy `.env` by default, and runtime `data`, `logs`,
`models`, and `reports` directories are mounted as volumes. Live trading remains
blocked.

## Codex Workflow

Do not ask Codex to build the entire bot at once.

Use phase-based prompts.

Example:

```text
Read codex-task.json, AGENTS.md, ARCHITECTURE.md, STRATEGY_NOTES.md, and RISK_POLICY.md.

Implement Phase 1 only:
- project_scaffold
- configuration_system
- exchange_adapter_interface
- market_data_fetcher
- data_storage_layer

Constraints:
- Do not implement live trading yet.
- Do not place real orders.
- Paper mode must be default.
- Add type hints, docstrings, and pytest tests.
- Update PROGRESS.md after finishing.
```

## Non-Negotiable Rules

- No hardcoded API keys.
- No live trading by default.
- No martingale.
- No averaging down.
- No trade without stop loss.
- No ML-generated trades.
- No optimization on the final test set.
- No hidden strategy changes without logging.
- Every trade must have an explanation record.
