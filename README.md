# Silver Bot

An ICT Silver Bullet trading bot for crypto futures (Binance Futures), written in Python 3.11+ for personal use by its owner. It is built as a rule-based strategy engine behind a mandatory risk engine, with backtesting, paper trading and testnet readiness checks, and an optional ML filter that can only approve, reject or reduce risk on a rule-based signal.

## Important Warning

This project is for research, backtesting, paper trading, and carefully controlled live experimentation. Trading crypto futures is high risk. Leverage can quickly liquidate an account. This bot must never be treated as guaranteed profitable.

Default mode is always:

```text
PAPER_TRADING=true
LIVE_TRADING=false
DEMO_TRADING=false
```

Live trading is blocked: the config loader rejects `LIVE_TRADING=true`, and order methods on the exchange adapter raise `OrderPlacementDisabled`. Live trading should only be considered after:

1. The strategy passes backtesting.
2. The strategy passes out-of-sample validation.
3. Paper trading is stable.
4. Risk controls are working.
5. Kill switch is enabled.
6. API withdrawals are disabled.
7. The owner accepts the risk.

## Current Status

Honest summary at commit `62037d1` (see [docs/prd-silverbot.md](docs/prd-silverbot.md) section 3 for the per-feature table):

- Built and tested: signal engine, risk engine, config loading, readiness checkers (108 tests pass).
- Partial: backtester, paper trading, demo/testnet mode, ML filter, monitoring, market data, deployment files.
- Not working end to end: `main()` is a startup stub. There is no runnable backtest, paper or demo mode from the entrypoint yet (G-3).
- No evidence: `reports/backtest_report.json`, `reports/out_of_sample_validation_report.json` and `reports/paper_trading_report.json` are empty. Nothing here supports any claim about strategy performance.
- Known safety hazards are listed in [docs/audit-docs-drift.md](docs/audit-docs-drift.md) and [docs/scrutiny-silverbot.md](docs/scrutiny-silverbot.md).

## Quick Start

Set up the environment and run the tests by following [docs/runbook-local-dev.md](docs/runbook-local-dev.md). Backtest steps are in [docs/runbook-backtest.md](docs/runbook-backtest.md) and testnet steps in [docs/runbook-demo-testnet.md](docs/runbook-demo-testnet.md); read their status notes first, because the entrypoint does not yet dispatch those modes.

## Safe Defaults

```text
LIVE_TRADING=false
PAPER_TRADING=true
DEMO_TRADING=false
USE_ML_FILTER=false
ALLOW_MARKET_ORDERS=false
REQUIRE_STOP_LOSS=true
```

Risk limits, with the caveat that not all of them reach the risk engine yet (D-11): maximum risk per trade 0.5%, maximum daily loss 2%, maximum consecutive losses 3, maximum trades per day 3. See [docs/sdd-silverbot.md](docs/sdd-silverbot.md) section 3.4 for the exact configuration keys and [docs/rfc-silverbot-risk-kill-switch.md](docs/rfc-silverbot-risk-kill-switch.md) for the risk gates.

## Documentation Map

Start at [docs/index.md](docs/index.md); it lists every document, its status and the open items.

- What and why: [docs/prd-silverbot.md](docs/prd-silverbot.md), [docs/brd-silverbot.md](docs/brd-silverbot.md)
- How it is built: [docs/sdd-silverbot.md](docs/sdd-silverbot.md), [docs/build-silverbot.md](docs/build-silverbot.md)
- Strategy and risk: [docs/rfc-silverbot-signal-engine.md](docs/rfc-silverbot-signal-engine.md), [docs/rfc-silverbot-risk-kill-switch.md](docs/rfc-silverbot-risk-kill-switch.md)
- Testing and gates: [docs/qad-silverbot.md](docs/qad-silverbot.md)
- Operations: [docs/ops-silverbot.md](docs/ops-silverbot.md)
- What is wrong today: [docs/scrutiny-silverbot.md](docs/scrutiny-silverbot.md), [docs/audit-docs-drift.md](docs/audit-docs-drift.md)

## Non-Negotiable Rules

The full rule set is in [AGENTS.md](AGENTS.md). In short:

- No hardcoded API keys; never commit `.env`.
- No live trading by default.
- No martingale and no averaging down.
- No trade without a stop loss.
- ML never generates trades or bypasses the risk engine.
- The risk engine and kill switch are never bypassed.
- No optimization on the final test set.
- Every trade has an explanation record.
