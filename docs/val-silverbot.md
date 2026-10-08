# Validation Brief (VALIDATION)

**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Version:** 0.1
**Owner:** Cian Jake Francisco
**Status:** Draft
**Last updated:** 2026-10-08
**Last reconciled:** N/A (not a code-describing doc)

This brief asks whether the idea in [idea-silverbot.md](idea-silverbot.md) deserves more effort, and states when to stop. It is deliberately conservative: no market evidence and no performance evidence exist today. Gap ids are in [scrutiny-silverbot.md](scrutiny-silverbot.md); drift findings are in [audit-docs-drift.md](audit-docs-drift.md); requirements are in [brd-silverbot.md](brd-silverbot.md).

## 1. Problem Evidence

**Owner motivation (stated, not measured).** README.md §Project Philosophy sets the motive: build around survival, protect capital, log every decision, prove performance before live trading, and never trade without a stop loss. README.md §Important Warning states that crypto futures are high risk, that leverage can liquidate an account, and that the bot "must never be treated as guaranteed profitable".

**Evidence that the strategy has an edge: none.** `reports/backtest_report.json`, `reports/out_of_sample_validation_report.json` and `reports/paper_trading_report.json` are 0 bytes (G-1, D-86). The backtest engine is covered by tests on synthetic data only. No profit, win rate, drawdown or return figure exists anywhere in this repository, and none is claimed here.

**Evidence that the cost model is realistic: none.** Backtest slippage and spread default to 0 bps (`src/silver_bot/backtest/models.py:34-35`; D-5, G-11), although the old BACKTESTING.md described its cost treatment as conservative. See [ues-silverbot.md](ues-silverbot.md) §1.

## 2. Alternatives / Substitute Scan

No vendor performance claims are used. The comparison is about what each option offers against the Silver Bullet rule set plus a mandatory risk engine.

| Alternative | What it offers | Versus Silver Bot |
|---|---|---|
| Manual discretionary trading of the same method | No build cost; human judgment on context and news | Not repeatable; depends on attention and mood; no enforced stop, sizing or daily-loss rule; no audit trail. Silver Bot trades only the encoded rules and logs every rejection reason. |
| Exchange-native grid or DCA bots | Hosted by the venue; no code to maintain; simple to start | Different strategy family. DCA-style averaging conflicts with the project rules "no averaging down" and "no martingale"; none of them encode session windows, liquidity sweeps or FVG entries. |
| TradingView alerts plus manual execution | Good charting; alerts on conditions; low build cost | Alerts can flag conditions but a human still places and manages orders, so discipline and latency remain manual. No integrated backtest with costs, risk gates or kill switch. |
| Generic open-source bot frameworks | Existing exchange connectors, backtesting and order management | The strategy would still need to be written, and the owner's safety rules (fail-closed config, demo caps, kill switch, ML as filter only) would need to be adapted and trusted. The trade-off is build time versus control and auditability; not evaluated further (Open). |

Conclusion: nothing in the scan proves the project is worth finishing; it shows only that the combination of an exact rule set and an enforced risk layer is not available off the shelf for this method as far as this scan went. Whether that combination is profitable is the open question (G-1).

## 3. Feasibility

Feature ids are from PRD §3 (not yet written); statuses are from [scrutiny-silverbot.md](scrutiny-silverbot.md).

| Item | Built today | Evidence still missing |
|---|---|---|
| PRD-F1 Signal engine | Implemented with tests (caveats G-18, G-19) | Any proof of edge; lookahead check (U-7) |
| PRD-F2 Backtester | Event-driven engine, fee model, journal, metrics (partial, G-20) | Non-empty reports; a run with non-zero slippage and spread; walk-forward and out-of-sample split (G-12) |
| PRD-F3 Risk engine and kill switch | 14 gates implemented | Unified limits (G-5); kill switch inert by default (G-6); persisted state (G-7) |
| PRD-F4 Paper trading | Paper executor and engine | Market stream, reconnect and REST fallback are skeletons (G-13); no runtime (G-3) |
| PRD-F5 Demo/testnet | Config rules and readiness checks | All network I/O is a stub (G-13, G-17) |
| PRD-F6 ML filter | Components and tests; disabled | Not wired (G-9); no model shipped; leakage unchecked (G-22) |
| PRD-F7 Monitoring | Builders for logs, reports, dashboard JSON | No Telegram transport (G-15); unwired (G-16) |
| PRD-F8 Readiness | Checkers and report export | Existence-only checks accept 0-byte files (G-2) |
| PRD-F9 Safe config | Typed loader, fail-closed validation | Shipped `.env.example` does not load (G-4) |
| PRD-F10 Data and storage | SQLite storage | Historical fetch raises NotImplementedError (G-13, G-14) |
| PRD-F11 Deployment | Dockerfile, compose, systemd files | Container runs a stub that exits (G-3, G-26) |
| PRD-F12 Live trading | Blocked at config load | `Planned, blocked` |

Feasibility verdict: the foundations are real; running anything end to end is not yet possible. The next evidence step is a cost-inclusive backtest on owner-supplied history (G-1, G-12).

## 4. Kill Criteria

Source: the old BACKTESTING.md §Pass/Fail Criteria (lines 487-504) and §Red Flags (lines 506-520), restated as stop rules. Thresholds not given in the old document are marked Owner input required (OI-#) or Open; none is invented.

| # | Stop and do not proceed to the next mode if... | Threshold | Threshold source |
|---|---|---|---|
| K1 | Backtest profit factor is below the minimum | profit factor below 1.2 | BACKTESTING.md:494 (research threshold, not a profit guarantee) |
| K2 | Expectancy is not positive | expectancy at or below 0 | BACKTESTING.md:495 |
| K3 | Profit disappears after fees | net profit at or below 0 with the coded fees | BACKTESTING.md:511 |
| K4 | Profit disappears after realistic slippage and spread | net profit at or below 0 with non-zero slippage and spread | BACKTESTING.md:512; the 0 bps default is not realistic (G-11) |
| K5 | Maximum drawdown exceeds what the owner can accept | Owner input required (OI-3) | BACKTESTING.md:496 ("acceptable for account size") |
| K6 | Trade count is too small to be meaningful | Owner input required (OI-9) | BACKTESTING.md:497 and :516 (no number given) |
| K7 | Result depends on one lucky trade or one month | Open (no definition in old docs; to be set in QAD) | BACKTESTING.md:498-499, :513-514 |
| K8 | Walk-forward or Monte Carlo results collapse | Open; neither exists in code (D-6, G-12) | BACKTESTING.md:517-518 |
| K9 | Out-of-sample results are not acceptable | Open; the split helper is unwired (G-12) | BACKTESTING.md:501 |
| K10 | Paper trading does not match backtest behaviour | Open (no tolerance defined) | BACKTESTING.md:519 |
| K11 | Any evidence report is empty or missing | Any of the three report files is 0 bytes | G-1, D-86; the readiness check does not catch this today (G-2) |
| K12 | Any safety rule is broken in a test or run | Any order without a stop loss, any bypass of the risk engine or kill switch | AGENTS.md safety rules; risk engine rejection at `src/silver_bot/risk/engine.py:36-37` |

Mode order for proceeding: backtest, then paper, then demo/testnet, then (blocked) live. A stop on any row means fix or rework, not skip ahead.

## Self-Check

- [x] The brief states plainly that no market or performance evidence exists and cites G-1 and D-86.
- [x] The alternatives table has four rows (manual, exchange-native bots, TradingView alerts, open-source frameworks) with no vendor performance claims.
- [x] Every PRD-F1 to PRD-F12 appears in the feasibility table with built and missing evidence.
- [x] Each kill criterion names its threshold source or is marked Owner input required or Open.
- [x] Links point only to existing files; unwritten documents are plain text.
- [ ] Kill-criteria thresholds K5 to K10 are numeric (open until the owner answers OI-3 and OI-9 and the QAD defines the rest).
