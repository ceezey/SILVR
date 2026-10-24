# Documentation Index: Silver Bot (pointer)

**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Slug:** `silverbot`
**Maintainer:** Cian Jake Francisco
**Last updated:** 2026-10-19

**The project docs are no longer in this repo.** On 2026-10-19 every SilverBot doc moved into the owner's Obsidian vault, the AI Memory Vault at `C:\AI Agentic Memory`, which syncs to a private GitHub repo. This file stays in the repo only so that humans and agents know where to look.

## Start here

1. Read the vault rules: `C:\AI Agentic Memory\AGENTS.md`.
2. Open the project index, which is also the doc status manifest (versions, stale items, change log, health check, open safety items): [`01_Projects/SilverBot/00_Project_Index.md`](<C:/AI Agentic Memory/01_Projects/SilverBot/00_Project_Index.md>).
3. Read prior session notes, decisions and the superpowers specs and plans in `C:\AI Agentic Memory\01_Projects\SilverBot\Memory`.

Write every doc change in the vault: suite docs, RFCs, runbooks, Change Records, the LOG and session notes. Do not add docs under `docs/`. Keep the vault's frontmatter and wikilink rules (vault `AGENTS.md` sections 3 and 4), and never rename a note.

## What stays in the repo

| File | Role |
|---|---|
| [AGENTS.md](../AGENTS.md) | Build guide (formerly `build-silverbot.md`) and every safety rule. Hand-maintained; the only copy. |
| [CLAUDE.md](../CLAUDE.md) | Claude Code notes; points to `AGENTS.md` and here. |
| [README.md](../README.md) | Project overview and quick start. |
| `.claude/agents/*.md` (5 files) | Canonical subagent cards (SAD-A1..A4, SAD-B1); the SAD in the vault keeps a snapshot. |
| `docs/index.md` | This pointer. |

`MODEL_CARD.md`, `BRAND.md`, `DESIGN.md` and `tools/materialize_docs.py` were removed. The model card is AIA section 1, and the brand and design system are DSD sections 0 to 7, both in the vault. Earlier versions of every doc remain in git history before this commit.

## Where each doc lives

Paths are relative to the vault root. Basenames did not change, so `[[name]]` wikilinks resolve in Obsidian.

| Note | Vault path |
|---|---|
| Project index (manifest) | [01_Projects/SilverBot/00_Project_Index.md](<C:/AI Agentic Memory/01_Projects/SilverBot/00_Project_Index.md>) |
| `cr-silverbot-operator-dashboard` | [01_Projects/SilverBot/Change_Records/cr-silverbot-operator-dashboard.md](<C:/AI Agentic Memory/01_Projects/SilverBot/Change_Records/cr-silverbot-operator-dashboard.md>) |
| `cr-silverbot-dashboard-reskin` | [01_Projects/SilverBot/Change_Records/cr-silverbot-dashboard-reskin.md](<C:/AI Agentic Memory/01_Projects/SilverBot/Change_Records/cr-silverbot-dashboard-reskin.md>) |
| `log-silverbot` | [01_Projects/SilverBot/Logs/log-silverbot.md](<C:/AI Agentic Memory/01_Projects/SilverBot/Logs/log-silverbot.md>) |
| `idea-silverbot` | [01_Projects/SilverBot/Planning/idea-silverbot.md](<C:/AI Agentic Memory/01_Projects/SilverBot/Planning/idea-silverbot.md>) |
| `scrutiny-silverbot` | [01_Projects/SilverBot/Planning/scrutiny-silverbot.md](<C:/AI Agentic Memory/01_Projects/SilverBot/Planning/scrutiny-silverbot.md>) |
| `brd-silverbot` | [03_Resources/Blueprints/brd-silverbot.md](<C:/AI Agentic Memory/03_Resources/Blueprints/SilverBot/brd-silverbot.md>) |
| `prd-silverbot` | [03_Resources/Blueprints/prd-silverbot.md](<C:/AI Agentic Memory/03_Resources/Blueprints/SilverBot/prd-silverbot.md>) |
| `sdd-silverbot` | [03_Resources/Blueprints/sdd-silverbot.md](<C:/AI Agentic Memory/03_Resources/Blueprints/SilverBot/sdd-silverbot.md>) |
| `sad-silverbot` | [03_Resources/Blueprints/sad-silverbot.md](<C:/AI Agentic Memory/03_Resources/Blueprints/SilverBot/sad-silverbot.md>) |
| `dsd-silverbot` | [03_Resources/Blueprints/dsd-silverbot.md](<C:/AI Agentic Memory/03_Resources/Blueprints/SilverBot/dsd-silverbot.md>) |
| `rfc-silverbot-signal-engine` | [03_Resources/RFCs/rfc-silverbot-signal-engine.md](<C:/AI Agentic Memory/03_Resources/RFCs/SilverBot/rfc-silverbot-signal-engine.md>) |
| `rfc-silverbot-risk-kill-switch` | [03_Resources/RFCs/rfc-silverbot-risk-kill-switch.md](<C:/AI Agentic Memory/03_Resources/RFCs/SilverBot/rfc-silverbot-risk-kill-switch.md>) |
| `rfc-silverbot-ml-filter-gate` | [03_Resources/RFCs/rfc-silverbot-ml-filter-gate.md](<C:/AI Agentic Memory/03_Resources/RFCs/SilverBot/rfc-silverbot-ml-filter-gate.md>) |
| `rfc-silverbot-readiness-gates` | [03_Resources/RFCs/rfc-silverbot-readiness-gates.md](<C:/AI Agentic Memory/03_Resources/RFCs/SilverBot/rfc-silverbot-readiness-gates.md>) |
| `aia-silverbot` | [02_Areas/Compliance_&_Security/aia-silverbot.md](<C:/AI Agentic Memory/02_Areas/Compliance_&_Security/SilverBot/aia-silverbot.md>) |
| `clr-silverbot` | [02_Areas/Compliance_&_Security/clr-silverbot.md](<C:/AI Agentic Memory/02_Areas/Compliance_&_Security/SilverBot/clr-silverbot.md>) |
| `qad-silverbot` | [02_Areas/Quality_&_Strategy/qad-silverbot.md](<C:/AI Agentic Memory/02_Areas/Quality_&_Strategy/SilverBot/qad-silverbot.md>) |
| `ues-silverbot` | [02_Areas/Quality_&_Strategy/ues-silverbot.md](<C:/AI Agentic Memory/02_Areas/Quality_&_Strategy/SilverBot/ues-silverbot.md>) |
| `val-silverbot` | [02_Areas/Quality_&_Strategy/val-silverbot.md](<C:/AI Agentic Memory/02_Areas/Quality_&_Strategy/SilverBot/val-silverbot.md>) |
| `voice-silverbot` | [02_Areas/Quality_&_Strategy/voice-silverbot.md](<C:/AI Agentic Memory/02_Areas/Quality_&_Strategy/SilverBot/voice-silverbot.md>) |
| `ops-silverbot` | [02_Areas/Dev_&_Ops/ops-silverbot.md](<C:/AI Agentic Memory/02_Areas/Dev_&_Ops/SilverBot/ops-silverbot.md>) |
| `runbook-local-dev` | [02_Areas/Dev_&_Ops/runbook-local-dev.md](<C:/AI Agentic Memory/02_Areas/Dev_&_Ops/SilverBot/runbook-local-dev.md>) |
| `runbook-backtest` | [02_Areas/Dev_&_Ops/runbook-backtest.md](<C:/AI Agentic Memory/02_Areas/Dev_&_Ops/SilverBot/runbook-backtest.md>) |
| `runbook-demo-testnet` | [02_Areas/Dev_&_Ops/runbook-demo-testnet.md](<C:/AI Agentic Memory/02_Areas/Dev_&_Ops/SilverBot/runbook-demo-testnet.md>) |
| `audit-docs-drift` | [04_Archives/Audits/2026-10/audit-docs-drift.md](<C:/AI Agentic Memory/04_Archives/Audits/2026-10/audit-docs-drift.md>) |
| `2026-10-08-canonical-docs-design` | [01_Projects/SilverBot/Memory/2026-10-08-canonical-docs-design.md](<C:/AI Agentic Memory/01_Projects/SilverBot/Memory/2026-10-08-canonical-docs-design.md>) |
| `2026-10-09-g3-entrypoint-design` | [01_Projects/SilverBot/Memory/2026-10-09-g3-entrypoint-design.md](<C:/AI Agentic Memory/01_Projects/SilverBot/Memory/2026-10-09-g3-entrypoint-design.md>) |
| `2026-10-09-high-safety-fixes-design` | [01_Projects/SilverBot/Memory/2026-10-09-high-safety-fixes-design.md](<C:/AI Agentic Memory/01_Projects/SilverBot/Memory/2026-10-09-high-safety-fixes-design.md>) |
| `2026-10-14-silverbot-brand-design` | [01_Projects/SilverBot/Memory/2026-10-14-silverbot-brand-design.md](<C:/AI Agentic Memory/01_Projects/SilverBot/Memory/2026-10-14-silverbot-brand-design.md>) |
| `2026-10-14-silverbot-design-system-design` | [01_Projects/SilverBot/Memory/2026-10-14-silverbot-design-system-design.md](<C:/AI Agentic Memory/01_Projects/SilverBot/Memory/2026-10-14-silverbot-design-system-design.md>) |
| `2026-10-08-canonical-docs` | [01_Projects/SilverBot/Memory/2026-10-08-canonical-docs.md](<C:/AI Agentic Memory/01_Projects/SilverBot/Memory/2026-10-08-canonical-docs.md>) |
| `2026-10-09-g3-entrypoint` | [01_Projects/SilverBot/Memory/2026-10-09-g3-entrypoint.md](<C:/AI Agentic Memory/01_Projects/SilverBot/Memory/2026-10-09-g3-entrypoint.md>) |
| `2026-10-09-high-safety-fixes` | [01_Projects/SilverBot/Memory/2026-10-09-high-safety-fixes.md](<C:/AI Agentic Memory/01_Projects/SilverBot/Memory/2026-10-09-high-safety-fixes.md>) |
| `2026-10-09-operator-dashboard` | [01_Projects/SilverBot/Memory/2026-10-09-operator-dashboard.md](<C:/AI Agentic Memory/01_Projects/SilverBot/Memory/2026-10-09-operator-dashboard.md>) |
| `2026-10-14-silverbot-brand-design-system` | [01_Projects/SilverBot/Memory/2026-10-14-silverbot-brand-design-system.md](<C:/AI Agentic Memory/01_Projects/SilverBot/Memory/2026-10-14-silverbot-brand-design-system.md>) |
