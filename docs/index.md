# Documentation Index: Silver Bot

**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Slug:** `silverbot`
**Maintainer:** Cian Jake Francisco
**Last updated:** 2026-10-14

This is the entry point for every working session. It lists each document, its version and status, what is stale, and the open safety items. Every doc is `Draft` at version 0.1; nothing is `Locked` yet. Two Change Records exist (both approved and built), listed under Change Records in section 1. The manifest below is hand-maintained: when a file is added, renamed or removed under `docs/`, update the tables here in the same change. Start with [prd-silverbot.md](prd-silverbot.md) for what the bot is meant to do, [sdd-silverbot.md](sdd-silverbot.md) for how it is built, and [scrutiny-silverbot.md](scrutiny-silverbot.md) for what is wrong with it today.

## 1. Document Suite

All suite docs were reconciled against code at commit `62037d1`, except the four marked N/A, which describe intent, not code. On 2026-10-09 the docs that describe the eight gaps fixed in the HIGH safety fixes batch 1 (merged to `dev` at `70ccaec`) were re-checked against `70ccaec`; "batch 1 items" in the Last Reconciled column means only those statements and the `file:line` citations into the eight changed source files were re-checked, and the rest still dates from `62037d1`. On 2026-10-09 the docs that describe the G-3 entrypoint batch 2 (code complete on `dev` at `099085b`) were re-checked against `099085b`; "batch 2 items" means the entrypoint, loader, runner, `build_risk_config`, deploy-file and test-count statements and their `file:line` citations. On 2026-10-09 the statements changed by the G-3 safety review fixes (`5c781fc`) were re-checked against `5c781fc`; "review-fix items" means the systemd exit 2, loader candle-duration, `bot_stopped` on a crash, run-record, `.env.example` `MODE` and test-count statements.

| Document | File | Version | Status | Last Updated | Last Reconciled |
|---|---|---|---|---|---|
| Scrutiny Gate (SCRUTINY) | [scrutiny-silverbot.md](scrutiny-silverbot.md) | 0.1 | Draft | 2026-10-09 | 2026-10-09 (`5c781fc`, review-fix items; `099085b`, batch 2 items; `70ccaec`, batch 1 items) |
| Idea Brief (IDEA) | [idea-silverbot.md](idea-silverbot.md) | 0.1 | Draft | 2026-10-09 | N/A |
| Validation Brief (VALIDATION) | [val-silverbot.md](val-silverbot.md) | 0.1 | Draft | 2026-10-09 | N/A |
| House Style & Voice (VOICE) | [voice-silverbot.md](voice-silverbot.md) | 0.1 | Draft | 2026-10-08 | N/A |
| Business Requirements (BRD) | [brd-silverbot.md](brd-silverbot.md) | 0.1 | Draft | 2026-10-09 | 2026-10-09 (`099085b`, batch 2 items; `70ccaec`, batch 1 items) |
| Unit Economics (UES) | [ues-silverbot.md](ues-silverbot.md) | 0.1 | Draft | 2026-10-09 | 2026-10-09 (`70ccaec`, batch 1 items) |
| Product Requirements (PRD) | [prd-silverbot.md](prd-silverbot.md) | 0.1 | Draft | 2026-10-14 | 2026-10-09 (`5c781fc`, review-fix items; `099085b`, batch 2 items; `70ccaec`, batch 1 items; `feat/operator-dashboard`, PRD-F13 items) |
| Design System (DSD) | [dsd-silverbot.md](dsd-silverbot.md) | 0.1 | Draft (Silverbot brand and design system specified; mode A approved, built and reskinned per silverbot-cr-002) | 2026-10-14 | N/A |
| System Design (SDD) | [sdd-silverbot.md](sdd-silverbot.md) | 0.1 | Draft | 2026-10-14 | 2026-10-09 (`5c781fc`, review-fix items; `099085b`, batch 2 items; `70ccaec`, batch 1 items; `feat/operator-dashboard`, PRD-F13 items) |
| QA and Test Plan (QAD) | [qad-silverbot.md](qad-silverbot.md) | 0.1 | Draft | 2026-10-14 | 2026-10-09 (`5c781fc`, review-fix items; `099085b`; `feat/operator-dashboard`, PRD-F13 items) |
| Subagent Roster (SAD) | [sad-silverbot.md](sad-silverbot.md) | 0.1 | Draft | 2026-10-09 | 2026-10-09 (`099085b`, batch 2 items; `70ccaec`, batch 1 items; `feat/operator-dashboard`, PRD-F13 items) |
| Project Build Guide (BUILD) | [build-silverbot.md](build-silverbot.md) | 0.1 | Draft | 2026-10-09 | 2026-10-09 (`099085b`, batch 2 items; `70ccaec`, batch 1 items) |
| Compliance & Legal Readiness Register (CLR) | [clr-silverbot.md](clr-silverbot.md) | 0.1 | Draft | 2026-10-09 | 2026-10-09 (`099085b`, batch 2 items; `70ccaec`, batch 1 items) |
| AI Assurance Dossier (AIA) | [aia-silverbot.md](aia-silverbot.md) | 0.1 | Draft | 2026-10-09 | 2026-10-09 (`70ccaec`; `099085b`, batch 2 items) |
| Operations & Observability Runbook (OPS) | [ops-silverbot.md](ops-silverbot.md) | 0.1 | Draft | 2026-10-14 | 2026-10-14 (`f83b3e1`, §5.6 dashboard items); 2026-10-09 (`5c781fc`, review-fix items; `099085b`, batch 2 items; `70ccaec`, batch 1 items; `feat/operator-dashboard`, PRD-F13 items) |
| Build Session Log (LOG) | [log-silverbot.md](log-silverbot.md) | 0.1 | Draft (append-only) | 2026-10-14 | 2026-10-09 (`5c781fc`, review-fix items; `099085b`; `feat/operator-dashboard`, PRD-F13 items) |

### Change Records

| CR ID | File | Subject | Status | Last Updated |
|---|---|---|---|---|
| `silverbot-cr-001` | [cr-silverbot-operator-dashboard.md](cr-silverbot-operator-dashboard.md) | Operator dashboard (PRD-F13) | Approved | 2026-10-09 |
| `silverbot-cr-002` | [cr-silverbot-dashboard-reskin.md](cr-silverbot-dashboard-reskin.md) | Dashboard reskin and SAD-B1 update | Approved, built | 2026-10-14 |

### Runbooks

| Runbook | File | Version | Status | Last Updated | Last Reconciled |
|---|---|---|---|---|---|
| Local Development | [runbook-local-dev.md](runbook-local-dev.md) | 0.1 | Draft | 2026-10-09 | 2026-10-09 (`5c781fc`, review-fix items; `099085b`, batch 2 items; `70ccaec`, batch 1 items) |
| Backtest and Evidence | [runbook-backtest.md](runbook-backtest.md) | 0.1 | Draft | 2026-10-09 | 2026-10-09 (`5c781fc`, review-fix items; `099085b`) |
| Demo / Testnet | [runbook-demo-testnet.md](runbook-demo-testnet.md) | 0.1 | Draft | 2026-10-09 | 2026-10-09 (`5c781fc`, review-fix items; `099085b`, batch 2 items; `70ccaec`, batch 1 items) |

### Audits

| Audit | File | Version | Status | Last Updated | Last Reconciled |
|---|---|---|---|---|---|
| Docs vs Code Drift (86 findings D-1..D-86, 14 HIGH; code hazards H-1..H-14) | [audit-docs-drift.md](audit-docs-drift.md) | 0.1 | Draft | 2026-10-09 | 2026-10-08 (`62037d1`); Resolved lines 2026-10-09 (`70ccaec` batch 1; `099085b` batch 2: D-1, D-4, D-33, D-46, H-4; `5c781fc`: H-4) |

### RFCs

| RFC ID | File | Feature | Status | Last Updated |
|---|---|---|---|---|
| `silverbot-rfc-001` | [rfc-silverbot-signal-engine.md](rfc-silverbot-signal-engine.md) | Signal engine (PRD-F1) | Draft | 2026-10-08 |
| `silverbot-rfc-002` | [rfc-silverbot-risk-kill-switch.md](rfc-silverbot-risk-kill-switch.md) | Risk engine and kill switch (PRD-F3) | Draft | 2026-10-09 |
| `silverbot-rfc-003` | [rfc-silverbot-ml-filter-gate.md](rfc-silverbot-ml-filter-gate.md) | ML filter gate (PRD-F6) | Draft | 2026-10-09 |
| `silverbot-rfc-004` | [rfc-silverbot-readiness-gates.md](rfc-silverbot-readiness-gates.md) | Readiness gates (PRD-F5, PRD-F8, PRD-F12) | Draft | 2026-10-09 |

### Root files

| File | Kind | Source of truth |
|---|---|---|
| [README.md](../README.md) | Hand-maintained | Itself |
| [CLAUDE.md](../CLAUDE.md) | Hand-maintained pointer | Itself; points here |
| [AGENTS.md](../AGENTS.md) | Materialized | [build-silverbot.md](build-silverbot.md) |
| [MODEL_CARD.md](../MODEL_CARD.md) | Materialized | [aia-silverbot.md](aia-silverbot.md) section 1 |
| [BRAND.md](../BRAND.md) | Materialized | [dsd-silverbot.md](dsd-silverbot.md) sections 0 and 1 |
| [DESIGN.md](../DESIGN.md) | Materialized | [dsd-silverbot.md](dsd-silverbot.md) sections 2 to 7 |
| `.claude/agents/*.md` (5 files) | Materialized | [sad-silverbot.md](sad-silverbot.md) section 3 |

Edit the source of truth, never the materialized file.

### Process records

| Record | File |
|---|---|
| Design spec for this documentation suite | [superpowers/specs/2026-10-08-canonical-docs-design.md](superpowers/specs/2026-10-08-canonical-docs-design.md) |
| Implementation plan | [superpowers/plans/2026-10-08-canonical-docs.md](superpowers/plans/2026-10-08-canonical-docs.md) |
| Design spec for the HIGH safety fixes batch 1 | [superpowers/specs/2026-10-09-high-safety-fixes-design.md](superpowers/specs/2026-10-09-high-safety-fixes-design.md) |
| Implementation plan for the HIGH safety fixes batch 1 | [superpowers/plans/2026-10-09-high-safety-fixes.md](superpowers/plans/2026-10-09-high-safety-fixes.md) |
| Design spec for the G-3 entrypoint batch 2 | [superpowers/specs/2026-10-09-g3-entrypoint-design.md](superpowers/specs/2026-10-09-g3-entrypoint-design.md) |
| Implementation plan for the G-3 entrypoint batch 2 | [superpowers/plans/2026-10-09-g3-entrypoint.md](superpowers/plans/2026-10-09-g3-entrypoint.md) |
| Implementation plan for the operator dashboard (silverbot-cr-001) | [superpowers/plans/2026-10-09-operator-dashboard.md](superpowers/plans/2026-10-09-operator-dashboard.md) |
| Design spec for the Silverbot brand (DSD sections 0 and 1) | [superpowers/specs/2026-10-14-silverbot-brand-design.md](superpowers/specs/2026-10-14-silverbot-brand-design.md) |
| Design spec for the Silverbot design system and Figma foundations (DSD sections 2 to 8) | [superpowers/specs/2026-10-14-silverbot-design-system-design.md](superpowers/specs/2026-10-14-silverbot-design-system-design.md) |
| Implementation plan for the Silverbot brand and design system | [superpowers/plans/2026-10-14-silverbot-brand-design-system.md](superpowers/plans/2026-10-14-silverbot-brand-design-system.md) |

### 1.1 Traceability Matrix

Status is taken from [prd-silverbot.md](prd-silverbot.md) section 3; every feature appears in the SDD and the QAD.

| PRD-F# | Feature | Priority | Status | In SDD | In QAD | In RFC |
|---|---|---|---|---|---|---|
| PRD-F1 | Silver Bullet signal engine | Must | Built | Yes | Yes | silverbot-rfc-001 |
| PRD-F2 | Backtester, cost simulation, reports, out-of-sample validation | Must | Partial | Yes | Yes | N/A |
| PRD-F3 | Risk engine and kill switch | Must | Built (caveats) | Yes | Yes | silverbot-rfc-002 |
| PRD-F4 | Paper trading | Must | Partial | Yes | Yes | N/A |
| PRD-F5 | Binance Futures demo/testnet mode | Should | Partial | Yes | Yes | silverbot-rfc-004 |
| PRD-F6 | ML probability filter | Could | Partial | Yes | Yes | silverbot-rfc-003 |
| PRD-F7 | Monitoring and alerting | Must | Partial | Yes | Yes | N/A |
| PRD-F8 | Readiness gates | Must | Built (caveats) | Yes | Yes | silverbot-rfc-004 |
| PRD-F9 | Safe configuration | Must | Built | Yes | Yes | N/A |
| PRD-F10 | Market data and storage | Must | Partial | Yes | Yes | N/A |
| PRD-F11 | Deployment | Should | Partial | Yes | Yes | N/A |
| PRD-F12 | Live trading | Won't (this release) | Planned, blocked | Yes | Yes | silverbot-rfc-004 |
| PRD-F13 | Operator dashboard | Should | Built (caveats) | Yes | Yes | N/A |

## 2. Change Log

Change Records are listed in the table below and in section 1 under Change Records.

| Date | Change | Reference |
|---|---|---|
| 2026-10-14 | Branch flow added to BUILD section 5.1 (and `AGENTS.md` regenerated): BE and FE branches from `dev`, merge to `dev`, QA on `dev`, then a PR to `main` with owner sign-off. Docs only. | [build-silverbot.md](build-silverbot.md) |
| 2026-10-14 | `silverbot-cr-002` (dashboard reskin and SAD-B1 update) approved and built on `dev` (commits `af3e746` to `c9b410f`; 226 to 253 test functions, 272 to 304 passing tests). The dashboard shows the Silverbot header and the Sterling tokens, the evidence ladder and the Next strip, a 24-hour readiness stale rule, a degraded line and a branded 404, and serves vendored IBM Plex Mono from its own server under `font-src 'self'`. Docs reconciled: PRD AC-23.1 reworded and AC-23.8 to AC-23.13 added, QAD rows QAD-T253 to QAD-T279, DSD and OPS §5.6. | [cr-silverbot-dashboard-reskin.md](cr-silverbot-dashboard-reskin.md), [prd-silverbot.md](prd-silverbot.md), [qad-silverbot.md](qad-silverbot.md), [dsd-silverbot.md](dsd-silverbot.md), [ops-silverbot.md](ops-silverbot.md) |
| 2026-10-14 | Silverbot brand and Sterling design system specified in DSD sections 0 to 8; `silverbot-cr-002` (dashboard reskin and SAD-B1 update) proposed, not built. No bot code changed. | [dsd-silverbot.md](dsd-silverbot.md), [cr-silverbot-dashboard-reskin.md](cr-silverbot-dashboard-reskin.md), [brand spec](superpowers/specs/2026-10-14-silverbot-brand-design.md), [design-system spec](superpowers/specs/2026-10-14-silverbot-design-system-design.md), [plan](superpowers/plans/2026-10-14-silverbot-brand-design-system.md) |
| 2026-10-09 | Operator dashboard (PRD-F13) built on `feat/operator-dashboard` from `dev` at `b24faf5`, approved as `silverbot-cr-001` (181 to 225 test functions, 220 to 271 passing tests). A read-only status page with six panels, standard library only, served on `127.0.0.1` with `python -m silver_bot.monitoring.dashboard_server`; restraint-guardian PASS and a whole-branch review fixed in `604425e`. Docs reconciled: PRD-F13 and US-23 with AC-23.1 to AC-23.7, DSD (mode A Built, section 2.3 waiver for mode A), SAD-B1 gate scoped and the materialized files regenerated, SDD module table, QAD-T208 to QAD-T251, OPS section 5.6, the Change Record. Panels 3 and 4 stay empty until a paper session runs (G-3). | [cr-silverbot-operator-dashboard.md](cr-silverbot-operator-dashboard.md), [plan](superpowers/plans/2026-10-09-operator-dashboard.md), [log-silverbot.md](log-silverbot.md) |
| 2026-10-09 | G-3 safety review fixes on `dev` at `5c781fc` (218 to 220 passing tests, 179 to 181 test functions). systemd has `RestartPreventExitStatus=2 78`, so exit 2 (rejected arguments, configuration or candle data) no longer restarts and a crash (exit 1) still does; the loader rejects a candle whose duration differs from `TIMEFRAME`, so a 5m file no longer loads as `1m`; `main()` audits `bot_stopped` with `exit_code` 1 when dispatch raises; `backtest_run.json` records costs, ML flag and risk per trade from the config the engine ran with; `.env.example` ships `MODE=` blank, so a copied `.env` no longer blocks backtests. Docs reconciled: OPS, SDD, PRD, AUDIT H-4, SCRUTINY G-3, G-24 and G-28 notes plus new gap G-33 (backtest runtime grows roughly quadratically with candle count; measured timings only), QAD-T187 and QAD-T200 rewritten, QAD-T206 and QAD-T207 added, the three runbooks and README. | [scrutiny-silverbot.md](scrutiny-silverbot.md) section 3, [log-silverbot.md](log-silverbot.md) |
| 2026-10-09 | G-3 entrypoint batch 2 on `dev`, code complete at `099085b` (loader `e5baec7`, deploy `f6bc017`, `build_risk_config` `4726cb5`, runner `f84557e`, entrypoint `099085b`; 170 to 218 passing tests). Backtest mode runs from the CLI on Binance kline CSV files and writes six reports, including a chronological out-of-sample report and a run record, on a simulated per-run kill switch (ED-5); paper and demo exit 78 and the supervisors stop on 78. Docs reconciled: G-3, G-5, G-6, G-9 and G-12 Partial with batch 2 notes, H-4 fixed, G-1 still Open with the tooling noted; audit Resolved lines on D-1, D-4, D-33, D-46 and H-4; OPS exit 78 (§4.8) and container backtest (§5.5); backtest runbook rewritten; QAD-T174 to QAD-T205; SAD cards and the materialized files regenerated. | [design spec](superpowers/specs/2026-10-09-g3-entrypoint-design.md), [plan](superpowers/plans/2026-10-09-g3-entrypoint.md), [scrutiny-silverbot.md](scrutiny-silverbot.md) section 3 |
| 2026-10-09 | Batch 1 safety review: no blocking findings; `release_trade` saves risk state before tripping, and load errors are logged. Tests 169 passed. | [rfc-silverbot-risk-kill-switch.md](rfc-silverbot-risk-kill-switch.md), [log-silverbot.md](log-silverbot.md) |
| 2026-10-09 | HIGH safety fixes batch 1 merged to `dev` at `70ccaec` (G-2 `88220e6`, G-4 `c6d909d`, G-5 `5e4acc5`, G-6 `08c81ad`, G-7 `2d7f713`, G-8 `8e66054`, G-10 `0a76564`, G-11 `59ed6d5`; 109 to 167 passing tests). Docs reconciled: G-2, G-4, G-8, G-10 and G-11 Closed, G-5 to G-7 Partial; Resolved lines in the audit; OPS kill-switch clearing and `risk_state` reset steps; QAD scenarios for the 34 new test functions; citations into the changed files re-pointed; SAD cards and the materialized files regenerated. | [design spec](superpowers/specs/2026-10-09-high-safety-fixes-design.md), [plan](superpowers/plans/2026-10-09-high-safety-fixes.md), [scrutiny-silverbot.md](scrutiny-silverbot.md) section 3 |
| 2026-10-09 | Linked the Figma design file from the DSD header. | [dsd-silverbot.md](dsd-silverbot.md) |
| 2026-10-09 | Added the tech stack table, SDD section 2.4, verified against `2b916d1`; README links to it. | [sdd-silverbot.md](sdd-silverbot.md) section 2.4 |
| 2026-10-08 | Canonicalization pass: the root docs were absorbed into this suite, reconciled against code at `62037d1`, and removed. Originals remain in git history at that commit. | [design spec](superpowers/specs/2026-10-08-canonical-docs-design.md), [plan](superpowers/plans/2026-10-08-canonical-docs.md) |

## 3. Incident Log

No incidents recorded. The bot has never run a paper, demo or live session, so there is nothing to log. Incident procedure is in [ops-silverbot.md](ops-silverbot.md) section 4.

## 4. Health Check

- [~] All docs are Draft at 0.1; no doc is Locked yet, so the suite is reviewed but not frozen.
- [ ] Evidence reports are empty: `reports/backtest_report.json`, `reports/out_of_sample_validation_report.json` and `reports/paper_trading_report.json` are 0 bytes (G-1). Since `099085b` the backtest CLI can write the first two ([runbook-backtest.md](runbook-backtest.md)); the owner has not run it on real data. `reports/` is git-ignored. No performance claim is made anywhere in the suite.
- [x] Materialized artifacts match their sources: `python tools/materialize_docs.py --check` reports no changes, and `tests/test_materialize_docs.py` runs it in the suite. It checks generation only, not docs-vs-code semantics (see the process finding in [audit-docs-drift.md](audit-docs-drift.md)).
- [x] The tables in section 1 list every file under `docs/` (27 files including this index).
- [x] The SAD roster matches `.claude/agents/` (four reviewers, SAD-A1..A4, and one UI builder, SAD-B1).
- [ ] Phase 9 live-readiness evidence is open: no backtest, out-of-sample, paper, kill-switch or Telegram evidence exists (see [prd-silverbot.md](prd-silverbot.md) section 9).
- [ ] Code hazards still open; each is in [audit-docs-drift.md](audit-docs-drift.md) and [scrutiny-silverbot.md](scrutiny-silverbot.md):
  - Partial: the entrypoint stub (G-3). Since `099085b` backtest mode runs from the CLI, and paper and demo exit 78 without a restart loop (H-4 fixed, `f6bc017`). No paper or demo runtime exists (G-13, G-17), so the batch 1 risk fixes reach backtests only (settings caps and a simulated per-run kill switch) and no paper bot.
  - Settings risk limits reach CLI backtests through `build_risk_config`; `build_risk_engine` has no runtime caller; daily-loss and leverage bounds are checked in demo mode only (D-11, H-5, G-5 partial).
  - The real kill switch is armed only through `build_risk_config` or `build_risk_engine`, which no paper runtime calls, and does not close positions; reset is deleting the file; backtests use a simulated switch per run (D-12, H-9, G-6 partial).
  - Risk state persists only for an engine built with SQLite storage, and `open_positions` can outlive a paper position after a crash (H-11, G-7 partial).
  - Readiness is consulted by nothing, and a live-ready result needs settings the app refuses to load (D-10, H-3).
  - Model and registry pickles are loaded without trust checks (H-8).
- [x] Fixed in the HIGH safety fixes batch 1 (2026-10-09, `70ccaec`): NaN model probability approval (H-1, G-8, `8e66054`); testnet URL substring match (D-13, G-10, `0a76564`); `.env.example` failing to load (H-14, G-4, `c6d909d`); 0 bps backtest cost defaults (H-7, G-11, `59ed6d5`); 0-byte reports passing readiness (H-2, G-2, `88220e6`); 5% `RiskConfig` per-trade ceiling (H-5, `5e4acc5`); kill switch existence-only with no automatic trip (H-9, `08c81ad`); risk state lost on restart for a store-backed engine (H-11, `2d7f713`).
- [x] Fixed in the G-3 entrypoint batch 2 (2026-10-09, `099085b`): supervisor restart loop (H-4, `f6bc017`); backtest runtime from the CLI (G-3 partial); chronological out-of-sample report (G-12 partial, `f84557e`); ML settings reach backtests (G-9 partial, `f84557e`).
- [x] Fixed in the G-3 safety review (2026-10-09, `5c781fc`): a `.env` copied from `.env.example` no longer overrides `TRADING_MODE`, because `MODE` ships blank (G-24 partial; a non-blank `MODE` still overrides, D-42; [runbook-backtest.md](runbook-backtest.md) step 5); systemd stops on exit 2 as well as 78, and a crash (exit 1) still restarts (H-4); the loader rejects a candle whose duration differs from `TIMEFRAME`; `bot_stopped` is audited when a mode run raises; the run record reads costs and risk from the engine's config.

## 5. Notes

Owner decisions that shaped this suite (OD-1 to OD-7, from the [design spec](superpowers/specs/2026-10-08-canonical-docs-design.md)). Citations of the form `FILE.md:N` to retired root docs (ARCHITECTURE.md, BACKTESTING.md, CONFIGURATION.md, DEPLOYMENT.md, ML_MODEL.md, RISK_POLICY.md, STRATEGY_NOTES.md, PROGRESS.md, TODO.md, the old README.md and the old AGENTS.md) refer to `git show 62037d1:FILE.md`.

- OD-1: Personal trading only. No customers, no pricing.
- OD-2: Generic jurisdiction. Country-specific compliance rows are open items for the owner.
- OD-3: Old root docs were absorbed, then deleted. Baseline commit `62037d1` keeps the originals.
- OD-4: The DSD is created with empty design-system sections ("Not started") plus a labelled Recommended UI proposal. Nothing was claimed as built at the time; mode A has since been built under `silverbot-cr-001`.
- OD-5: Personal financial targets are an owner-input register; items not derivable from code are `Owner input required` (BRD section 8).
- OD-6: A small safety subagent roster, materialized to `.claude/agents/`.
- OD-7: Code-first audit, then write. Code wins over old docs.

Doc count: 17 suite docs (16 in the first table plus this index), 4 RFCs, 3 runbooks and 1 audit, which is 25 files under `docs/`, plus the two Change Records (the operator dashboard and the dashboard reskin; 27 files in all), plus 10 tracked process records under `docs/superpowers/` (five design specs and five implementation plans: the 2026-10-08 canonical docs pair, the 2026-10-09 HIGH safety fixes pair, the 2026-10-09 G-3 entrypoint pair, the 2026-10-09 operator dashboard plan, and the 2026-10-14 brand spec, design-system spec and plan). The root holds README.md, CLAUDE.md, AGENTS.md, MODEL_CARD.md, BRAND.md and DESIGN.md.

Excluded: GTM, PITCH and WRAP. This is a personal trading bot with no customers, no pitch audience and no external product launch, so market, investor and launch-wrap docs do not apply.

Unbuilt roadmap items are labelled `Planned`; live trading is `Planned, blocked` (PRD-F12). When code and a doc disagree, the code wins and the disagreement becomes a row in [audit-docs-drift.md](audit-docs-drift.md).
