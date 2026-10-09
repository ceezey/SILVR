# Design System (DSD)

**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Version:** 0.1
**Owner:** Cian Jake Francisco
**Status:** Draft (design system specified; mode A built per silverbot-cr-001)
**Last updated:** 2026-10-09
**Last reconciled:** N/A (not a code-describing doc)
**Design file:** [Figma](https://www.figma.com/design/g1n3J4j2L1iPrbdjiOS30e/Untitled?node-id=0-1&p=f). It is the working canvas for the section 9 proposal; it is not a requirement, and mode B in it is not built.

> Mode A, the read-only localhost dashboard, is built (PRD-F13, [cr-silverbot-operator-dashboard.md](cr-silverbot-operator-dashboard.md)); modes B and D are not. Sections 0 to 7 specify the brand and design system that any operator surface must follow (materialized to `BRAND.md` and `DESIGN.md`, section 8). Section 9 is the approved scope of mode A (PRD-F13) and a proposal for mode B, which adds no requirement. Building mode B or any other surface still needs its own Change Record (§9.6). The operator surface that exists is listed in [prd-silverbot.md](prd-silverbot.md) section 5.1 (command-line entrypoints, the dashboard entrypoint and files).

## 0. Brand Stance

**Brand idea: compile evidence, execute deterministically.** Data crosses a few hard boundaries in Silver Bot: market candles, in-memory features, a deterministic logistic regression baseline, SQLite writes and asynchronous alerts. Every operator surface answers four questions, in this order: is it safe (mode, live flag, kill switch), is it ready (readiness and evidence), what did it decide and why (signals, rejections, ML probability), and is the host sane (files present, logs written).

**Brand promise.** An isolated, standard-library-only trading research environment that stays transparent, auditable and traceable. It shows what exists and says plainly what does not.

**Experience character.** Monospace-first, clinical, dense, operational and predictable, like an industrial telemetry panel built for scanning. No decoration, no administrative chrome, no persona phrasing and no "intelligence" packaging.

Silver Bot communicates three things:

1. **Algorithmic transparency.** Features, probabilities and rejection reasons are shown as data; a decision is never presented as a black-box conclusion.
2. **Infrastructure sanity.** Mode flags, the kill-switch path, report files and log files are surfaced so a missing or empty one is visible at a glance.
3. **Traceable auditability.** Every alert maps to an audit event (`logs/audit.jsonl`) that can be found by its `event_type` and `created_at`.

## 1. Design Philosophy & Vision

### 1.1 Canonical name and descriptor

The name is written `silver-bot` on every surface (the package and console-script name in `pyproject.toml`). Descriptor: *An isolated, dependency-free asynchronous quantitative trading bot, read through a local status surface.*

### 1.2 Surface modes

| Mode | Surface | Status | Character |
|------|---------|--------|-----------|
| A | Localhost read-only status dashboard (primary; §9) | Built (PRD-F13) | Server-rendered HTML from the standard library (`http.server`, `string.Template`), inline CSS, monospace, bound to `127.0.0.1`. Same grid, tokens and glyphs as mode B. |
| B | Terminal status view (secondary) | Planned, gated by §9.6 | Black canvas, box-drawing grids, dense tables, ANSI colour always paired with a status glyph. 80 x 24 minimum. |
| C | JSON-lines audit log | Built (`monitoring/audit.py`) | One flat JSON object per line, keys sorted, secrets redacted (§4.3). |
| D | Telegram alerts | Planned (G-15); message text built, no transport | Compact MarkdownV2 messages with monospace dividers (§4.2). |

### 1.3 Anti-references

Never produce or use:

- A hosted or remotely reachable web UI, a JavaScript framework or bundler, a Node runtime, or any asset loaded from a CDN or another host. Mode A is the only browser surface: local, read-only and server-rendered by the standard library.
- Playful, chatty or first-person phrasing ("I found a trading opportunity for you!", "Thinking...").
- Saturated backgrounds, soft cards, drop shadows, gradients or rounded containers.
- Colour-only indicators: every coloured state carries a glyph and a word (§2.2, §6).
- Estimated, interpolated or sample values in place of missing data. An empty source shows `not available` and the reason.
- Marketing visuals or generic SaaS dashboard styling.

## 2. Brand Primitives (tokens, color, type)

### 2.1 Neutral tokens

Each token has a hex value for mode A (CSS custom properties) and an ANSI 16-colour index for mode B.

| Token | Hex | ANSI | Use |
|-------|-----|------|-----|
| `canvas` | `#000000` | 0 black | Page and terminal background |
| `surface` | `#111827` | 0 black | Header band and panel background (mode B draws it as `canvas`) |
| `border` | `#374151` | 8 bright black | Box-drawing lines, table rules |
| `ink` | `#F9FAFB` | 15 bright white | Live values, data rows |
| `muted` | `#9CA3AF` | 7 white | Column titles, timestamps, static names, the neutral state |

### 2.2 Semantic tokens

Semantic colour marks state only, never decoration, and always travels with its glyph and a word.

| Token | Hex | ANSI | Glyph | Means |
|-------|-----|------|-------|-------|
| `success` | `#10B981` | 2 green | `[ OK ]` | Check passed, report non-empty, event written, flag in its safe position |
| `warning` | `#F59E0B` | 3 yellow | `[ WRN ]` | Needs attention but not failing: kill-switch path unset (G-6), stale readiness report, model loaded without a trust check (H-8) |
| `danger` | `#EF4444` | 1 red | `[ ERR ]` | Check failed, evidence report 0 bytes, kill switch active, `error` event |
| `muted` | `#9CA3AF` | 7 white | `[ OFF ]` | A flag that is off or a source that is not available |

Direction arrows `▲` (long) and `▼` (short) may accompany a direction word; they are never a health signal.

### 2.3 Type

Monospace only. Mode A uses the font stack `ui-monospace, "Cascadia Mono", Menlo, Consolas, monospace` and loads no web font. One size for data, bold for panel titles, no italics in data rows. Numbers are right-aligned, use `.` as the decimal mark and carry no thousands separator. Mode A waives the right-alignment: each row is label, state, detail, so numbers sit inside left-aligned detail text; they are shown exactly as stored and never rounded ([cr-silverbot-operator-dashboard.md](cr-silverbot-operator-dashboard.md) V-6).

## 3. Layout & Spatial System

### 3.1 Grid

- Viewport: 80 columns x 24 rows minimum; the layout widens up to 120 x 40. Mode A uses the same character grid (`ch` units).
- Outlines use Unicode box drawing only: `─` U+2500, `│` U+2502, corners `┌ ┐ └ ┘`, joints `├ ┤ ┬ ┴ ┼`.
- Spacing is one or two spaces. No tabs and no variable spacing.
- Panels follow the six sources in §9.3, safety first: the mode and safety banner is always the top row and never scrolls away.

### 3.2 Reference layout

A layout sketch, not a chart. Values are today's real state where one exists (report sizes and readiness flags read from `reports/` on 2026-10-09); every other panel shows its empty state.

```text
┌───────────────── silver-bot status · read-only · 127.0.0.1 ──────────────────┐
│ MODE PAPER   LIVE [ OFF ]   DEMO [ OFF ]   KILL [ WRN ] path not set         │
│ config read once at start; the bot itself is not running (G-3)               │
├──────────────────────────────────────┬───────────────────────────────────────┤
│ READINESS                            │ EVIDENCE REPORTS        size  state   │
├──────────────────────────────────────┼───────────────────────────────────────┤
│ live  [ ERR ] NOT READY              │ backtest_report          0 B  [ ERR ] │
│       generated 2026-06-15 07:24 UTC │ oos_validation_report    0 B  [ ERR ] │
│ demo  [ OK ] READY                   │ paper_trading_report     0 B  [ ERR ] │
│       generated 2026-06-15 14:31 UTC │ live_readiness_report 2229 B  [ OK ]  │
│                                      │ demo_readiness_report 2404 B  [ OK ]  │
├──────────────────────────────────────┴───────────────────────────────────────┤
│ RISK BUDGET   not available: risk_state table empty, no running bot (G-3)    │
├──────────────────────────────────────┬───────────────────────────────────────┤
│ OPEN POSITIONS / RECENT TRADES       │ ALERTS (logs/audit.jsonl)             │
├──────────────────────────────────────┼───────────────────────────────────────┤
│ none recorded (no paper run, G-3)    │ [ OK ] bot_started                    │
│                                      │ [ OK ] bot_stopped                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

Narrower than 80 columns, the two-column rows stack (left above right). The banner never wraps away: if it must shorten, it keeps `MODE`, `LIVE` and `KILL`.

## 4. Core Component Specs

### 4.1 Status cell

A status cell is `glyph word detail`, for example `[ ERR ] NOT READY` or `[ WRN ] path not set`. The glyph sets the colour (§2.2); the word is mandatory; the detail is optional muted text. Missing data is `[ OFF ] not available:` followed by the reason and the gap ID when one exists.

### 4.2 Telegram alert (MarkdownV2)

Alerts use Telegram `parse_mode=MarkdownV2`. The layout, using an event the bot already emits (`TelegramAlerter.risk_rejection`, with a real rejection reason from `risk/engine.py` and the default symbol):

```text
*\[SILVER\-BOT \| RISK REJECTED\]*
`────────────────────────`
*Symbol:* `BTCUSDT`
*Reason:* Max daily loss limit reached
*Mode:* `paper`
`────────────────────────`
_Simulated only; no real order exists_
```

Rules:

- **Header.** Line 1 is the bold, escaped `\[SILVER\-BOT \| ` anchor followed by the event name in upper case and `\]`. Fields are `*Label:* value`; identifiers and numbers go in `` `code` ``.
- **Escaping.** Every dynamic value passes one sanitizer before insertion. Outside code spans it escapes `\` first, then all 18 reserved characters `_ * [ ] ( ) ~ ` > # + - = | { } . !` with a backslash. Inside a code span it escapes only `` ` `` and `\`. A message that fails escaping is not sent; the failure is logged and the alert loop continues.
- **Length.** The rendered message is at most 400 characters so it fits one phone screen. Dynamic fields are truncated before escaping (never inside an escape sequence) and end with `…`. Telegram's own limit is 4096.
- **Content.** Only events the alerter defines (bot started or stopped, signal detected or rejected, risk rejection, ML approval or rejection, paper trade opened or closed, daily report, error, kill switch active). Paper events say they are simulated. No secret, token or account identifier ever appears.
- **Status today.** `TelegramAlerter` formats `[title] message` as plain text and has no network transport (G-15). This layout applies when the transport is built.

### 4.3 Audit log line (JSON lines)

The audit log is the source of record for mode C and the alerts panel. Built format, one object per line, written by `StructuredAuditLogger` with `json.dumps(..., sort_keys=True)`. A line of the shape found in `logs/audit.jsonl`:

```json
{"context": {"mode": "paper"}, "created_at": "2026-06-14T17:32:06.316862+00:00", "event_type": "bot_stopped", "level": "INFO", "message": "Silver bot startup command completed"}
```

- Keys are exactly `context`, `created_at`, `event_type`, `level`, `message`. `context` passes through `redact_secrets` before writing.
- Numbers are raw JSON numbers, never strings and never with thousands separators, so the file pipes cleanly into `jq`.
- The application log (`utils/logging.py`) is plain text today; a structured application log is tracked as G-16 and would reuse these keys.

### 4.4 Report and file rows

Every evidence or readiness file is a row: name, size in bytes, state. A 0-byte or non-JSON file is `[ ERR ]` and no metric from it is shown (G-1). Readiness rows add `generated_at` so staleness is visible.

## 5. Motion

None. No animation, transitions, spinners or blinking. Mode B redraws in place on a fixed interval; mode A refreshes only when the operator reloads the page.

## 6. Accessibility

- State is never carried by colour alone: glyph, word and colour together (§2.2).
- Mode B prints plain text when stdout is not a terminal or `NO_COLOR` is set; the glyphs and words keep their meaning without colour.
- `ink`, `muted` and every semantic colour on `canvas` meet WCAG AA contrast for normal text (`border` is for lines only).
- Mode A uses semantic HTML tables with header cells, so a screen reader reads each panel as a table.

## 7. Quality Gate

A UI or alert change passes only if:

- [ ] Every value shown comes from a source named in §9.3 or an alerter event; nothing is estimated or sampled.
- [ ] Every coloured state has its glyph and word; the view reads correctly with `NO_COLOR`.
- [ ] The safety banner (mode, live, demo, kill switch) is the top row and fits 80 columns.
- [ ] 0-byte evidence files show `[ ERR ]` and no metric.
- [ ] No secret, API key or Telegram token is read for display or rendered.
- [ ] Telegram messages are escaped by the shared sanitizer, are at most 400 characters and have tests for each reserved character.
- [ ] Mode A binds to `127.0.0.1`, answers GET only and loads nothing from another host.
- [ ] Only the standard library is used (`dependencies = []`).

## 8. Materialization

Sections 0 and 1 of this document are materialized to `BRAND.md` and sections 2 to 7 to `DESIGN.md` at the repository root by `python tools/materialize_docs.py` (`--check` verifies). Edit this document, never the generated files. The UI builder agent `psl-purist` (SAD-B1 in [sad-silverbot.md](sad-silverbot.md)) builds against sections 2 to 7 and §9.

## 9. Recommended UI (mode A approved and built; mode B proposal)

### 9.1 Why

The owner operates the bot by reading files, not by clicking. The core flows in [prd-silverbot.md](prd-silverbot.md) section 5.3 are: run a readiness checker and read its JSON (flow 4), create or delete the kill-switch file (flow 5), and review evidence reports and logs after a run (flows 1 and 2). Each is a check of safety state or evidence. Today that means opening several files by hand, and the one failure that is easy to miss is an evidence report that is present but 0 bytes (G-1, D-86, H-2).

### 9.2 Recommended form

A local, read-only status dashboard served on localhost (surface mode A, §1.2), with a terminal status view (mode B) showing the same panels. Both follow sections 2 to 7. It has no order buttons and no write path to configuration, the kill-switch file or the database. Rationale: the owner mostly checks safety state and evidence, and any control surface would be a new path around the live-trading block ([sdd-silverbot.md](sdd-silverbot.md) section 5.1). The kill switch stays a file the owner creates or deletes ([ops-silverbot.md](ops-silverbot.md) section 4.1).

### 9.3 Panels

Every panel reads one named source. The "Status today" column says whether that source holds data or is produced at all.

| # | Panel | Data source (as it exists today) | Status today |
|---|---|---|---|
| 1 | Mode & Safety banner: mode, LIVE / PAPER / DEMO flags, kill switch | Settings loaded by `silver_bot.config` from the environment and `.env` (`TRADING_MODE`, `MODE`, `LIVE_TRADING`, `PAPER_TRADING`, `DEMO_TRADING`); kill-switch state from the file at `KILL_SWITCH_PATH` (fails closed: a file, a directory or an unreadable path counts as active; an automatic trip writes a JSON `reason` and `tripped_at` to show) | Readable now, but only as a point-in-time load by the dashboard process. The bot itself exits after startup (G-3), so the banner shows configuration, not the state of a running bot. The kill switch has effect only if the engine is built with the path, which only `build_risk_engine` does (G-6) |
| 2 | Readiness checklist | `reports/live_readiness_report.json` and `reports/demo_readiness_report.json` (`ready`, `generated_at`, `checks[]` with `name`, `passed`, `reason`) | Both files exist. Written on demand only; each shows its `generated_at` so staleness is visible (the demo report dates from 2026-06-15). Advisory: nothing in the bot reads them (D-10). Since `88220e6` the report checks fail empty or non-JSON evidence files (H-2 fixed), so a fresh live report shows those three checks failing |
| 3 | Today's risk budget used | The single-row SQLite table `risk_state` (`current_day`, `daily_realized_pnl`, `consecutive_losses`, `trades_today`, `open_positions`, `updated_at`; [sdd-silverbot.md](sdd-silverbot.md) section 3.2), written only by an engine built with a state store ([rfc-silverbot-risk-kill-switch.md](rfc-silverbot-risk-kill-switch.md) section 3.7) | Source exists since `2d7f713` but is empty today: no running bot builds a store-backed engine (G-3, G-7 partial). A panel must read the row and never write it |
| 4 | Open positions and recent trades | SQLite `data/silver_bot.sqlite3`: `paper_trades` for closed trades (its `exit_time` and `exit_price` are `NOT NULL`, so open positions are not stored there) and `paper_events` for lifecycle rows such as `paper_trade_opened`; trade journal CSV from `monitoring/reports.py` | Tables exist but are empty because no entrypoint runs a paper session (G-3). The journal and dashboard JSON builders (`monitoring/dashboard.py`) have no caller (G-16), so there is no journal file to read yet. Open positions have no direct source |
| 5 | Alerts feed | `logs/audit.jsonl` (one JSON object per line: `created_at`, `level`, `event_type`, `message`, `context`) filtered to `risk_rejected`, `kill_switch_active`, `signal_rejected` and `error` | File exists and is written by every run, but holds only `bot_started` and `bot_stopped` today. `error` is never emitted (D-47). Telegram alerts are not a source: the client is in-memory (G-15) |
| 6 | Evidence reports | `reports/backtest_report.json`, `reports/out_of_sample_validation_report.json`, `reports/paper_trading_report.json`: file size in bytes and modified timestamp, plus the same two fields for the two readiness reports | Files exist. Three of the five are 0 bytes, so the panel flags them as empty (G-1, D-86, H-2). No strategy performance figure is shown until a report is non-empty |

Panels 3 and 4 cannot be built truthfully before the unwired pieces (entrypoint, report scheduler, persisted risk state) exist. That is a dependency of the proposal, not a new requirement here.

### 9.4 Wireframe

The reference layout is in §3.2; it uses these six panels in this order, with the safety banner on top.

### 9.5 Explicit non-goals

- No order entry, no close-position button, no kill-switch toggle.
- No configuration editing and no write access to `.env`, `config.yaml`, the SQLite file or any report.
- No remote exposure: bind to `127.0.0.1` only, with no port published by Docker Compose.
- No display of secrets: the dashboard must not read API keys or the Telegram token, and must reuse the audit log's redaction.
- No performance claims while the evidence reports are empty.

### 9.6 Next step

If the owner wants this dashboard, open a Change Record that adds a PRD feature for it, with acceptance criteria and a decision on persisting risk state. Only then do sections 0 to 8 begin. Until that record is approved, this section stays a proposal. Mode A was approved by [cr-silverbot-operator-dashboard.md](cr-silverbot-operator-dashboard.md) on 2026-10-09.

## Self-Check

- [x] Status line reads `Draft (design system specified; mode A built per silverbot-cr-001)` and the banner states that mode A is built and that mode B or any other surface still needs its own Change Record (§9.6).
- [x] Sections 0 to 7 hold the brand and design system; section 8 names the materialized `BRAND.md` (sections 0 and 1) and `DESIGN.md` (sections 2 to 7).
- [x] The §3.2 layout shows only real values (report sizes, readiness flags) or an explicit empty state; no invented metric, position or PnL.
- [x] The §4.2 Telegram example is valid MarkdownV2, uses an event and a rejection reason that exist in the code, and is under 400 characters.
- [x] The §4.3 audit line matches the keys written by `monitoring/audit.py` and is copied from `logs/audit.jsonl`.
- [x] Section 9 is labelled as the approved scope of mode A and a proposal for mode B, and states that the proposal adds no requirement.
- [x] Every panel in §9.3 names a concrete file or SQLite table and says where that source is empty or unproduced.
- [x] The evidence-reports panel shows byte size and timestamp so 0-byte reports are visible.
- [x] No order entry, config editing or remote exposure appears in the proposal (§9.5).
- [x] Links point only to existing suite files.
