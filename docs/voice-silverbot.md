# House Style & Voice (VOICE)

**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Version:** 0.1
**Owner:** Cian Jake Francisco
**Status:** Draft
**Last updated:** 2026-10-08
**Last reconciled:** N/A (not a code-describing doc)

## 1. Hard Bans

- No em dashes in suite docs or root artifacts. Use `;`, `:`, `,` or parentheses.
- No performance or profit claim without a non-empty evidence file. The three files under `reports/` are 0 bytes today.
- No "guaranteed", "risk-free" or "passive income".
- No invented numbers. Write `Owner input required` for owner facts and `Open` for everything else.
- No naming of external template sources, products or tools used to produce the docs.
- Every diagram is a `mermaid` fenced block.
- No placeholder tokens in committed docs.

## 2. Register by Document Type

| Type | Register |
|------|----------|
| RFC, SDD | Terse and precise. Name the file and line. Define terms once. |
| Runbooks (OPS) | Imperative, numbered steps, one action per step, expected result after each. |
| Audit, drift, QAD | Factual. State what the code does, then what the old doc said. |
| BRD, PRD, IDEA | Plain. State the goal, the status and what is not built. |
| AGENTS, CLAUDE | Short rules an agent can follow without interpretation. |

## 3. AI-Tell Pass Before Locking a Doc

Before a doc moves from Draft to Locked:

1. Cut filler openers and closers.
2. Cut hedges ("may", "might", "generally") unless the uncertainty is real; then say what is unknown.
3. Break up triplets that exist only for rhythm.
4. One claim per sentence, each with evidence (file, line, test or report).
5. Replace adjectives with numbers or file references, or delete them.

## 4. Project Voice Tuning

Plain, cautious and safety-first. Say what is `Planned` and what is built. Live trading is `Planned, blocked`. Use trading terms as defined in [rfc-silverbot-signal-engine.md](rfc-silverbot-signal-engine.md) (session window, liquidity sweep, displacement, MSS, FVG). When a safety property is unverified, say so.

## 5. Self-Check

- [x] Bans listed with the replacement for each.
- [x] Register table covers every doc type in the suite.
- [x] Pass before locking is a numbered, checkable list.
- [x] Trading terms point to RFC-001 ([rfc-silverbot-signal-engine.md](rfc-silverbot-signal-engine.md)).
- [x] This doc contains no em dashes.
