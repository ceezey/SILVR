# Change Record: Silverbot Dashboard Reskin and SAD-B1 Update

**CR ID:** `silverbot-cr-002`
**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Version:** 0.1
**Author:** Cian Jake Francisco
**Status:** Proposed (awaiting owner approval; nothing in section 3 is built)
**Last updated:** 2026-10-14
**Base commit:** `f0ff6e9` on `dev`
**PRD Reference:** [prd-silverbot.md](prd-silverbot.md) PRD-F13 (amended: AC-23.1 reworded, AC-23.8 to AC-23.13 added)
**DSD Reference:** [dsd-silverbot.md](dsd-silverbot.md) §0 to §7 (Silverbot brand and design system), §9 (mode A scope and the §9.6 gate)
**SAD Reference:** [sad-silverbot.md](sad-silverbot.md) SAD-B1 `psl-purist` (builder; card amended), SAD-A4 `restraint-guardian` (reviewer)
**Design records:** [2026-10-14-silverbot-brand-design.md](superpowers/specs/2026-10-14-silverbot-brand-design.md), [2026-10-14-silverbot-design-system-design.md](superpowers/specs/2026-10-14-silverbot-design-system-design.md)

This record is the gate that [dsd-silverbot.md](dsd-silverbot.md) §9.6 requires before the built mode A dashboard (PRD-F13, `silverbot-cr-001`) changes. It applies the Silverbot brand and the Sterling design system to the dashboard, adds the evidence ladder and the Next strip, serves the IBM Plex Mono font from the dashboard's own server, and amends the SAD-B1 `psl-purist` card so the builder may do so. It adds no control surface, no write path and no remote exposure.

## 1. Why

The design system in DSD §0 to §7 (Silverbot name, Sterling palette, IBM Plex Mono, instrument panels, evidence ladder) is specified, but the built dashboard still uses the earlier grey palette, the `silver-bot status` title and the system font stack (`monitoring/dashboard_server.py:32-69`). Two rules block the change without a record: the §9.6 gate allows mode A changes only within `silverbot-cr-001`'s scope, and the SAD-B1 card tells `psl-purist` to load no web fonts and to send exactly `default-src 'none'; style-src 'unsafe-inline'` (`docs/sad-silverbot.md:296`).

The ladder makes the evidence path visible (brand §0, "progress, not emptiness"): three of the five evidence reports are 0 bytes today (G-1), and the page should say which step comes next instead of only listing files.

## 2. Divergences

| # | Current text | Change | Reason |
|---|---|---|---|
| V-1 | SAD-B1 card: "load nothing from a CDN or any other host, including web fonts. Send Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'." (`docs/sad-silverbot.md:296`) | "Load nothing from a CDN or any other host. Serve only the vendored IBM Plex Mono woff2 files from the dashboard's own server. Send Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; font-src 'self'." The card's standard-library toolbox (`docs/sad-silverbot.md:288`) gains `importlib.resources` for reading the packaged font files. | Owner chose to serve the brand font locally (design spec DS-4); same-origin only |
| V-2 | SAD-B1 gate sentence: mode A may change "only within that record's scope" (`silverbot-cr-001`) | Mode A may change within the scope of `silverbot-cr-001` and this record | §9.6 gate for the reskin |
| V-3 | `cr-001` §3.2: `GET /` is the only route | Two more GET routes, an exact allow-list: `/fonts/IBMPlexMono-Regular.woff2` and `/fonts/IBMPlexMono-Bold.woff2`; every other path stays 404 | Font delivery without another host |
| V-4 | AC-23.1: six panels in the §3.2 order with the safety banner first | Banner first, then the evidence ladder and the Next strip, then the six-panel order of `cr-001` | DSD §3 page order |
| V-5 | `cr-001` §3.3 panel 2: stale when a strategy evidence report changed after `generated_at` | Stale when that is true **or** `generated_at` is older than 24 hours | Design spec DS-9 |
| V-6 | Design spec §5.5: branded 404 and 500 pages | 404 becomes a branded HTML page in the shell (header, message, link to `/`, no data). No 500 page is added | Collector failures are already isolated per panel (AC-23.7); a 500 page would handle only render bugs |
| V-7 | Design spec §7: "the safety banner is the first content on every page" | "on every status page"; error pages carry no status data, so no banner | A banner on the 404 page would need a full collect for a wrong URL |
| V-8 | Design spec §8: Telegram anchor and voice in this record | Deferred to the Telegram transport record (G-15) | `TelegramAlerter` builds plain `[title] message` text (`monitoring/telegram.py:103`) and has no MarkdownV2 sanitizer; restyling it is G-15 work |
| V-10 | DSD §2.3 (as of `silverbot-cr-001`): mode A "loads no web font" | DSD §2.3 says mode A serves the two vendored fonts once this record is built; the "until then" clause is removed on merge | DS-4 |
| V-9 | `pyproject.toml` has no package data | `[tool.setuptools.package-data]` ships `silver_bot.monitoring` `fonts/*.woff2` and `fonts/OFL.txt` | Without it the fonts would not install with the package |

## 3. Changes

### 3.1 Amended PRD feature

PRD-F13 keeps its row. AC-23.1 is reworded and six criteria are added under US-23.

- AC-23.1 (reworded) Given the server is running, when the owner requests `GET /` from the same machine, then the page shows the safety banner first, then the evidence ladder and the Next strip, then the six panels in the `silverbot-cr-001` order.
- AC-23.8 Given any combination of evidence and readiness files, when the page renders, then the ladder shows five steps (Backtest, Out-of-sample, Paper, Demo, Live) with the states of [dsd-silverbot.md](dsd-silverbot.md) §4.5, and step 5 is always `[ OFF ] blocked (PRD-F12)`, including when `live_readiness_report.json` has `ready` true.
- AC-23.9 Given the ladder states, when the page renders, then the first of steps 1 to 4 that is not `[ OK ]` is marked NEXT, and the Next strip shows exactly the DSD §4.5 text for that step, or `All evidence gates pass. Live trading stays blocked (PRD-F12).` when steps 1 to 4 are all `[ OK ]`.
- AC-23.10 Given a readiness report whose `generated_at` is more than 24 hours before the page time, when the page renders, then its readiness row and (for demo) its ladder step show `stale`, with `[ WRN ]` when the report is otherwise READY and `[ ERR ]` kept when it is NOT READY.
- AC-23.11 Given the server is running, when `GET /fonts/IBMPlexMono-Regular.woff2` or `GET /fonts/IBMPlexMono-Bold.woff2` is requested, then the response is 200 with `Content-Type: font/woff2`, the security headers and the file's bytes; any other path under `/fonts/`, including encoded or `..` paths, gets 404.
- AC-23.12 Given any response, when the server sends it, then `Content-Security-Policy` is exactly `default-src 'none'; style-src 'unsafe-inline'; font-src 'self'`, and the page HTML contains no `http:` or `https:` URL.
- AC-23.13 Given the page renders, when it is inspected, then the title and header read `Silverbot`, the header holds the S-tier mark as inline SVG, the CSS `:root` values equal the dark tokens of [dsd-silverbot.md](dsd-silverbot.md) §2.1, and one or more unreadable panels add a single `degraded` summary line under the banner.

### 3.2 Architecture

The three units of `silverbot-cr-001` stay. Standard library only; `dependencies = []` is unchanged.

| Unit | File | Change |
|---|---|---|
| Collect | `src/silver_bot/monitoring/status.py` | New `_ladder` step in its own `try`/`except` (AC-23.7 pattern) that derives five step rows and the NEXT index from the rows `_evidence` and `_readiness` already produced (no second read or parse of any file); a fixed `NEXT_TEXT` constant; the 24-hour rule added to the existing stale check in `_generated_row`; a `degraded` count of unreadable panels in the status dict. |
| Render | `src/silver_bot/monitoring/dashboard_server.py` | The Sterling tokens the page uses, as CSS custom properties (no CSS for deferred components); `@font-face` rules pointing at the two same-origin font paths; the Plex Mono stack; instrument-panel CSS (surface panels, 1 px hairlines, 4 px radius); header with the inline S mark and `Silverbot`; ladder and Next strip rendering; branded 404 page. Status cells keep their markup (`<td class="{state}">[ TAG ]</td>`), so the glyph, word and colour rule is unchanged. |
| Serve | `src/silver_bot/monitoring/dashboard_server.py` | A `FONTS` dict mapping the two exact paths to file names, read with `importlib.resources.files("silver_bot.monitoring").joinpath("fonts", name)` (anchored on the package, because `fonts/` has no `__init__.py`); no generic static-file handler; CSP with `font-src 'self'`. Host check, GET-only, 405, bind address and port handling unchanged. |

New files: `src/silver_bot/monitoring/fonts/IBMPlexMono-Regular.woff2`, `src/silver_bot/monitoring/fonts/IBMPlexMono-Bold.woff2`, `src/silver_bot/monitoring/fonts/OFL.txt`. The font files come from the official IBM Plex release at a pinned version; a test holds their SHA-256 values as constants, so a changed file fails the suite. Tests read the source tree (`pythonpath = ["src"]`), so the package-data entry is checked by a non-editable install (`pip install .`, as the `Dockerfile` does) during verification.

Unchanged: `main.py`, `src/silver_bot/main.py`, configuration, Docker and `deploy/**`; the read-only rules of `cr-001` §3.2 (SQLite `mode=ro`, config allow-list, redaction, no script, no polling).

### 3.3 Ladder and Next strip

As specified in [dsd-silverbot.md](dsd-silverbot.md) §4.5 (from the design spec §5.5):

| Step | Source | States |
|---|---|---|
| 1 Backtest | `reports/backtest_report.json` | non-empty JSON object `[ OK ]`; 0 bytes or not a JSON object `[ ERR ]`; missing `[ OFF ]` |
| 2 Out-of-sample | `reports/out_of_sample_validation_report.json` | as step 1 |
| 3 Paper | `reports/paper_trading_report.json` | as step 1 |
| 4 Demo | `reports/demo_readiness_report.json` | READY and fresh `[ OK ]`; READY and stale `[ WRN ]`; NOT READY `[ ERR ]`; missing `[ OFF ]`; unreadable `[ ERR ]` |
| 5 Live | none | always `[ OFF ] blocked (PRD-F12)` |

Next strip text: steps 1 or 2, `Next: run a backtest (runbook-backtest.md steps 5 and 6)` (the backtest command needs the step 5 environment, so the strip points at the runbook); step 3, `Next: paper trading (not available yet, G-3)`; step 4, `Next: refresh demo readiness  python -m silver_bot.demo_readiness (runbook-demo-testnet.md steps 3 and 4)` (its default output, `reports/demo_readiness_report.json`, is the file the step reads); none, `All evidence gates pass. Live trading stays blocked (PRD-F12).` No other text is possible.

Today's files give: Backtest `[ ERR ] 0 B` (NEXT), Out-of-sample `[ ERR ] 0 B`, Paper `[ ERR ] 0 B`, Demo `[ WRN ] READY · stale` (generated 2026-06-15), Live `[ OFF ] blocked`.

### 3.4 Doc updates on merge

- [prd-silverbot.md](prd-silverbot.md): AC-23.1 reworded; AC-23.8 to AC-23.13 added.
- [dsd-silverbot.md](dsd-silverbot.md): banner and §9 say mode A is reskinned per this record; §3.2 layout marked built; §2.3 drops its "until then" clause (V-10).
- [sad-silverbot.md](sad-silverbot.md): SAD-B1 card per V-1 and V-2, then `python tools/materialize_docs.py`.
- [qad-silverbot.md](qad-silverbot.md): test rows for AC-23.8 to AC-23.13 and the changed AC-23.1 test.
- [ops-silverbot.md](ops-silverbot.md) §5.6: ladder states, NEXT, the 24-hour stale rule.
- [index.md](index.md) and [log-silverbot.md](log-silverbot.md): status and one row.

## 4. Verification

Standard library and pytest only, `tmp_path`, no network.

| Area | Test | AC |
|---|---|---|
| Order | Banner, ladder, Next strip, then the six panels (updates `test_page_shows_six_panels_in_layout_order_with_banner_first`) | AC-23.1 |
| Ladder | Each step with missing, 0-byte, invalid and valid inputs; demo fresh, stale, NOT READY, missing; Live blocked with `live_readiness_report.json` `ready` true | AC-23.8 |
| Next | NEXT on the first non-OK step; each of the four strip texts asserted exactly | AC-23.9 |
| Stale | `generated_at` 25 hours old READY gives `[ WRN ] stale`; NOT READY keeps `[ ERR ]` with `stale`; 23 hours is fresh; the `cr-001` evidence-newer rule still holds | AC-23.10 |
| Fonts | Both paths 200 with `font/woff2` and the headers; one parametrized test sends `/fonts/x.woff2`, `/fonts/../status.py`, `/fonts/%2e%2e/x` and `/fonts/` and gets 404; SHA-256 of each served body equals the constant in the test | AC-23.11 |
| CSP | Exact header on 200, 404, 405 and 400 responses (updates the two tests that assert the literal string: `test_get_root_returns_page_with_security_headers` and `test_other_methods_get_405`); no `http` URL in the HTML | AC-23.12 |
| Brand | `<title>` and header contain `Silverbot`; inline `<svg>` in the header; every `:root` value the page uses equals its DSD §2.1 dark token; a raising collector adds one `degraded` line | AC-23.13 |
| Unchanged | All `silverbot-cr-001` tests still pass (secrets, read-only, Host check, bind, escaping, isolation) | AC-23.2 to AC-23.7 |

Commands: `python -m pytest` (all pass) and `python tools/materialize_docs.py --check` (no changes).

## 5. Pre-merge gate runs

Per [sad-silverbot.md](sad-silverbot.md) §4: `restraint-guardian` (SAD-A4) on the full diff. The diff touches `src/silver_bot/monitoring/**`, `tests/**`, `pyproject.toml` and docs only (including the regenerated `.claude/agents/psl-purist.md`); none is a live-gate surface or risk, execution, exchange, config or readiness code, so SAD-A1 to SAD-A3 are not required. Results are recorded here before merge.

| Reviewer | Result | Notes |
|---|---|---|
| restraint-guardian (SAD-A4) | Not run on code | Runs on the build diff after approval. A scope review of this record (2026-10-14) found no safety check or `cr-001` test cut and suggested trims, now applied (font hashes in the test only, ladder reuses collected rows, one parametrized 404 test, only used CSS tokens). It also suggested dropping the branded 404 page and the `degraded` line; both are kept because the owner approved them in the design review, and the owner may still cut them before approval. |

## 6. Deferred

- Telegram anchor `SILVERBOT` and the voice in alert text: with the Telegram transport record (G-15), V-8.
- Top navigation bar and any page other than `GET /`: each needs its own record.
- Buttons, inputs, toasts and dialogs from DSD §4.5: specified, not built; each use needs its own record.
- Light theme for the dashboard: not planned (design spec DS-7).
- Favicon and a 500 page: not added (V-6).
- Terminal status view (mode B): later record, unchanged from `cr-001`.

## Self-Check

- [x] Sections Why, Divergences, Changes, Verification, Pre-merge gate runs and Deferred are present ([build-silverbot.md](build-silverbot.md) §5.1).
- [x] Every new or reworded acceptance criterion maps to a test in section 4.
- [x] No control surface, write path or remote exposure is added; the bind address stays `127.0.0.1` and the server stays GET-only.
- [x] The only CSP change is `font-src 'self'`; nothing is loaded from another host.
- [x] The Live step can never show a reachable state; the Next strip has four fixed texts, none of which changes configuration, enables live trading or touches the kill switch.
- [x] No invented number: ladder states come from files the dashboard already reads.
- [x] No em dashes; links point only to existing suite files.
