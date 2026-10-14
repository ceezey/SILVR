# Business Requirements (Personal Trading) (BRD)

**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Version:** 0.1
**Owner:** Cian Jake Francisco
**Status:** Draft
**Last updated:** 2026-10-09
**Last reconciled:** 2026-10-08 against code at commit `62037d1`; risk, cost and kill-switch statements re-checked 2026-10-09 against `70ccaec`; the section 5 risk-wiring sentence and OI-8 and OI-11 re-checked 2026-10-09 against `099085b`

This document states why the project exists, what it must achieve, and which numbers only the owner can supply. It defines the ids `BRD-V#` (impact variables), `BRD-M#` (success metrics) and `OI-#` (owner inputs) that the PRD, SDD and index cite. Context: [idea-silverbot.md](idea-silverbot.md), [val-silverbot.md](val-silverbot.md), [ues-silverbot.md](ues-silverbot.md), [scrutiny-silverbot.md](scrutiny-silverbot.md) and [audit-docs-drift.md](audit-docs-drift.md). The documents that cite these ids are [prd-silverbot.md](prd-silverbot.md), [sdd-silverbot.md](sdd-silverbot.md), [qad-silverbot.md](qad-silverbot.md) and [clr-silverbot.md](clr-silverbot.md).

## 1. Executive Summary

Silver Bot is a personal, single-operator trading bot for the ICT Silver Bullet method on crypto futures (default venue Binance Futures, default symbol BTCUSDT, default timeframe 1m; `src/silver_bot/config/settings.py:74-76`). It must earn its way through four modes in order: backtest, paper, exchange demo/testnet, and only then, if ever, live. Live trading is `Planned, blocked` and is hard-rejected at config load (`settings.py:105-108`).

The business requirement is survival first: no trade without a stop loss, no martingale, no averaging down, fixed fractional risk, and a mandatory risk engine and kill switch. The success requirement is evidence: cost-inclusive, out-of-sample results and a stable paper run before any step toward live. Today no such evidence exists: the three evidence reports are 0 bytes (G-1, D-86) and no performance claim is made in this document.

## 2. Problem & Opportunity (personal)

**Problem.** Discretionary execution of a rule-based method is inconsistent: stops move, size drifts, trades are skipped or forced. A person also cannot watch the session windows continuously or keep a complete decision log (old README.md (commit `62037d1`) §Project Philosophy).

**Opportunity.** If the method has an edge after realistic costs, encoding it plus an enforced risk layer could trade it consistently with a full audit trail. If it has no edge, the project's value is finding that out cheaply and safely in backtest and paper modes. Both outcomes are acceptable; an unvalidated live deployment is not.

**What is not claimed.** No expected return, win rate or profit is stated or implied. Whether an edge exists is Open until non-empty reports exist (G-1).

## 3. Operating Model

- **Capital:** the owner's personal capital only. The amount is Owner input required (OI-1). The 10,000.0 `initial_balance` in `BacktestConfig` (`src/silver_bot/backtest/models.py:30`) is a simulation default, not a capital decision.
- **Operator:** the owner is the sole operator and decision maker; there are no customers, no outside funds and no product pricing.
- **Time:** monitoring time the owner can give per day is Owner input required (OI-5); it decides how much unattended operation the alerts and kill switch must cover.
- **Environment:** development on the owner's machine; 24/7 runs on a VPS with Docker and systemd were the old plan (DEPLOYMENT.md §Recommended Hosting); costs in [ues-silverbot.md](ues-silverbot.md) §3.
- **Mode ladder:** backtest, paper, demo/testnet, live (blocked). Moving up a rung requires the stop checks in [val-silverbot.md](val-silverbot.md) §4 to pass.

## 4. Impact Variables

The few variables that dominate whether the project succeeds. Each is something the owner can measure from the bot's own outputs. Unit economics for BRD-V2 and BRD-V3 are in [ues-silverbot.md](ues-silverbot.md).

| ID | Variable | Why it dominates | Where it lives |
|---|---|---|---|
| BRD-V1 | Edge per trade (expectancy in R, and win rate at a given reward-to-risk) | Without positive expectancy after costs nothing else matters. Unproven (G-1). | Backtest metrics `expectancy`, `average_r`, `win_rate`, `profit_factor` (`src/silver_bot/backtest/metrics.py:30-46`) |
| BRD-V2 | Cost per trade (fees, slippage, spread, as a fraction of notional and in R) | Costs are subtracted from every trade and rise with 1m trade frequency. Backtest slippage and spread default to 5.0 and 3.0 bps since `59ed6d5` (D-5, G-11 closed); whether that matches real fills is unverified. | `BacktestConfig` and `PaperExecutionConfig` (`backtest/models.py:32-35`, `execution/models.py:30-33`) |
| BRD-V3 | Risk per trade (fraction of equity at stake) | Sets loss size per stop-out and, with the stop distance, the notional and the cost in R. | `RiskConfig.risk_per_trade` (`risk/models.py:21`) |
| BRD-V4 | Trade frequency | More trades raise cost drag and exposure; fewer trades make evidence slow to gather. Capped at 3 per day by default. | `RiskConfig.max_trades_per_day` (`risk/models.py:26`) |
| BRD-V5 | Drawdown control (daily loss cap, consecutive-loss cap, kill switch) | Bounds the damage while the edge is still unproven. The kill switch now trips itself on the daily-loss and consecutive-loss limits and risk state can persist in SQLite, but only an engine built by `build_risk_engine` gets either, and nothing builds one yet (G-6, G-7 partial). | `risk/models.py:24-25,29`; `risk/engine.py:81-88` |

## 5. Capital Philosophy Gate

These rules are not tunable per trade; they are conditions for the project to exist. Code locations are the reconciled commit.

| Rule | Where it is enforced or stated | Honest status |
|---|---|---|
| No martingale and no averaging down | Stated in `risk/models.py:18`; AGENTS.md safety rules. `max_open_positions` is 1 (`risk/models.py:27`, checked at `risk/engine.py:90`), so a second position cannot be added. | No code path scales size up after a loss; verified by reading, test coverage tracked in [qad-silverbot.md](qad-silverbot.md). |
| Stop loss always | `risk/engine.py:54-55` rejects a request with no stop loss; rejects wrong-side stops (`:60-61`) and stops tighter than `minimum_stop_distance` (`:62-63`). Config requires `STOP_LOSS_REQUIRED=true` in demo mode (`config/settings.py:189-190`). | Enforced in the risk engine. `minimum_stop_distance` is an absolute price amount, default 0.01 (`risk/models.py:22`), so it is a floor, not a percent control. |
| Fixed fractional risk | Position size = risk amount / stop distance (`risk/engine.py:94`), with `risk_per_trade` defaulting to 0.005 (0.5% of equity; `risk/models.py:21`). | Enforced when the risk engine sizes the trade. |
| Minimum reward-to-risk | `minimum_reward_to_risk` defaults to 2.0 (`risk/models.py:23`). | Enforced; a setup below it is rejected. |
| Daily loss, consecutive loss, trades per day, open positions | Defaults 0.02, 3, 3, 1 (`risk/models.py:24-27`); checks at `risk/engine.py:81-90`. | Enforced. State persists across restarts only for an engine built with SQLite storage; the paper and backtest engines keep it in memory (G-7 partial). |
| Leverage cap | Default 3.0 (`risk/models.py:28`); rejection at `risk/engine.py:97-98`. | Enforced in the risk engine. |
| Kill switch | `kill_switch_path` default None, which makes it inert (`risk/models.py:29`); active check at `risk/engine.py:48-49`; fail-closed check and automatic trip at `risk/kill_switch.py:22-60`. | Inert by default; when a path is set it fails closed and trips on the daily-loss and consecutive-loss limits. No position close (G-6 partial). |

**Precision on where the percentages apply.** The Settings caps `MAX_RISK_PER_TRADE` 0.005, `MAX_DAILY_LOSS` 0.02 and `MAX_LEVERAGE` 3 (`config/settings.py:177-179`) behave differently since `5e4acc5`. `MAX_RISK_PER_TRADE` must be in (0, 0.005] in every mode (`config/settings.py:180-181`), and `RiskConfig` rejects a per-trade risk above 0.005 (`risk/models.py:10,32-33`), so 0.5% is both the default and the ceiling. `MAX_DAILY_LOSS` and `MAX_LEVERAGE` are still validated only in demo mode (`config/settings.py:191-194`). `build_risk_config` maps all three into `RiskConfig` (`risk/factory.py:15-23`) and CLI backtests use it since `099085b`; `build_risk_engine` (`risk/factory.py:26-33`) adds SQLite state, but no paper runtime calls it yet (D-11, G-5 partial, G-3 partial). Details are in [RFC-002](rfc-silverbot-risk-kill-switch.md) (risk and kill switch).

The ML filter can only approve, reject or reduce risk; it never creates a trade, places an order, raises risk or bypasses the stop loss or kill switch (AGENTS.md ML rules; `ml/filter.py`). A NaN or out-of-range model probability rejects since `8e66054` (G-8 closed).

## 6. Scope

Feature ids are defined in PRD §3 of [prd-silverbot.md](prd-silverbot.md).

- **In scope:** PRD-F1 to PRD-F11, for personal use, one instrument by default, research, backtest, paper and demo modes.
- **Out of scope:** PRD-F12 live trading (`Planned, blocked`); selling or licensing the bot; multi-user operation; custody of other people's funds; any go-to-market activity; strategies other than ICT Silver Bullet.
- **Release boundary:** this release ends when evidence reports exist and the stop checks pass, not when live trading is switched on. Switching live on is a separate decision with its own change record.

## 7. Success Metrics

Targets come only from code or old-document thresholds. Where neither supplies a number the target is `Owner input required (OI-#)` or `Open`. The old thresholds are minimum research thresholds, not profit guarantees (BACKTESTING.md:504). No row below reports a measured result; none exists (G-1).

| ID | Metric | Target | Source of target | Measured by |
|---|---|---|---|---|
| BRD-M1 | Backtest profit factor (after costs) | At least 1.2 | BACKTESTING.md:494 | `profit_factor` in the backtest report (`backtest/metrics.py:35`) |
| BRD-M2 | Backtest expectancy (after costs) | Greater than 0 (positive) | BACKTESTING.md:495 | `expectancy` in the backtest report |
| BRD-M3 | Costs are realistic in the evidence run | Backtest run with non-zero slippage and spread; the bps values are Open (to be set in QAD, ideally from paper or demo fills) | BACKTESTING.md:500; G-11 | `slippage_bps` and `spread_bps` recorded in the report config |
| BRD-M4 | Maximum drawdown | Owner input required (OI-3) | BACKTESTING.md:496 ("acceptable for account size") | `max_drawdown` and `max_drawdown_percent` |
| BRD-M5 | Number of trades in the evidence run | Owner input required (OI-9) | BACKTESTING.md:497 (no number given) | `total_trades` |
| BRD-M6 | Result is not carried by one trade or one short period | Open (definition to be set in QAD) | BACKTESTING.md:498-499 | Trade journal and `session_performance` |
| BRD-M7 | Out-of-sample result acceptable | Open (criteria to be set in QAD); the final test set stays untouched until final validation | BACKTESTING.md:501, :108-127 | Out-of-sample report (currently 0 bytes, G-1, G-12) |
| BRD-M8 | Paper run matches backtest behaviour | Open (tolerance not defined) | BACKTESTING.md:519 | `reports/paper_trading_report.json` against the backtest report |
| BRD-M9 | Return goal | Owner input required (OI-4) | None in code or old docs | Backtest `return_percent`, later paper and demo reports |
| BRD-M10 | Safety integrity: orders placed without a stop loss, or bypassing the risk engine or kill switch | Zero | AGENTS.md safety rules; `risk/engine.py:54-55` | Risk-engine rejection tests and audit log ([qad-silverbot.md](qad-silverbot.md)) |

Evidence gate: BRD-M1 to BRD-M8 cannot be marked met while any of the three reports is empty (G-1).

## 8. Owner Input Register

Every number or decision that only the owner can give. Referenced as `Owner input required (OI-#)` elsewhere. No default is assumed. Collects G-30 and owner unknowns U-1 to U-4 from [scrutiny-silverbot.md](scrutiny-silverbot.md).

| OI-# | Input | Why it matters | Used by |
|---|---|---|---|
| OI-1 | Trading capital for paper sizing context and, if ever enabled, live (amount, currency) | Converts every risk percent into money; sets what a stop-out costs | BRD §5, UES §4; scrutiny G-30 |
| OI-2 | Monthly running-cost budget (VPS, data, any paid tooling) | Sets runway and whether the project is affordable to run unattended | UES §3 |
| OI-3 | Maximum drawdown tolerance, as a percent of capital and in money | Defines the stop line for BRD-M4 and kill criterion K5 | BRD-M4, VALIDATION K5, UES §4 |
| OI-4 | Return goal, if any (period and measure) | Without it, success has no upper target; the bot cannot be judged against a goal | BRD-M9 |
| OI-5 | Monitoring hours per day the owner can give | Decides alerting, restart and kill-switch requirements for unattended runs | BRD §3, [ops-silverbot.md](ops-silverbot.md) |
| OI-6 | Jurisdiction and tax treatment (kept generic here) | Determines legal and tax obligations for personal trading | [clr-silverbot.md](clr-silverbot.md), scrutiny §6 |
| OI-7 | Target instruments and timeframe for the first evidence run (code default BTCUSDT, 1m) | Fixes the data and cost assumptions for the evidence run | IDEA §6, BRD-M3, QAD |
| OI-8 | Historical data source and how far back to test | Without data no evidence backtest exists. The backtest CLI reads Binance kline CSV files the owner downloads ([runbook-backtest.md](runbook-backtest.md)); the network fetch raises NotImplementedError (G-13) | BRD-M3, UES §3 |
| OI-9 | Minimum number of trades the owner accepts as meaningful evidence | The old document requires "enough trades" but gives no number | BRD-M5, VALIDATION K6 |
| OI-10 | Intended venue account for demo and, if ever, live (and whether it is already opened) | Needed for API key handling, withdrawal restrictions and venue terms | [clr-silverbot.md](clr-silverbot.md), [RFC-004](rfc-silverbot-readiness-gates.md) |
| OI-11 | Is the container restart loop after `main()` exits intentional, and should `config.yaml` be present in the container (U-1, U-2) | Decides the configuration source in deployment. The restart part is moot: since `f6bc017` paper exits 78 and the supervisors do not restart it | [ops-silverbot.md](ops-silverbot.md), [sdd-silverbot.md](sdd-silverbot.md) |
| OI-12 | Who builds the ML filter configuration from settings, and how should stream reconnection be configured (U-3, U-4) | Closes two design questions only the owner can decide | [sdd-silverbot.md](sdd-silverbot.md), [RFC-003](rfc-silverbot-ml-filter-gate.md) |

## 9. Stakeholders

| Stakeholder | Role | Interest or dependency |
|---|---|---|
| Owner (Cian Jake Francisco) | Sole operator, trader, funder and decision maker | Capital safety first; evidence before live; all OI-# answers |
| Exchange (Binance Futures, production and testnet) | Venue and data dependency | API availability, fees, rate limits and terms of use; no network code exists yet (G-13, G-17) |
| Telegram | Alert channel dependency | Required for the alerting readiness item; no real transport exists yet (G-15) |

## Self-Check

- [x] The BRD defines BRD-V1 to BRD-V5, BRD-M1 to BRD-M10 and OI-1 to OI-12 with no gaps in numbering.
- [x] Every metric target is either a cited code or old-document value, or is marked Owner input required (OI-#) or Open.
- [x] Risk percentages are stated with their exact scope: the 0.005 per-trade cap applies in every mode and in `RiskConfig`; the daily-loss and leverage caps apply in demo mode only (D-11, G-5).
- [x] No performance or profit claim is made; G-1 and D-86 are cited for the empty reports.
- [x] The capital philosophy rows each cite a file and line number from the reconciled commit.
- [x] Links point only to existing files.
- [ ] Every OI-# has an answer from the owner (open; all twelve are unanswered).
