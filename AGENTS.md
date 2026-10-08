# Agent Instructions

## Project

This repository contains an ICT Silver Bullet automated trading bot.

The bot is written in Python and must prioritize safety, testability, and clear documentation.

## Main Goal

Build a stable research, backtesting, paper trading, and eventually live trading system for the ICT Silver Bullet strategy.

The bot must be developed phase by phase.

Do not attempt to build the entire roadmap in one pass.

## Read These Files First

Before making changes, read:

```text
README.md
ARCHITECTURE.md
BACKTESTING.md
STRATEGY_NOTES.md
RISK_POLICY.md
ML_MODEL.md
DEPLOYMENT.md
PROGRESS.md
TODO.md
codex-task.json
```

## Non-Negotiable Safety Rules

Never:

```text
enable live trading by default
place real orders unless LIVE_TRADING=true
hardcode API keys
commit .env files
use martingale
average down
trade without stop loss
let ML generate trades directly
bypass the risk engine
bypass the kill switch
optimize on the final test set
```

## Default Mode

Default mode must be:

```text
paper or backtest
```

Live trading must be blocked unless explicitly enabled and readiness checks pass.

## Development Style

Use:

```text
Python 3.11+
type hints
docstrings
modular files
pytest tests
clear error handling
structured logging
```

Prefer simple, understandable code over clever code.

## Expected Repository Layout

Use this structure unless there is a strong reason to change it:

```text
src/silver_bot/
  config/
  data/
  exchange/
  strategy/
  risk/
  execution/
  backtest/
  ml/
  monitoring/
  storage/
  utils/

tests/
data/
models/
logs/
reports/
```

## Implementation Rules

For every task:

1. Read the relevant documentation.
2. Implement only the requested phase or task.
3. Add or update tests.
4. Do not introduce live trading unless explicitly requested.
5. Update `PROGRESS.md`.
6. Update `TODO.md` checkboxes if tasks are completed.
7. Summarize changed files.
8. Explain how to run tests.

## Strategy Rules

The strategy is ICT Silver Bullet.

The bot should look for:

```text
session window
liquidity sweep
displacement
market structure shift
Fair Value Gap
retracement into FVG
defined stop loss
liquidity-based take profit
```

The strategy engine should output:

```text
LONG
SHORT
NO_TRADE
```

Every rejected setup must include a reason.

## ML Rules

ML is optional.

ML can only:

```text
approve a rule-based signal
reject a rule-based signal
reduce risk
```

ML cannot:

```text
generate trades
place orders
increase risk beyond maximum
bypass stop loss
bypass kill switch
```

## Risk Rules

The risk engine is mandatory.

Every trade must pass:

```text
position sizing
stop-loss validation
reward-to-risk validation
daily loss validation
consecutive loss validation
max trades validation
kill switch validation
```

## Testing Requirements

When adding code, add tests for:

```text
normal cases
edge cases
unsafe cases
invalid config
risk rejection
```

Use mocks for exchange calls.

Do not require real API keys for tests.

## Documentation Updates

When completing a task, update:

```text
PROGRESS.md
TODO.md
```

If architecture changes, update:

```text
ARCHITECTURE.md
```

If strategy logic changes, update:

```text
STRATEGY_NOTES.md
```

If risk logic changes, update:

```text
RISK_POLICY.md
```

If ML logic changes, update:

```text
ML_MODEL.md
```

## Final Response After Each Task

After completing a task, provide:

```text
Summary
Files changed
Tests added
How to run
Remaining risks
Next recommended task
```