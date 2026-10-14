# CLAUDE.md

> Read [AGENTS.md](AGENTS.md) first. It is materialized from [docs/build-silverbot.md](docs/build-silverbot.md) and holds the read order, pinned stack, golden paths and every safety rule. This file adds Claude-Code-only notes.

## Claude-Code-specific notes

- **Start every session at [docs/index.md](docs/index.md).** It lists each doc's status and what is stale.
- **Subagents:** `.claude/agents/` holds the four safety reviewers (SAD-A1..A4) and the stdlib-only UI builder `psl-purist` (SAD-B1) defined in [docs/sad-silverbot.md](docs/sad-silverbot.md). Edit the SAD, not the generated files. Use `psl-purist` for operator UI or Telegram work; its diffs still go through the reviewers.
- **Materialized files** (`AGENTS.md`, `MODEL_CARD.md`, `BRAND.md`, `DESIGN.md`, `.claude/agents/*.md`) are build artifacts. Edit their canonical docs ([docs/build-silverbot.md](docs/build-silverbot.md), [docs/aia-silverbot.md](docs/aia-silverbot.md) §1, [docs/dsd-silverbot.md](docs/dsd-silverbot.md) §0-7, [docs/sad-silverbot.md](docs/sad-silverbot.md) §3) and re-materialize with `python tools/materialize_docs.py` (`--check` to verify).
- **Never** enable live trading, place real orders, or weaken a risk, kill-switch or readiness gate. PRD-F12 (live trading) is Planned and blocked.
