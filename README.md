# SILVR

A quant trend-following system for crypto futures (Binance USDT-M perpetuals), written in Python 3.11+ for personal use by its owner. It runs rule-based strategies with published evidence behind them, each behind a mandatory risk engine and a promotion gate. The one strategy today, `trend_ensemble`, is a long-only Donchian-ensemble trend follower over 15 frozen coins, adapted from Zarattini, Pagani and Barbon (2025), "Catching Crypto Trends" (SSRN 5209907). It runs in backtest only; paper and demo modes refuse to start until a trend runtime exists.

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

Full proposal conditions: [RFC-004 §7.1](<C:/AI Agentic Memory/03_Resources/RFCs/SILVR/rfc-silvr-readiness-gates.md>).

## Current Status

Honest summary on `feat/be-trend-ensemble` at `492c4b8` (2026-11-10; see [prd-silvr](<C:/AI Agentic Memory/03_Resources/Blueprints/SILVR/prd-silvr.md>) section 3 for the per-feature table):

- Strategy `trend_ensemble` (built and tested): daily bars in UTC; nine lookbacks per coin (5, 10, 20, 30, 60, 90, 150, 250 and 360 days); a slice enters long when a daily close beats the highest close of the prior N days, filled at the next day's first 1m open; its stop is the midpoint of the N-day close channel, only ever raised, and fills intraday; no take-profit and no resizing. Rules: [RFC-001](<C:/AI Agentic Memory/03_Resources/RFCs/SILVR/rfc-silvr-signal-engine.md>).
- Sizing: slice notional = k x (0.25 / 90-day annualized volatility) / 15 / 9 x equity, with k = `SCALE_K` = 1.0, the paper's own per-slice weight (owner decision, not fitted to results). Caps: 0.5% risk per slice, total notional at most 2x equity, Binance minimums (skip, never round up).
- Risk: the `trend` risk profile plus a drawdown kill switch that flattens everything and halts the segment after a $4,500 drop from peak marked equity (30% of $15,000). The `default` profile is unchanged.
- Backtest: one shared simulated $15,000 account per segment (chronological 60/20/20), marked to market every 1m close, with fees, spread, slippage and funding. The report carries the gate metrics and a success standard: average weekly net against a $50 target. No counted gate run has been made yet, and no result is claimed.
- Paper and demo: `python -m silvr` in paper or demo mode exits 2 with "no strategy available for paper or demo mode yet: trend_ensemble runs in backtest only", before any network call or database connection. The default mode is still paper, so the compose `bot` service and the systemd unit stop with exit 2 (systemd does not restart exit 2).
- ML: no ML code exists; `ML_FILTER_ENABLED=true` is refused at config load.
- Evidence: the live-readiness evidence checks (`backtest_report.json`, `paper_trading_report.json`) cannot pass today, so readiness fails closed. Live trading (PRD-F12) stays Planned and blocked.
- Tests: `python -m pytest -q` (the tests need a PostgreSQL server at `TEST_DATABASE_URL`).
- Known safety hazards are listed in [audit-docs-drift](<C:/AI Agentic Memory/04_Archives/Audits/2026-10/audit-docs-drift.md>) and [scrutiny-silvr](<C:/AI Agentic Memory/01_Projects/SILVR/Planning/scrutiny-silvr.md>).

## Quick Start

Set up the environment and run the tests by following [runbook-local-dev](<C:/AI Agentic Memory/02_Areas/Dev_&_Ops/SILVR/runbook-local-dev.md>). The tests need PostgreSQL (`TEST_DATABASE_URL`, default `postgresql://silvr:silvr@localhost:5432/silvr`; `docker compose up -d postgres` starts one). Backtests need no database. Hosting files for an Oracle Cloud server (`docker compose` under the systemd unit in `deploy/`) exist, but with no paper or demo strategy the bot service stops with exit 2; setup steps are in [ops-silvr](<C:/AI Agentic Memory/02_Areas/Dev_&_Ops/SILVR/ops-silvr.md>).

Backtest `trend_ensemble` on Binance USD-M futures klines (full steps in [runbook-backtest](<C:/AI Agentic Memory/02_Areas/Dev_&_Ops/SILVR/runbook-backtest.md>)):

1. Download 1m candles for the 15 frozen coins (BTCUSDT files at the root of `data/candles/`, the others in `data/candles/<SYMBOL>/`) and their funding history (`data/funding/<SYMBOL>-funding.csv`) with `python -m silvr.data.download --start 2022-01-01 --end 2026-10-21 --symbol <SYMBOL> [--out DIR]` and the same command with `--funding` (public API, no API key; rerun it to resume).
2. In `.env` set `MODE=` (blank), `TRADING_MODE=backtest` and `PAPER_TRADING=false`.
3. Run `python -m silvr --candles data/candles --funding data/funding [--output-dir DIR] [--segments training|all]`, or directly `python -m silvr.backtest.trend_runner --candles-root data/candles --funding-root data/funding --output-dir DIR --segments training|all`. Expected: exit 0 and `out_of_sample_validation_report.json` in the output directory; exit 2 on missing or partial data (the run fails closed naming the symbol and month). `--segments training` (the default) runs the training segment only; the validation and final-test segments run only with `all`.
4. Run `python -m silvr.backtest.gate --report DIR/out_of_sample_validation_report.json`. Expected: one PASS or FAIL row per criterion and `GATE: PASS` or `GATE: FAIL` (exit 0, 1; 2 if the report is missing, malformed or its final test was skipped). Every run is logged and counted as a look at the data range; change no frozen setting between looks: the runbook explains why.

The reports are not committed (`reports/` is git-ignored), and no number from them is a performance claim.

## Safe Defaults

These are the `load_config` defaults (`src/silvr/config/settings.py:66-86`); the shipped `.env.example` keeps them:

```text
LIVE_TRADING=false
PAPER_TRADING=true
DEMO_TRADING=false
ML_FILTER_ENABLED=false
STOP_LOSS_REQUIRED=true
MAX_RISK_PER_TRADE=0.005
```

The risk engine requires a stop loss whatever `STOP_LOSS_REQUIRED` says, and there is no market-order setting (no order code exists). Maximum risk per trade is 0.5%, enforced at config load in every mode and by `RiskConfig` itself. The `default` risk profile keeps maximum daily loss 2%, maximum consecutive losses 3, maximum trades per day 3, one open position and maximum leverage 3x. The `trend` profile that `trend_ensemble` uses keeps 0.5% per slice, 2% daily loss, 3x leverage and the stop loss, allows 135 trades a day and 135 open slices, uses a relative minimum stop of 0.1% of the entry price, applies no take-profit or reward-to-risk check and no consecutive-loss trip, and adds the $4,500 drawdown kill switch; the full table is in [AGENTS.md](AGENTS.md) under Risk Rules. A backtest always uses its own simulated kill switch, never `KILL_SWITCH_PATH`. See [sdd-silvr](<C:/AI Agentic Memory/03_Resources/Blueprints/SILVR/sdd-silvr.md>) section 3.4 for the exact configuration keys and [rfc-silvr-risk-kill-switch](<C:/AI Agentic Memory/03_Resources/RFCs/SILVR/rfc-silvr-risk-kill-switch.md>) for the risk gates.

## Documentation Map

Project docs live in the owner's Obsidian vault (the AI Memory Vault at `C:\AI Agentic Memory`), not in this repo. The vault syncs to a private GitHub repo. Start at [docs/index.md](docs/index.md), which points to the vault project index `01_Projects/SILVR/00_Project_Index.md`. That index lists every document, its status and the open items. The links below are local vault paths.

- What and why: [prd-silvr](<C:/AI Agentic Memory/03_Resources/Blueprints/SILVR/prd-silvr.md>), [brd-silvr](<C:/AI Agentic Memory/03_Resources/Blueprints/SILVR/brd-silvr.md>)
- How it is built: [sdd-silvr](<C:/AI Agentic Memory/03_Resources/Blueprints/SILVR/sdd-silvr.md>), [AGENTS.md](AGENTS.md) (build guide)
- Tech stack: [sdd-silvr](<C:/AI Agentic Memory/03_Resources/Blueprints/SILVR/sdd-silvr.md>) section 2.4; version pins in [AGENTS.md](AGENTS.md) section 3
- Strategy (`trend_ensemble`), risk, ML and readiness: [RFC-001](<C:/AI Agentic Memory/03_Resources/RFCs/SILVR/rfc-silvr-signal-engine.md>), [RFC-002](<C:/AI Agentic Memory/03_Resources/RFCs/SILVR/rfc-silvr-risk-kill-switch.md>), [RFC-003](<C:/AI Agentic Memory/03_Resources/RFCs/SILVR/rfc-silvr-ml-filter-gate.md>), [RFC-004](<C:/AI Agentic Memory/03_Resources/RFCs/SILVR/rfc-silvr-readiness-gates.md>)
- Testing and gates: [qad-silvr](<C:/AI Agentic Memory/02_Areas/Quality_&_Strategy/SILVR/qad-silvr.md>)
- Operations: [ops-silvr](<C:/AI Agentic Memory/02_Areas/Dev_&_Ops/SILVR/ops-silvr.md>)
- What is wrong today: [scrutiny-silvr](<C:/AI Agentic Memory/01_Projects/SILVR/Planning/scrutiny-silvr.md>), [audit-docs-drift](<C:/AI Agentic Memory/04_Archives/Audits/2026-10/audit-docs-drift.md>)

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
