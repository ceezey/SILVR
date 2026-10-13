# Design System (DSD)

**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Version:** 0.1
**Owner:** Cian Jake Francisco
**Status:** Draft (Silverbot brand and design system specified; mode A built per silverbot-cr-001; reskin proposed in silverbot-cr-002)
**Last updated:** 2026-10-14
**Last reconciled:** N/A (not a code-describing doc)
**Design file:** [SILVR](https://www.figma.com/design/g1n3J4j2L1iPrbdjiOS30e/SILVR): pages Branding and Foundation Components mirror sections 0 to 7 (section 8).

> Mode A, the read-only localhost dashboard, is built (PRD-F13, [cr-silverbot-operator-dashboard.md](cr-silverbot-operator-dashboard.md)); modes B and D are not. Sections 0 to 7 specify the brand and design system that any operator surface must follow (materialized to `BRAND.md` and `DESIGN.md`, section 8). Section 9 is the approved scope of mode A (PRD-F13) and a proposal for mode B, which adds no requirement. Building mode B or any other surface still needs its own Change Record (§9.6). The operator surface that exists is listed in [prd-silverbot.md](prd-silverbot.md) section 5.1 (command-line entrypoints, the dashboard entrypoint and files). Sections 0 to 7 now specify the Silverbot brand and the Sterling design system; the built dashboard still uses the earlier tokens and layout until [cr-silverbot-dashboard-reskin.md](cr-silverbot-dashboard-reskin.md) (`silverbot-cr-002`, Proposed) is approved and built.

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

Never write "SilverBot", "SILVR" or "the Bot" as a proper name. "Silver Bot" (two words) is the legacy form still used across the suite docs; a separate rename pass replaces it. The built dashboard and the built Telegram text still show `silver-bot` until [cr-silverbot-dashboard-reskin.md](cr-silverbot-dashboard-reskin.md) (`silverbot-cr-002`, Proposed) changes the dashboard and the Telegram transport record (G-15) changes the alerts.

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
| Empty source | `not available` | `not available: no backtest yet. Next: run a backtest (runbook-backtest.md steps 5 and 6)` |
| Risk rejection | `Trade failed: limit hit` | `Risk engine held. Setup declined: Max daily loss limit reached.` |
| Step finished | `Done!` | `Backtest and out-of-sample reports written. Next gate: paper trading (not available yet, G-3).` |
| Gate closed | `Error: not ready` | `Live gate closed: 3 evidence reports empty (G-1).` |
| Signal | `I found a great trade for you!` | `Setup detected: BTCUSDT long. Passing to risk engine.` |

Rejection reasons are quoted as the code emits them (signal reasons: [rfc-silverbot-signal-engine.md](rfc-silverbot-signal-engine.md) section 3.8; risk reasons: `risk/engine.py`).

### 1.5 Mark

The Silverbot mark is a bot head in two parts:

- **Visor (upper part).** A long position drawn like a trading position tool: an entry line, a stop zone of height 1R below it, a target zone of height 3R above it, and candles that reach the target at 1:3 risk to reward. 1:3 is above the engine's minimum risk to reward of 2.0 (`strategy/models.py`, `minimum_rr`).
- **Badge (lower band).** A periodic-table cell: `47` small in the top-left corner, `Ag` large. Silver, measured precisely.
- **Antennae.** Two short stubs on top of the head.

Guardrail: the mark illustrates the risk-to-reward rule. It never appears next to performance figures, win rates or result claims, and no surface uses it to suggest Silverbot has been profitable.

Construction, tiers and lockups: §2.4.

## 2. Brand Primitives (tokens, color, type)

Target values: the Sterling system below is specified, not built. The built dashboard still follows `silverbot-cr-001` and uses the earlier tokens (`canvas` `#000000`, `surface` `#111827`, `border` `#374151`, `ink` `#F9FAFB`, `muted` `#9CA3AF`, `success` `#10B981`, `warning` `#F59E0B`, `danger` `#EF4444`; `monitoring/dashboard_server.py:32-69`) until [cr-silverbot-dashboard-reskin.md](cr-silverbot-dashboard-reskin.md) (`silverbot-cr-002`, Proposed) is approved and built.

### 2.1 Neutral and brand tokens

Each token has a dark and a light hex value and an ANSI 16-colour index for mode B. The dashboard and the terminal are dark only; the light theme is for the README, slides, social images and Figma. Every text token meets WCAG AA (at least 4.5:1) on both `canvas` and `surface` in its theme; the contrast ratio (lowest of the two backgrounds) is in brackets. `border` is for lines only.

| Token | Dark | Light | ANSI (mode B) | Use |
|-------|------|-------|---------------|-----|
| `canvas` | `#0B0D10` | `#F6F7F9` | 0 | Page background |
| `surface` | `#13161B` | `#FFFFFF` | 0 | Panels, header, step cards (mode B draws it as `canvas`) |
| `border` | `#2A2F38` | `#D9DDE3` | 8 | Hairlines and rules, never text |
| `ink` | `#E8EAED` (15.0) | `#14171C` (16.8) | 15 | Values and data rows |
| `muted` | `#9AA1AC` (7.0) | `#5B6370` (5.7) | 7 | Labels, timestamps, the `[ OFF ]` state |
| `brand` | `#C3C9D2` (10.9) | `#646D79` (4.9) | 7, bold | The mark and the wordmark only |
| `accent` | `#7AA2F7` (7.2) | `#2F5BD3` (5.5) | 12 | The next step and links only; never a state |

### 2.2 Semantic tokens

Semantic colour marks state only, never decoration, and always travels with its glyph and a word.

| Token | Dark | Light | ANSI | Glyph | Means |
|-------|------|-------|------|-------|-------|
| `success` | `#3FB68B` (7.1) | `#1E7F5A` (4.6) | 2 green | `[ OK ]` | Check passed, report non-empty, event written, flag in its safe position |
| `warning` | `#E3B341` (9.3) | `#8A5D00` (5.4) | 3 yellow | `[ WRN ]` | Needs attention but not failing: kill-switch path unset (G-6), stale readiness report (an evidence report modified after its `generated_at`, or `generated_at` older than 24 hours), model loaded without a trust check (H-8) |
| `danger` | `#F0616D` (5.7) | `#C23142` (5.1) | 1 red | `[ ERR ]` | Check failed, evidence report 0 bytes, kill switch active, `error` event |
| `muted` | `#9AA1AC` | `#5B6370` | 7 white | `[ OFF ]` | A flag that is off or a source that is not available |

Direction arrows `▲` (long) and `▼` (short) may accompany a direction word; they are never a health signal. The 24-hour rule is in addition to the `silverbot-cr-001` rule; either condition makes a readiness report stale.

### 2.3 Type

IBM Plex Mono only (monospace). Font stack: `"IBM Plex Mono", ui-monospace, "Cascadia Mono", Menlo, Consolas, monospace`. Mode A serves IBM Plex Mono Regular and Bold as woff2 from its own `127.0.0.1` server once `silverbot-cr-002` is built; until then it renders with `ui-monospace, "Cascadia Mono", Menlo, Consolas, monospace` and loads no web font. Brand surfaces (Figma, README images, slides) use Plex Mono directly.

| Style | Size / weight | Use |
|-------|---------------|-----|
| `Label` | 10 / Bold, upper case | Panel titles, step labels |
| `Detail` | 11 / Regular | Timestamps, report rows, secondary lines |
| `Data` | 12 / Regular | Banner, status cells, Next strip, data rows |
| `Wordmark` | 14 / Bold, `brand` | Dashboard header |
| `Showcase 18`, `Showcase 22`, `Showcase 40` | Bold | Tagline, headings, hero wordmark (brand surfaces) |

Numbers are shown exactly as stored, use `.` as the decimal mark, carry no thousands separator and are never italic in data rows. Numbers are right-aligned in mode B. Mode A waives the right-alignment: each row is label, state, detail, so numbers sit inside left-aligned detail text; they are never rounded ([cr-silverbot-operator-dashboard.md](cr-silverbot-operator-dashboard.md) V-6).

### 2.4 Mark

Concept: a bot head whose visor shows a long position at 1:3 risk to reward with price reaching the target, above a periodic-table badge. Construction on a 160 x 160 grid:

| Part | Geometry | Colour |
|------|----------|--------|
| Antennae | Two 5 x 16 stubs, radius 2, at x = 40 and x = 115 | `brand` |
| Head | 160 x 144 at y = 14, radius 12, stroke 3 | stroke `brand`, fill `surface` |
| Visor | 132 x 76, inset 14 from the head's left and top, radius 6 | `canvas` |
| Entry line | Full visor width less 6 each side, 2 high, at 62% of the visor height | `ink` at 75% |
| Stop zone (1R) | Height 12, directly below the entry line, from 53% of the visor width to 6 from its right edge | `danger` at 38% |
| Target zone (3R) | Height 36, directly above the entry line, same horizontal extent | `success` at 28% |
| Candles | Seven: bodies 8 wide, wicks 2 wide. Three range around the entry line, then four bullish candles climb; the last candle's high touches the target zone's top edge | bullish `success`, bearish `danger` |
| Badge divider | Hairline 1.5 high at y = 96 of the head, inset 14 | `border` |
| `47` | Plex Mono Regular 12, top left of the badge band | `muted` |
| `Ag` | Plex Mono Bold 30, right of centre in the badge band | `brand` |

Size tiers:

| Tier | Rendered size | Content |
|------|---------------|---------|
| L | 96 px and up | Everything above |
| M | 32 to 95 px | Three climbing candles; no `47` |
| S | Under 32 px (dashboard header, avatars) | Zones and entry line only; blank badge band |
| Text | Modes B, C and D | `[Ag]` |

- Horizontal lockup: mark, then the `Silverbot` wordmark in Plex Mono Bold; wordmark cap height is 40% of the mark height; the gap is 25% of the mark width.
- Stacked lockup: the horizontal lockup with the tagline "Discipline over id." below the wordmark in `muted`.
- Clear space: 25% of the mark width on every side.
- Versions: full colour dark, full colour light, and one colour (zones as 1 px outlines, candles solid).
- Misuse: never recolour the zones (target is always `success`, stop always `danger`), rotate, stretch, add glow or gradients, place the mark on busy imagery, or show it next to performance figures, win rates or result claims (§1.5).
- Mode A header (when built): the S tier as inline SVG in the HTML, not a fetched resource, so it needs no CSP change. No favicon.

### 2.5 Spacing, shape and touch targets

- Spacing: 4 px base; steps 4, 8, 12, 16, 24, 32.
- Lines: 1 px hairlines in `border`.
- Radius: panels 4, step cards and controls 3, page container 6; mode B is 0 everywhere.
- Elevation: none in the UI. One hairline shadow is allowed on brand surfaces only.
- Rows: data rows 24 px high; interactive rows 32 px.
- Touch targets: every interactive element at least 24 x 24 px (WCAG 2.2 AA, 2.5.8); standard control height 32 px; at least 8 px between adjacent targets.

## 3. Layout & Spatial System

### 3.1 Standard desktop layout

Top to bottom, on every page:

1. Header, 48 px: S mark, `Silverbot` wordmark, `status · read-only · 127.0.0.1`.
2. Top navigation bar: hidden while only one page exists.
3. Safety banner: always first in the content of a status page and pinned on scroll (CSS `position: sticky`; no script).
4. Content: 80 to 120 characters wide (`ch`), 24 px gutters.
5. Footer: `generated <time> · read-only; reading <root> · reload to refresh` (the footer as built, `monitoring/dashboard_server.py:64`).

Breakpoints: standard at 1280 px and up; compact at 960 to 1279 px (16 px gutters); stacked under 960 px (panels stack, 80 characters). Safety-first ordering applies to every status page. Mode A uses the same character grid (`ch` units) as mode B.

Status page order (mode A): header; safety banner; evidence ladder; Next strip; Readiness and Evidence Reports side by side; Risk budget full width; Open positions / recent trades and Alerts side by side. The §9.3 sources are unchanged; the ladder and the Next strip are new presentations of sources 2 and 6.

### 3.2 Reference layout

Target layout (silverbot-cr-002, Proposed); the built page follows silverbot-cr-001. A layout sketch, not a chart. Values are today's real state where one exists (report sizes and readiness flags read from `reports/`, both readiness reports generated on 2026-06-15 and therefore stale); every other panel shows its empty state.

```text
┌────────────────── Silverbot status · read-only · 127.0.0.1 ──────────────────┐
│ MODE PAPER   LIVE [ OFF ]   DEMO [ OFF ]   KILL [ WRN ] path not set         │
│ config read once at start; the bot itself is not running (G-3)               │
├──────────────────────────────────────────────────────────────────────────────┤
│ EVIDENCE LADDER                                                              │
│ 1 Backtest [ ERR ] 0 B NEXT   2 Out-of-sample [ ERR ] 0 B                    │
│ 3 Paper [ ERR ] 0 B   4 Demo [ WRN ] READY · stale   5 Live [ OFF ] blocked  │
│ Next: run a backtest (runbook-backtest.md steps 5 and 6)                     │
├──────────────────────────────────────┬───────────────────────────────────────┤
│ READINESS                            │ EVIDENCE REPORTS        size  state   │
├──────────────────────────────────────┼───────────────────────────────────────┤
│ live  [ ERR ] NOT READY · stale      │ backtest_report          0 B  [ ERR ] │
│       generated 2026-06-15 07:24 UTC │ oos_validation_report    0 B  [ ERR ] │
│ demo  [ WRN ] READY · stale          │ paper_trading_report     0 B  [ ERR ] │
│       generated 2026-06-15 14:31 UTC │ live_readiness_report 2229 B  [ OK ]  │
│                                      │ demo_readiness_report 2404 B  [ OK ]  │
├──────────────────────────────────────┴───────────────────────────────────────┤
│ RISK BUDGET   not available: risk_state table empty, no running bot (G-3)    │
├──────────────────────────────────────┬───────────────────────────────────────┤
│ OPEN POSITIONS / RECENT TRADES       │ ALERTS (logs/audit.jsonl)             │
├──────────────────────────────────────┼───────────────────────────────────────┤
│ none recorded (no paper run, G-3)    │ [ OK ] bot_started                    │
│                                      │ [ OK ] bot_stopped                    │
└──────────────────────────────────────┴───────────────────────────────────────┘
```

Narrower than 80 columns, the two-column rows stack (left above right). The banner never wraps away: if it must shorten, it keeps `MODE`, `LIVE` and `KILL`.

### 3.3 Terminal (mode B)

- Viewport: 80 columns x 24 rows minimum; the layout widens up to 120 x 40.
- Outlines use Unicode box drawing only: `─` U+2500, `│` U+2502, corners `┌ ┐ └ ┘`, joints `├ ┤ ┬ ┴ ┼`.
- Spacing is one or two spaces. No tabs and no variable spacing.
- Same panel order as §3.1, safety first: the mode and safety banner is always the top row and never scrolls away.
- The evidence ladder collapses to one line: `BT [ ERR ] ▸ OOS [ ERR ] ▸ PAPER [ ERR ] ▸ DEMO [ WRN ] ▸ LIVE [ OFF ] blocked`.

## 4. Core Component Specs

### 4.1 Status cell

A status cell is `glyph word detail`, for example `[ ERR ] NOT READY` or `[ WRN ] path not set`. The glyph sets the colour (§2.2); the word is mandatory; the detail is optional muted text. Missing data is `[ OFF ] not available:` followed by the reason and the gap ID when one exists.

### 4.2 Telegram alert (MarkdownV2)

Alerts use Telegram `parse_mode=MarkdownV2`. The layout, using an event the bot already emits (`TelegramAlerter.risk_rejection`, with a real rejection reason from `risk/engine.py` and the default symbol):

```text
*\[SILVERBOT \| RISK REJECTED\]*
`────────────────────────`
Risk engine held\.
*Symbol:* `BTCUSDT`
*Reason:* Max daily loss limit reached
*Mode:* `paper`
`────────────────────────`
_Simulated only; no real order exists_
```

Rules:

- **Header.** Line 1 is the bold, escaped `\[SILVERBOT \| ` anchor followed by the event name in upper case and `\]`. Body lines follow the voice of §1.4 (for example `Risk engine held\.`). Fields are `*Label:* value`; identifiers and numbers go in `` `code` ``.
- **Escaping.** Every dynamic value passes one sanitizer before insertion. Outside code spans it escapes `\` first, then all 18 reserved characters `_ * [ ] ( ) ~ ` > # + - = | { } . !` with a backslash. Inside a code span it escapes only `` ` `` and `\`. A message that fails escaping is not sent; the failure is logged and the alert loop continues.
- **Length.** The rendered message is at most 400 characters so it fits one phone screen. Dynamic fields are truncated before escaping (never inside an escape sequence) and end with `…`. Telegram's own limit is 4096.
- **Content.** Only events the alerter defines (bot started or stopped, signal detected or rejected, risk rejection, ML approval or rejection, paper trade opened or closed, daily report, error, kill switch active). Paper events say they are simulated. No secret, token or account identifier ever appears.
- **Status today.** `TelegramAlerter` formats `[title] message` as plain text and has no network transport (G-15). This layout, including the `SILVERBOT` anchor and the voice, applies when the transport is built (deferred in `silverbot-cr-002`).

### 4.3 Audit log line (JSON lines)

The audit log is the source of record for mode C and the alerts panel. Built format, one object per line, written by `StructuredAuditLogger` with `json.dumps(..., sort_keys=True)`. A line of the shape found in `logs/audit.jsonl`:

```json
{"context": {"mode": "paper"}, "created_at": "2026-06-14T17:32:06.316862+00:00", "event_type": "bot_stopped", "level": "INFO", "message": "Silver bot startup command completed"}
```

- Keys are exactly `context`, `created_at`, `event_type`, `level`, `message`. `context` passes through `redact_secrets` before writing.
- Numbers are raw JSON numbers, never strings and never with thousands separators, so the file pipes cleanly into `jq`.
- The application log (`utils/logging.py`) is plain text today; a structured application log is tracked as G-16 and would reuse these keys.
- Only the `message` text follows the voice (§1.4); the format is unchanged.

### 4.4 Report and file rows

Every evidence or readiness file is a row: name, size in bytes, state. A 0-byte or non-JSON file is `[ ERR ]` and no metric from it is shown (G-1). Readiness rows add `generated_at` so staleness is visible. A readiness report is `[ WRN ] stale` when it is READY and either stale condition of §2.2 holds; a NOT READY report keeps `[ ERR ]` and adds `stale` to its detail.

### 4.5 Interface Foundations

Five groups of parts from which every future surface is assembled. They are specified, not built: the built dashboard still follows `silverbot-cr-001`. The groups reuse §4.1 to §4.4 where noted.

#### 4.5.1 Geometry and Rhythm

The tokens of §2: colour (§2.1, §2.2), type (§2.3), spacing, lines, radius, elevation, row heights and touch targets (§2.5).

#### 4.5.2 Actions, Navigation, Inputs and Touch Targets

| Component | Variants | Allowed use |
|-----------|----------|-------------|
| Link | inline, standalone | Mode A now (in-page anchors and GET pages) |
| Top navigation bar | tabs with an active marker (`accent` underline plus bold; never colour alone) | Each new page needs a Change Record (§9.6) |
| Section anchor nav | in-page jump list | Mode A now |
| Button | `secondary` (hairline), `next` (accent outline), `ghost`; sizes 24 and 32 | Change Record required |
| Text field, select, checkbox, segmented control | default, focus, disabled, read-only | Change Record required; read-only filtering only |

Interaction states for all of the above: default, hover, focus-visible (2 px `accent` ring, 2 px offset), active, disabled. The system has no filled danger button and no execute or confirm-order button.

Hard rule, repeated in §7: no action or input component may place or cancel an order, edit configuration, change the kill switch or change a gate, on any surface.

#### 4.5.3 Surfaces, Cards and Rows

- Levels: `canvas` (page), `surface` (panels and cards), `border` hairline. No shadows.
- Panel: `default` and `next` (accent outline) variants; a `Label` title, then the body.
- Cards: the ladder step card and, on brand surfaces only, a lockup card. No metric card.
- Rows: data row, key-value row, report row (name, size in bytes, state; §4.4), readiness row (adds `generated_at`), alert row (an audit `event_type` with its glyph; §4.3), table header row.

#### 4.5.4 Standard Desktop Layout

The app shell and breakpoints of §3.1, as a Figma template and as this text.

#### 4.5.5 Feedback, Overlays and System States

**Inline feedback**

- Status cell: `glyph word detail`, variants OK, WRN, ERR, OFF (§4.1).
- Safety banner: MODE, LIVE, DEMO, KILL; first on every status page; fits 80 characters.
- Evidence ladder (rules below) and Next strip.

**Evidence ladder rules**

| Step | Source | State |
|------|--------|-------|
| 1 Backtest | `reports/backtest_report.json` | non-empty JSON `[ OK ]`; 0 B or not JSON `[ ERR ]`; missing `[ OFF ]` |
| 2 Out-of-sample | `reports/out_of_sample_validation_report.json` | as step 1 |
| 3 Paper | `reports/paper_trading_report.json` | as step 1 |
| 4 Demo | `reports/demo_readiness_report.json` (`ready`, `generated_at`) | `ready` true and fresh `[ OK ] READY`; `ready` true and stale (older than 24 h, or an evidence report modified after `generated_at`) `[ WRN ] READY · stale`; `ready` false `[ ERR ] NOT READY`; missing `[ OFF ]`; unreadable `[ ERR ] unreadable` |
| 5 Live | none | always `[ OFF ] blocked (PRD-F12)`, whatever the live readiness report says |

- NEXT is the first of steps 1 to 4 whose state is not `[ OK ]`. Its card takes the `next` variant (accent outline and a `NEXT` label).
- Today's ladder: Backtest `[ ERR ] 0 B` (NEXT), Out-of-sample `[ ERR ] 0 B`, Paper `[ ERR ] 0 B`, Demo `[ WRN ] READY · stale`, Live `[ OFF ] blocked`.

**Next strip text (fixed mapping)**

| First step not OK | Text |
|-------------------|------|
| 1 or 2 | `Next: run a backtest (runbook-backtest.md steps 5 and 6)` (one backtest run writes both reports; the command needs the backtest environment of step 5, so the strip points at the runbook) |
| 3 | `Next: paper trading (not available yet, G-3)` |
| 4 | `Next: refresh demo readiness  python -m silver_bot.demo_readiness (runbook-demo-testnet.md steps 3 and 4)` (its default output is `reports/demo_readiness_report.json`, the file step 4 reads) |
| none | `All evidence gates pass. Live trading stays blocked (PRD-F12).` |

The strip never suggests editing configuration, enabling live trading or removing the kill switch.

**Source states** (every panel row): `ok`; `empty` (0 B, `[ ERR ]`); `unavailable` (missing, `[ OFF ]`); `unreadable` (bad JSON or permission denied, `[ ERR ]`); `stale` (`[ WRN ]`, readiness only, either stale condition of §2.2; an `[ ERR ]` row keeps `[ ERR ]` and adds `stale` to its detail). Each shows the reason and, where one exists, the next step.

**Page states:** `nominal`; `degraded` (at least one source unreadable; one summary line under the banner); a branded `404` page in the same shell (header, message, link to `/`, no data). There is no 500 page, because collector failures are isolated per panel. Error pages carry no status data, so they carry no banner.

**Overlays:** native disclosure (`<details>`) and native tooltip (`title`) are allowed in mode A now. Toast and dialog are specified for the future: they need a script and a Change Record, have no motion, and a dialog is never used to confirm a risky action (the system has none). No loading spinners: pages are server-rendered and motion stays none (§5).

## 5. Motion

None. No animation, transitions, spinners or blinking. Mode B redraws in place on a fixed interval; mode A refreshes only when the operator reloads the page.

## 6. Accessibility

- State is never carried by colour alone: glyph, word and colour together (§2.2).
- Mode B prints plain text when stdout is not a terminal or `NO_COLOR` is set; the glyphs and words keep their meaning without colour.
- `ink`, `muted` and every semantic colour meet WCAG AA contrast for normal text (at least 4.5:1) on `canvas` and `surface` in both themes (§2.1, §2.2); `border` is for lines only.
- Mode A uses semantic HTML tables with header cells, so a screen reader reads each panel as a table.
- Every interactive target is at least 24 x 24 px with at least 8 px between adjacent targets (§2.5).
- Every interactive element shows a focus-visible ring (2 px `accent`, 2 px offset).
- The active navigation tab is marked by underline and weight, not colour alone.

## 7. Quality Gate

A UI or alert change passes only if:

- [ ] Every value shown comes from a source named in §9.3 or an alerter event; nothing is estimated or sampled.
- [ ] Every coloured state has its glyph and word; the view reads correctly with `NO_COLOR`.
- [ ] The safety banner (mode, live, demo, kill switch) is the first content on every status page and fits 80 columns.
- [ ] 0-byte evidence files show `[ ERR ]` and no metric.
- [ ] No secret, API key or Telegram token is read for display or rendered.
- [ ] Telegram messages are escaped by the shared sanitizer, are at most 400 characters and have tests for each reserved character.
- [ ] Mode A binds to `127.0.0.1`, answers GET only and loads nothing from another host.
- [ ] Only the standard library is used (`dependencies = []`).
- [ ] The Live ladder step is always `[ OFF ] blocked (PRD-F12)`. NEXT is the first of steps 1 to 4 that is not OK. The Next strip uses only the fixed mapping of §4.5.5 and never suggests a configuration, live-trading or kill-switch action.
- [ ] `accent` marks only the next step and links; `brand` only the mark and wordmark.
- [ ] Fonts are served only from the dashboard's own `127.0.0.1` server. The only CSP change is `font-src 'self'`.
- [ ] No action or input component is wired to orders, configuration, the kill switch or a gate; any control needs a Change Record.
- [ ] Interactive targets are at least 24 x 24 px; a readiness report older than 24 hours shows `[ WRN ] stale`.
- [ ] DSD token values match the Figma variables in SILVR.

## 8. Materialization

Sections 0 and 1 of this document are materialized to `BRAND.md` and sections 2 to 7 to `DESIGN.md` at the repository root by `python tools/materialize_docs.py` (`--check` verifies). Edit this document, never the generated files. The UI builder agent `psl-purist` (SAD-B1 in [sad-silverbot.md](sad-silverbot.md)) builds against sections 2 to 7 and §9. The SILVR Figma file (pages Branding and Foundation Components) mirrors sections 0 to 7; if they disagree, this document wins and the Figma file is corrected.

## 9. Recommended UI (mode A approved and built; mode B proposal)

### 9.1 Why

The owner operates the bot by reading files, not by clicking. The core flows in [prd-silverbot.md](prd-silverbot.md) section 5.3 are: run a readiness checker and read its JSON (flow 4), create or delete the kill-switch file (flow 5), and review evidence reports and logs after a run (flows 1 and 2). Each is a check of safety state or evidence. Today that means opening several files by hand, and the one failure that is easy to miss is an evidence report that is present but 0 bytes (G-1, D-86, H-2).

### 9.2 Recommended form

A local, read-only status dashboard served on localhost (surface mode A, §1.2), with a terminal status view (mode B) showing the same panels. Both follow sections 2 to 7. It has no order buttons and no write path to configuration, the kill-switch file or the database. Rationale: the owner mostly checks safety state and evidence, and any control surface would be a new path around the live-trading block ([sdd-silverbot.md](sdd-silverbot.md) section 5.1). The kill switch stays a file the owner creates or deletes ([ops-silverbot.md](ops-silverbot.md) section 4.1).

### 9.3 Panels

Every panel reads one named source. The "Status today" column says whether that source holds data or is produced at all.

| # | Panel | Data source (as it exists today) | Status today |
|---|---|---|---|
| 1 | Mode & Safety banner: mode, LIVE / PAPER / DEMO flags, kill switch | Settings loaded by `silver_bot.config` from the environment and `.env` (`TRADING_MODE`, `MODE`, `LIVE_TRADING`, `PAPER_TRADING`, `DEMO_TRADING`); kill-switch state from the file at `KILL_SWITCH_PATH` (fails closed: a file, a directory or an unreadable path counts as active; an automatic trip writes a JSON `reason` and `tripped_at` to show) | Readable now, but only as a point-in-time load by the dashboard process. The bot itself exits after startup (G-3), so the banner shows configuration, not the state of a running bot. The kill switch has effect only if the engine is built with the path, which only `build_risk_engine` does (G-6) |
| 2 | Readiness checklist | `reports/live_readiness_report.json` and `reports/demo_readiness_report.json` (`ready`, `generated_at`, `checks[]` with `name`, `passed`, `reason`) | Both files exist. Written on demand only; each shows its `generated_at` so staleness is visible (the demo report dates from 2026-06-15). Advisory: nothing in the bot reads them (D-10). Since `88220e6` the report checks fail empty or non-JSON evidence files (H-2 fixed), so a fresh live report shows those three checks failing |
| 3 | Today's risk budget used | The single-row SQLite table `risk_state` (`current_day`, `daily_realized_pnl`, `consecutive_losses`, `trades_today`, `open_positions`, `updated_at`; [sdd-silverbot.md](sdd-silverbot.md) section 3.2), written only by an engine built with a state store ([rfc-silverbot-risk-kill-switch.md](rfc-silverbot-risk-kill-switch.md) section 3.7) | Source exists since `2d7f713` but is empty today: no running bot builds a store-backed engine (G-3, G-7 partial). A panel must read the row and never write it |
| 4 | Open positions and recent trades | SQLite `data/silver_bot.sqlite3`: `paper_trades` for closed trades (its `exit_time` and `exit_price` are `NOT NULL`, so open positions are not stored there) and `paper_events` for lifecycle rows such as `paper_trade_opened`; trade journal CSV from `monitoring/reports.py` | Tables exist but are empty because no entrypoint runs a paper session (G-3). The journal and dashboard JSON builders (`monitoring/dashboard.py`) have no caller (G-16), so there is no journal file to read yet. Open positions have no direct source |
| 5 | Alerts feed | `logs/audit.jsonl` (one JSON object per line: `created_at`, `level`, `event_type`, `message`, `context`) filtered to `risk_rejected`, `kill_switch_active`, `signal_rejected` and `error` | File exists and is written by every run, but holds only `bot_started` and `bot_stopped` today. `error` is never emitted (D-47). Telegram alerts are not a source: the client is in-memory (G-15) |
| 6 | Evidence reports | `reports/backtest_report.json`, `reports/out_of_sample_validation_report.json`, `reports/paper_trading_report.json`: file size in bytes and modified timestamp, plus the same two fields for the two readiness reports | Files exist. Three of the five are 0 bytes, so the panel flags them as empty (G-1, D-86, H-2). No strategy performance figure is shown until a report is non-empty |

Panels 3 and 4 cannot be built truthfully before the unwired pieces (entrypoint, report scheduler, persisted risk state) exist. That is a dependency of the proposal, not a new requirement here.

### 9.4 Wireframe

The reference layout is in §3.2; it uses these six panels in this order, with the safety banner on top.

### 9.5 Explicit non-goals

- No order entry, no close-position button, no kill-switch toggle.
- No configuration editing and no write access to `.env`, `config.yaml`, the SQLite file or any report.
- No remote exposure: bind to `127.0.0.1` only, with no port published by Docker Compose.
- No display of secrets: the dashboard must not read API keys or the Telegram token, and must reuse the audit log's redaction.
- No performance claims while the evidence reports are empty.

### 9.6 Next step

If the owner wants this dashboard, open a Change Record that adds a PRD feature for it, with acceptance criteria and a decision on persisting risk state. Only then do sections 0 to 8 begin. Until that record is approved, this section stays a proposal. Mode A was approved by [cr-silverbot-operator-dashboard.md](cr-silverbot-operator-dashboard.md) on 2026-10-09. The reskin of mode A is proposed in [cr-silverbot-dashboard-reskin.md](cr-silverbot-dashboard-reskin.md).

## Self-Check

- [x] Status line reads `Draft (Silverbot brand and design system specified; mode A built per silverbot-cr-001; reskin proposed in silverbot-cr-002)` and the banner states that mode A is built, that the reskin is not built, and that mode B or any other surface still needs its own Change Record (§9.6).
- [x] Sections 0 to 7 hold the Silverbot brand (§0, §1) and the Sterling design system (§2 to §7); section 8 names the materialized `BRAND.md` (sections 0 and 1) and `DESIGN.md` (sections 2 to 7) and the SILVR Figma pages that mirror them.
- [x] Sterling tokens, the IBM Plex Mono fonts, the evidence ladder, the Next strip and the §3.2 layout are labelled as target (`silverbot-cr-002`, Proposed); none is described as built.
- [x] The §3.2 layout shows only real values (report sizes, readiness flags) or an explicit empty state; no invented metric, position or PnL.
- [x] The Next strip texts in §4.5.5 point at runbooks and at `python -m silver_bot.demo_readiness`; none suggests editing configuration, enabling live trading or removing the kill switch.
- [x] The §4.2 Telegram example is valid MarkdownV2, uses an event and a rejection reason that exist in the code, and is under 400 characters; it is marked as applying when the transport is built.
- [x] The §4.3 audit line matches the keys written by `monitoring/audit.py` and is copied from `logs/audit.jsonl`.
- [x] Section 9 is labelled as the approved scope of mode A and a proposal for mode B, and states that the proposal adds no requirement.
- [x] Every panel in §9.3 names a concrete file or SQLite table and says where that source is empty or unproduced.
- [x] The evidence-reports panel shows byte size and timestamp so 0-byte reports are visible.
- [x] No order entry, config editing or remote exposure appears in the proposal (§9.5) or in the interface foundations (§4.5.2).
- [x] No em dash appears in this document.
- [x] Links point only to existing suite files.
