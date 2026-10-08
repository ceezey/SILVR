# Compliance & Legal Readiness Register (CLR)

**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Version:** 0.1
**Owner:** Cian Jake Francisco
**Status:** Draft
**Last updated:** 2026-10-08
**Last reconciled:** 2026-10-08 against code at commit `62037d1`

This register lists the compliance, legal and data-handling obligations that a personal automated trading bot can meet, what the code does to support each, and what stays open. It is written generically: no jurisdiction is chosen, and every jurisdiction-specific item is `Open (OI-6)` (BRD [brd-silverbot.md](brd-silverbot.md) OI-6). It is a readiness register for the owner, not legal advice, and it does not say what any law requires of the owner. Requirements are stated at the level of common practice.

Related documents: [prd-silverbot.md](prd-silverbot.md), [sdd-silverbot.md](sdd-silverbot.md) §5 (security and safety) and §3.3 (file artifacts), [rfc-silverbot-risk-kill-switch.md](rfc-silverbot-risk-kill-switch.md), [rfc-silverbot-readiness-gates.md](rfc-silverbot-readiness-gates.md), [aia-silverbot.md](aia-silverbot.md), [ops-silverbot.md](ops-silverbot.md), [scrutiny-silverbot.md](scrutiny-silverbot.md), [audit-docs-drift.md](audit-docs-drift.md). Live trading is `Planned, blocked` (PRD-F12): the application refuses `LIVE_TRADING=true` and the exchange adapter cannot place orders, so most obligations below are forward-looking and apply in full only if live trading is ever approved.

## 0. Scope

- **Who.** One natural person (the owner) running the bot for their own account. No customers, no third-party funds, no advice to others, no pooled money, no marketing of returns.
- **What.** Research, backtesting, paper trading and, `Planned`, exchange demo (testnet) use. No real order can be placed today (SDD §5.1).
- **Where.** Jurisdiction-neutral by owner decision. The owner's country of residence, tax status and the venue's eligibility rules are not recorded in the repository. Every row whose answer depends on them says `Open (OI-6)`.
- **Out of scope.** Corporate or fund structures, regulated-entity obligations, employment, and anything involving other people's money or personal data.

Status vocabulary: `Supported` (the code provides the mechanism and it is tested), `Partial` (mechanism exists with a stated gap), `Not built` (`Planned` or absent), `Owner action` (a step only the owner can do), `Open (OI-6)` (depends on jurisdiction, not decided).

## 1. Data Inventory

What the bot stores or handles, where, and how long it is kept. The bot holds no personal data about anyone other than the owner. "Retention as coded" means what the code does; the code has no deletion or expiry for any item.

| Data | Where | Content | Protection as built | Retention as coded | Retention policy |
|---|---|---|---|---|---|
| Exchange API key and secret | Environment (`BINANCE_API_KEY`, `BINANCE_API_SECRET`), `.env` on the host | Credentials | `.env` and `.env.*` git-ignored (`.gitignore:1-2`), excluded from the image (`.dockerignore:1-3`), `prepare-host.sh` sets `.env` to mode 600 (`deploy/scripts/prepare-host.sh:2-13`); redacted from audit lines by key name (`monitoring/audit.py:12-21,79-103`); held as plain public attributes in the adapter (`exchange/binance_futures.py:32-33`) | Lives as long as the `.env` file | Rotate on suspected exposure; interval `Owner input required` |
| Telegram bot token | Environment (`TELEGRAM_BOT_TOKEN`), `.env` | Credential | Same as above; redacted by key name; never read by the alerter (`monitoring/telegram.py`) | As above | As above |
| Telegram chat id | Environment (`TELEGRAM_CHAT_ID`), `.env` | Identifier of the owner's chat | Redacted by key name (`chat_id` substring) | As above | As above |
| Trade, paper-event and ML-prediction records | SQLite file `data/silver_bot.sqlite3` (compose volume `./data`) | Seven tables: candles, signals, trades, logs, paper_trades, paper_events, ml_predictions (`storage/sqlite.py:20-27,100-113`); the ML table stores a features snapshot | File permissions only; `prepare-host.sh` sets the directory to mode 700; WAL journal mode | Kept indefinitely; no pruning code | `Open`: how long to keep trade records is tax-dependent (OI-6) |
| Audit log | `logs/audit.jsonl` (path hard-coded, `main.py:29`) | One JSON line per event: `created_at`, `level`, `event_type`, `message`, redacted `context` | Key-based redaction; values are not scanned (`monitoring/audit.py:101-103`) | Rotated daily, 14 files kept, compressed (`deploy/logrotate/silver-bot:1-8`) | 14 days of history on the host; the rotation file is a sample for the VPS, not applied by the code |
| Backtest exports | Directory given as `export_dir`: `trades.csv`, `equity_curve.csv`, `rejected_signals.csv`, `backtest_report.json` | Simulated results | Plain files | Kept until deleted | `Open` |
| Trade journal CSV, daily and weekly report JSON, dashboard JSON | Written only if a caller invokes the builders; none does today (`monitoring/reports.py:140,156`, `monitoring/dashboard.py:27`) | Per-trade fields (entry, exit, size, pnl, fees, slippage, reason) | Journal and report JSON are redacted; the dashboard export is not (`dashboard.py:27-33`) | Kept until deleted | `Open` |
| Readiness reports | `reports/live_readiness_report.json`, `reports/demo_readiness_report.json` | Check names and pass/fail; no secret values (test `test_demo_readiness_report_does_not_print_secrets`) | Plain files | Kept until deleted | `Open` |
| ML model registry and artifacts | `models/` (empty today) | Pickled models, feature list, metrics | Local files; pickle trust applies (AIA-R10) | Entries never deleted (`ml/registry.py:104-116`) | Per AIA |
| Kill-switch file | Path in `KILL_SWITCH_PATH` (compose `demo`: `/app/data/KILL_SWITCH`) | Existence only | Operator-created | Until the operator deletes it | n/a |
| Container logs | Docker or journald on the host | stdout of `python -m silver_bot` | Host defaults | Host defaults | `Open` |

Data not held: no customer data, no identity documents, no payment details, no biometric or location data, no analytics sent anywhere. No data leaves the host in the built system: there is no network client for Telegram or the exchange (D-3, G-13, G-17).

## 2. Obligations Matrix

Each row is a generic obligation (what practice commonly expects of an individual running an automated trading tool), how the bot supports it today, and the jurisdiction-specific status. "Supports" cites code or a committed document. No row asserts what a particular law requires.

| CLR-# | Obligation | Generic requirement | How the bot supports it | Jurisdiction-specific status |
|---|---|---|---|---|
| CLR-1 | Exchange terms of service and eligibility | The owner must be eligible to use the venue and comply with its terms, including automated or API access | Nothing in code checks eligibility. Live is blocked and orders cannot be placed (SDD §5.1). The venue account is not recorded (BRD OI-10) | Open (OI-6) |
| CLR-2 | Derivatives and leverage restrictions | Leveraged futures are restricted or prohibited for some residents and account types; the owner must know whether they may trade them | Leverage cap in the risk engine: `max_leverage=3.0`, gate 14 (`risk/engine.py:73-78`); demo readiness requires leverage at most 3. The cap is a safety limit, not a legal one, and Settings limits are not wired to the engine (G-5) | Open (OI-6) |
| CLR-3 | Tax record-keeping | Individuals commonly must keep a record of every trade (time, instrument, side, size, prices, fees, profit or loss) for the period set by local tax rules, and report gains | Paper and backtest records: SQLite `paper_trades` and `paper_events`, trade journal CSV with entry and exit time, prices, size, fees, slippage, realized pnl (`monitoring/reports.py:244-272`), report JSON exports. These are simulated records, not evidence of real trades. The journal exporter has no caller (S-31, G-16) | Open (OI-6) |
| CLR-4 | Source-of-record for real trades | If live trading is ever approved, the exchange statement is the authoritative record; the bot journal is a reconciliation aid | Not built. No exchange fill import or reconciliation exists (G-17) | Not built; Open (OI-6) |
| CLR-5 | API key hygiene: withdrawals disabled | Keys used by automation should have withdrawal permission off | Owner assertion only: `API_WITHDRAWALS_DISABLED` is a live-readiness check (`readiness.py:99`); no exchange call verifies key permissions (SDD §5.6) | Owner action |
| CLR-6 | API key hygiene: trade-only scope and IP allow-list | Keys should grant only the permissions needed (read, and trade only when live) and be restricted to the host's IP address where the venue supports it | Not checked by code. The old deployment checklist asked for it; it is carried here as an owner step | Owner action; venue support Open (OI-6) |
| CLR-7 | API key hygiene: storage and rotation | Secrets stay out of the repository, images and logs; are rotated on exposure | `.gitignore`, `.dockerignore`, `.env` mode 600, key-based log redaction (SDD §5.2). Demo readiness check 17 and 18 scan for a tracked `.env` and secret-looking patterns (`demo_readiness.py:181-222`). Gap: redaction is key-based only; dashboard export not redacted | Supported with gaps |
| CLR-8 | Third-party API terms: Binance | Use of the exchange API is subject to its published terms and rate limits | Adapter makes no network calls today; endpoint is limited to the testnet URL in demo mode, with a substring guard that lookalike hosts pass (D-13, G-10) | Open (OI-6) |
| CLR-9 | Third-party API terms: Telegram | Use of the Bot API is subject to Telegram's terms | No transport exists, so no call is made (D-3, G-15). The chat id and token are secrets | Open |
| CLR-10 | Local data protection for the owner's own data | Personal and financial records on a host should be access-controlled and backed up | Directory mode 700 and `.env` mode 600 via `prepare-host.sh`; container runs as a non-root user (`Dockerfile:20,24`). No encryption at rest, no backup tooling (see [ops-silverbot.md](ops-silverbot.md) §5). No `read_only` or `cap_drop` (S-33) | Owner action |
| CLR-11 | Data retention and deletion | Keep records as long as obligations require, then delete | No retention logic except log rotation (14 days). The database is never pruned | Open (OI-6) |
| CLR-12 | Automated-trading controls | Where rules exist for automated trading, they commonly expect pre-trade risk limits, a kill function, testing and an audit trail | Risk engine gates, stop-loss requirement, kill-switch file, audit log, tests (SDD §5.3 to §5.5). The kill switch is inert unless a path is configured and has no automatic trigger (D-12, G-6); risk state is lost on restart (H-11, G-7) | Open (OI-6) |
| CLR-13 | Market conduct | No manipulation, spoofing or wash trading | The strategy trades one instrument with market-structure rules; single account; no order placement exists | Open (OI-6) |
| CLR-14 | Licences of dependencies | Respect the licences of software used | See §5; no runtime dependency is declared | Supported |
| CLR-15 | No advice, no solicitation | Do not present the bot's output as advice or invite others to use it | The documents state no performance claims and a single owner. No distribution is planned | Owner action |
| CLR-16 | Publication of the repository | If the repository is published, no secrets, account data or screenshots may be in it | `.gitignore` covers `.env`; the old checklist forbids keys, tokens, private keys and account screenshots in the repository. History has not been scanned (BUILD to confirm) | Owner action |

## 3. Escalation Flags

Stop and seek qualified advice (tax, legal or the venue's support) before proceeding if any of these arise. They are triggers, not conclusions.

| Flag | Trigger | Action |
|---|---|---|
| F-1 | The owner intends to move from paper or demo to real orders | Complete CLR-1, CLR-2, CLR-3 and CLR-5 to CLR-7 first; the live gate is `Planned` (RFC-004) and live trading stays blocked |
| F-2 | The owner is unsure whether leveraged derivatives are permitted for them | Do not enable any venue account for futures until answered (OI-6) |
| F-3 | Anyone other than the owner would use the bot, or its output | Out of scope; stop |
| F-4 | A secret appears in a log, a commit, an image or a screenshot | Treat as compromised; follow the API key compromise runbook in [ops-silverbot.md](ops-silverbot.md) §4.5 |
| F-5 | Real trade records exist and tax treatment is unknown | Obtain exchange statements; do not rely on the bot journal (CLR-4) |
| F-6 | The venue changes its API terms or restricts the owner's account | Pause automation; review CLR-1 and CLR-8 |
| F-7 | A regulator or venue asks about automated trading | Provide this register, the audit log and [aia-silverbot.md](aia-silverbot.md); seek advice |

## 4. Third-Party Terms

| Party | Used for | Terms reviewed | Notes |
|---|---|---|---|
| Binance (Futures API and testnet) | Planned exchange adapter; demo endpoint `testnet.binancefuture.com` | Owner action: review the current terms and API rules for the account's region (OI-6, OI-10) | No network call is made by the code today |
| Telegram (Bot API) | Planned alert transport | Owner action | No transport exists; a client exception would propagate into the paper loop (D-3) |
| Docker and Docker Compose | Packaging and run | Standard open-source terms; Docker Desktop and Hub have their own terms if used | The base image is `python:3.11-slim` (`Dockerfile:1`) |
| Cloud or VPS provider | Hosting | Owner action; provider is not chosen (BRD OI-2) | Provider terms may restrict automated trading traffic or data location (OI-6) |
| Market data provider | Historical and live candles | Not chosen (BRD OI-8) | Data terms may restrict storage and redistribution |

No agreement has been signed or accepted on the project's behalf by this documentation.

## 5. IP & Licensing

- **Runtime dependencies.** None declared: `dependencies = []` (`pyproject.toml:10`). The image installs only the project itself with `pip install --no-cache-dir .` (`Dockerfile`). The code uses the Python standard library (PSF licence).
- **Optional, undeclared.** scikit-learn (BSD-3-Clause) is used only if the environment happens to have it (`ml/training.py:157-199`, G-25).
- **Development.** pytest (MIT) in the `dev` extra (`pyproject.toml:12-15`). Build backend: setuptools 68 or later (MIT) (`pyproject.toml:2`).
- **Container.** Base image `python:3.11-slim`; its contents carry the licences of Debian packages and Python.
- **This project's licence.** No `LICENSE` file is present and `pyproject.toml` declares none. The default is therefore all rights reserved by the owner. Choosing a licence is `Owner input required`.
- **Strategy concept.** ICT Silver Bullet is a publicly taught trading methodology. The rule logic in `strategy/` is the owner's own implementation of those public concepts; no third-party code was copied. Course material and proprietary indicators are not included. Whether the methodology's author claims rights over derived commercial use is `Open`, and is irrelevant while the bot is personal and unpublished.
- **Generated artefacts.** Trained models and reports derive from the owner's data and code and are the owner's.

## 6. Self-Check

- [x] The register states that it is generic and not legal advice, and every jurisdiction-specific row says `Open (OI-6)`, `Owner action` or `Not built`.
- [x] The data inventory covers API keys, the Telegram token and chat id, the SQLite database, the audit log, exports and reports, with retention as coded.
- [x] Each `CLR-#` row has an obligation, a generic requirement, how the bot supports it with a citation, and a status.
- [x] No row claims the bot meets a legal requirement; support statements describe code behaviour only.
- [x] Dependency licences are taken from `pyproject.toml`; the absence of a project licence is recorded as `Owner input required`.
- [ ] The venue, jurisdiction and tax treatment are recorded; they are not (OI-6, OI-10), so most rows stay open.
