# Idea Brief (IDEA)

**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Version:** 0.1
**Owner:** Cian Jake Francisco
**Status:** Draft
**Last updated:** 2026-10-08
**Last reconciled:** N/A (not a code-describing doc)

Silver Bot is a personal Python bot that looks for ICT Silver Bullet setups in crypto futures, checks every candidate against a mandatory risk engine, and runs first as a backtest, then as paper trading, then against the exchange demo/testnet. Live trading is `Planned, blocked`. This brief is the starting point; evidence and costs follow in [val-silverbot.md](val-silverbot.md), [brd-silverbot.md](brd-silverbot.md) and [ues-silverbot.md](ues-silverbot.md). Gaps are tracked in [scrutiny-silverbot.md](scrutiny-silverbot.md). Documents not yet written (PRD, SDD, QAD, CLR) are plain-text references.

## 1. The Spark

The owner wants a disciplined, repeatable way to trade one specific method, the ICT Silver Bullet, without relying on attention, mood or screen time. The method is rule-like enough to encode (README.md §Core Strategy): price enters a session window, takes liquidity, shows displacement and a market structure shift, leaves a Fair Value Gap, and the entry is taken on the retracement into that gap with a defined stop and a liquidity-based target.

Automation is attractive for three reasons stated in the project's own philosophy (README.md §Project Philosophy): protect capital first, log every decision, and prove performance before any live execution. A bot can enforce the same stop-loss and sizing rules on every trade and leave an audit trail; a human cannot do that reliably.

What this brief does not claim: that the method is profitable. No backtest, out-of-sample or paper evidence exists yet (all three report files are 0 bytes, G-1). The idea is worth pursuing only as a research and validation project until that evidence exists.

## 2. Who It's For

One person: the owner, as sole operator and trader, on personal capital. There are no customers, no outside users and no custody of anyone else's funds. There is no product, pricing or go-to-market plan. See [brd-silverbot.md](brd-silverbot.md) §3.

## 3. Scope & Cut Line

Feature ids are defined in PRD §3 (not yet written).

| In scope (this release) | Out of scope |
|---|---|
| PRD-F1 Silver Bullet signal engine | PRD-F12 Live trading (`Planned, blocked`) |
| PRD-F2 Backtester, costs, reports, out-of-sample validation | Selling, licensing or hosting the bot for others |
| PRD-F3 Risk engine and kill switch | Multi-user accounts, billing, support |
| PRD-F4 Paper trading | Marketing and go-to-market work |
| PRD-F5 Binance Futures demo/testnet mode | Any strategy other than ICT Silver Bullet |
| PRD-F6 Optional ML probability filter (filter only) | ML that generates or sizes trades |
| PRD-F7 Monitoring and alerting | |
| PRD-F8 Readiness gates | |
| PRD-F9 Safe configuration | |
| PRD-F10 Market data and storage | |
| PRD-F11 Deployment | |

Cut line: everything in the left column is allowed to be partial or stubbed today (see [scrutiny-silverbot.md](scrutiny-silverbot.md) for the honest status); nothing in the right column is built or planned for this release.

## 4. Success Criteria

Success is defined once, in [brd-silverbot.md](brd-silverbot.md) §7 (BRD-M1 to BRD-M10). Targets there come only from code or old-document thresholds; anything that needs a personal number is an Owner Input Register row (OI-#).

## 5. Operating Concept

```text
Market data (historical fetch, stream)         PRD-F10, PRD-F4
        |
        v
Strategy engine: LONG / SHORT / NO_TRADE       PRD-F1
(every NO_TRADE carries a reason)
        |
        v
ML filter (optional): approve / reject /       PRD-F6
reduce risk only; never creates a trade
        |
        v
Risk engine + kill switch (mandatory)          PRD-F3
sizing, stop loss, RR, daily loss, limits
        |
        v
Execution: paper executor, or demo/testnet     PRD-F4, PRD-F5
(live trading blocked at config load)
        |
        v
Monitoring: logs, audit log, journal,          PRD-F7
Telegram alerts, reports
```

Backtesting (PRD-F2) feeds the same strategy and risk engines with historical candles. Today the entrypoint is a startup stub, so this pipeline is not yet runnable end to end (G-3).

## 6. Open Questions

- Which instrument and timeframe should the first evidence run use? Code defaults are BTCUSDT on 1m. Owner input required (OI-7).
- Where will historical data come from and how far back? Owner input required (OI-8).
- Does the 1m timeframe survive realistic costs? Open; no evidence either way (scrutiny §4).
- Is the Silver Bullet rule set, as coded, faithful enough to the method to be worth testing? Open (G-19).
- What would make the owner stop the project? Kill criteria are drafted in [val-silverbot.md](val-silverbot.md) §4; the personal thresholds are Owner input required (OI-3, OI-9).

## Self-Check

- [x] Scope table covers PRD-F1 to PRD-F11 in and PRD-F12 out, with no GTM or multi-user work.
- [x] The brief makes no performance or profit claim and cites G-1 for the empty evidence reports.
- [x] The operating concept lists the pipeline order data, strategy, optional ML, risk, execution, monitoring.
- [x] Success criteria point to BRD §7 instead of restating numbers.
- [x] Links point only to files that exist; unwritten documents are plain text.
- [x] No em dashes and no unfinished-work tokens.
