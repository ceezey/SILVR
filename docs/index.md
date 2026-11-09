# Documentation Index: SILVR (pointer)

**Project:** SILVR (ICT Silver Bullet trading bot)
**Slug:** `silvr`
**Maintainer:** Cian Jake Francisco
**Last updated:** 2026-10-19

**The project docs are no longer in this repo.** On 2026-10-19 every SILVR doc moved into the owner's Obsidian vault, the AI Memory Vault at `C:\AI Agentic Memory`, which syncs to a private GitHub repo. This file stays in the repo only so that humans and agents know where to look.

## Start here

1. Read the vault rules: `C:\AI Agentic Memory\AGENTS.md`.
2. Open the project index, which is also the doc status manifest (versions, stale items, change log, health check, open safety items): [`01_Projects/SILVR/00_Project_Index.md`](<C:/AI Agentic Memory/01_Projects/SILVR/00_Project_Index.md>).
3. Read prior session notes, decisions and the superpowers specs and plans in `C:\AI Agentic Memory\01_Projects\SILVR\Memory`.

Write every doc change in the vault: suite docs, RFCs, runbooks, Change Records, the LOG and session notes. Do not add docs under `docs/`. Keep the vault's frontmatter and wikilink rules (vault `AGENTS.md` sections 3 and 4), and never rename a note.

## What stays in the repo

| File | Role |
|---|---|
| [AGENTS.md](../AGENTS.md) | Build guide (formerly `build-silvr.md`) and every safety rule. Hand-maintained; the only copy. |
| [CLAUDE.md](../CLAUDE.md) | Claude Code notes; points to `AGENTS.md` and here. |
| [README.md](../README.md) | Project overview and quick start. |
| `.claude/agents/*.md` (5 files) | Canonical subagent cards (SAD-A1..A4, SAD-B1); the SAD in the vault keeps a snapshot. |
| `docs/index.md` | This pointer. |

`MODEL_CARD.md`, `BRAND.md`, `DESIGN.md` and `tools/materialize_docs.py` were removed. The model card is AIA section 1, and the brand and design system are DSD sections 0 to 7, both in the vault. Earlier versions of every doc remain in git history before this commit.

## Where each doc lives

Paths are relative to the vault root. Basenames did not change, so `[[name]]` wikilinks resolve in Obsidian.

| Note | Vault path |
|---|---|
| Project index (manifest) | [01_Projects/SILVR/00_Project_Index.md](<C:/AI Agentic Memory/01_Projects/SILVR/00_Project_Index.md>) |
| `cr-silvr-operator-dashboard` | [01_Projects/SILVR/Change_Records/cr-silvr-operator-dashboard.md](<C:/AI Agentic Memory/01_Projects/SILVR/Change_Records/cr-silvr-operator-dashboard.md>) |
| `cr-silvr-dashboard-reskin` | [01_Projects/SILVR/Change_Records/cr-silvr-dashboard-reskin.md](<C:/AI Agentic Memory/01_Projects/SILVR/Change_Records/cr-silvr-dashboard-reskin.md>) |
| `log-silvr` | [01_Projects/SILVR/Logs/log-silvr.md](<C:/AI Agentic Memory/01_Projects/SILVR/Logs/log-silvr.md>) |
| `idea-silvr` | [01_Projects/SILVR/Planning/idea-silvr.md](<C:/AI Agentic Memory/01_Projects/SILVR/Planning/idea-silvr.md>) |
| `scrutiny-silvr` | [01_Projects/SILVR/Planning/scrutiny-silvr.md](<C:/AI Agentic Memory/01_Projects/SILVR/Planning/scrutiny-silvr.md>) |
| `brd-silvr` | [03_Resources/Blueprints/brd-silvr.md](<C:/AI Agentic Memory/03_Resources/Blueprints/SILVR/brd-silvr.md>) |
| `prd-silvr` | [03_Resources/Blueprints/prd-silvr.md](<C:/AI Agentic Memory/03_Resources/Blueprints/SILVR/prd-silvr.md>) |
| `sdd-silvr` | [03_Resources/Blueprints/sdd-silvr.md](<C:/AI Agentic Memory/03_Resources/Blueprints/SILVR/sdd-silvr.md>) |
| `sad-silvr` | [03_Resources/Blueprints/sad-silvr.md](<C:/AI Agentic Memory/03_Resources/Blueprints/SILVR/sad-silvr.md>) |
| `dsd-silvr` | [03_Resources/Blueprints/dsd-silvr.md](<C:/AI Agentic Memory/03_Resources/Blueprints/SILVR/dsd-silvr.md>) |
| `rfc-silvr-signal-engine` | [03_Resources/RFCs/rfc-silvr-signal-engine.md](<C:/AI Agentic Memory/03_Resources/RFCs/SILVR/rfc-silvr-signal-engine.md>) |
| `rfc-silvr-risk-kill-switch` | [03_Resources/RFCs/rfc-silvr-risk-kill-switch.md](<C:/AI Agentic Memory/03_Resources/RFCs/SILVR/rfc-silvr-risk-kill-switch.md>) |
| `rfc-silvr-ml-filter-gate` | [03_Resources/RFCs/rfc-silvr-ml-filter-gate.md](<C:/AI Agentic Memory/03_Resources/RFCs/SILVR/rfc-silvr-ml-filter-gate.md>) |
| `rfc-silvr-readiness-gates` | [03_Resources/RFCs/rfc-silvr-readiness-gates.md](<C:/AI Agentic Memory/03_Resources/RFCs/SILVR/rfc-silvr-readiness-gates.md>) |
| `aia-silvr` | [02_Areas/Compliance_&_Security/aia-silvr.md](<C:/AI Agentic Memory/02_Areas/Compliance_&_Security/SILVR/aia-silvr.md>) |
| `clr-silvr` | [02_Areas/Compliance_&_Security/clr-silvr.md](<C:/AI Agentic Memory/02_Areas/Compliance_&_Security/SILVR/clr-silvr.md>) |
| `qad-silvr` | [02_Areas/Quality_&_Strategy/qad-silvr.md](<C:/AI Agentic Memory/02_Areas/Quality_&_Strategy/SILVR/qad-silvr.md>) |
| `ues-silvr` | [02_Areas/Quality_&_Strategy/ues-silvr.md](<C:/AI Agentic Memory/02_Areas/Quality_&_Strategy/SILVR/ues-silvr.md>) |
| `val-silvr` | [02_Areas/Quality_&_Strategy/val-silvr.md](<C:/AI Agentic Memory/02_Areas/Quality_&_Strategy/SILVR/val-silvr.md>) |
| `voice-silvr` | [02_Areas/Quality_&_Strategy/voice-silvr.md](<C:/AI Agentic Memory/02_Areas/Quality_&_Strategy/SILVR/voice-silvr.md>) |
| `ops-silvr` | [02_Areas/Dev_&_Ops/ops-silvr.md](<C:/AI Agentic Memory/02_Areas/Dev_&_Ops/SILVR/ops-silvr.md>) |
| `runbook-local-dev` | [02_Areas/Dev_&_Ops/runbook-local-dev.md](<C:/AI Agentic Memory/02_Areas/Dev_&_Ops/SILVR/runbook-local-dev.md>) |
| `runbook-backtest` | [02_Areas/Dev_&_Ops/runbook-backtest.md](<C:/AI Agentic Memory/02_Areas/Dev_&_Ops/SILVR/runbook-backtest.md>) |
| `runbook-demo-testnet` | [02_Areas/Dev_&_Ops/runbook-demo-testnet.md](<C:/AI Agentic Memory/02_Areas/Dev_&_Ops/SILVR/runbook-demo-testnet.md>) |
| `audit-docs-drift` | [04_Archives/Audits/2026-10/audit-docs-drift.md](<C:/AI Agentic Memory/04_Archives/Audits/2026-10/audit-docs-drift.md>) |
| `2026-10-08-canonical-docs-design` | [01_Projects/SILVR/Memory/2026-10-08-canonical-docs-design.md](<C:/AI Agentic Memory/01_Projects/SILVR/Memory/2026-10-08-canonical-docs-design.md>) |
| `2026-10-09-g3-entrypoint-design` | [01_Projects/SILVR/Memory/2026-10-09-g3-entrypoint-design.md](<C:/AI Agentic Memory/01_Projects/SILVR/Memory/2026-10-09-g3-entrypoint-design.md>) |
| `2026-10-09-high-safety-fixes-design` | [01_Projects/SILVR/Memory/2026-10-09-high-safety-fixes-design.md](<C:/AI Agentic Memory/01_Projects/SILVR/Memory/2026-10-09-high-safety-fixes-design.md>) |
| `2026-10-14-silvr-brand-design` | [01_Projects/SILVR/Memory/2026-10-14-silvr-brand-design.md](<C:/AI Agentic Memory/01_Projects/SILVR/Memory/2026-10-14-silvr-brand-design.md>) |
| `2026-10-14-silvr-design-system-design` | [01_Projects/SILVR/Memory/2026-10-14-silvr-design-system-design.md](<C:/AI Agentic Memory/01_Projects/SILVR/Memory/2026-10-14-silvr-design-system-design.md>) |
| `2026-10-08-canonical-docs` | [01_Projects/SILVR/Memory/2026-10-08-canonical-docs.md](<C:/AI Agentic Memory/01_Projects/SILVR/Memory/2026-10-08-canonical-docs.md>) |
| `2026-10-09-g3-entrypoint` | [01_Projects/SILVR/Memory/2026-10-09-g3-entrypoint.md](<C:/AI Agentic Memory/01_Projects/SILVR/Memory/2026-10-09-g3-entrypoint.md>) |
| `2026-10-09-high-safety-fixes` | [01_Projects/SILVR/Memory/2026-10-09-high-safety-fixes.md](<C:/AI Agentic Memory/01_Projects/SILVR/Memory/2026-10-09-high-safety-fixes.md>) |
| `2026-10-09-operator-dashboard` | [01_Projects/SILVR/Memory/2026-10-09-operator-dashboard.md](<C:/AI Agentic Memory/01_Projects/SILVR/Memory/2026-10-09-operator-dashboard.md>) |
| `2026-10-14-silvr-brand-design-system` | [01_Projects/SILVR/Memory/2026-10-14-silvr-brand-design-system.md](<C:/AI Agentic Memory/01_Projects/SILVR/Memory/2026-10-14-silvr-brand-design-system.md>) |
