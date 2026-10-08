# Scrutiny Gate (SCRUTINY)

**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Version:** 0.1
**Owner:** Cian Jake Francisco
**Status:** Draft
**Last updated:** 2026-10-08
**Last reconciled:** 2026-10-08 against code at commit `62037d1`

This gate decides whether the project should keep moving toward live trading, and records every gap that stands in the way. It is the source of the `G-#` ids cited by the other suite documents. Drift findings (`D-#`) live in [audit-docs-drift.md](audit-docs-drift.md); hazards (`H-#`) are recorded there under "Code hazards (not doc drift)". Scope: personal trading by the owner only; no outside users, no custody of other people's funds. Live trading is `Planned, blocked`. The other suite documents are listed in the [index](index.md).

## 1. Verdict

**Question:** should the project continue toward live trading?

**Verdict: PROCEED WITH FIXES.**

The foundations are real and tested (strategy engine, risk engine, backtest engine, paper execution engine, config validation, 108 tests in 19 files) and live trading is hard-blocked at config load (`config/settings.py:104-107`), so continuing carries no capital risk today. But the bot cannot yet run (the entrypoint is a startup stub), no strategy performance evidence exists (all three evidence reports are 0 bytes), and several safety gates are weaker than the old documents claim. Live trading must not be enabled until the fixes below are closed and evidence is produced. No performance claim may be made for the strategy until a non-empty evidence report exists.

Required fixes before any step toward live trading (order of priority):

1. Produce real evidence: run a backtest with non-zero costs and an out-of-sample split, and a paper run; store non-empty reports. See G-1, G-11, G-12.
2. Make readiness meaningful: reject empty or invalid evidence files and make the live-ready state reachable and consulted. See G-2.
3. Give the bot a real runtime: mode dispatch for backtest, paper and demo, and a supervisor-safe exit behaviour. See G-3, G-13.
4. Fix the shipped configuration: `.env.example` must load. See G-4.
5. Unify risk limits: one source of truth for per-trade risk, daily loss and leverage, capped at the documented 0.5%. See G-5.
6. Make the kill switch effective by default, with automatic triggers and persisted risk state. See G-6, G-7.
7. Harden the ML filter: NaN output must reject, and the filter must be built from settings. See G-8, G-9, G-23.
8. Tighten the testnet URL guard to an exact host match. See G-10.
9. Replace Telegram's in-memory client with a real transport and test it. See G-15.
10. Close the owner-input items in BRD §8 ([brd-silverbot.md](brd-silverbot.md)) and the open unknowns. See G-29, G-30.

## 2. Claim & Reference Audit

Claims checked against code at the reconciled commit. "Verified?" is Yes, Partial or No.

| Claim (source) | Verified? | Evidence |
|---|---|---|
| Default mode is paper, LIVE_TRADING=false (README.md:23-25) | Yes | Defaults in `config/settings.py:68-71`; Dockerfile ENV and compose force paper and LIVE_TRADING false. `.env.example` itself does not load (D-2). |
| Live trading only after the readiness checklist passes (README.md:221, ARCHITECTURE.md:547-556, PROGRESS.md:272) | Partial | Live is blocked unconditionally at config load; no code consults any readiness report (D-10, G-2). The block is safe but the described gate does not exist. |
| Run backtest, paper and demo with `python main.py` (README.md:332-351) | No | `main.py:14-50` ignores mode and exits 0 (D-1, G-3). |
| `pip install -r requirements.txt` (README.md:302) | No | No such file; `dependencies = []` in `pyproject.toml:10` (D-40, G-25). |
| Slippage and spread are modelled conservatively (BACKTESTING.md:194, 210) | No | Defaults are 0.0 bps (D-5, G-11). |
| Walk-forward, Monte Carlo, sensitivity and multi-symbol backtests (README.md Phase 3, BACKTESTING.md:45-55) | No | Not present (D-6, G-12). |
| Risk limits capped at 0.5% per trade (RISK_POLICY.md:99-121) | Partial | Enforced only by demo-mode config checks; `RiskConfig` accepts up to 5% risk per trade (validation ceiling; default 0.5%; `risk/models.py:18,29`) and is not wired to settings (D-11, H-5, G-5). |
| Kill switch is mandatory (AGENTS.md, RISK_POLICY.md:61, 139) | Partial | Implemented as a file check; inert by default (D-12, H-9, G-6). |
| ML can only approve, reject or reduce risk (AGENTS.md, ML_MODEL.md) | Yes | `ml/filter.py` returns approve, reject or a multiplier in (0,1]. Caveat: a NaN probability approves (H-1, G-8). |
| ML filter is configurable by environment (ML_MODEL.md:322-331) | No | Keys parsed but never wired (D-4, G-9). |
| Telegram alerts work (DEPLOYMENT.md:7-11, 285, 336-337) | No | Protocol and in-memory client only (D-3, G-15). |
| Demo/testnet mode (PROGRESS.md:286, CONFIGURATION.md:198-201) | Partial | Config rules, 18-check demo readiness and URL guard exist; all network I/O is a stub (D-46, G-3, G-13). |
| PROGRESS "Completed" list (roadmap, concept, strategy choice, ML-as-filter, documentation files) | Yes | Planning items only; no code claim is made there. The phase sections later in PROGRESS.md are covered by the TODO.md rows below. |
| PROGRESS "Current phase: Phase 9.5 demo/testnet readiness implemented" (PROGRESS.md:7) | Partial | Readiness checker, config rules and tests exist; no demo runtime (G-3). |
| PROGRESS "Live trading is not approved" (PROGRESS.md:82-98) | Yes | Consistent with config rejection and empty evidence (G-1). |
| TODO.md checkbox [x] Phase 1: scaffold, config loader and validation, adapter interface, storage, tests | Yes | Present; 16 config tests. |
| TODO.md checkbox [x] "Add historical data fetcher" (TODO.md Phase 1) | Partial | Wrapper over a stub that raises NotImplementedError (D-8, G-13). |
| TODO.md checkbox [x] "Add pyproject.toml or requirements.txt" | Partial | `pyproject.toml` exists with no runtime dependencies (G-25). |
| TODO.md checkbox [x] Phase 2 strategy items (sessions, swings, liquidity, sweep, FVG, displacement, MSS, HTF bias, engine, score) | Yes | Present with tests; caveats in G-18 and G-19. |
| TODO.md checkbox [x] Phase 3 backtesting items | Partial | Engine, costs, journal, equity curve and metrics exist; walk-forward and several metrics do not (D-6, D-25 to D-32, G-12, G-20). |
| TODO.md checkbox [x] Phase 4 risk items (sizing, limits, kill switch) | Partial | 14 gates exist; unwired and inert defaults (G-5, G-6, G-7). |
| TODO.md checkbox [x] "Add live market stream", "Add WebSocket reconnect", "Add REST fallback" (TODO.md Phase 5) | No | No WebSocket; polling skeleton depends on the stubbed fetch (S-4, S-5, G-13). |
| TODO.md checkbox [x] "Add Telegram alerts", status alerts, error alerts (TODO.md:66, 86-87) | No | No transport, `error()` never called (D-47, G-15). |
| TODO.md checkbox [x] "Add daily paper report", daily and weekly report (TODO.md:67, 88-89) | Partial | Builders exist, no caller (D-48, G-16). |
| TODO.md checkbox [x] "Add structured logging" (TODO.md:84) | Partial | Only the audit log is JSON (D-81, G-16). |
| TODO.md checkbox [x] "Add dashboard" (TODO.md:90) | Partial | JSON export builder only (D-49, G-16). |
| TODO.md checkbox [x] Phase 6 ML items (dataset, features, split, training, calibration, promotion, registry, filter, rollback) | Partial | Components exist and are tested; not wired, no shipped model, promotion not enforced (D-4, D-36, D-37, G-9, G-22). |
| TODO.md checkbox [x] Phase 8 deployment items (Dockerfile, compose, script, systemd, logrotate, VPS instructions) | Partial | Files exist; the container runs the stub and loops; user never created (D-1, D-50, H-4, G-3, G-26). |
| TODO.md checkbox [x] Phase 9 and 9.5 readiness and demo items | Yes | Checkers, report export and tests exist; reports are existence-only (H-2, G-2). |
| TODO.md checkbox [ ] Phase 9 evidence items (backtest passes, OOS passes, paper stable, kill switch tested, Telegram tested, API key secured, withdrawals disabled, readiness passes) | Yes (open) | Correctly unchecked; none can be ticked today (G-1, G-6, G-15). |
| Test inventory: 19 files, 108 tests | Yes | Counted by `^def test_` grep over `tests/`. |

### 2.1 References Integrity

| Reference | Status | Evidence |
|---|---|---|
| Binance Futures production base URL `https://fapi.binance.com` | Verified in code at `exchange/binance_futures.py:17` | Constant only; no request is ever sent. |
| Binance Futures testnet URL `https://testnet.binancefuture.com` | Verified in code at `exchange/binance_futures.py:18`; guard at `config/settings.py:345-347` and `exchange/binance_futures.py:74-78` | Guard is a substring match (D-13, G-10). |
| Binance Futures REST and WebSocket endpoints, request signing, rate limits | Open | No endpoint path, signing or WebSocket code exists (`exchange/binance_futures.py:32-33`, S-3). Must be verified against Binance documentation when implemented (RFC-004 or SDD §4.2 and §4.3). |
| Telegram Bot API (`sendMessage`, bot token, chat id) | Open | No code references the Telegram API host; `monitoring/telegram.py` defines a Protocol and an in-memory client only (S-30). Config keys `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are validated in `config/settings.py:146-148` but never used by the alerter. |

## 3. Gap Analysis

Status values: Open (answerable from code or work), Planned (roadmap item not built), Owner input required.

| G-# | Gap | Impact | Lands in (doc §) | Status |
|---|---|---|---|---|
| G-1 | Evidence reports are empty: `reports/backtest_report.json`, `reports/out_of_sample_validation_report.json`, `reports/paper_trading_report.json` are 0 bytes (D-86, H-2). No strategy performance number exists. | HIGH. No edge claim, no live decision possible. | BRD §7 (success metrics), PRD §3 PRD-F2, QAD §3 | Open |
| G-2 | Readiness is unreliable and unused: "exists" check passes 0-byte files (H-2); live-ready needs settings the app refuses to load (H-3); no code consults any readiness report (D-10, S-26). | HIGH. A green report would be meaningless; the described live gate does not exist. | SDD (exchange and readiness), CLR §2, RFC-004, PRD §3 PRD-F8 | Open |
| G-3 | Entrypoint is a startup-only stub: no mode dispatch, no backtest, paper or demo runtime; supervisors restart-loop it (D-1, D-46, H-4, S-8, S-9, S-10, S-25). | HIGH. Nothing can be run end to end; deployment loops. | SDD (runtime wiring), OPS, PRD §3 PRD-F4, PRD-F5, PRD-F11 | Open |
| G-4 | `.env.example` fails `load_config` as shipped (D-2, H-14). | HIGH. First-run configuration error for the owner. | SDD (configuration), OPS | Open |
| G-5 | Risk limits not unified: Settings limits never reach `RiskConfig`; `RiskConfig` accepts up to 5% risk per trade (validation ceiling; default 0.5%; `risk/models.py:18,29`) vs the documented 0.5% cap (D-11, H-5). | HIGH. Position sizing can exceed the documented cap. | SDD (risk engine), RFC-002, PRD §3 PRD-F3 | Open |
| G-6 | Kill switch inert by default, existence-only, no automatic trigger, no position close, no reset tooling (D-12, D-22, H-9, S-18, D-80). | HIGH. The mandatory safety stop does not stop anything unless manually armed. | SDD (risk engine), RFC-002, QAD §3 | Open |
| G-7 | Risk state (daily loss, consecutive losses, trade count) is in memory; restart resets it (H-11). | HIGH. Loss limits can be evaded by a restart or the H-4 loop. | SDD (risk engine), RFC-002 | Open |
| G-8 | NaN model probability becomes 1.0 and approves a signal (H-1). | HIGH. Broken model output approves trades (risk engine still applies). | AIA §2, SDD (ML), QAD §3 | Open |
| G-9 | ML filter is not wired to settings (D-4, S-22, S-21), and no model is shipped (S-23). | MEDIUM. Safe (filter disabled) but the documented control does not work. | AIA §1, §2, SDD (ML), PRD §3 PRD-F6 | Open |
| G-10 | Testnet URL guard is a substring match; lookalike hosts pass (D-13). | HIGH. Latent (no network I/O yet) but weakens the testnet-only gate. | SDD (exchange), CLR §2 | Open |
| G-11 | Backtest slippage and spread default to 0 bps (D-5, H-7). | HIGH. Results are flattered unless the caller overrides. | SDD (backtest), BRD §7, QAD §3 | Open |
| G-12 | Validation missing: no walk-forward, Monte Carlo, sensitivity, multi-symbol or pass/fail criteria; the out-of-sample split helper is unwired and the final test set is not enforced (D-6, D-33, S-10, S-11). | HIGH. Cannot demonstrate out-of-sample performance; overfitting risk unchecked. | SDD (backtest and validation), QAD §3, PRD §3 PRD-F2 | Open |
| G-13 | Market data is stubbed: historical fetch raises NotImplementedError; no WebSocket; polling skeleton depends on the stub; no normaliser, quality report or gap detection; polling may yield a forming candle (D-7, D-8, H-12, S-1, S-3 to S-7). | HIGH. No real data can enter the bot. | SDD (data and exchange), PRD §3 PRD-F4, PRD-F10, SDD §4.4 | Open |
| G-14 | Storage is smaller than described: one file, seven tables, `signals` and `trades` unused, no candle read, no migrations (D-9, D-34, D-35, S-14). | MEDIUM. Backtests cannot load stored candles; no signal or trade history. | SDD (data and storage), PRD §3 PRD-F10 | Open |
| G-15 | Telegram has no real transport and is not wired; `error()` and daily report never called (D-3, D-47, S-30). | HIGH for operations. No alerting exists, which the readiness checklist requires. | SDD (monitoring), OPS, PRD §3 PRD-F7 | Open |
| G-16 | Monitoring is unwired: daily, weekly, journal and dashboard builders have no caller; app log is plain text (D-48, D-49, D-81, S-31, S-32). | MEDIUM. No reports produced in operation. | SDD (monitoring), OPS, PRD §3 PRD-F7 | Open |
| G-17 | Exchange order placement, cancellation, signing and account endpoints are stubs; no live executor (S-2, S-3, S-20). | Planned. Required before any live or demo order flow. | PRD §3 PRD-F5, PRD-F12, RFC-004, SDD §4.2 and §4.3, CLR §2 | Planned |
| G-18 | Strategy config is never built from settings; sessions and parameters are hard-coded defaults (D-14, H-6, S-15). | MEDIUM. Documented configurability does not exist. | SDD (strategy), PRD §3 PRD-F1 | Open |
| G-19 | Strategy gaps: swing-only liquidity, no invalidation, no spread, ATR or news filters, crude HTF bias, differing MSS and scoring definitions, unreachable code branches (D-15 to D-19, S-16, S-17). | MEDIUM. Behaviour differs from the documented strategy; edge unproven. | SDD (strategy), PRD §3 PRD-F1 | Open |
| G-20 | Backtest metrics and exports incomplete: no `daily_summary.csv`, median R, largest and average win and loss, symbol and risk-hit metrics, per-session drawdown; only four exit reasons; no trailing stop, session-end exit, funding or gap fills (D-25 to D-32, S-12, S-13). | MEDIUM. Evidence reports will be thinner than planned. | SDD (backtest), QAD §3 | Open |
| G-21 | Execution gaps: paper only; stop and take-profit only; no stale-order cancel, partial fills or gap-through-stop; pending-order reservation can leak risk capacity (D-23, D-24, S-19, H-10). | MEDIUM. Paper results may be optimistic. | SDD (execution), PRD §3 PRD-F4 | Open |
| G-22 | ML pipeline gaps: no entry point, calibration report-only, promotion criteria narrower and not enforced on the registry, 23 features, name-based leakage control, no purge or embargo, possible HTF lookahead (D-36 to D-39, D-68 to D-76, S-21, S-24, U-6). | MEDIUM. Any trained model would be unvalidated. | AIA §1, §2, SDD (ML) | Open |
| G-23 | Pickle model artifact load is arbitrary code execution if the registry or artifacts are untrusted (H-8). | MEDIUM. Safe while artifacts are self-generated and local. | AIA §2, CLR §2 | Open |
| G-24 | Configuration quirks: `MODE` overrides `TRADING_MODE`, root yaml keys after a section are ignored, `risk.engine_enabled` ignored, readiness env sources differ, DEMO_TRADING promotes paper, risk limits unchecked outside demo (D-41 to D-45, D-77 to D-79, S-28). | MEDIUM. Silent misconfiguration risk. | SDD (configuration), OPS | Open |
| G-25 | Dependencies undeclared: no `requirements.txt`; `dependencies = []`; scikit-learn optional and undeclared (D-40, S-29, U-13). | MEDIUM. Fresh installs and CI may differ from the tested environment. | SDD (build and dependencies), OPS | Open |
| G-26 | Deployment gaps: `silverbot` user never created, no compose healthcheck, no container hardening or systemd sandboxing, hard-coded `/opt/silver-bot`, bind-mount ownership unverified (D-50, D-83, S-33, U-9, U-12). | MEDIUM. Deployment steps will fail or run with excess privilege. | OPS, SDD (deployment), PRD §3 PRD-F11 | Open |
| G-27 | Health check validates configuration only and the live branch is unreachable; defined only in the Dockerfile (S-27, D-82). | LOW. Healthy status does not mean the bot works. | OPS, SDD (deployment) | Open |
| G-28 | Test gaps: no tests for NaN model output, stale model, corrupt artifact, `main()`, `health.py`, `prepare-host.sh` or logrotate (H-13, S-34). | MEDIUM. The riskiest paths are untested. | QAD §3, §4 | Open |
| G-29 | Open code-answerable unknowns: U-5 (scripts building non-default configs), U-6 (HTF lookahead in ML dataset), U-7 (strategy lookahead), U-8 (tzdata in deployment), U-9 (bind-mount UID), U-10 (`.env.example` completeness), U-11 (CONFIGURATION.md completeness), U-12 (compose version), U-13 (sklearn tests in CI), U-14 (newer ML docs under `docs/`), U-15 (other consumers of AppConfig fields), U-16 (real `.env` behaviour; not opened by design), U-17 (callers of `from_config`), U-18 (None session names), U-19 (kill-switch file semantics documentation), U-20 (secret scan outside git). U-21 is resolved (risk multiplier bounded to (0,1]). | MEDIUM. Each could hide a defect; none is answered by current evidence. | SDD (per topic), QAD §3, OPS | Open |
| G-30 | Owner input required: capital and risk budget, target instruments, tolerance for drawdown, success criteria, jurisdiction, intended venue account, and the owner-only unknowns U-1 (is the restart loop intentional), U-2 (config.yaml in container), U-3 (who builds `MLFilterConfig`), U-4 (reconnect policy configuration). Collected as the owner input register in BRD §8 ([brd-silverbot.md](brd-silverbot.md)). | HIGH for planning. Numeric targets and limits cannot be set without the owner. | BRD §8 | Owner input required |
| G-31 | LOW-severity documentation drift D-51 to D-85 (file layouts, field names, option lists, metric columns, image names, log globs). | LOW. Documentation only; closed when the canonical docs are written. | SDD, AIA, OPS (per D-# Resolved in line) | Open |
| G-32 | Uncovered test scenarios; register in QAD §3.8 ([qad-silverbot.md](qad-silverbot.md)). Behaviours the PRD and RFCs state that no test pins and no other gap tracks: quality-score and reward-to-risk rejection in the strategy, the NO_TRADE-needs-a-reason construction error, partial take profit and breakeven, backtest determinism, audit-write failure handling, ML filter probability clamping and registry file errors. | MEDIUM. These paths run in operation but a regression would pass the suite. | QAD §3.8 | Open |

Coverage check: each row shows which stubs (S-#), drift findings (D-#) and hazards (H-#) a gap covers. Every HIGH drift finding (D-1 to D-13, D-86) maps to a HIGH gap row.

| G-# | Covers |
|---|---|
| G-1 | D-86, H-2 |
| G-2 | D-10, H-2, H-3, S-26 |
| G-3 | D-1, D-46, H-4, S-8, S-9, S-10, S-25 |
| G-4 | D-2, H-14 |
| G-5 | D-11, H-5 |
| G-6 | D-12, D-22, D-80, H-9, S-18 |
| G-7 | H-11 |
| G-8 | H-1 |
| G-9 | D-4, S-21, S-22, S-23 |
| G-10 | D-13 |
| G-11 | D-5, H-7 |
| G-12 | D-6, D-33, S-10, S-11 |
| G-13 | D-7, D-8, H-12, S-1, S-3, S-4, S-5, S-6, S-7 |
| G-14 | D-9, D-34, D-35, S-14 |
| G-15 | D-3, D-47, S-30 |
| G-16 | D-48, D-49, D-81, S-31, S-32 |
| G-17 | S-2, S-3, S-20 |
| G-18 | D-14, H-6, S-15 |
| G-19 | D-15 to D-19, S-16, S-17 |
| G-20 | D-25 to D-32, S-12, S-13 |
| G-21 | D-23, D-24, H-10 (LOW, grouped), S-19 |
| G-22 | D-36 to D-39, D-68 to D-76, S-21, S-24 |
| G-23 | H-8 |
| G-24 | D-41 to D-45, D-77 to D-79, S-28 |
| G-25 | D-40, S-29 |
| G-26 | D-50, D-83, S-33 |
| G-27 | D-82, S-27 |
| G-28 | H-13, S-34 |
| G-29 | U-5 to U-20 (open unknowns) |
| G-30 | U-1 to U-4 and missing owner inputs (BRD §8) |
| G-31 | D-51 to D-85 (LOW drift not named in another row) |
| G-32 | Test scenarios with no S/D/H finding (PRD-stated behaviour with no test); see QAD §3.8 |

## 4. Assumption Stress-Test

| Assumption | What would falsify it | Current evidence |
|---|---|---|
| The Silver Bullet strategy has a statistical edge on the chosen instrument | A cost-inclusive out-of-sample backtest with expectancy at or below zero, or results that vanish under walk-forward or small parameter changes | None. The backtest, out-of-sample and paper reports are 0 bytes (G-1). The engine exists and is tested on synthetic data only; no edge is claimed. |
| The fee and slippage model is realistic | Paper or demo fills that cost more than the model, or results that flip sign when slippage and spread are raised | Fees match Binance-style maker 0.0002 and taker 0.0005 defaults (`backtest/models.py:32-33`), but slippage and spread default to 0 in backtests (G-11). Paper executor defaults of 1 bp each are untested against real fills. Funding is not modelled (G-20). |
| The 1-minute timeframe is appropriate | Edge that disappears after realistic latency and costs on 1m, or signals whose frequency makes fees dominate | The default `TIMEFRAME` is 1m (`config/settings.py:75`). No evidence either way (Open). Fee drag on a 1m scalping style is the main concern. |
| Testnet (demo) behaves like live | Different liquidity, spreads, fills, rate limits or order-rejection behaviour between testnet and the production venue | None. No network code exists (G-13, G-17); the testnet is generally a thin, unrepresentative book, so it can validate plumbing but not performance. |
| The ML filter adds value | Filtered trades show no better expectancy than unfiltered trades on a held-out set, or calibration is poor | None. No model is shipped (S-23); the filter is disabled and unwired (G-9). ML stays optional and can only reduce risk or reject. |

## 5. Feasibility & Scope

- **Scope:** personal use by the owner; one instrument by default (BTCUSDT); research, backtesting, paper and demo first. Live trading is `Planned, blocked` and out of scope for this release (PRD-F12).
- **Feasible now:** hardening what exists (G-4 to G-8, G-10, G-11), producing evidence with the existing backtest engine on historical data supplied by the owner (G-1), and writing the canonical docs.
- **Larger work:** a real runtime (G-3), real data access (G-13), Telegram transport (G-15), validation suite (G-12). These are new code and need their own plans (Planned).
- **Dependencies on the owner:** historical data source and capital figures (G-30). No cost, schedule or headcount estimate is made; none is available (Open).
- **Out of scope for this pass:** all code, test, config and deploy changes. This pass writes documents only.

## 6. Risk & Compliance Pre-flight

- **Trading risk:** leverage up to 3x is the documented cap (`src/silver_bot/risk/models.py:25`); the bot must never trade without a stop loss, average down or use martingale (AGENTS.md rules; stop-loss requirement is enforced by the risk engine gates). Details in RFC-002 (risk and kill switch) and RISK sections of SDD.
- **Compliance:** personal trading on the owner's own account; jurisdiction and tax treatment are Owner input required (G-30). Venue terms of use, API-key withdrawal restrictions and key handling are tracked in CLR §2.
- **AI/ML risk:** ML is a filter only; NaN handling (G-8), pickle loading (G-23) and leakage (G-22) are tracked in AIA §2.
- **Security:** no secrets in the repository; `.env` is never committed; the readiness secret scan exists but its behaviour outside git is Open (U-20, G-29).
- **Operational:** restart loop and in-memory risk state (G-3, G-7) must be fixed before any unattended run.

## 7. Blocking Questions

Owner-facing only. Answers go to the owner input register, BRD §8 ([brd-silverbot.md](brd-silverbot.md)).

1. What capital will the bot trade on paper first and, eventually, live; and what loss would make you stop entirely?
2. Which instruments and timeframe should the first evidence run use (the code defaults to BTCUSDT on 1m)?
3. What would count as success for the strategy (for example minimum expectancy, maximum drawdown, minimum number of out-of-sample trades)?
4. Where will historical data come from, and how far back should the backtest go?
5. Is the container restart loop after `main()` exits intentional (U-1), and should `config.yaml` be present in the container (U-2)?
6. Which component should build the ML filter configuration from settings (U-3), and how should stream reconnection be configured (U-4)?
7. Which jurisdiction and exchange account will apply if live trading is ever enabled?
8. Do you accept that live trading stays blocked until every fix in section 1 is closed and non-empty evidence reports exist?

## Self-Check

- [x] The verdict is one of PROCEED, PROCEED WITH FIXES or STOP, and each fix points at a `G-#`.
- [x] Every STUB S-1 to S-34 and every HIGH or MEDIUM hazard maps to a `G-#` row (see the coverage check under section 3).
- [x] Every unknown tagged open (U-5 to U-20) is listed in G-29; owner unknowns U-1 to U-4 are in G-30 pointing to BRD §8.
- [x] The empty evidence reports are a HIGH gap (G-1) and no performance claim is made anywhere in this document.
- [x] External references (Binance Futures URLs, Telegram Bot API) are each marked Verified in code at file:line or Open.
- [x] References to other suite documents are links to existing files.
- [ ] Every `G-#` has been closed or re-scoped in its landing document (open until those documents exist).
