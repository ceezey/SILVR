# Design System (DSD)

**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Version:** 0.1
**Owner:** Cian Jake Francisco
**Status:** Draft (design system not started)
**Last updated:** 2026-10-09
**Last reconciled:** N/A (not a code-describing doc)
**Design file:** [Figma](https://www.figma.com/design/g1n3J4j2L1iPrbdjiOS30e/Untitled?node-id=0-1&p=f). It is the working canvas for the section 9 proposal; nothing in it is built or approved.

> The bot has no user interface today. Sections 0 to 8 are intentionally empty. Section 9 is a proposal, not built, and adds no requirement: no PRD feature, user story or acceptance criterion depends on it. The operator surface that exists is listed in [prd-silverbot.md](prd-silverbot.md) section 5.1 (command-line entrypoints and files only).

## 0. Brand Stance

Not started. Begins only if the Recommended UI in §9 is approved through a Change Record.

## 1. Design Philosophy & Vision

Not started. Begins only if the Recommended UI in §9 is approved through a Change Record.

## 2. Brand Primitives (tokens, color, type)

Not started. Begins only if the Recommended UI in §9 is approved through a Change Record.

## 3. Layout & Spatial System

Not started. Begins only if the Recommended UI in §9 is approved through a Change Record.

## 4. Core Component Specs

Not started. Begins only if the Recommended UI in §9 is approved through a Change Record.

## 5. Motion

Not started. Begins only if the Recommended UI in §9 is approved through a Change Record.

## 6. Accessibility

Not started. Begins only if the Recommended UI in §9 is approved through a Change Record.

## 7. Quality Gate

Not started. Begins only if the Recommended UI in §9 is approved through a Change Record.

## 8. Materialization

Not started. Begins only if the Recommended UI in §9 is approved through a Change Record.

## 9. Recommended UI (Proposal, not built)

### 9.1 Why

The owner operates the bot by reading files, not by clicking. The core flows in [prd-silverbot.md](prd-silverbot.md) section 5.3 are: run a readiness checker and read its JSON (flow 4), create or delete the kill-switch file (flow 5), and review evidence reports and logs after a run (flows 1 and 2). Each is a check of safety state or evidence. Today that means opening several files by hand, and the one failure that is easy to miss is an evidence report that is present but 0 bytes (G-1, D-86, H-2).

### 9.2 Recommended form

A local, read-only status dashboard served on localhost. It has no order buttons and no write path to configuration, the kill-switch file or the database. Rationale: the owner mostly checks safety state and evidence, and any control surface would be a new path around the live-trading block ([sdd-silverbot.md](sdd-silverbot.md) section 5.1). The kill switch stays a file the owner creates or deletes ([ops-silverbot.md](ops-silverbot.md) section 4.1).

### 9.3 Panels

Every panel reads one named source. The "Status today" column says whether that source holds data or is produced at all.

| # | Panel | Data source (as it exists today) | Status today |
|---|---|---|---|
| 1 | Mode & Safety banner: mode, LIVE / PAPER / DEMO flags, kill switch | Settings loaded by `silver_bot.config` from the environment and `.env` (`TRADING_MODE`, `MODE`, `LIVE_TRADING`, `PAPER_TRADING`, `DEMO_TRADING`); kill-switch state from the file at `KILL_SWITCH_PATH` (file exists = active) | Readable now, but only as a point-in-time load by the dashboard process. The bot itself exits after startup (G-3), so the banner shows configuration, not the state of a running bot. The kill switch has effect only if the path is configured (G-6) |
| 2 | Readiness checklist | `reports/live_readiness_report.json` and `reports/demo_readiness_report.json` (`ready`, `generated_at`, `checks[]` with `name`, `passed`, `reason`) | Both files exist. Written on demand only; each shows its `generated_at` so staleness is visible (the demo report dates from 2026-06-15). Advisory: nothing in the bot reads them (D-10, G-2), and the "exists" checks pass 0-byte evidence files (H-2) |
| 3 | Today's risk budget used | None persisted. `RiskState` (daily realized pnl, consecutive losses, trades today, open positions) lives in memory only ([rfc-silverbot-risk-kill-switch.md](rfc-silverbot-risk-kill-switch.md) section 3.7) | Not available. A real panel needs a new persisted risk-state source, which is the Planned change in H-11 and G-7. Until then the panel could only approximate from closed rows in SQLite `paper_trades`, which is not the risk engine's own view |
| 4 | Open positions and recent trades | SQLite `data/silver_bot.sqlite3`: `paper_trades` for closed trades (its `exit_time` and `exit_price` are `NOT NULL`, so open positions are not stored there) and `paper_events` for lifecycle rows such as `paper_trade_opened`; trade journal CSV from `monitoring/reports.py` | Tables exist but are empty because no entrypoint runs a paper session (G-3). The journal and dashboard JSON builders (`monitoring/dashboard.py`) have no caller (G-16), so there is no journal file to read yet. Open positions have no direct source |
| 5 | Alerts feed | `logs/audit.jsonl` (one JSON object per line: `created_at`, `level`, `event_type`, `message`, `context`) filtered to `risk_rejected`, `kill_switch_active`, `signal_rejected` and `error` | File exists and is written by every run, but holds only `bot_started` and `bot_stopped` today. `error` is never emitted (D-47). Telegram alerts are not a source: the client is in-memory (G-15) |
| 6 | Evidence reports | `reports/backtest_report.json`, `reports/out_of_sample_validation_report.json`, `reports/paper_trading_report.json`: file size in bytes and modified timestamp, plus the same two fields for the two readiness reports | Files exist. Three of the five are 0 bytes, so the panel flags them as empty (G-1, D-86, H-2). No strategy performance figure is shown until a report is non-empty |

Panels 3 and 4 cannot be built truthfully before the unwired pieces (entrypoint, report scheduler, persisted risk state) exist. That is a dependency of the proposal, not a new requirement here.

### 9.4 Wireframe

A layout sketch, not a chart.

```text
+------------------------------------------------------------------+
| SILVER BOT   mode: PAPER   LIVE: off   DEMO: off   KILL: ARMED?  |
| (read-only, localhost only)               config loaded 10:42:07 |
+--------------------------------+---------------------------------+
| READINESS                      | EVIDENCE REPORTS   size   saved |
| live  NOT READY  <generated_at>| backtest_report         0 B  !  |
|  - checks, pass/fail, reason   | oos_validation_report   0 B  !  |
| demo  READY      <generated_at>| paper_trading_report    0 B  !  |
|  - checks, pass/fail, reason   | live_readiness_report   2.2 KB  |
|                                | demo_readiness_report   2404 B  |
+--------------------------------+---------------------------------+
| RISK BUDGET (needs persisted state: not available today)         |
+---------------------------------------+--------------------------+
| OPEN POSITIONS / RECENT TRADES        | ALERTS (audit.jsonl)     |
| none recorded                         | bot_started  bot_stopped |
+---------------------------------------+--------------------------+
```

The layout is a sketch; values shown are not measured results.

### 9.5 Explicit non-goals

- No order entry, no close-position button, no kill-switch toggle.
- No configuration editing and no write access to `.env`, `config.yaml`, the SQLite file or any report.
- No remote exposure: bind to `127.0.0.1` only, with no port published by Docker Compose.
- No display of secrets: the dashboard must not read API keys or the Telegram token, and must reuse the audit log's redaction.
- No performance claims while the evidence reports are empty.

### 9.6 Next step

If the owner wants this dashboard, open a Change Record that adds a PRD feature for it, with acceptance criteria and a decision on persisting risk state. Only then do sections 0 to 8 begin. Until that record is approved, this section stays a proposal.

## Self-Check

- [x] Status line reads `Draft (design system not started)` and the banner states there is no UI today.
- [x] Sections 0 to 8 each carry only the required "Not started" sentence.
- [x] Section 9 is labelled a proposal, not built, and states it adds no requirement.
- [x] Every panel in §9.3 names a concrete file or SQLite table and says where that source is empty or unproduced.
- [x] The evidence-reports panel shows byte size and timestamp so 0-byte reports are visible.
- [x] No order entry, config editing or remote exposure appears in the proposal (§9.5).
- [x] Links point only to existing suite files.
