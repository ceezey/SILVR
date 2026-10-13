# Silverbot Brand (BRAND.md): Design Spec

**Date:** 2026-10-14
**Status:** Approved design; spec awaiting owner review
**Owner:** Cian Jake Francisco (ceezey)
**Branch:** `dev` (base commit `1d91623`)
**Baseline:** at `1d91623`, `python tools/materialize_docs.py --check` reports no changes and `python -m pytest -q` passes 271 tests

---

## 1. Intent

### What the owner asked for

- Create `BRAND.md` as an official, startup-style brand for the project.
- Ask questions first; settle the brand before the design system (`DESIGN.md`).
- Decide the colour palette and the Figma components later, in the `DESIGN.md` phase, using the Figma design file.

### Purpose

A portfolio and showcase brand. Silverbot stays a personal tool: one operator, no customers, no selling ([idea-silverbot.md](../../idea-silverbot.md) section 2 is unchanged). The brand must make the project read as a credible product to engineers and traders alike, without breaking any honesty rule in [voice-silverbot.md](../../voice-silverbot.md).

### Decomposition

The owner chose one brand and design system across every surface. That is three sub-projects, done in order, each with its own spec and plan:

1. **Brand (this spec).** Rewrite DSD sections 0 and 1; re-materialize `BRAND.md`.
2. **Design system and reskin.** DSD sections 2 to 7 (`DESIGN.md`): palette, type, mark geometry and Figma components; then the dashboard and Telegram changes through `psl-purist` (SAD-B1) and the reviewers, under a Change Record as DSD section 9.6 requires.
3. **Showcase assets.** README header, repository social preview, exported mark files.

### Decisions made during brainstorming

| # | Question | Decision |
|---|----------|----------|
| BD-1 | Purpose | Portfolio and showcase. Personal tool; no customers. |
| BD-2 | Name | One-word brand **Silverbot** for people; `silver-bot` / `silver_bot` stays the technical name. |
| BD-3 | Personality | Precision instrument, with a productive tone that motivates the operator. |
| BD-4 | Motivation | Aimed at progress and restraint only; never at trade count, profit, urgency or overriding limits. |
| BD-5 | Audience | Engineers and traders, equally. |
| BD-6 | Tagline | "Discipline over id." with the subline "Rules, not impulse, decide every trade." |
| BD-7 | Reach | One system across every surface (sub-projects 2 and 3 carry it out). |
| BD-8 | Style bans kept | Monospace only; no SaaS-template look; no chatty persona. Loosened: a small corner radius and hairline borders or shadows are allowed. |
| BD-9 | Structure | Rewrite DSD sections 0 and 1 in place; no tooling restructure. |
| BD-10 | Mark | Chart-visor bot: a bot head whose visor shows a long position at 1:3 risk to reward with price reaching the target, above a periodic-table badge (`47`, `Ag`). |
| BD-11 | Mark guardrail | The mark illustrates the RR rule; it is never paired with performance figures or result claims. |

### Invariants

- No bot code changes. No risk, kill-switch, readiness or live gate is touched. PRD-F12 stays `Planned, blocked`.
- The honesty rules stay: no performance or profit claim without a non-empty evidence file, no estimated or sample values, no colour-only states.
- DSD sections 2 to 9 are not edited in this sub-project, except one sentence in the DSD banner that records the pending name change on built surfaces.
- No em dashes in the new DSD text or `BRAND.md` ([voice-silverbot.md](../../voice-silverbot.md) section 1).
- Nothing is pushed to a remote.

## 2. Target content of DSD sections 0 and 1

The text below replaces everything in [dsd-silverbot.md](../../dsd-silverbot.md) from `## 0. Brand Stance` up to (not including) `## 2. Brand Primitives`. Headings `## 0. Brand Stance` and `## 1. Design Philosophy & Vision` keep their exact text (asserted by `tests/test_materialize_docs.py`). Surface modes stay at §1.2, because §9.2 cites "surface mode A, §1.2".

````markdown
## 0. Brand Stance

**Silverbot. Discipline over id.** *Rules, not impulse, decide every trade.*

The id is the impulsive part of the mind; in discretionary trading it chases, revenge-trades and moves stops. Silverbot replaces it with rules that run the same way every time.

**Positioning.** A disciplined trading method, built like production infrastructure. Traders see one ICT Silver Bullet setup enforced identically on every candle. Engineers see a mandatory risk engine, a fail-closed kill switch, deterministic execution, a full audit trail and zero third-party dependencies.

**Brand promise.** Silverbot shows what exists, says plainly what does not, and names the next step.

**Personality: a productive precision instrument.** Calm, exact and quietly confident, like a well-made tool that makes the operator want to do the work properly. Every surface moves the operator forward: what is done, what is next, and what the rules protected.

**How Silverbot motivates.** Only from real data in a source named in §9.3 or an alerter event:

1. **Progress, not emptiness.** The evidence path (backtest, out-of-sample, paper, demo, then live, which is blocked) reads as a ladder of gates. Every empty state names the action that fills it.
2. **Restraint counts as success.** A rejection is the system working ("Risk engine held"), never a failure to apologise for.
3. **Quiet completion.** A finished step gets a short confirmation that points at the next gate.
4. **Forward language.** Present tense, active verbs, short lines. Momentum comes from the words, not from decoration.

Silverbot never motivates with profit or win celebrations, streaks or scores tied to trade count, urgency or scarcity, reward animations, or prompts to trade more, override a rejection or loosen a limit.

**Operator questions.** Every operator surface answers, in this order: is it safe (mode, live flag, kill switch), is it ready (readiness and evidence), what did it decide and why (signals, rejections, ML probability), is the host sane (files present, logs written), and what is next.

## 1. Design Philosophy & Vision

### 1.1 Name

| Context | Form | Example |
|---------|------|---------|
| Read by people: README, dashboard title, alert header, prose | **Silverbot** | `Silverbot status · read-only` |
| Read by code: package, console script, module, paths | `silver-bot` / `silver_bot` | `python -m silver_bot` |

Never write "SilverBot", "SILVR" or "the Bot" as a proper name. "Silver Bot" (two words) is the legacy form still used across the suite docs; a separate rename pass replaces it. The built dashboard and the §4.2 Telegram anchor still show `silver-bot` until the design-system phase changes them.

Descriptor: *A disciplined ICT Silver Bullet trading bot, built like production infrastructure.*

### 1.2 Surface modes

| Mode | Surface | Status | Character |
|------|---------|--------|-----------|
| A | Localhost read-only status dashboard (primary; §9) | Built (PRD-F13) | Server-rendered HTML from the standard library (`http.server`, `string.Template`), inline CSS, monospace, bound to `127.0.0.1`. Same grid, tokens and glyphs as mode B. |
| B | Terminal status view (secondary) | Planned, gated by §9.6 | Black canvas, box-drawing grids, dense tables, ANSI colour always paired with a status glyph. 80 x 24 minimum. |
| C | JSON-lines audit log | Built (`monitoring/audit.py`) | One flat JSON object per line, keys sorted, secrets redacted (§4.3). |
| D | Telegram alerts | Planned (G-15); message text built, no transport | Compact MarkdownV2 messages with monospace dividers (§4.2). |

All four carry the Silverbot name and voice (§1.4). Mode C keeps its machine format; only its `message` text follows the voice.

### 1.3 Anti-references

Non-negotiable (safety and honesty):

- A hosted or remotely reachable web UI, a JavaScript framework or bundler, a Node runtime, or any asset loaded from a CDN or another host. Mode A is the only browser surface: local, read-only and server-rendered by the standard library.
- Colour-only indicators: every coloured state carries a glyph and a word (§2.2, §6).
- Estimated, interpolated or sample values in place of missing data. An empty source shows `not available`, the reason and the next step.
- Any performance or profit claim without a non-empty evidence file.
- Motivation tied to trade count, profit, urgency, or overriding a rejection or limit (§0).

Style:

- Playful, chatty or first-person phrasing ("I found a trading opportunity for you!", "Thinking...").
- Generic SaaS dashboard templates and stock marketing imagery.
- Any typeface other than monospace.
- Gradients, heavy drop shadows, frosted glass and saturated backgrounds. A small corner radius and hairline borders or shadows are allowed where they clarify structure.

### 1.4 Voice

Third person or no person. Present tense, active verbs, one claim per line. Say what is missing or just finished, then the next step. Numbers come only from real sources.

| Moment | Not this | Silverbot |
|--------|----------|-----------|
| Empty source | `not available` | `not available: no backtest yet. Next: python -m silver_bot --candles data/candles` |
| Risk rejection | `Trade failed: limit hit` | `Risk engine held. Setup declined: Max daily loss limit reached.` |
| Step finished | `Done!` | `Backtest and out-of-sample reports written. Next gate: paper trading (not available yet, G-3).` |
| Gate closed | `Error: not ready` | `Live gate closed: 3 evidence reports empty (G-1).` |
| Signal | `I found a great trade for you!` | `Setup detected: BTCUSDT long. Passing to risk engine.` |

Rejection reasons are quoted as the code emits them (signal reasons: [rfc-silverbot-signal-engine.md](rfc-silverbot-signal-engine.md) section 3.8; risk reasons: `risk/engine.py`).

### 1.5 Mark

The Silverbot mark is a bot head in two parts:

- **Visor (upper part).** A long position drawn like a trading position tool: an entry line, a stop zone of height 1R below it, a target zone of height 3R above it, and candles climbing from the entry into the top of the target. 1:3 is above the engine's minimum risk to reward of 2.0 (`strategy/models.py`, `minimum_rr`).
- **Badge (lower band).** A periodic-table cell: `47` small in the top-left corner, `Ag` large. Silver, measured precisely.
- **Antennae.** Two short stubs on top of the head.

Below 32 px the candles are dropped, leaving the entry line and the two zones. Text-only surfaces (modes B, C and D) use `[Ag]`. The mark may sit left of the `Silverbot` wordmark.

Guardrail: the mark illustrates the risk-to-reward rule. It never appears next to performance figures, win rates or result claims, and no surface uses it to suggest Silverbot has been profitable.

Colours, geometry, clear space, light and dark versions and the Figma component are specified in the design-system phase (§2 to §7).
````

## 3. Files changed

| File | Change |
|------|--------|
| [dsd-silverbot.md](../../dsd-silverbot.md) | Replace sections 0 and 1 with section 2 of this spec. Set **Last updated** to 2026-10-14. Add one sentence to the banner: the brand is Silverbot (§0 to §1); sections 2 to 7 and the built dashboard still use `silver-bot` until the design-system phase. Update the Self-Check line for sections 0 to 7 if its wording no longer matches. |
| `BRAND.md` | Regenerated by `python tools/materialize_docs.py`. Never hand-edited. |
| `tools/materialize_docs.py` | The generated title changes from `# Brand: silver-bot` to `# Brand: Silverbot` (one string, line 78). The `DESIGN.md` title changes in sub-project 2. |
| [index.md](../../index.md) | DSD row **Last updated** 2026-10-14; the process-records table and the doc-count paragraph gain this spec. |
| [log-silverbot.md](../../log-silverbot.md) | One appended row: brand rewrite, decisions BD-1 to BD-11, verification commands. |
| [sad-silverbot.md](../../sad-silverbot.md) | Re-reconcile SAD-B1 as its section on re-reconciling requires: confirm that the `psl-purist` card still points at DSD sections 0 to 7 and needs no change. Edit only if a statement became false. |

Not changed: bot code, DSD sections 2 to 9 (apart from the banner sentence), `DESIGN.md`, README, the other suite docs, [voice-silverbot.md](../../voice-silverbot.md) (it governs the docs; DSD §1.4 governs product surfaces).

## 4. Verification

1. `python tools/materialize_docs.py`, then `python tools/materialize_docs.py --check`. Expected: no changes reported on the second run.
2. `python -m pytest -q tests/test_materialize_docs.py`. Expected: all pass (QAD-T205 still finds `## 0. Brand Stance` and `## 1. Design Philosophy` and no `## 2. ` in `BRAND.md`).
3. `python -m pytest -q`. Expected: 271 passed, as at `1d91623`.
4. Search the new DSD sections 0 and 1 and `BRAND.md` for the em dash character U+2014. Expected: none.
5. Read-through against [voice-silverbot.md](../../voice-silverbot.md) section 1: no profit claim, no invented number, no placeholder token, and every example value traceable to code or a gap ID.

## 5. Follow-ups (not in this spec)

- **Sub-project 2, design system:** palette (including the stop and target zone tones of the mark), type, mark geometry and the Figma components in the design file named in the DSD header; DSD sections 2 to 7; the `DESIGN.md` title; the dashboard header and the Telegram anchor move to `Silverbot`; a "next step" line in the §7 quality gate.
- **Reskin Change Record** for the dashboard and Telegram changes (DSD section 9.6).
- **Sub-project 3, showcase assets:** README header, social preview, exported mark files.
- **Docs rename pass:** "Silver Bot" to "Silverbot" across the suite docs.
