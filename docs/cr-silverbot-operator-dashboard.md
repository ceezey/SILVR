# Change Record: Operator Dashboard (read-only, localhost)

**CR ID:** `silverbot-cr-001`
**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Version:** 0.1
**Author:** Cian Jake Francisco
**Status:** Proposed (awaiting owner approval)
**Last updated:** 2026-10-09
**Base commit:** `f8a51b4` on `dev`
**PRD Reference:** [prd-silverbot.md](prd-silverbot.md) PRD-F7 (monitoring), new PRD-F13 (this record)
**DSD Reference:** [dsd-silverbot.md](dsd-silverbot.md) §0 to §7 (design system), §9 (UI proposal and the §9.6 gate)
**SAD Reference:** [sad-silverbot.md](sad-silverbot.md) SAD-B1 `psl-purist` (builder), SAD-A4 `restraint-guardian` (reviewer)

This record is the gate that [dsd-silverbot.md](dsd-silverbot.md) §9.6 requires before any operator UI is built. It adds one PRD feature, a local read-only status dashboard (surface mode A), and fixes its scope, panels, states, security rules and tests. It is the first of three records: the candle source and the paper-session entrypoint that fill panels 3 and 4 with data are separate records (section 6).

## 1. Why

The owner operates the bot by reading files: readiness JSON, the kill-switch file, evidence reports and the audit log ([prd-silverbot.md](prd-silverbot.md) §5.3, flows 1, 2, 4 and 5). Checking safety state means opening several files by hand, and the failure that is easiest to miss is an evidence report that is present but 0 bytes (G-1, D-86, H-2). A single read-only page that shows mode, kill switch, readiness, risk state, paper activity, recent audit events and evidence-file health makes that check one reload ([dsd-silverbot.md](dsd-silverbot.md) §9.1).

The page has no control surface. Any button that places an order, flips a flag or toggles the kill switch would be a new path around the live-trading block ([sdd-silverbot.md](sdd-silverbot.md) §5.1), so none exists. The kill switch stays a file the owner creates or deletes ([ops-silverbot.md](ops-silverbot.md) §4.1).

## 2. Divergences

| # | Current text | Change | Reason |
|---|---|---|---|
| V-1 | DSD banner and §9: "Section 9 is a proposal, not built, and adds no requirement" | §9 becomes the approved scope of PRD-F13; the §9.6 gate is met for mode A only | Owner approval of this record |
| V-2 | DSD §9.2: dashboard and terminal view (mode B) together | Mode A only; mode B is deferred (section 6) | Owner chose to focus on the localhost dashboard |
| V-3 | DSD §9.3 panels 3 and 4: "cannot be built truthfully before the unwired pieces exist" | Both panels are built now as read-only views with explicit empty states; they fill when a paper run writes rows | Persisted risk state exists (`risk_state`, commit `2d7f713`); the remaining gap is a running bot (G-3), handled by record 3 |
| V-4 | SAD-B1 card: "Gate first ... write nothing" for all UI work | The gate sentence is dropped for the PRD-F13 scope and kept for mode B and any other surface | [sad-silverbot.md](sad-silverbot.md) §6 re-reconcile rule for SAD-B1 |
| V-5 | `monitoring/dashboard.py` builds a dashboard JSON payload | Not reused; it stays as is | Its inputs (daily and weekly reports) have no producer (G-16), so reusing it would show nothing; the new page reads the sources directly |

## 3. Changes

### 3.1 New PRD feature

| ID | Feature | Priority | Status after merge | Design |
|---|---|---|---|---|
| PRD-F13 | Operator dashboard: read-only status page on localhost | Should | Built (caveats: panels 3 and 4 empty until record 3) | this record; [dsd-silverbot.md](dsd-silverbot.md) §3.2 and §9 |

**US-23** As the owner, I want one local read-only page that shows mode, kill switch, readiness, risk state, paper activity, recent audit events and evidence-file health, so that I can check the bot's safety state without opening files by hand.

- AC-23.1 Given the server is running, when the owner requests `GET /` from the same machine, then the page shows six panels in the [dsd-silverbot.md](dsd-silverbot.md) §3.2 order with the safety banner first.
- AC-23.2 Given any request, when the server handles it, then a method other than GET gets 405, and no file under `data/`, `reports/`, `logs/` or the kill-switch path is created or changed, except the `-wal` and `-shm` sidecar files that SQLite itself creates for any reader of a WAL-mode database (the database file's bytes are unchanged).
- AC-23.3 Given an evidence report that is missing, 0 bytes or not valid JSON, when the page renders, then that row shows `[ ERR ]` and no metric from it.
- AC-23.4 Given API keys and a Telegram token in the configuration, when the page renders, then neither value appears anywhere in the response.
- AC-23.5 Given an empty `risk_state`, `paper_trades` or `paper_events` table, when the page renders, then the panel shows its stated empty state and no invented value.
- AC-23.6 Given the server is started, when it binds, then it listens on `127.0.0.1` only, and a request whose `Host` header is not `127.0.0.1` or `localhost` (with the server port) gets 400.
- AC-23.7 Given one source that raises on read, when the page renders, then only that panel shows `[ ERR ] unreadable` with the exception type, and the other panels render.

### 3.2 Architecture

Three units, each testable alone. All code is standard library only (`pyproject.toml` keeps `dependencies = []`).

| Unit | File | Responsibility |
|---|---|---|
| Collect | `src/silver_bot/monitoring/status.py` | `collect_status(config, root) -> dict`: one collector per panel, each returning a state (`ok`, `warn`, `err`, `off`, `empty`) and the values to show. Each collector runs in its own `try`/`except` (AC-23.7). |
| Render | `src/silver_bot/monitoring/dashboard_server.py` | `render_page(status) -> str`: `string.Template` with `html.escape` on every value, inline CSS from the DSD §2 tokens, glyph plus word for every state ([dsd-silverbot.md](dsd-silverbot.md) §4.1, §6). No I/O. |
| Serve | `src/silver_bot/monitoring/dashboard_server.py` | `main()`: `ThreadingHTTPServer` on `127.0.0.1`, started with `python -m silver_bot.monitoring.dashboard_server [--port N]` (default 8765). Each `GET /` collects and renders afresh. |

Read-only rules:

- SQLite is opened read-only (a `file:` URI built from `database_path` with `mode=ro`), so the dashboard cannot write. A missing database file is the empty state, not a new file. The database uses WAL journaling (`storage/sqlite.py`), and SQLite creates the `-wal` and `-shm` sidecar files for any reader, read-only or not; the bot's own connections create the same files, and the database file itself is not modified.
- Settings come from the existing `load_config`. Only an allow-list is copied into the status dict: `mode`, `live_trading`, `paper_trading`, `demo_trading`, `kill_switch_enabled`, `kill_switch_path`, `database_path`, `symbol`, `timeframe`, `max_daily_loss`, `max_risk_per_trade`. `api_key`, `api_secret`, `telegram_bot_token` and `telegram_chat_id` never enter it (AC-23.4).
- The kill switch is read with `KillSwitch(path).is_active()`, which never writes; the file's `reason` and `tripped_at` are read if it holds JSON.
- Audit lines pass through `redact_secrets` from `monitoring/audit.py` before rendering, and the page shows only their `created_at`, `event_type` and `message`. A rejected configuration shows the `ConfigError` message as is: every such message in `config/settings.py` names the setting, never its value.
- The page refreshes only when the owner reloads it ([dsd-silverbot.md](dsd-silverbot.md) §5). No script, polling or animation.

Server rules:

- Bind address is fixed to `127.0.0.1`; there is no `--host` option and Docker Compose publishes no port for it.
- `GET /` returns 200; any other path returns 404; any other method returns 405 (AC-23.2).
- A `Host` header other than `127.0.0.1` or `localhost` with the server's port returns 400, which blocks DNS rebinding (AC-23.6).
- Response headers: `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'`, `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`, `Referrer-Policy: no-referrer`.
- No change to `main.py`, `src/silver_bot/main.py`, config, Docker or `deploy/**`.

### 3.3 Panels and states

States use the DSD §2.2 tags `[ OK ]`, `[ WRN ]`, `[ ERR ]` and `[ OFF ]`.

| # | Panel | Source | Shows | States |
|---|---|---|---|---|
| 1 | Safety banner | `load_config` allow-list; `KillSwitch.is_active()` | Mode; LIVE, PAPER and DEMO flags; kill switch | LIVE false is `[ OFF ]`. Kill switch disabled is `[ OFF ]`; enabled with no path is `[ WRN ] path not set` (G-6); active is `[ ERR ] ACTIVE` with `reason` and `tripped_at`. A rejected configuration is `[ ERR ] config invalid` with the redacted message |
| 2 | Readiness | `reports/live_readiness_report.json`, `reports/demo_readiness_report.json` (`ready`, `generated_at`, `checks[]`) | `ready`, `generated_at`, and the name and reason of each failing check | READY is `[ OK ]`; NOT READY, missing or invalid is `[ ERR ]`; `[ WRN ] stale` when any of the three strategy evidence reports (backtest, out-of-sample, paper) was modified after `generated_at` |
| 3 | Risk budget | SQLite `risk_state` (single row) | `current_day`, `daily_realized_pnl`, `trades_today`, `consecutive_losses`, `open_positions`, `updated_at`, beside the configured `max_daily_loss` and `max_risk_per_trade` | No row is `not available: no running bot (G-3)`; `current_day` not today in UTC is `[ WRN ] stale`. No "percent of budget used" is shown, because equity is not stored |
| 4 | Positions and trades | `risk_state.open_positions`; last 10 `paper_trades` by `exit_time` descending; last 10 `paper_events` by `id` descending | Open-position count, recent closed trades, recent lifecycle events, every row labelled simulated | Empty is `none recorded (no paper run, G-3)` |
| 5 | Alerts | Last 64 KiB of `logs/audit.jsonl`, last 20 events | `created_at`, `event_type`, `message` | `risk_rejected`, `signal_rejected`, `kill_switch_active` and `mode_unavailable` (added by G-3 batch 2) are `[ WRN ]`; `error` is `[ ERR ]`; every other event is `[ OK ]` (event written, [dsd-silverbot.md](dsd-silverbot.md) §2.2 and the §3.2 layout). Unparseable lines are shown as a count of unreadable lines |
| 6 | Evidence reports | `reports/backtest_report.json`, `reports/out_of_sample_validation_report.json`, `reports/paper_trading_report.json`, and the two readiness reports | Byte size, modified time (UTC), JSON validity | Missing, 0 bytes or not a JSON object is `[ ERR ]`; otherwise `[ OK ]`. No performance figure is shown |

Footer: page generation time in UTC and the text `read-only; reload to refresh`.

### 3.4 Decision on persisting risk state

[dsd-silverbot.md](dsd-silverbot.md) §9.6 asks for this decision. Risk state is already persisted: `build_risk_engine(config, storage)` builds an engine that saves to the single-row `risk_state` table (`risk/factory.py`, `storage/sqlite.py`, commit `2d7f713`). The dashboard reads that row and never writes it. Getting rows into it needs a running paper session built with a store-backed engine, which is record 3 (section 6).

### 3.5 Doc updates on merge

- [prd-silverbot.md](prd-silverbot.md): PRD-F13 row in §3, US-23 with AC-23.1 to AC-23.7 in §4, the dashboard entrypoint in §5.1, story count updated.
- [dsd-silverbot.md](dsd-silverbot.md): status and banner say mode A is built; §9 says approved by this record for mode A; self-check updated.
- [sad-silverbot.md](sad-silverbot.md): SAD-B1 gate sentence scoped per V-4, then `python tools/materialize_docs.py`.
- [qad-silverbot.md](qad-silverbot.md): test rows for AC-23.1 to AC-23.7.
- [ops-silverbot.md](ops-silverbot.md): how to start the dashboard and what each state means.
- [index.md](index.md): this record registered in §2 and listed in the manifest; [log-silverbot.md](log-silverbot.md): one row.

## 4. Verification

New files `tests/test_dashboard_status.py` (collectors) and `tests/test_dashboard_server.py` (render and server), standard library and pytest only, using `tmp_path`, no network and no real keys.

| Area | Test | AC |
|---|---|---|
| Collectors | Each panel with missing, 0-byte, invalid-JSON and valid inputs; SQLite empty and with rows; kill switch disabled, enabled without path, active with JSON reason; stale readiness rule | AC-23.3, AC-23.5 |
| Read-only | Bytes and modified time of the SQLite file, reports and audit log are identical before and after collecting and serving; a missing database file is not created | AC-23.2 |
| Secrets | Config with `api_key="SENTINEL-KEY"` and a Telegram token: neither string appears in the HTML | AC-23.4 |
| Escaping | An audit message holding `<script>` renders escaped | AC-23.1 |
| Failure isolation | One collector raising leaves the other five panels rendered | AC-23.7 |
| Server | Started on port 0 in a thread: `GET /` returns 200 with the four headers; POST returns 405; an unknown path returns 404; a foreign `Host` returns 400; the socket address is `127.0.0.1` | AC-23.1, AC-23.2, AC-23.6 |

Commands: `python -m pytest` (all tests pass) and `python tools/materialize_docs.py --check` (no changes).

## 5. Pre-merge gate runs

Per [sad-silverbot.md](sad-silverbot.md) §4: `restraint-guardian` (SAD-A4) on the full diff. The diff touches no live-gate surface and no risk, execution, exchange, config or readiness code, so SAD-A1 to SAD-A3 are not required. Results are recorded here before merge.

| Reviewer | Result | Notes |
|---|---|---|
| restraint-guardian (SAD-A4) | PASS | Run 2026-10-09 on `e88f5c6..84a2ab4` (four new files, no existing file touched, no dependency). Reuses `KillSwitch.is_active()` and `redact_secrets`; `_query` is new because `SQLiteStorage` has no read-only open; the per-panel `except Exception` is required by AC-23.7 and shows the exception type. No dead code or unused configuration. |

## 6. Deferred

- Terminal status view (mode B): same panels, later record.
- Telegram transport (G-15): deferred by the owner.
- Live candle source (record 2): `fetch_ohlcv` over the public, no-key Binance klines endpoint with the standard library, closed candles only (G-13). Touches `exchange/`, so all four reviewers run. The G-3 batch 2 work adds only an offline loader (`data/csv_loader.py`, `load_binance_kline_csv`) for hand-downloaded kline CSV files, used by backtests; it does not close G-13.
- Paper-session entrypoint (record 3): after G-3 batch 2, `main()` runs backtest mode only and paper mode logs `mode_unavailable` and exits 78. Record 3 replaces that branch with one that builds `build_risk_engine(config, storage)` (signature kept by batch 2) and runs `PaperTradingEngine` on record 2's candles (G-3, PRD-F4 AC-08.3). Touches live-gate surfaces, so all four reviewers run. This is what fills panels 3 and 4.
- A JSON endpoint for the status dict: no consumer.

## Self-Check

- [x] Sections Why, Divergences, Changes, Verification, Pre-merge gate runs and Deferred are present ([build-silverbot.md](build-silverbot.md) §5.1).
- [x] PRD-F13 has one user story and seven Given/When/Then acceptance criteria, each mapped to a test in section 4.
- [x] No control surface, write path or remote exposure is added; bind address is fixed to `127.0.0.1`.
- [x] No secret field enters the status dict; redaction reuses `monitoring/audit.py`.
- [x] No invented number: every value shown comes from a named file, table or setting, or is an explicit empty state.
- [x] The §9.6 risk-state decision is recorded (section 3.4).
- [x] No em dashes; links point only to existing suite files.
