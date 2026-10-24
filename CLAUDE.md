# CLAUDE.md

> Read [AGENTS.md](AGENTS.md) first. It is the hand-maintained build guide and holds the read order, pinned stack, golden paths and every safety rule. This file adds Claude-Code-only notes.

## Claude-Code-specific notes

- **Project docs live in the AI Memory Vault**, not in this repo. Start every session at [docs/index.md](docs/index.md), which points to the vault project index `C:\AI Agentic Memory\01_Projects\SilverBot\00_Project_Index.md`. That index lists each doc's status and what is stale. Write doc updates, CRs and session notes in the vault, following the vault `AGENTS.md`.
- **Subagents:** `.claude/agents/` holds the four safety reviewers (SAD-A1..A4) and the stdlib-only UI builder `psl-purist` (SAD-B1). The cards are hand-maintained and canonical; the SAD (`C:\AI Agentic Memory\03_Resources\Blueprints\SilverBot\sad-silverbot.md`) section 3 keeps a snapshot, so copy any card change there. Use `psl-purist` for operator UI or Telegram work; its diffs still go through the reviewers.
- **Nothing is materialized.** `tools/materialize_docs.py`, `MODEL_CARD.md`, `BRAND.md` and `DESIGN.md` were retired on 2026-10-19. The model card is AIA section 1, and the brand and design system are DSD sections 0 to 7, both in the vault.
- **Never** enable live trading, place real orders, or weaken a risk, kill-switch or readiness gate. PRD-F12 (live trading) is Planned and blocked.
