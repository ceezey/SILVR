# Silverbot Brand, Design System and Figma Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the Silverbot brand and Sterling design system in DSD sections 0 to 8 (materialized to `BRAND.md` and `DESIGN.md`) and build the matching Branding and Foundation Components pages in the SILVR Figma file.

**Architecture:** Two independent tracks. The docs track edits one canonical file (`docs/dsd-silverbot.md`), the materializer titles and the suite bookkeeping, then regenerates the root artifacts. The Figma track creates variables and text styles first, then the mark, then the Branding page and the component sets in parallel, then the layout template and a reference Status page built only from instances. No bot code changes.

**Tech Stack:** Markdown docs, `tools/materialize_docs.py` (Python 3.11+ standard library), pytest, Figma Plugin API through the Figma MCP `use_figma` tool, IBM Plex Mono.

**Spec:** [2026-10-14-silverbot-brand-design.md](../specs/2026-10-14-silverbot-brand-design.md) (DSD §0 and §1, exact text in its section 2) and [2026-10-14-silverbot-design-system-design.md](../specs/2026-10-14-silverbot-design-system-design.md) (DSD §2 to §8 and Figma). Change Record [cr-silverbot-dashboard-reskin.md](../../cr-silverbot-dashboard-reskin.md) (`silverbot-cr-002`, Proposed) narrows two design-spec items that the DSD follows: a branded 404 page only (no 500 page), and the safety banner first on every *status* page.

## Global Constraints

- No bot code changes: nothing under `src/` changes. Only `tools/materialize_docs.py` and `tests/test_materialize_docs.py` change among code files.
- Do not change the SAD-B1 `psl-purist` card (`docs/sad-silverbot.md` §3, `.claude/agents/psl-purist.md`). It changes only when `silverbot-cr-002` is approved.
- Do not describe the reskin, the ladder, the Next strip or served fonts as built. They are specified; the built dashboard still follows `silverbot-cr-001`.
- No em dash (U+2014) in any changed doc. Use `;`, `:`, `,` or parentheses.
- No profit or performance claim; no invented number; no placeholder token ([voice-silverbot.md](../../voice-silverbot.md) §1).
- Headings `## 0. Brand Stance`, `## 1. Design Philosophy & Vision`, `## 2. Brand Primitives (tokens, color, type)`, `## 7. Quality Gate`, `## 8. Materialization` keep their exact text (asserted by `tests/test_materialize_docs.py`).
- DSD §1.2 stays "Surface modes"; DSD §4.1 to §4.4 keep their numbers; Interface Foundations is a new §4.5.
- Figma file key `g1n3J4j2L1iPrbdjiOS30e` (SILVR). Existing pages: `0:1` "Page 1" (old draft), `9:2` "Silverbot · Exploration". Never delete either.
- Figma font: IBM Plex Mono (`Regular`, `Bold`) only. Every component colour, spacing and radius is bound to a variable.
- Before any `use_figma` call an agent reads the MCP resource `skill://figma/figma-use/SKILL.md` (server `claude.ai Figma`) and, for component or token work, `skill://figma/figma-generate-library/SKILL.md`; it passes `skillNames` accordingly (prefixed `resource:`).
- Nothing is pushed until Task 9 passes.

## Review Focus

1. A DSD heading renamed by accident breaks the BRAND/DESIGN split: pinned by the existing `test_brand_and_design_are_split_from_the_dsd` and the new title test (Task 1).
2. An em dash or a "Built" claim for the reskin slips into the DSD: pinned by the grep checks in Task 3, Step 4.
3. A Figma component keeps a hard-coded colour instead of a bound variable: pinned by the unbound-paint audit in Task 9, Step 3.
4. Figma text falls back to Inter or clips: pinned by the font audit and the per-page screenshot review in Task 9, Steps 3 and 4.
5. DSD hex values drift from the Figma variables: pinned by the parity check in Task 9, Step 2.

---

## Execution waves

| Wave | Tasks (run in parallel within a wave) |
|------|----------------------------------------|
| 1 | Task 1 to Task 3 (one docs agent, in order) **and** Task 4 (Figma foundations agent) |
| 2 | Task 5 (Branding), Task 6 (actions and inputs), Task 7 (surfaces and feedback) |
| 3 | Task 8 (layout template and reference Status page) |
| 4 | Task 9 (verification, then push) |

---

### Task 1: Materializer titles use the brand name

**Files:**
- Modify: `tools/materialize_docs.py:78` and the `DESIGN.md` title line below it
- Test: `tests/test_materialize_docs.py`

**Interfaces:**
- Produces: generated `BRAND.md` starts (after the banner) with `# Brand: Silverbot`; `DESIGN.md` with `# Design System: Silverbot`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_materialize_docs.py`)

```python
def test_root_titles_use_the_brand_name() -> None:
    spec = importlib.util.spec_from_file_location("materialize_docs", ROOT / "tools" / "materialize_docs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = module.targets(ROOT)

    assert "\n# Brand: Silverbot\n" in out["BRAND.md"]
    assert "\n# Design System: Silverbot\n" in out["DESIGN.md"]
```

- [ ] **Step 2: Run it and see it fail**

Run: `python -m pytest -q tests/test_materialize_docs.py::test_root_titles_use_the_brand_name`
Expected: FAIL (titles still read `silver-bot`).

- [ ] **Step 3: Change the two title strings** in `tools/materialize_docs.py`: `"# Brand: silver-bot\n\n"` becomes `"# Brand: Silverbot\n\n"` and `"# Design System: silver-bot\n\n"` becomes `"# Design System: Silverbot\n\n"`.

- [ ] **Step 4: Run the new test**

Run: `python -m pytest -q tests/test_materialize_docs.py::test_root_titles_use_the_brand_name`
Expected: PASS. (`test_materialized_files_are_up_to_date` fails until Task 3 regenerates; that is expected inside the docs track.)

- [ ] **Step 5: Commit**

```bash
git add tools/materialize_docs.py tests/test_materialize_docs.py
git commit -m "docs(tooling): brand name in BRAND.md and DESIGN.md titles"
```

### Task 2: DSD sections 0 to 8

**Files:**
- Modify: `docs/dsd-silverbot.md` (header lines 1 to 11, sections 0 to 8, Self-Check)

**Interfaces:**
- Consumes: brand spec §2 (verbatim text for DSD §0 and §1); design-system spec §2 to §7, §9.1 (page names) and §10.
- Produces: the DSD skeleton below, which Task 3 materializes and Task 9 parity-checks.

- [ ] **Step 1: Replace DSD §0 and §1** with the fenced block in the brand spec section 2, verbatim (it starts at `## 0. Brand Stance` and ends after the §1.5 Mark paragraph). Then replace §1.5 "Mark" body with a pointer: keep the concept paragraph from the brand spec but change its two bullets "Visor" and "Badge" to match the design-system spec §3 (visor shows the 1:3 position with candles reaching the target; badge `47` and `Ag`), and end with "Construction, tiers and lockups: §2.4."

- [ ] **Step 2: Replace DSD §2 to §7** with this skeleton, filling each subsection from the design-system spec section named in brackets. Keep tables as tables; copy hex values, sizes, rules and texts exactly.

```text
## 2. Brand Primitives (tokens, color, type)
### 2.1 Neutral and brand tokens        [spec 2.1: canvas, surface, border, ink, muted, brand, accent; Dark, Light, ANSI, Use, contrast]
### 2.2 Semantic tokens                 [spec 2.1 rows success, warning, danger + today's glyph table and meanings; add the 24 h stale meaning per DS-9]
### 2.3 Type                            [spec 2.2; say mode A serves the fonts once silverbot-cr-002 is built and uses the stack until then]
### 2.4 Mark                            [spec 3.1 to 3.3]
### 2.5 Spacing, shape and touch targets [spec 2.3]
## 3. Layout & Spatial System
### 3.1 Standard desktop layout         [spec 4.1; footer text as built]
### 3.2 Reference layout                [spec 4.2; redraw the text sketch in the new order with today's values; label it "target layout (silverbot-cr-002, Proposed); the built page follows silverbot-cr-001"]
### 3.3 Terminal (mode B)               [today's 80 x 24 grid, box drawing, one-line ladder from spec 4.2]
## 4. Core Component Specs
### 4.1 Status cell                     [unchanged]
### 4.2 Telegram alert (MarkdownV2)     [today's text; header anchor becomes \[SILVERBOT \| ...\]; body lines follow the §1.4 voice; "Status today" bullet unchanged]
### 4.3 Audit log line (JSON lines)     [unchanged]
### 4.4 Report and file rows            [unchanged + readiness stale per DS-9]
### 4.5 Interface Foundations
#### 4.5.1 Geometry and Rhythm          [spec 5.1]
#### 4.5.2 Actions, Navigation, Inputs and Touch Targets [spec 5.2, including the allowed-use column and the hard rule]
#### 4.5.3 Surfaces, Cards and Rows     [spec 5.3]
#### 4.5.4 Standard Desktop Layout      [pointer to §3.1]
#### 4.5.5 Feedback, Overlays and System States [spec 5.5: ladder table, NEXT rule, Next strip table, source states, page states (branded 404 only, no 500 page), overlays]
## 5. Motion                            [unchanged]
## 6. Accessibility                     [today's bullets + spec 6 additions]
## 7. Quality Gate                      [today's 8 items + spec 7 items; banner item reads "first content on every status page"]
## 8. Materialization                   [today's paragraph + "The SILVR Figma file (pages Branding and Foundation Components) mirrors sections 0 to 7; if they disagree, this document wins and the Figma file is corrected."]
```

- [ ] **Step 3: Update the DSD header and banner**
  - `**Status:**` `Draft (Silverbot brand and design system specified; mode A built per silverbot-cr-001; reskin proposed in silverbot-cr-002)`
  - `**Last updated:**` `2026-10-14`
  - `**Design file:**` `[SILVR](https://www.figma.com/design/g1n3J4j2L1iPrbdjiOS30e/SILVR): pages Branding and Foundation Components mirror sections 0 to 7 (section 8).`
  - Banner: add one sentence: "Sections 0 to 7 now specify the Silverbot brand and the Sterling design system; the built dashboard still uses the earlier tokens and layout until [cr-silverbot-dashboard-reskin.md](cr-silverbot-dashboard-reskin.md) (`silverbot-cr-002`, Proposed) is approved and built."
  - §9.6: append "The reskin of mode A is proposed in [cr-silverbot-dashboard-reskin.md](cr-silverbot-dashboard-reskin.md)."

- [ ] **Step 4: Update the DSD Self-Check** so every checked line is true for the new text (sections 0 to 7 hold the Silverbot brand and Sterling system; the §3.2 layout is labelled target; no em dashes; links point to existing files).

- [ ] **Step 5: Commit**

```bash
git add docs/dsd-silverbot.md
git commit -m "docs(dsd): Silverbot brand and Sterling design system (sections 0 to 8)"
```

### Task 3: Bookkeeping, regeneration and docs checks

**Files:**
- Modify: `docs/index.md`, `docs/log-silverbot.md`, `docs/qad-silverbot.md`
- Regenerate: `BRAND.md`, `DESIGN.md`
- Read only: `docs/sad-silverbot.md` (SAD-B1 check)

- [ ] **Step 1: index.md**
  - DSD row: Last Updated `2026-10-14`; Status as in Task 2 Step 3.
  - Change Records table: add `silverbot-cr-002` | [cr-silverbot-dashboard-reskin.md](cr-silverbot-dashboard-reskin.md) | Dashboard reskin and SAD-B1 update | Proposed | 2026-10-14.
  - Process records table: add the two 2026-10-14 specs and this plan.
  - Doc-count paragraph: recount files under `docs/` and `docs/superpowers/` with `ls` and state the new totals.
  - **Last updated:** `2026-10-14`.

- [ ] **Step 2: qad-silverbot.md**: add `| QAD-T252 | BRAND.md and DESIGN.md titles use the brand name Silverbot | None (docs tooling) | tests/test_materialize_docs.py::test_root_titles_use_the_brand_name |` after the QAD-T205 row's table section (same table), and update any test count in that doc that this changes.

- [ ] **Step 3: log-silverbot.md**: append two rows in the existing format: (a) 2026-10-14 "Brand and design system": DSD §0 to §8 rewritten for the Silverbot brand (name, tagline, voice, chart-visor mark) and the Sterling system (tokens, IBM Plex Mono, Interface Foundations, evidence ladder specified), Figma Branding and Foundation Components pages built in SILVR, BRAND.md and DESIGN.md regenerated, no bot code changed; evidence `python -m pytest -q`, `python tools/materialize_docs.py --check`. (b) 2026-10-14 "Change Record proposed": `silverbot-cr-002` dashboard reskin and SAD-B1 update, Proposed, not built.

- [ ] **Step 4: Regenerate and check**

```bash
python tools/materialize_docs.py
python tools/materialize_docs.py --check
python -m pytest -q
grep -n "—" docs/dsd-silverbot.md BRAND.md DESIGN.md docs/index.md docs/log-silverbot.md docs/qad-silverbot.md
grep -n -i "reskin" docs/dsd-silverbot.md
```

Expected: second command prints `materialized: no changes`; pytest prints `272 passed`; the em dash grep prints nothing; every "reskin" line says proposed or not built.

- [ ] **Step 5: SAD-B1 check**: confirm `docs/sad-silverbot.md` SAD-B1 still points at "DSD sections 0 to 7" and "section 4.2" and that both still exist. Make no edit.

- [ ] **Step 6: Commit**

```bash
git add docs/index.md docs/log-silverbot.md docs/qad-silverbot.md BRAND.md DESIGN.md
git commit -m "docs: regenerate BRAND.md and DESIGN.md; register specs, plan and silverbot-cr-002"
```

### Task 4: Figma foundations (variables, text styles, mark, lockups)

**Files:** SILVR Figma file only.

**Interfaces:**
- Produces (found later by name, not by ID): page `Foundation Components`; collections `Silverbot/Color` (modes `Dark`, `Light`), `Silverbot/Space`, `Silverbot/Radius`; text styles `Silverbot/Label`, `Silverbot/Detail`, `Silverbot/Data`, `Silverbot/Wordmark`, `Silverbot/Showcase 18`, `Silverbot/Showcase 22`, `Silverbot/Showcase 40`; component sets `Mark` (property `Tier` = `L`, `M`, `S`) and `Lockup` (property `Layout` = `Horizontal`, `Stacked`), inside a section frame `01 Brand assets`.

- [ ] **Step 1: Inspect** (read-only `use_figma`): list pages, variable collections and text styles; stop and report if `Silverbot/Color` already exists.

- [ ] **Step 2: Create page and variables.** Create page `Foundation Components`. Create `Silverbot/Color` with modes renamed `Dark` and `Light` and these COLOR variables:

| name | Dark | Light | scopes |
|------|------|-------|--------|
| canvas | #0B0D10 | #F6F7F9 | FRAME_FILL, SHAPE_FILL |
| surface | #13161B | #FFFFFF | FRAME_FILL, SHAPE_FILL |
| border | #2A2F38 | #D9DDE3 | STROKE_COLOR, SHAPE_FILL |
| ink | #E8EAED | #14171C | TEXT_FILL, SHAPE_FILL |
| muted | #9AA1AC | #5B6370 | TEXT_FILL, SHAPE_FILL |
| brand | #C3C9D2 | #646D79 | TEXT_FILL, SHAPE_FILL, STROKE_COLOR |
| accent | #7AA2F7 | #2F5BD3 | TEXT_FILL, STROKE_COLOR, SHAPE_FILL |
| success | #3FB68B | #1E7F5A | TEXT_FILL, SHAPE_FILL |
| warning | #E3B341 | #8A5D00 | TEXT_FILL, SHAPE_FILL |
| danger | #F0616D | #C23142 | TEXT_FILL, SHAPE_FILL |

`Silverbot/Space` FLOAT: `space-4`=4, `space-8`=8, `space-12`=12, `space-16`=16, `space-24`=24, `space-32`=32, scopes `GAP`. `Silverbot/Radius` FLOAT: `radius-0`=0, `radius-3`=3, `radius-4`=4, `radius-6`=6, scopes `CORNER_RADIUS`. Return collection and variable counts.

- [ ] **Step 3: Text styles** (IBM Plex Mono, line height 150%): `Silverbot/Label` Bold 10, `textCase` UPPER, letter spacing 4%; `Silverbot/Detail` Regular 11; `Silverbot/Data` Regular 12; `Silverbot/Wordmark` Bold 14; `Silverbot/Showcase 18`, `22`, `40` Bold. Return style IDs.

- [ ] **Step 4: Mark, tier L (160 x 160)**, built from rectangles and text in a frame, every fill and stroke bound to `Silverbot/Color`. Coordinates are absolute in the 160 frame:

| part | x | y | w | h | radius | paint |
|------|---|---|---|---|--------|-------|
| antenna left | 40 | 0 | 5 | 16 | 2 | brand |
| antenna right | 115 | 0 | 5 | 16 | 2 | brand |
| head | 0 | 14 | 160 | 144 | 12 | fill surface, stroke brand 3 inside |
| visor | 14 | 28 | 132 | 76 | 6 | canvas |
| target zone 3R | 84 | 38 | 56 | 36 | 0 | success, opacity 28% |
| stop zone 1R | 84 | 76 | 56 | 12 | 0 | danger, opacity 38% |
| entry line | 20 | 74 | 120 | 2 | 0 | ink, opacity 75% |
| badge divider | 14 | 110 | 132 | 1.5 | 0 | border |
| text `47` | 17 | 116 | auto | auto | | Plex Mono Regular 12, muted |
| text `Ag` | 86 | 112 | auto | auto | | Plex Mono Bold 30, brand |

Candles: body 8 wide, radius 1; wick 2 wide at body x + 3. (x, body top, body bottom, wick top, wick bottom, paint): (24, 70, 84, 66, 88, danger), (40, 68, 80, 64, 84, success), (56, 71, 79, 67, 83, danger), (72, 64, 76, 60, 78, success), (90, 54, 68, 50, 71, success), (106, 44, 58, 41, 61, success), (122, 41, 52, 38, 56, success). The last wick top (38) touches the target zone's top edge.

- [ ] **Step 5: Tiers M and S.** Duplicate L. M: remove candles at x 24, 40, 56, 72 and the `47` text, then `rescale(0.3)` (48 px). S: remove all candles and both texts, keep zones, entry line, divider, then `rescale(0.15)` (24 px) and set the head stroke to 1.5 and antennae width to 1.5. Combine the three as component set `Mark`, property `Tier`.

- [ ] **Step 6: Lockups.** `Lockup / Horizontal`: auto layout, Mark L instance scaled to 64 px, gap 16, text `Silverbot` with `Silverbot/Showcase 22` in `brand`. `Lockup / Stacked`: the horizontal lockup above the tagline `Discipline over id.` in `Silverbot/Data`, `muted`. Combine as set `Lockup`, property `Layout`. Place Mark and Lockup in a section frame `01 Brand assets` at x 0, y 0 on `Foundation Components`.

- [ ] **Step 7: Verify**: return counts (10 colour variables x 2 modes, 6 space, 4 radius, 7 text styles, 3 Mark variants, 2 Lockup variants) and one screenshot of `01 Brand assets`. Fix clipping if seen.

### Task 5: Branding page

**Files:** SILVR Figma file only.

**Interfaces:**
- Consumes: Task 4 variables, text styles, `Mark` and `Lockup` sets (find by name on `Foundation Components`).

- [ ] **Step 1: Create page `Branding`**; a vertical auto-layout wrapper, frames 1440 wide, `canvas` (Dark mode), padding 64, gap 64, one frame per section below. All text uses `Silverbot/*` styles; all colours bound.
- [ ] **Step 2: Sections, in order:**
  1. Cover: `Lockup / Stacked` instance at 2x, subline `Rules, not impulse, decide every trade.`
  2. Mark construction: Mark L at 4x (640 px) with annotation labels for antennae, head, visor, entry line, stop zone 1R, target zone 3R, candles, badge (`47`, `Ag`); note "1:3 risk to reward; engine minimum 2.0".
  3. Size tiers: L, M, S instances side by side with labels `L 96 px and up`, `M 32 to 95 px`, `S under 32 px`, plus the text form `[Ag]`.
  4. Lockups and clear space: both lockups; clear space shown as a dashed outline at 25% of mark width.
  5. Colour versions: the Mark on a Dark-mode frame, a Light-mode frame (`setExplicitVariableModeForCollection`), and a one-colour version (zones as 1 px outlines, candles solid, all `brand`).
  6. Misuse: four small crossed-out examples: recoloured zones, rotated, stretched, next to a performance figure (use the text `+42% win rate` struck through and labelled "never").
  7. Palette: swatches for all ten tokens in both modes with hex and contrast (values from the design-system spec 2.1).
  8. Typography: IBM Plex Mono specimen and the seven text styles with size and weight.
  9. Voice: the five-row "Not this / Silverbot" table from DSD §1.4.
- [ ] **Step 3: Verify**: one screenshot of the page wrapper; no clipped text; no Inter.

### Task 6: Actions, navigation and inputs components

**Files:** SILVR Figma file only, page `Foundation Components`, section frame `02 Actions, Navigation, Inputs` placed right of `01 Brand assets` (x = right edge + 120).

**Interfaces:**
- Consumes: Task 4 variables and text styles.
- Produces component sets (exact names): `Link` (Variant `Inline`, `Standalone`; State `Default`, `Hover`, `Focus`), `Nav Tab` (State `Default`, `Active`, `Hover`, `Focus`), `Top Nav`, `Anchor Nav`, `Button` (Variant `Secondary`, `Next`, `Ghost`; Size `24`, `32`; State `Default`, `Hover`, `Focus`, `Active`, `Disabled`), `Text Field`, `Select`, `Checkbox`, `Segmented Control` (each State `Default`, `Focus`, `Disabled`, `Read-only`).

- [ ] **Step 1:** Build each set with auto layout, bound paints and `Silverbot/Data` text. Focus state: 2 px `accent` stroke outside with 2 px gap (an outer frame). Active nav tab: `accent` 2 px bottom border plus bold label. No fill-coloured danger button exists.
- [ ] **Step 2:** Heights: Size 24 and Size 32 exactly; minimum hit area 24 x 24; 8 px between items in `Top Nav` and `Anchor Nav`.
- [ ] **Step 3:** Set each component set's `description` to its allowed use from DSD §4.5.2 (e.g. Button: "Change Record required. Never wired to orders, configuration, the kill switch or a gate.").
- [ ] **Step 4: Verify**: screenshot of the section; return variant counts.

### Task 7: Surfaces, rows and feedback components

**Files:** SILVR Figma file only, page `Foundation Components`, section frame `03 Surfaces, Cards, Rows` and section frame `05 Feedback, Overlays, States`, placed below `01 Brand assets` (y = its bottom + 120), side by side.

**Interfaces:**
- Consumes: Task 4 variables, text styles, `Mark`.
- Produces component sets (exact names): `Panel` (Variant `Default`, `Next`), `Status Cell` (State `OK`, `WRN`, `ERR`, `OFF`; text `[ OK ]`, `[ WRN ]`, `[ ERR ]`, `[ OFF ]` in success, warning, danger, muted plus a word and a muted detail), `Ladder Step` (State `OK`, `ERR`, `WRN`, `OFF`, `Blocked`; Next `True`, `False`), `Evidence Ladder`, `Next Strip`, `Safety Banner`, `Header`, `Data Row`, `Key-Value Row`, `Report Row`, `Readiness Row`, `Alert Row`, `Table Header Row`, `Empty State`, `Degraded Line`, `Disclosure`, `Tooltip`, `Toast`, `Dialog`, `Telegram Alert Preview`, `Page 404`.

- [ ] **Step 1:** Surfaces and rows: `Panel` has `surface` fill, 1 px `border`, radius 4, padding 12 by 14, a `Silverbot/Label` title then a body slot; `Next` variant uses a 1 px `accent` stroke. Rows are 24 px high with `Silverbot/Detail` or `Silverbot/Data` text.
- [ ] **Step 2:** Feedback: `Ladder Step` card: radius 3, `canvas` fill, label (`Silverbot/Label`) above state; `Next=True` adds `accent` 1.5 px stroke and the label suffix ` · NEXT`; `Blocked` shows `[ OFF ] blocked (PRD-F12)`. `Evidence Ladder` is five step instances joined by `▸` with today's states: Backtest ERR 0 B Next, Out-of-sample ERR 0 B, Paper ERR 0 B, Demo WRN `READY · stale`, Live Blocked. `Next Strip`: panel `Next` variant with `Next:` in `accent` then `run a backtest (runbook-backtest.md steps 5 and 6)`. `Safety Banner`: `MODE PAPER   LIVE [ OFF ]   DEMO [ OFF ]   KILL [ WRN ] path not set` and the muted note line. `Header`: Mark S, `Silverbot` (`Silverbot/Wordmark`, `brand`), `status · read-only · 127.0.0.1` (`muted`).
- [ ] **Step 3:** States and overlays: `Empty State` `[ OFF ] not available: no paper session yet (G-3). Next: paper trading (not available yet, G-3)`; `Degraded Line` `[ WRN ] degraded: 1 source unreadable`; `Disclosure` and `Tooltip` (allowed now); `Toast` and `Dialog` with descriptions "Future: needs a script and a Change Record; no motion; never confirms a risky action". `Telegram Alert Preview`: the DSD §4.2 example with header `[SILVERBOT | RISK REJECTED]`. `Page 404`: header plus `not found` and a `Link` to `/`.
- [ ] **Step 4: Verify**: screenshots of both sections; every state carries glyph and word.

### Task 8: Standard desktop layout and reference Status page

**Files:** SILVR Figma file only, page `Foundation Components`, section frame `04 Standard Desktop Layout` placed right of `03`/`05`; rename page `0:1` to `Archive · superseded draft`.

**Interfaces:**
- Consumes: all component sets from Tasks 4, 6 and 7.

- [ ] **Step 1: App shell template** (1280 wide): `Header` instance (48 px), hidden `Top Nav` instance, `Safety Banner` (pinned note), content column 80 to 120 ch (use 960 px at 1280), gutters 24, footer text `generated <time> · read-only; reading <root> · reload to refresh` in `muted`. Show breakpoint annotations: standard 1280+, compact 960 to 1279 (16 px gutters), stacked under 960.
- [ ] **Step 2: Reference Status page** (1280 wide) made only of instances plus auto-layout frames, in order: Header; Safety Banner; Evidence Ladder; Next Strip; row of two Panels (Readiness: `live [ ERR ] NOT READY · stale`, `demo [ WRN ] READY · stale`, `generated 2026-06-15 14:31 UTC`; Evidence Reports: five Report Rows `backtest_report 0 B [ ERR ]`, `out_of_sample_validation_report 0 B [ ERR ]`, `paper_trading_report 0 B [ ERR ]`, `live_readiness_report 2229 B [ OK ]`, `demo_readiness_report 2404 B [ OK ]`); Risk budget Panel with Empty State `not available: no risk_state row, no running bot (G-3)`; row of two Panels (Positions: `none recorded (no paper run, G-3)`; Alerts: `[ OK ] bot_started`, `[ OK ] bot_stopped`); footer. Label the frame "Target layout (silverbot-cr-002, Proposed)".
- [ ] **Step 3: Rename page** `0:1` to `Archive · superseded draft`.
- [ ] **Step 4: Verify**: count descendants by type in the reference page (instances must dominate; no rectangles with raw fills); one screenshot.

### Task 9: Verification and push

- [ ] **Step 1: Docs QA**

```bash
python tools/materialize_docs.py --check
python -m pytest -q
grep -c "—" docs/dsd-silverbot.md BRAND.md DESIGN.md
```

Expected: `materialized: no changes`; `272 passed`; every count `0`.

- [ ] **Step 2: Token parity** (read-only `use_figma`): read every `Silverbot/Color` variable value in both modes, convert to hex, and compare with the DSD §2.1 and §2.2 table hex values (parse the DSD with a short Python script in the scratchpad). Expected: 20 of 20 match.

- [ ] **Step 3: Figma audit** (read-only `use_figma` on `Foundation Components` and `Branding`): list any SOLID paint on a component or the reference page that has no bound variable; list any text node whose font family is not `IBM Plex Mono`. Expected: both lists empty (Branding misuse examples may carry deliberate raw paints; they are labelled "never").

- [ ] **Step 4: Screenshot review**: one screenshot each of `Branding`, `Foundation Components` sections and the reference page; check for clipped text, overlaps and placeholder text.

- [ ] **Step 5: Push** only if Steps 1 to 4 pass:

```bash
git status --short
git push origin dev
```
