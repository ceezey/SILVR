# Canonical Documentation Suite: Design Spec

**Date:** 2026-10-08
**Status:** Approved; implemented on branch docs/canonical-suite
**Owner:** Cian Jake Francisco (ceezey)
**Doc slug:** `silverbot`

---

## 1. Intent

### What the owner asked for

- Build a canonical `docs/` suite for Silver Bot.
- Fill every topic accurately and reconcile the old root `.md` files into it.
- Write it as this project's own documentation. Never name, credit or describe any
  external source repository or its product anywhere in committed content.
- Exclude GTM and PITCH.
- Before producing output, surface any topic the available information cannot fill.
- Afterwards, push the codebase to a new **private** GitHub repo under the owner's
  account.

### Decisions made during brainstorming

| # | Question | Decision |
|---|----------|----------|
| OD-1 | Purpose of the bot | **Personal trading only.** No customers, no product pricing. |
| OD-2 | Compliance jurisdiction | **Generic.** CLR is jurisdiction-neutral; country-specific rows are open items for the owner. |
| OD-3 | Old root docs | **Absorb, then delete.** Baseline commit `62037d1` keeps the originals in history. |
| OD-4 | DSD (design system) | **Create the file but leave the design-system sections empty** ("Not started"). Add a clearly labelled **Recommended UI** proposal based on how the bot is actually used. Nothing is claimed as built. |
| OD-5 | Personal financial targets | **Owner-input register.** Everything derivable from code/config is filled; capital, monthly budget, drawdown tolerance in money and return goal are listed as `Owner input required`. |
| OD-6 | Subagents (SAD) | **Small safety roster, materialized** to `.claude/agents/`. |
| OD-7 | Build approach | **Code-first audit, then write.** |

### Information gaps flagged before output

These cannot be filled from code, config or the old docs and will appear as explicit
open items, never guesses:

- Owner financials: capital, running budget, drawdown tolerance in money, return goal,
  monitoring time (BRD / UES).
- Jurisdiction-specific legal and tax obligations (CLR).
- Real strategy performance: `reports/backtest_report.json`,
  `reports/out_of_sample_validation_report.json` and
  `reports/paper_trading_report.json` are **0-byte files**, while
  `reports/live_readiness_report.json` records them as "found". No performance
  claim can be made (SCRUTINY gap, VALIDATION evidence).
- Problem evidence for VALIDATION beyond the owner's own motivation.

### Success criteria

1. Every doc in §2 exists, and every statement about behaviour is traceable to code
   (`file:line` in the fact sheets) or labelled `Planned` / `Owner input required`.
2. Zero mentions of any external source repository or product in any committed file.
3. Old root docs are absorbed and deleted; only `README.md`, `AGENTS.md`, `CLAUDE.md`
   and `MODEL_CARD.md` remain at the root as docs.
4. All relative links resolve. Every `PRD-F#` appears in SDD and QAD.
5. `pytest` result is unchanged (docs-only pass; no code change).
6. The repo is pushed to a private GitHub repo under `ceezey`.

---

## 2. Suite Map

All suite docs live in `docs/` and are named `<type>-silverbot.md`. All start as
`Draft`. Nothing becomes `Locked` until the owner reviews it.

| Doc | File | Holds | Primary sources |
|-----|------|-------|-----------------|
| Index | `docs/index.md` | Manifest (version, status, dates), traceability matrix, change log, health check, notes | all |
| IDEA | `idea-silverbot.md` | The spark, who it is for, scope and cut line, success criteria, open questions | README, codex-task.json |
| VALIDATION | `val-silverbot.md` | Evidence the strategy is worth automating, alternatives (manual trading, off-the-shelf bots), feasibility, kill criteria | README, BACKTESTING, owner input |
| SCRUTINY | `scrutiny-silverbot.md` | Verdict, claim audit, gap register `G-#`, assumption stress test, risk pre-flight, blocking questions | code vs old docs |
| VOICE | `voice-silverbot.md` | House style: hard bans, register per doc type, project tuning | project-specific rules |
| BRD | `brd-silverbot.md` | Personal objectives, `BRD-M#` metrics, `BRD-V#` impact variables, scope, owner-input register, stakeholders (owner only) | README, BACKTESTING pass/fail |
| UES | `ues-silverbot.md` | Cost of running (VPS, exchange fees, slippage, spread, data), capital and runway as owner input, cost per trade | DEPLOYMENT, backtest fee model |
| PRD | `prd-silverbot.md` | Features `PRD-F#`, user stories `US-##` with acceptance criteria, operator flows, instrumentation, NFRs, out of scope, ML spec, phase plan | TODO, PROGRESS, codex-task.json, code |
| DSD | `dsd-silverbot.md` | Design-system sections present but empty ("Not started") + **Recommended UI** proposal | OD-4 |
| SDD | `sdd-silverbot.md` | Principles, architecture, modules, data models, SQLite storage, exchange adapter, modes, config, security, NFRs, ML architecture | ARCHITECTURE, CONFIGURATION, code |
| QAD | `qad-silverbot.md` | Strategy, environments, test matrix (happy / sad / abuse / unsafe-config), `QAD-T#` rows mapped to the 19 test files and `PRD-F#`, release criteria, ML evaluation | tests/, BACKTESTING |
| SAD | `sad-silverbot.md` | Roster of 4 safety agents, orchestration, materialization | OD-6 |
| BUILD | `build-silverbot.md` | Read order, traceability map, pinned stack, golden-path patterns, conventions and guardrails (all existing AGENTS.md safety rules preserved), definition of done | AGENTS.md, pyproject, code |
| CLR | `clr-silverbot.md` | Generic retail-trader register: API key security, exchange terms, tax record-keeping, data held, open jurisdiction rows | OD-2 |
| AIA | `aia-silverbot.md` | ML filter assurance: intended use, allowed / forbidden powers, data and leakage, calibration, promotion and rollback, risk register | ML_MODEL, ml/ |
| OPS | `ops-silverbot.md` | Operating posture per mode, SLOs, logs / `audit.jsonl` / Telegram, alerting, kill-switch and emergency runbooks, VPS / systemd / Docker routine ops | DEPLOYMENT, monitoring/, deploy/ |
| LOG | `log-silverbot.md` | Append-only build history backfilled from PROGRESS.md, plus this pass | PROGRESS |
| RFC-001 | `rfc-silverbot-signal-engine.md` | Silver Bullet signal engine: sessions, sweep, displacement, MSS, FVG, entry / SL / TP, rejection reasons, scoring | STRATEGY_NOTES, strategy/ |
| RFC-002 | `rfc-silverbot-risk-kill-switch.md` | Risk engine gates, position sizing, kill switch | RISK_POLICY, risk/ |
| RFC-003 | `rfc-silverbot-ml-filter-gate.md` | ML approve / reject / reduce-risk gate, thresholds, registry | ML_MODEL, ml/ |
| RFC-004 | `rfc-silverbot-readiness-gates.md` | Demo/testnet and live-readiness checkers, required evidence | readiness.py, demo_readiness.py |
| Runbook | `runbook-local-dev.md` | Environment setup, running tests, config files | README, CONFIGURATION |
| Runbook | `runbook-backtest.md` | Producing backtest and out-of-sample evidence | BACKTESTING, backtest/ |
| Runbook | `runbook-demo-testnet.md` | Binance Futures testnet setup and dry startup | CONFIGURATION, DEPLOYMENT |
| Audit | `audit-docs-drift.md` | Findings: old docs vs code, with evidence | fact sheets |

**Excluded:** GTM, PITCH. **WRAP is excluded for now**: the project has not reached
an outcome to wrap. A WRAP doc is created when a phase closes.

### Root files

| File | Kind | Source |
|------|------|--------|
| `README.md` | Hand-maintained | Rewritten to orient and link into `docs/` |
| `AGENTS.md` | Materialized | from BUILD |
| `CLAUDE.md` | Hand-maintained pointer | points to `AGENTS.md`, adds Claude-Code-only notes |
| `MODEL_CARD.md` | Materialized | from AIA §1 |
| `.claude/agents/*.md` | Materialized | from SAD |

Absorbed and deleted after the suite lands: `ARCHITECTURE.md`, `BACKTESTING.md`,
`CONFIGURATION.md`, `DEPLOYMENT.md`, `ML_MODEL.md`, `RISK_POLICY.md`,
`STRATEGY_NOTES.md`, `PROGRESS.md`, `TODO.md`, `codex-task.json`.

Status tracking that lived in PROGRESS.md / TODO.md moves to `docs/index.md`
(health check), PRD §9 (phase plan with checkboxes) and LOG.

### SAD roster (OD-6)

| Agent | Purpose | Never |
|-------|---------|-------|
| `live-trading-gate-guardian` | Proves no code path can place a real order unless `LIVE_TRADING=true` and readiness checks pass; default mode stays paper/backtest | approves a diff that weakens a gate |
| `risk-bypass-checker` | Proves every order path goes through the risk engine and kill switch, with a stop loss | accepts "temporary" bypasses |
| `lookahead-leakage-auditor` | Checks backtest and ML code for lookahead bias, future data in features, and test-set optimization | treats final-test-set tuning as acceptable |
| `restraint-guardian` | Flags over-engineering (YAGNI ladder) | cuts validation, risk, safety or tests |

Each agent is read-only (Read, Grep, Glob), returns a verdict plus evidence, and treats
its inputs as untrusted.

### DSD Recommended UI (OD-4) scope

A proposal only, derived from the operator workflow: mode and safety state at a glance
(mode, LIVE/PAPER/DEMO flags, kill switch), readiness checklist status, open positions
and today's risk budget used, trade journal, and links to report files. It names the
data each panel reads (dashboard JSON, SQLite, `audit.jsonl`, `reports/*.json`). It is
marked `Proposal, not built` and adds no requirement to the PRD.

---

## 3. Build Pipeline

### 3.1 Fact gathering (read-only)

Six parallel read-only agents, one per slice:

1. strategy/
2. risk/ + execution/
3. backtest/ + storage/ + data/
4. ml/
5. config/ + readiness.py + demo_readiness.py + exchange/ + health.py + main.py
6. monitoring/ + deploy/ + Dockerfile + docker-compose + tests/

Each returns a fact sheet: behaviour with `file:line`, config keys and defaults, gates
and rejection reasons, covering tests, and every contradiction with the old docs.
Fact sheets are working files in the session scratchpad, not committed.

`pytest` is run once to record the real pass / fail count.

### 3.2 Reconcile rules

1. **Code wins** over the old docs. Each disagreement becomes a row in
   `audit-docs-drift.md` and, where it affects a claim, a `G-#` in SCRUTINY.
2. What neither source answers becomes an explicit open item (`Owner input required`
   or `Open`), never a guess.
3. Unbuilt roadmap items (live trading, Phase 9 evidence items) are labelled `Planned`.
4. No performance claim is made without a non-empty evidence report.

### 3.3 Writing order

SCRUTINY → IDEA / VALIDATION / BRD / UES → PRD → SDD → RFC-001..004 → QAD → AIA / CLR /
OPS → SAD → BUILD → VOICE → DSD → LOG → runbooks → audit → index → root files.

Stable IDs, never renumbered: `PRD-F#`, `US-##`, `BRD-M#`, `BRD-V#`, `G-#`, `QAD-T#`,
`AIA-R#`, `SAD-A#`.

### 3.4 Language

- No mention of any external source repository or product, and no "based on" credit.
- Materialization, Change Records, Locked/Draft status and the health check are this
  project's own conventions.
- From now on, any change to a `Locked` doc requires a Change Record
  (`docs/cr-silverbot-<slug>.md`).

---

## 4. Git and Publishing

1. Done: `git init`, `.gitignore` hardened (`.venv/`, `runtime/`, `*.egg-info/`,
   `.claude/settings.local.json`, and the gitignored reference folder, which stays on disk and is
   never committed). Secret scan clean. Baseline commit `62037d1`.
2. This spec is committed next.
3. The suite lands in a few commits; the last one deletes the absorbed root files.
4. Before pushing: confirm the repo name with the owner (proposed `ceezey/silver-bot`),
   then `gh repo create <name> --private --source . --push`.

---

## 5. Verification

- Link check: every relative Markdown link resolves.
- Leak check: grep finds zero references to the forbidden external names across all
  tracked files.
- Traceability: every `PRD-F#` appears in SDD and QAD; the index matrix matches.
- Materialization: `AGENTS.md` matches BUILD; `MODEL_CARD.md` matches AIA §1;
  `.claude/agents/*` match the SAD cards.
- Placeholder scan: no `TBD` except `Owner input required` / `Open` rows.
- `pytest` result unchanged from §3.1.
- `git status` clean; `.env` and the gitignored reference folder are not tracked.

---

## 6. Out of Scope

- Any code change, including fixes for drift the audit finds (recorded, not fixed).
- GTM, PITCH, WRAP.
- Building the Recommended UI.
- Jurisdiction-specific legal research.
- Generating real backtest / paper evidence.
