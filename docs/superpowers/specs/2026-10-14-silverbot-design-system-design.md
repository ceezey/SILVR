# Silverbot Design System (DESIGN.md) and Figma Foundations: Design Spec

**Date:** 2026-10-14
**Status:** Approved design; spec awaiting owner review
**Owner:** Cian Jake Francisco (ceezey)
**Branch:** `dev` (base commit `3881f2f`)
**Baseline:** at `3881f2f`, `python tools/materialize_docs.py --check` reports no changes and `python -m pytest -q` passes 271 tests
**Depends on:** [2026-10-14-silverbot-brand-design.md](2026-10-14-silverbot-brand-design.md) (sub-project 1, brand; DSD sections 0 and 1)
**Design file:** [SILVR](https://www.figma.com/design/g1n3J4j2L1iPrbdjiOS30e/SILVR) (file key `g1n3J4j2L1iPrbdjiOS30e`)

---

## 1. Intent

### What the owner asked for

- Design sub-project 2: the design system, written to DSD sections 2 to 7 and materialized to `DESIGN.md`.
- Decide the palette and the components in Figma, and build an official **Branding** page and a **Foundation Components** page there, so every future feature is assembled from the same parts and the UI stays consistent across features.
- Run the docs work and the Figma work as a parallel workflow.
- Cover the interface foundations: geometry and rhythm; actions, navigation, inputs and touch targets; surfaces, cards and rows; a standard desktop layout; feedback, overlays and system states.

### Scope

Sub-project **2a**: DSD sections 2 to 7 and 8, the Figma Branding and Foundation Components pages, and the doc bookkeeping. The brand spec (sub-project 1) is applied in the same docs track, so DSD sections 0 to 7 land as one consistent edit.

Out of scope (sub-project **2b**, its own Change Record `silverbot-cr-002`): every code change to the dashboard and Telegram text (section 8 lists them), and the SAD-B1 (`psl-purist`) card changes that go with them. Sub-project 3 (README header, social preview, exported mark files) and the docs rename pass ("Silver Bot" to "Silverbot") are also out of scope.

### Decisions made during brainstorming

| # | Question | Decision |
|---|----------|----------|
| DS-1 | Themes | Dark first, plus a designed light theme. |
| DS-2 | Palette | Direction A, **Sterling**: graphite and true silver, one steel-blue accent. |
| DS-3 | Typeface | **IBM Plex Mono**, monospace only. |
| DS-4 | Font delivery | Vendor Plex Mono Regular and Bold (woff2, SIL OFL) and serve them from the dashboard's own `127.0.0.1` server (built in 2b). |
| DS-5 | Dashboard structure | **Instrument panels**: surface panels, 1 px hairlines, 4 px radius. Mode B keeps box drawing. |
| DS-6 | Evidence ladder | Yes, as its own row **under the safety banner**. |
| DS-7 | Theme per surface | Dashboard and terminal are dark only; light is for README, slides, social and Figma. |
| DS-8 | Interface foundations | Five groups (section 5), with an "allowed use" rule on every action and input component. |
| DS-9 | Staleness | A readiness report older than **24 hours** is `[ WRN ] stale`. |
| DS-10 | Figma | Pages **Branding** and **Foundation Components** in SILVR; the DSD wins on any conflict. |
| DS-11 | Execution | Parallel workflow: a docs track and a Figma track (section 9). |

### Invariants

- No bot code changes in 2a. No risk, kill-switch, readiness or live gate is touched. PRD-F12 stays `Planned, blocked`.
- Every operator surface stays read-only. No component in this system may place or cancel an order, edit configuration, change the kill switch or change a gate, on any surface. Mode A stays GET-only and bound to `127.0.0.1`.
- No state is shown by colour alone. No estimated or sample value replaces missing data. No performance claim without a non-empty evidence file.
- No em dashes in the new DSD text, `BRAND.md` or `DESIGN.md`.
- Nothing is pushed to a remote.

## 2. Tokens (DSD §2.1, §2.2, §2.3, new §2.5)

### 2.1 Colour (Sterling)

All text tokens meet WCAG AA (at least 4.5:1) on both `canvas` and `surface` in their theme; measured values are in brackets (lowest of the two backgrounds). `border` is for lines only.

| Token | Dark | Light | ANSI (mode B) | Use |
|-------|------|-------|---------------|-----|
| `canvas` | `#0B0D10` | `#F6F7F9` | 0 | Page background |
| `surface` | `#13161B` | `#FFFFFF` | 0 | Panels, header, step cards |
| `border` | `#2A2F38` | `#D9DDE3` | 8 | Hairlines and rules, never text |
| `ink` | `#E8EAED` (15.0) | `#14171C` (16.8) | 15 | Values and data rows |
| `muted` | `#9AA1AC` (7.0) | `#5B6370` (5.7) | 7 | Labels, timestamps, the `[ OFF ]` state |
| `brand` | `#C3C9D2` (10.9) | `#646D79` (4.9) | 7, bold | The mark and the wordmark only |
| `accent` | `#7AA2F7` (7.2) | `#2F5BD3` (5.5) | 12 | The next step and links only; never a state |
| `success` | `#3FB68B` (7.1) | `#1E7F5A` (4.6) | 2 | `[ OK ]` |
| `warning` | `#E3B341` (9.3) | `#8A5D00` (5.4) | 3 | `[ WRN ]` |
| `danger` | `#F0616D` (5.7) | `#C23142` (5.1) | 1 | `[ ERR ]` |

The §2.2 glyph table (`[ OK ]`, `[ WRN ]`, `[ ERR ]`, `[ OFF ]`) and its meanings stay. The `warning` meaning gains "readiness report older than 24 hours" (DS-9).

### 2.2 Type

IBM Plex Mono only. Font stack: `"IBM Plex Mono", ui-monospace, "Cascadia Mono", Menlo, Consolas, monospace`. Mode A serves Regular and Bold as woff2 from its own server once `silverbot-cr-002` is built; until then it renders with the same stack and the system fallback. Brand surfaces (Figma, README images, slides) use Plex Mono directly.

| Style | Size / weight | Use |
|-------|---------------|-----|
| `Label` | 10 / Bold, upper case | Panel titles, step labels |
| `Detail` | 11 / Regular | Timestamps, report rows, secondary lines |
| `Data` | 12 / Regular | Banner, status cells, Next strip, data rows |
| `Wordmark` | 14 / Bold, `brand` | Dashboard header |
| `Showcase 18`, `Showcase 22`, `Showcase 40` | Bold | Tagline, headings, hero wordmark (brand surfaces) |

Number rules stay: shown exactly as stored, `.` as the decimal mark, no thousands separator, no italics in data rows.

### 2.3 Spacing, shape and touch targets (new §2.5)

- Spacing: 4 px base; steps 4, 8, 12, 16, 24, 32.
- Lines: 1 px hairlines in `border`.
- Radius: panels 4, step cards and controls 3, page container 6; mode B is 0 everywhere.
- Elevation: none in the UI. One hairline shadow is allowed on brand surfaces only.
- Rows: data rows 24 px high; interactive rows 32 px.
- Touch targets: every interactive element at least 24 x 24 px (WCAG 2.2 AA, 2.5.8); standard control height 32 px; at least 8 px between adjacent targets.

## 3. The mark (new DSD §2.4)

Concept from the brand spec (BD-10, BD-11): a bot head whose visor shows a long position at 1:3 risk to reward reaching its target, above a periodic-table badge.

### 3.1 Construction (160 x 160 grid)

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

### 3.2 Size tiers

| Tier | Rendered size | Content |
|------|---------------|---------|
| L | 96 px and up | Everything in 3.1 |
| M | 32 to 95 px | Three climbing candles; no `47` |
| S | Under 32 px (dashboard header, avatars) | Zones and entry line only; blank badge band |
| Text | Modes B, C and D | `[Ag]` |

### 3.3 Lockups, clear space, versions and misuse

- Horizontal lockup: mark, then the `Silverbot` wordmark in Plex Mono Bold; wordmark cap height is 40% of the mark height; gap is 25% of the mark width.
- Stacked lockup: the horizontal lockup with the tagline "Discipline over id." below the wordmark in `muted`.
- Clear space: 25% of the mark width on every side.
- Versions: full colour dark, full colour light, and one colour (zones as 1 px outlines, candles solid).
- Misuse: never recolour the zones (target is always `success`, stop always `danger`), rotate, stretch, add glow or gradients, place on busy imagery, or show the mark next to performance figures, win rates or result claims.
- Mode A header: the S tier as inline SVG in the HTML (not a fetched resource, so it needs no CSP change). No favicon.

## 4. Layout (DSD §3)

### 4.1 Standard desktop layout (app shell)

Top to bottom, on every page:

1. Header, 48 px: S mark, `Silverbot` wordmark, `status · read-only · 127.0.0.1`.
2. Top navigation bar: hidden while only one page exists.
3. Safety banner: always first in the content and pinned on scroll (CSS `position: sticky`; no script).
4. Content: 80 to 120 characters wide (`ch`), 24 px gutters.
5. Footer: `generated <time> · read-only; reading <root> · reload to refresh` (the footer as built).

Breakpoints: standard at 1280 px and up; compact at 960 to 1279 px (16 px gutters); stacked under 960 px (panels stack, 80 characters). Safety-first ordering applies to every page.

### 4.2 Status page order (mode A)

Header; safety banner; evidence ladder; Next strip; Readiness and Evidence Reports side by side; Risk budget full width; Open positions / recent trades and Alerts side by side. The §9.3 sources are unchanged; the ladder and the Next strip are new presentations of sources 2 and 6.

Mode B keeps the same order with box drawing, and the ladder collapses to one line: `BT [ ERR ] ▸ OOS [ ERR ] ▸ PAPER [ ERR ] ▸ DEMO [ WRN ] ▸ LIVE [ OFF ] blocked`.

The §3.2 reference layout is redrawn in this order with today's real values: three evidence reports at 0 B, live readiness `NOT READY` and demo readiness `READY`, both generated on 2026-06-15 and therefore stale.

## 5. Interface Foundations (DSD §4)

DSD §4.1 to §4.4 keep their numbers, so existing references (including the SAD-B1 card's "DSD section 4.2") stay valid: §4.1 status cell, §4.2 Telegram alert (restyled per 5.6), §4.3 audit log line, §4.4 report and file rows. A new **§4.5 Interface Foundations** holds the five groups below as §4.5.1 to §4.5.5, and points back to §4.1 to §4.4 where a group reuses them.

### 5.1 Geometry and Rhythm

The tokens of section 2 of this spec: colour, type, spacing, radius, hairlines, row heights and touch targets.

### 5.2 Actions, Navigation, Inputs and Touch Targets

| Component | Variants | Allowed use |
|-----------|----------|-------------|
| Link | inline, standalone | Mode A now (in-page anchors and GET pages) |
| Top navigation bar | tabs with an active marker (`accent` underline plus bold; never colour alone) | Each new page needs a Change Record (§9.6) |
| Section anchor nav | in-page jump list | Mode A now |
| Button | `secondary` (hairline), `next` (accent outline), `ghost`; sizes 24 and 32 | Change Record required |
| Text field, select, checkbox, segmented control | default, focus, disabled, read-only | Change Record required; read-only filtering only |

Interaction states for all of the above: default, hover, focus-visible (2 px `accent` ring, 2 px offset), active, disabled. The system has no filled danger button and no execute or confirm-order button.

Hard rule, repeated in the §7 gate: no action or input component may place or cancel an order, edit configuration, change the kill switch or change a gate, on any surface.

### 5.3 Surfaces, Cards and Rows

- Levels: `canvas` (page), `surface` (panels and cards), `border` hairline. No shadows.
- Panel: `default` and `next` (accent outline) variants; a `Label` title, then the body.
- Cards: the ladder step card and, on brand surfaces only, a lockup card. No metric card.
- Rows: data row, key-value row, report row (name, size in bytes, state), readiness row (adds `generated_at`), alert row (an audit `event_type` with its glyph), table header row.

### 5.4 Standard Desktop Layout

The app shell and breakpoints of section 4.1, as a Figma template and as DSD text.

### 5.5 Feedback, Overlays and System States

**Inline feedback**

- Status cell: `glyph word detail`, variants OK, WRN, ERR, OFF (today's §4.1).
- Safety banner: MODE, LIVE, DEMO, KILL; first on every page; fits 80 characters.
- Evidence ladder (rules below) and Next strip.

**Evidence ladder rules**

| Step | Source | State |
|------|--------|-------|
| 1 Backtest | `reports/backtest_report.json` | non-empty JSON `[ OK ]`; 0 B or not JSON `[ ERR ]`; missing `[ OFF ]` |
| 2 Out-of-sample | `reports/out_of_sample_validation_report.json` | as step 1 |
| 3 Paper | `reports/paper_trading_report.json` | as step 1 |
| 4 Demo | `reports/demo_readiness_report.json` (`ready`, `generated_at`) | `ready` true and fresh `[ OK ] READY`; `ready` true and older than 24 h `[ WRN ] READY · stale`; `ready` false `[ ERR ] NOT READY`; missing `[ OFF ]`; unreadable `[ ERR ] unreadable` |
| 5 Live | none | always `[ OFF ] blocked (PRD-F12)`, whatever the live readiness report says |

- NEXT is the first of steps 1 to 4 whose state is not `[ OK ]`. Its card takes the `next` variant (accent outline and a `NEXT` label).
- Today's ladder: Backtest `[ ERR ] 0 B` (NEXT), Out-of-sample `[ ERR ] 0 B`, Paper `[ ERR ] 0 B`, Demo `[ WRN ] READY · stale`, Live `[ OFF ] blocked`.

**Next strip text (fixed mapping)**

| First step not OK | Text |
|-------------------|------|
| 1 or 2 | `Next: run a backtest  python -m silver_bot --candles data/candles` (one backtest run writes both reports) |
| 3 | `Next: paper trading (not available yet, G-3)` |
| 4 | `Next: run the demo readiness checker (runbook-demo-testnet.md step 4)` |
| none | `All evidence gates pass. Live trading stays blocked (PRD-F12).` |

The strip never suggests editing configuration, enabling live trading or removing the kill switch.

**Source states** (every panel row): `ok`; `empty` (0 B, `[ ERR ]`); `unavailable` (missing, `[ OFF ]`); `unreadable` (bad JSON or permission denied, `[ ERR ]`); `stale` (`[ WRN ]`, readiness only, older than 24 h; an `[ ERR ]` row keeps `[ ERR ]` and adds `stale` to its detail). Each shows the reason and, where one exists, the next step.

**Page states:** `nominal`; `degraded` (at least one source unreadable; one summary line under the banner); branded `404` and `500` pages in the same shell.

**Overlays:** native disclosure (`<details>`) and native tooltip (`title`) are allowed in mode A now. Toast and dialog are specified for the future: they need a script and a Change Record, have no motion, and a dialog is never used to confirm a risky action (the system has none). No loading spinners: pages are server-rendered and motion stays none (§5).

### 5.6 Text surfaces

- Telegram alert (§4.2 today): the anchor becomes `*\[SILVERBOT \| EVENT\]*`; message text follows the brand voice (DSD §1.4), for example `Risk engine held\.`; the escaping, 400-character and content rules are unchanged.
- Audit log line (§4.3 today): unchanged; only the `message` text follows the voice.

## 6. Motion and accessibility (DSD §5, §6)

- Motion: none, unchanged.
- Accessibility additions: the contrast table in section 2.1 of this spec, both themes; touch targets (section 2.3); focus-visible ring on every interactive element; the active navigation tab marked by underline and weight, not colour alone. Existing rules stay (glyph, word and colour together; `NO_COLOR`; semantic tables).

## 7. Quality gate additions (DSD §7)

The existing eight items stay. Added:

- [ ] The safety banner is the first content on every page.
- [ ] The Live ladder step is always `[ OFF ] blocked (PRD-F12)`. NEXT is the first of steps 1 to 4 that is not OK. The Next strip uses only the fixed mapping and never suggests a configuration, live-trading or kill-switch action.
- [ ] `accent` marks only the next step and links; `brand` only the mark and wordmark.
- [ ] Fonts are served only from the dashboard's own `127.0.0.1` server. The only CSP change is `font-src 'self'`.
- [ ] No action or input component is wired to orders, configuration, the kill switch or a gate; any control needs a Change Record.
- [ ] Interactive targets are at least 24 x 24 px; a readiness report older than 24 hours shows `[ WRN ] stale`.
- [ ] DSD token values match the Figma variables in SILVR.

## 8. Code changes deferred to sub-project 2b (`silverbot-cr-002`)

Listed so the DSD can describe the target honestly; none is built in 2a.

- `monitoring/dashboard_server.py`: Sterling tokens as CSS custom properties, Plex Mono stack, instrument-panel CSS, header with the inline S mark, sticky banner, branded 404 and 500 pages.
- Font serving: two GET-only routes for the vendored woff2 files, package data, the OFL licence file, and CSP `default-src 'none'; style-src 'unsafe-inline'; font-src 'self'`.
- `monitoring/status.py`: ladder states, NEXT, Next strip text and the 24-hour stale rule, all from existing sources.
- Telegram text: the `SILVERBOT` anchor and the voice.
- SAD-B1 (`psl-purist`) card: today it says to load no web fonts and pins the current CSP (`docs/sad-silverbot.md:296`, `.claude/agents/psl-purist.md:20`); it is updated with the Change Record.
- DSD §9.3 and §9.6, PRD-F13 acceptance criteria, QAD tests and the §3.2 layout's built status, reconciled when the code lands.

## 9. Figma deliverables (SILVR)

### 9.1 Pages

| Page | Contents |
|------|----------|
| **Branding** | Cover (stacked lockup and tagline); mark construction on the 160 grid (L); size tiers L, M, S and Text; horizontal and stacked lockups; clear space; dark, light and one-colour versions; misuse examples; Sterling palette in both themes with contrast values; Plex Mono specimen and type scale; the voice table (DSD §1.4) |
| **Foundation Components** | Variables and text styles (9.2); component sets grouped under five section headings matching section 5; the Standard Desktop Layout template; a reference Status page assembled only from instances, showing today's real values (section 4.2) |
| Silverbot · Exploration | Kept as the decision record (palette directions, type specimens, ladder options) |
| Page 1 | Renamed **Archive · superseded draft**; the old "Silver-bot trading terminal" frame is kept, not deleted |

### 9.2 Variables and styles

- Collection `Silverbot/Color`, modes `Dark` and `Light`, the ten tokens of section 2.1, scoped (fills for `canvas`, `surface`, `border`; text fills for `ink`, `muted`, `brand`, `accent`, `success`, `warning`, `danger`; strokes for `border` and `accent`).
- Collection `Silverbot/Space`: 4, 8, 12, 16, 24, 32 (gap and padding scopes).
- Collection `Silverbot/Radius`: 0, 3, 4, 6 (corner radius scope).
- Text styles: `Label`, `Detail`, `Data`, `Wordmark`, `Showcase 18`, `Showcase 22`, `Showcase 40` in IBM Plex Mono.
- Every component binds colours, spacing and radii to these variables; no hard-coded values on the Foundation Components page.

### 9.3 Component sets

Mark (tier L, M, S; theme via variable mode), lockup (horizontal, stacked), header, top navigation bar and tab, section anchor nav, link, button (variant x size x state), text field, select, checkbox, segmented control, panel (`default`, `next`), ladder step (`ok`, `err`, `wrn`, `off`, `blocked`; `next` true or false), evidence ladder, Next strip, status cell (OK, WRN, ERR, OFF), safety banner, data row, key-value row, report row, readiness row, alert row, table header row, empty state, degraded summary line, disclosure, tooltip, toast and dialog (each labelled "future, Change Record required"), Telegram alert preview, 404 and 500 page templates.

## 10. Docs changes (DESIGN.md track)

| File | Change |
|------|--------|
| [dsd-silverbot.md](../../dsd-silverbot.md) | Apply the brand spec (sections 0 and 1) and this spec (sections 2 to 7). Section 8 names the Figma pages and states that the DSD wins on conflict. Header: **Design file** link to SILVR; **Last updated** 2026-10-14; banner notes that the dashboard reskin is specified and not built (`silverbot-cr-002`). Self-Check updated. |
| `BRAND.md`, `DESIGN.md` | Regenerated by `python tools/materialize_docs.py`. |
| `tools/materialize_docs.py` | Titles `# Brand: Silverbot` and `# Design System: Silverbot`. |
| Suite cross-references | None move: §4.1 to §4.4 keep their numbers and the foundations are added as §4.5 (section 5). The plan greps the suite to confirm. |
| [index.md](../../index.md), [log-silverbot.md](../../log-silverbot.md) | DSD row, process records (both specs and the plan), one log row. |
| [sad-silverbot.md](../../sad-silverbot.md) | SAD-B1 re-reconciled: confirm its pointers still hold; the font and CSP lines change only with `silverbot-cr-002` (section 8). |

## 11. Execution (parallel workflow)

Run after this spec and its plan are approved, as one workflow of about five agents:

1. **Phase 1, in parallel.**
   - Docs agent: applies DSD sections 0 to 8 (brand spec plus this spec), the materializer titles, the index, log and SAD-B1 check; runs the checks in section 12.
   - Figma tokens agent: on a new **Foundation Components** page, creates the three variable collections and the text styles (section 9.2); returns their IDs.
2. **Phase 2, in parallel, one page each.**
   - Branding agent: builds the **Branding** page from the variables and text styles.
   - Components agent: builds the component sets, the layout template and the reference Status page on **Foundation Components**; renames Page 1.
3. **Phase 3, verification.** One agent: `materialize --check`, the test suite, a parity check of DSD hex values against the Figma variables, and one screenshot review per Figma page; reports defects for a targeted fix.

Each Figma agent loads the Figma usage guide before writing, switches page at most once per call, and returns every node ID it creates.

## 12. Verification

1. `python tools/materialize_docs.py`, then `--check`: no changes on the second run.
2. `python -m pytest -q`: 271 passed (no code changes).
3. No U+2014 em dash in DSD sections 0 to 8, `BRAND.md` or `DESIGN.md`.
4. Every hex value in DSD §2 equals the matching `Silverbot/Color` variable value in its mode.
5. Contrast: every text token in section 2.1 is at least 4.5:1 on `canvas` and `surface` in its theme.
6. Figma: the Foundation Components page uses no unbound colour on any component; the reference Status page contains only instances (plus layout frames); every page screenshot shows no clipped text.
7. Read-through against [voice-silverbot.md](../../voice-silverbot.md) section 1: no profit claim, no invented number, every example value traceable to code, a report file or a gap ID.
