# Risk Policy

## Purpose

This document defines mandatory risk controls for the ICT Silver Bullet bot.

The bot is currently limited to research, backtesting, and paper-trading foundations. Live trading is not approved.

## Non-Negotiable Rules

The bot must never:

```text
enable live trading by default
place real orders unless LIVE_TRADING=true
trade before readiness checks pass
hardcode API keys or secrets
use martingale
average down
trade without a stop loss
bypass the risk engine
bypass the kill switch
let ML generate or place trades directly
increase risk because of ML output
optimize on the final test set
```

## Safe Defaults

Default runtime settings must be:

```text
LIVE_TRADING=false
PAPER_TRADING=true
DEMO_TRADING=false
```

Allowed safe runtime modes are:

```text
paper
backtest
demo
```

Demo mode is Binance Futures demo/testnet only and must keep
`LIVE_TRADING=false`. Live mode must remain rejected until live-readiness work
is explicitly requested and implemented.

## Mandatory Trade Gates

Before any future trade can be executed, it must pass:

```text
position sizing
stop-loss validation
reward-to-risk validation
daily loss validation
consecutive loss validation
max trades validation
kill switch validation
```

## ML Restrictions

ML may only:

```text
approve a rule-based signal
reject a rule-based signal
reduce risk
```

ML must never:

```text
generate trades
place orders
increase risk
bypass stop loss
bypass kill switch
```

Implemented ML filter behavior:

```text
ML can only inspect an existing rule-based signal
ML rejection happens before risk evaluation
ML reduce_risk is applied only after risk approval
ML reduce_risk can only shrink position size, risk amount, and leverage
ML cannot increase configured risk_per_trade
Risk engine remains mandatory for every trade candidate
```

## Phase 1 Status

Phase 1 must not contain a live execution path. Exchange adapters may define interfaces, but real order placement and cancellation must remain disabled.

## Demo/Testnet Risk Gate

Binance Futures demo/testnet mode is not real-money live trading, but it must
still fail closed. Demo mode requires:

```text
MODE=demo
DEMO_TRADING=true
BINANCE_TESTNET=true
LIVE_TRADING=false
PAPER_TRADING=false
testnet Binance Futures endpoint only
demo API keys present
risk engine enabled
kill switch enabled and configured
kill switch file is not currently active
STOP_LOSS_REQUIRED=true
MAX_RISK_PER_TRADE <= 0.005
MAX_DAILY_LOSS <= 0.02
MAX_LEVERAGE <= 3
```

Production Binance endpoints must be rejected in demo mode.

## Implemented Backtest Risk Controls

The backtest engine must route every strategy candidate through the risk engine before a simulated pending order is created.

Implemented controls:

```text
position sizing from account equity and risk per trade
stop-loss required
stop-loss distance validation
minimum reward-to-risk validation
max daily loss validation
max consecutive losses validation
max trades per day validation
max open positions validation
maximum leverage validation
file-based kill switch validation
```

Backtest risk rejections must be logged as rejected signal records.

Fixed-size backtest position sizing must not bypass the risk engine.

## Live-Readiness Gate

Live execution remains unimplemented. Before any future live execution can be
considered, the readiness checker must pass every required gate:

```text
backtest report exists
out-of-sample validation report exists
paper trading report exists
risk engine enabled
kill switch enabled and configured
kill switch file is not currently active
Telegram alerts tested or explicitly disabled
API keys present in the process environment
LIVE_TRADING=true
PAPER_TRADING=false
READINESS_CHECK_PASSED=true
API_WITHDRAWALS_DISABLED=true
MAX_RISK_PER_TRADE <= 0.005
MAX_DAILY_LOSS <= 0.02
MAX_LEVERAGE <= 3
```

If any readiness check fails, live trading must remain blocked.
