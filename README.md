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

Full proposal conditions: [RFC-004 §7.1](<C:/AI Agentic Memory/03_Resources/RFCs/rfc-silverbot-readiness-gates.md>).

## Current Status

Honest summary at commit `5c781fc` on `dev` (see [prd-silverbot](<C:/AI Agentic Memory/03_Resources/Blueprints/prd-silverbot.md>) section 3 for the per-feature table):

- Built and tested: signal engine, risk engine, config loading, readiness checkers, backtest from the command line (`python -m pytest -q`: 220 passed).
- HIGH safety fixes batch 1 (2026-10-09): a NaN or out-of-range ML probability now rejects; the testnet URL guard is an exact `https` host match; `.env.example` loads as paper mode; readiness rejects empty or non-JSON reports; backtests default to 5 bps slippage and 3 bps spread; risk per trade is capped at 0.5% everywhere; the kill switch fails closed and trips itself on the daily-loss and consecutive-loss limits; risk state can persist in SQLite. Backtests use the settings caps and a simulated per-run kill switch; no paper bot uses the real kill switch or the persisted state until a paper runtime builds its engine with `build_risk_engine` (G-3). Details: [scrutiny-silverbot](<C:/AI Agentic Memory/01_Projects/SilverBot/Planning/scrutiny-silverbot.md>) section 3.
- Partial: backtester, paper trading, demo/testnet mode, ML filter, monitoring, market data, deployment files.
- Entrypoint (G-3 entrypoint batch 2, 2026-10-09): `python -m silver_bot` runs the mode from configuration. Backtest mode loads Binance kline CSV files given with `--candles` and writes six reports, including a chronological out-of-sample report and a run record (exit 0; 2 on bad input). Paper and demo exit 78 (`mode not available yet: needs market data (G-13)`), and the systemd unit and compose do not restart on 78 (systemd also stops on exit 2 since `5c781fc`). There is no paper or demo runtime yet (G-3, G-13, G-17).
- No evidence: `reports/backtest_report.json`, `reports/out_of_sample_validation_report.json` and `reports/paper_trading_report.json` are empty until the owner runs a backtest on real data, and `reports/` is git-ignored. Nothing here supports any claim about strategy performance.
- Known safety hazards are listed in [audit-docs-drift](<C:/AI Agentic Memory/04_Archives/Audits/2026-10/audit-docs-drift.md>) and [scrutiny-silverbot](<C:/AI Agentic Memory/01_Projects/SilverBot/Planning/scrutiny-silverbot.md>).

## Quick Start

Set up the environment and run the tests by following [runbook-local-dev](<C:/AI Agentic Memory/02_Areas/Dev_&_Ops/runbook-local-dev.md>).

Backtest on Binance USD-M futures klines (full steps, including checksums, in [runbook-backtest](<C:/AI Agentic Memory/02_Areas/Dev_&_Ops/runbook-backtest.md>)):

1. Download monthly files from `https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/`, for example `BTCUSDT-1m-2026-01.zip`, and unzip the CSVs into `data/candles/`.
2. In `.env` set `MODE=` (blank), `TRADING_MODE=backtest` and `PAPER_TRADING=false`; `SYMBOL` and `TIMEFRAME` must match the files.
3. Run `python -m silver_bot --candles data/candles`. Expected: exit 0 and six files in `reports/`.

The reports are not committed (`reports/` is git-ignored), and no number from them is a performance claim. Paper and demo modes exit 78 for now; testnet preparation steps are in [runbook-demo-testnet](<C:/AI Agentic Memory/02_Areas/Dev_&_Ops/runbook-demo-testnet.md>).

## Safe Defaults

These are the `load_config` defaults (`src/silver_bot/config/settings.py:69-91`); the shipped `.env.example` keeps them:

```text
LIVE_TRADING=false
PAPER_TRADING=true
DEMO_TRADING=false
ML_FILTER_ENABLED=false
STOP_LOSS_REQUIRED=true
MAX_RISK_PER_TRADE=0.005
```

The risk engine requires a stop loss whatever `STOP_LOSS_REQUIRED` says, and there is no market-order setting (no order code exists). Risk limits: maximum risk per trade 0.5%, enforced at config load in every mode and by `RiskConfig` itself; maximum daily loss 2%, maximum consecutive losses 3, maximum trades per day 3, maximum leverage 3x. D-11 is partly resolved: `build_risk_config` maps the settings limits and kill-switch path into `RiskConfig`, and command-line backtests use it with a simulated per-run kill switch; the paper engine still uses `RiskConfig` defaults with no kill-switch path because no paper runtime exists (G-3). See [sdd-silverbot](<C:/AI Agentic Memory/03_Resources/Blueprints/sdd-silverbot.md>) section 3.4 for the exact configuration keys and [rfc-silverbot-risk-kill-switch](<C:/AI Agentic Memory/03_Resources/RFCs/rfc-silverbot-risk-kill-switch.md>) for the risk gates.

## Documentation Map

Project docs live in the owner's Obsidian vault (the AI Memory Vault at `C:\AI Agentic Memory`), not in this repo. The vault syncs to a private GitHub repo. Start at [docs/index.md](docs/index.md), which points to the vault project index `01_Projects/SilverBot/00_Project_Index.md`. That index lists every document, its status and the open items. The links below are local vault paths.

- What and why: [prd-silverbot](<C:/AI Agentic Memory/03_Resources/Blueprints/prd-silverbot.md>), [brd-silverbot](<C:/AI Agentic Memory/03_Resources/Blueprints/brd-silverbot.md>)
- How it is built: [sdd-silverbot](<C:/AI Agentic Memory/03_Resources/Blueprints/sdd-silverbot.md>), [AGENTS.md](AGENTS.md) (build guide)
- Tech stack: [sdd-silverbot](<C:/AI Agentic Memory/03_Resources/Blueprints/sdd-silverbot.md>) section 2.4; version pins in [AGENTS.md](AGENTS.md) section 3
- Strategy, risk, ML and readiness: [RFC-001](<C:/AI Agentic Memory/03_Resources/RFCs/rfc-silverbot-signal-engine.md>), [RFC-002](<C:/AI Agentic Memory/03_Resources/RFCs/rfc-silverbot-risk-kill-switch.md>), [RFC-003](<C:/AI Agentic Memory/03_Resources/RFCs/rfc-silverbot-ml-filter-gate.md>), [RFC-004](<C:/AI Agentic Memory/03_Resources/RFCs/rfc-silverbot-readiness-gates.md>)
- Testing and gates: [qad-silverbot](<C:/AI Agentic Memory/02_Areas/Quality_&_Strategy/qad-silverbot.md>)
- Operations: [ops-silverbot](<C:/AI Agentic Memory/02_Areas/Dev_&_Ops/ops-silverbot.md>)
- What is wrong today: [scrutiny-silverbot](<C:/AI Agentic Memory/01_Projects/SilverBot/Planning/scrutiny-silverbot.md>), [audit-docs-drift](<C:/AI Agentic Memory/04_Archives/Audits/2026-10/audit-docs-drift.md>)

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
