# Documentation Index: Silver Bot

**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Slug:** `silverbot`
**Maintainer:** Cian Jake Francisco
**Last updated:** 2026-10-08

This is the entry point for every working session. It lists each document, its version and status, what is stale, and the open safety items. Every doc is `Draft` at version 0.1; nothing is `Locked` yet, so no Change Record exists. The manifest below is hand-maintained: when a file is added, renamed or removed under `docs/`, update the tables here in the same change. Start with [prd-silverbot.md](prd-silverbot.md) for what the bot is meant to do, [sdd-silverbot.md](sdd-silverbot.md) for how it is built, and [scrutiny-silverbot.md](scrutiny-silverbot.md) for what is wrong with it today.

## 1. Document Suite

All suite docs were last reconciled against code at commit `62037d1`, except the four marked N/A, which describe intent, not code.

| Document | File | Version | Status | Last Updated | Last Reconciled |
|---|---|---|---|---|---|
| Scrutiny Gate (SCRUTINY) | [scrutiny-silverbot.md](scrutiny-silverbot.md) | 0.1 | Draft | 2026-10-08 | 2026-10-08 (`62037d1`) |
| Idea Brief (IDEA) | [idea-silverbot.md](idea-silverbot.md) | 0.1 | Draft | 2026-10-08 | N/A |
| Validation Brief (VALIDATION) | [val-silverbot.md](val-silverbot.md) | 0.1 | Draft | 2026-10-08 | N/A |
| House Style & Voice (VOICE) | [voice-silverbot.md](voice-silverbot.md) | 0.1 | Draft | 2026-10-08 | N/A |
| Business Requirements (BRD) | [brd-silverbot.md](brd-silverbot.md) | 0.1 | Draft | 2026-10-08 | 2026-10-08 (`62037d1`) |
| Unit Economics (UES) | [ues-silverbot.md](ues-silverbot.md) | 0.1 | Draft | 2026-10-08 | 2026-10-08 (`62037d1`) |
| Product Requirements (PRD) | [prd-silverbot.md](prd-silverbot.md) | 0.1 | Draft | 2026-10-08 | 2026-10-08 (`62037d1`) |
| Design System (DSD) | [dsd-silverbot.md](dsd-silverbot.md) | 0.1 | Draft (design system not started) | 2026-10-08 | N/A |
| System Design (SDD) | [sdd-silverbot.md](sdd-silverbot.md) | 0.1 | Draft | 2026-10-08 | 2026-10-08 (`62037d1`) |
| QA and Test Plan (QAD) | [qad-silverbot.md](qad-silverbot.md) | 0.1 | Draft | 2026-10-08 | 2026-10-08 (`62037d1`) |
| Subagent Roster (SAD) | [sad-silverbot.md](sad-silverbot.md) | 0.1 | Draft | 2026-10-08 | 2026-10-08 (`62037d1`) |
| Project Build Guide (BUILD) | [build-silverbot.md](build-silverbot.md) | 0.1 | Draft | 2026-10-08 | 2026-10-08 (`62037d1`) |
| Compliance & Legal Readiness Register (CLR) | [clr-silverbot.md](clr-silverbot.md) | 0.1 | Draft | 2026-10-08 | 2026-10-08 (`62037d1`) |
| AI Assurance Dossier (AIA) | [aia-silverbot.md](aia-silverbot.md) | 0.1 | Draft | 2026-10-08 | 2026-10-08 (`62037d1`) |
| Operations & Observability Runbook (OPS) | [ops-silverbot.md](ops-silverbot.md) | 0.1 | Draft | 2026-10-08 | 2026-10-08 (`62037d1`) |
| Build Session Log (LOG) | [log-silverbot.md](log-silverbot.md) | 0.1 | Draft (append-only) | 2026-10-08 | 2026-10-08 (`62037d1`) |

### Runbooks

| Runbook | File | Version | Status | Last Updated | Last Reconciled |
|---|---|---|---|---|---|
| Local Development | [runbook-local-dev.md](runbook-local-dev.md) | 0.1 | Draft | 2026-10-08 | 2026-10-08 (`62037d1`) |
| Backtest and Evidence | [runbook-backtest.md](runbook-backtest.md) | 0.1 | Draft | 2026-10-08 | 2026-10-08 (`62037d1`) |
| Demo / Testnet | [runbook-demo-testnet.md](runbook-demo-testnet.md) | 0.1 | Draft | 2026-10-08 | 2026-10-08 (`62037d1`) |

### Audits

| Audit | File | Version | Status | Last Updated | Last Reconciled |
|---|---|---|---|---|---|
| Docs vs Code Drift (86 findings D-1..D-86, 14 HIGH; code hazards H-1..H-14) | [audit-docs-drift.md](audit-docs-drift.md) | 0.1 | Draft | 2026-10-08 | 2026-10-08 (`62037d1`) |

### RFCs

| RFC ID | File | Feature | Status |
|---|---|---|---|
| `silverbot-rfc-001` | [rfc-silverbot-signal-engine.md](rfc-silverbot-signal-engine.md) | Signal engine (PRD-F1) | Draft |
| `silverbot-rfc-002` | [rfc-silverbot-risk-kill-switch.md](rfc-silverbot-risk-kill-switch.md) | Risk engine and kill switch (PRD-F3) | Draft |
| `silverbot-rfc-003` | [rfc-silverbot-ml-filter-gate.md](rfc-silverbot-ml-filter-gate.md) | ML filter gate (PRD-F6) | Draft |
| `silverbot-rfc-004` | [rfc-silverbot-readiness-gates.md](rfc-silverbot-readiness-gates.md) | Readiness gates (PRD-F5, PRD-F8, PRD-F12) | Draft |

### Root files

| File | Kind | Source of truth |
|---|---|---|
| [README.md](../README.md) | Hand-maintained | Itself |
| [CLAUDE.md](../CLAUDE.md) | Hand-maintained pointer | Itself; points here |
| [AGENTS.md](../AGENTS.md) | Materialized | [build-silverbot.md](build-silverbot.md) |
| [MODEL_CARD.md](../MODEL_CARD.md) | Materialized | [aia-silverbot.md](aia-silverbot.md) section 1 |
| `.claude/agents/*.md` (4 files) | Materialized | [sad-silverbot.md](sad-silverbot.md) section 3 |

Edit the source of truth, never the materialized file.

### Process records

| Record | File |
|---|---|
| Design spec for this documentation suite | [superpowers/specs/2026-10-08-canonical-docs-design.md](superpowers/specs/2026-10-08-canonical-docs-design.md) |
| Implementation plan | [superpowers/plans/2026-10-08-canonical-docs.md](superpowers/plans/2026-10-08-canonical-docs.md) |

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

## 2. Change Log

No Change Records yet. Records start once a doc is Locked.

| Date | Change | Reference |
|---|---|---|
| 2026-10-08 | Canonicalization pass: the root docs were absorbed into this suite, reconciled against code at `62037d1`, and removed. Originals remain in git history at that commit. | [design spec](superpowers/specs/2026-10-08-canonical-docs-design.md), [plan](superpowers/plans/2026-10-08-canonical-docs.md) |

## 3. Incident Log

No incidents recorded. The bot has never run a paper, demo or live session, so there is nothing to log. Incident procedure is in [ops-silverbot.md](ops-silverbot.md) section 4.

## 4. Health Check

- [~] All docs are Draft at 0.1; no doc is Locked yet, so the suite is reviewed but not frozen.
- [ ] Evidence reports are empty: `reports/backtest_report.json`, `reports/out_of_sample_validation_report.json` and `reports/paper_trading_report.json` are 0 bytes (G-1). No performance claim is made anywhere in the suite.
- [~] Materialized artifacts match their sources. This was verified by a generator and checker kept outside the repo; the repo has no automated check yet (see the process finding in [audit-docs-drift.md](audit-docs-drift.md)).
- [x] The tables in section 1 list every file under `docs/` (25 files including this index).
- [x] The SAD roster matches `.claude/agents/` (four reviewers, SAD-A1..A4).
- [ ] Phase 9 live-readiness evidence is open: no backtest, out-of-sample, paper, kill-switch or Telegram evidence exists (see [prd-silverbot.md](prd-silverbot.md) section 9).
- [ ] Code hazards found and not fixed (this pass changed no bot code); each is in [audit-docs-drift.md](audit-docs-drift.md) and [scrutiny-silverbot.md](scrutiny-silverbot.md):
  - NaN model probability is treated as 1.0 and approves a signal (H-1, G-8).
  - The kill switch is inert unless a path is injected, checks existence only, never auto-triggers and does not close positions (D-12, H-9, G-6).
  - Readiness is unreliable and consulted by nothing: a 0-byte report passes "exists", and a live-ready result needs settings the app refuses to load (H-2, H-3, G-2).
  - Settings risk limits never reach the risk engine, whose RiskConfig accepts up to 5% risk per trade (validation ceiling; default 0.5%; `risk/models.py:18,29`) against the documented 0.5% cap (D-11, H-5, G-5).
  - Risk state lives in memory and resets on restart (H-11, G-7).
  - The entrypoint is a startup stub that exits 0, so supervisors restart it in a loop (H-4, G-3).
  - `.env.example` fails to load as shipped (H-14, G-4).
  - Backtest costs default to 0 bps, which flatters results (H-7, G-11).
  - Model and registry pickles are loaded without trust checks (H-8).

## 5. Notes

Owner decisions that shaped this suite (OD-1 to OD-7, from the [design spec](superpowers/specs/2026-10-08-canonical-docs-design.md)). Citations of the form `FILE.md:N` to retired root docs (ARCHITECTURE.md, BACKTESTING.md, CONFIGURATION.md, DEPLOYMENT.md, ML_MODEL.md, RISK_POLICY.md, STRATEGY_NOTES.md, PROGRESS.md, TODO.md, the old README.md and the old AGENTS.md) refer to `git show 62037d1:FILE.md`.

- OD-1: Personal trading only. No customers, no pricing.
- OD-2: Generic jurisdiction. Country-specific compliance rows are open items for the owner.
- OD-3: Old root docs were absorbed, then deleted. Baseline commit `62037d1` keeps the originals.
- OD-4: The DSD is created with empty design-system sections ("Not started") plus a labelled Recommended UI proposal. Nothing is claimed as built.
- OD-5: Personal financial targets are an owner-input register; items not derivable from code are `Owner input required` (BRD section 8).
- OD-6: A small safety subagent roster, materialized to `.claude/agents/`.
- OD-7: Code-first audit, then write. Code wins over old docs.

Doc count: 17 suite docs (16 in the first table plus this index), 4 RFCs, 3 runbooks and 1 audit, which is 25 files under `docs/`, plus 2 tracked process records under `docs/superpowers/` (the design spec and the implementation plan). The root holds README.md, CLAUDE.md, AGENTS.md and MODEL_CARD.md.

Excluded: GTM, PITCH and WRAP. This is a personal trading bot with no customers, no pitch audience and no external product launch, so market, investor and launch-wrap docs do not apply.

Unbuilt roadmap items are labelled `Planned`; live trading is `Planned, blocked` (PRD-F12). When code and a doc disagree, the code wins and the disagreement becomes a row in [audit-docs-drift.md](audit-docs-drift.md).
