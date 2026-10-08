# Request for Comments (RFC) / Tech Spec

**Title:** Readiness Gates: demo and live readiness checks, evidence files and the conditions before live trading could be proposed
**Project:** Silver Bot (ICT Silver Bullet trading bot)
**RFC ID:** `silverbot-rfc-004`
**Version:** 0.1
**Author:** Cian Jake Francisco
**Status:** Draft
**Last updated:** 2026-10-08
**Last reconciled:** 2026-10-08 against code at commit `62037d1`
**PRD Reference:** [prd-silverbot.md](prd-silverbot.md) PRD-F8 (readiness gates), PRD-F5 (demo/testnet mode), PRD-F12 (live trading, `Planned, blocked`)
**SDD Reference:** [sdd-silverbot.md](sdd-silverbot.md) §3.4 (configuration reference), §4.2 and §4.3 (exchange adapter), §5.1 (live-trading block), §5.2 (secrets handling)

This RFC is the single source of the readiness checks, their pass conditions and failure texts, the required evidence files, and the proposed conditions for ever raising live trading. It replaces the readiness and demo parts of the old `CONFIGURATION.md` and the readiness section of the old `RISK_POLICY.md`. Where the old text and the code disagree, the code wins and the disagreement is cited as a `D-#` or `H-#` finding in [audit-docs-drift.md](audit-docs-drift.md). All `file:line` references are relative to `src/silver_bot/` and describe the code at the reconciled commit.

## 1. Context & Objective

Two checkers produce readiness reports without trading: `silver_bot.demo_readiness` (18 checks, for Binance Futures demo/testnet operation) and `silver_bot.readiness` (15 checks, for live). Both build a list of named checks, set `ready` to true only if every check passes, write a JSON report, and exit 0 when ready or 2 when not (`demo_readiness.py:99-111`, `readiness.py:135-147`).

The aim of a readiness gate is to stop the operator moving to a riskier mode before the evidence and controls exist. As built, the gates do **not** do that:

1. **Advisory only.** No code reads any readiness report. `load_config` and `main` never call either checker. The only live control is the unconditional block at config load (D-10, G-2).
2. **Existence only.** The "report exists" checks accept a 0-byte file. The three evidence reports are 0 bytes yet pass (H-2, D-86, G-1).
3. **Unreachable green.** The live checker requires `LIVE_TRADING=true`, which the application refuses to load (H-3).

Objectives:

1. State every check, its pass condition and its failure text exactly as coded.
2. Record the evidence files the live checker names and what it does and does not verify.
3. Define, as a proposal, the conditions that must all hold before live trading could be proposed (PRD-F12). Live trading stays `Planned, blocked`; nothing here enables it.

No performance claim is made. The three evidence reports are 0 bytes (G-1).

## 2. Proposed Solution, as built

```text
python -m silver_bot.demo_readiness [--output reports/demo_readiness_report.json]
python -m silver_bot.readiness      [--output reports/live_readiness_report.json]
```

Both commands load their inputs, run the checks, call `export_readiness_report` to write `{"ready", "generated_at", "checks": [{"name", "passed", "reason"}]}` with `indent=2`, and return 0 if ready, else 2 (`readiness.py:126-147`, `demo_readiness.py:99-111`). Argument-parser usage errors also exit 2. The readiness code itself states that it only evaluates readiness; it does not enable live trading, connect to an exchange or place orders (`readiness.py:1-5`, `demo_readiness.py:1-5`).

Input sources differ between the two checkers (D-45):

| Checker | Reads | Boolean defaults | Float defaults | Source |
|---------|-------|------------------|----------------|--------|
| Demo | `.env` in the project root (simple loader that skips malformed lines), overlaid by `os.environ`; or only the `environ` mapping when one is passed. `config.yaml` is read only inside check 1 | None: a missing boolean fails with "value is missing" | A missing value counts as the safe limit and passes | `demo_readiness.py:51-53,114-123,274-276,297-307` |
| Live | `os.environ` only, or the passed mapping. It does **not** read `.env` or `config.yaml` | None: a missing boolean fails with "value is missing" | A missing value counts as the safe limit and passes | `readiness.py:74,168-187,279-281` |

Consequence: a value set only in `.env` is seen by the demo checker but not by the live checker, and a value set only in `config.yaml` fails the demo checks 2 to 16 (the yaml file reaches only check 1).

The safe limits used by both checkers are `MAX_RISK_PER_TRADE` 0.005, `MAX_DAILY_LOSS` 0.02 and `MAX_LEVERAGE` 3.0 (`readiness.py:19-21`).

## 3. Technical Details & Contracts

### 3.1 Demo readiness: 18 checks in evaluation order (`demo_readiness.py:55-89`)

`ready` is true only if all 18 pass.

| # | Check name | Pass condition | Failure reason (verbatim) | Source |
|---|-----------|----------------|---------------------------|--------|
| 1 | `demo_config_validation` | `load_config(env_path=root/.env, yaml_path=root/config.yaml, environ=env)` does not raise `ConfigError`; pass text `Demo configuration values are valid` | the `ConfigError` text | `demo_readiness.py:114-123` |
| 2 | `demo_mode_selected` | `MODE` (else `TRADING_MODE` only if the `MODE` key is absent), lower-cased, equals `demo`; pass text `MODE is demo` | `MODE must be demo for Binance Futures testnet operation` | `demo_readiness.py:126-130` |
| 3 | `demo_trading_enabled` | `DEMO_TRADING` is true | boolean failure text (section 3.4) | `demo_readiness.py:58` |
| 4 | `live_trading_disabled` | `LIVE_TRADING` is false | boolean failure text | `demo_readiness.py:59` |
| 5 | `paper_trading_disabled` | `PAPER_TRADING` is false | boolean failure text | `demo_readiness.py:60` |
| 6 | `binance_testnet_enabled` | `BINANCE_TESTNET` is true | boolean failure text | `demo_readiness.py:61` |
| 7 | `binance_testnet_endpoint` | `BINANCE_FUTURES_BASE_URL` is empty (pass text `Using default Binance Futures testnet endpoint`) or `is_binance_futures_testnet_url` is true (pass text `Configured endpoint is Binance Futures testnet`) | `BINANCE_FUTURES_BASE_URL must point to the Binance Futures testnet endpoint in demo mode` | `demo_readiness.py:133-147` |
| 8 | `demo_api_keys_present` | `BINANCE_API_KEY` and `BINANCE_API_SECRET` both non-blank; pass text `Demo API key and secret are present` | `BINANCE_API_KEY and BINANCE_API_SECRET are required for Binance Futures demo/testnet` | `demo_readiness.py:150-157` |
| 9 | `risk_engine_enabled` | `RISK_ENGINE_ENABLED` is true | boolean failure text | `demo_readiness.py:64` |
| 10 | `kill_switch_enabled` | `KILL_SWITCH_ENABLED` is true | boolean failure text | `demo_readiness.py:65` |
| 11 | `kill_switch_path_configured` | `KILL_SWITCH_PATH` non-blank; pass text `KILL_SWITCH_PATH is configured` | `KILL_SWITCH_PATH is required in demo mode` | `demo_readiness.py:160-163` |
| 12 | `kill_switch_not_active` | the resolved kill-switch path does not exist (relative paths resolve against the project root); pass text `Kill switch file is not active` | `KILL_SWITCH_PATH is required before active-state check` (path blank) or `Kill switch file is active; demo readiness is blocked until it is intentionally cleared` | `demo_readiness.py:166-178` |
| 13 | `stop_loss_required` | `STOP_LOSS_REQUIRED` is true | boolean failure text | `demo_readiness.py:68` |
| 14 | `max_risk_per_trade_safe` | `MAX_RISK_PER_TRADE` in `(0, 0.005]` or missing | float failure text (section 3.4) | `demo_readiness.py:69-74` |
| 15 | `max_daily_loss_safe` | `MAX_DAILY_LOSS` in `(0, 0.02]` or missing | float failure text | `demo_readiness.py:75-80` |
| 16 | `max_leverage_safe` | `MAX_LEVERAGE` in `(0, 3.0]` or missing | float failure text | `demo_readiness.py:81-86` |
| 17 | `env_ignored_by_git` | `.gitignore` exists and some stripped line equals exactly `.env`; pass text `.env is listed in .gitignore` | `.gitignore is missing` or `.env must be listed in .gitignore` | `demo_readiness.py:181-188` |
| 18 | `no_committed_secrets` | no file matches any of three secret-shaped patterns; pass text `No secret-looking values found outside private runtime files` | `Potential secret-looking values found outside private runtime files` (the paths are not listed) | `demo_readiness.py:191-222` |

Check 18 scans `git ls-files` when inside a git work tree, else walks the tree. It skips files whose name starts with `.env`, skips any path containing one of `.git .mypy_cache .pytest_cache .ruff_cache .tmp .venv __pycache__ data logs models reports`, skips undecodable files, and flags three patterns: `sk-[A-Za-z0-9_-]{20,}`, `xox[baprs]-[A-Za-z0-9_-]{20,}` and `(api[_-]?secret|api[_-]?key|bot[_-]?token)\s*[:=]\s*["']?[A-Za-z0-9_\-]{24,}` (case-insensitive). Behaviour outside a git work tree is Open (U-20).

### 3.2 Live readiness: 15 checks in evaluation order (`readiness.py:75-118`)

`ready` is true only if all 15 pass.

| # | Check name | Pass condition | Failure reason (verbatim) | Source |
|---|-----------|----------------|---------------------------|--------|
| 1 | `backtest_report_exists` | the file at env `BACKTEST_REPORT_PATH` (default `reports/backtest_report.json`) exists and is a file; pass text `Found <resolved path>` | `Missing required report: <resolved path>. Set BACKTEST_REPORT_PATH to the completed report path.` | `readiness.py:76,150-165` |
| 2 | `out_of_sample_validation_report_exists` | same for env `OOS_VALIDATION_REPORT_PATH` (default `reports/out_of_sample_validation_report.json`) | `Missing required report: <resolved path>. Set OOS_VALIDATION_REPORT_PATH to the completed report path.` | `readiness.py:77-83` |
| 3 | `paper_trading_report_exists` | same for env `PAPER_TRADING_REPORT_PATH` (default `reports/paper_trading_report.json`) | `Missing required report: <resolved path>. Set PAPER_TRADING_REPORT_PATH to the completed report path.` | `readiness.py:84-90` |
| 4 | `risk_engine_enabled` | `RISK_ENGINE_ENABLED` is true | boolean failure text | `readiness.py:91` |
| 5 | `kill_switch_enabled` | `KILL_SWITCH_ENABLED` is true and `KILL_SWITCH_PATH` non-blank; pass text `Kill switch is configured` | `KILL_SWITCH_ENABLED must be true and KILL_SWITCH_PATH must point to the kill-switch file` (flag unparsable or absent), `KILL_SWITCH_ENABLED must be true` (flag false), or `KILL_SWITCH_PATH is required when KILL_SWITCH_ENABLED=true` | `readiness.py:92,190-207` |
| 6 | `kill_switch_not_active` | the resolved kill-switch path does not exist; pass text `Kill switch file is not active` | `KILL_SWITCH_PATH is required before checking whether the kill switch is active` or `Kill switch file is active at <resolved path>; live readiness is blocked until this file is intentionally cleared` | `readiness.py:93,210-227` |
| 7 | `telegram_alerts_tested_or_disabled` | `TELEGRAM_ENABLED` is false (pass text `Telegram is explicitly disabled`), or it is true and `TELEGRAM_ALERTS_TESTED` is true (pass text `Telegram alerts tested`) | `TELEGRAM_ENABLED must be explicitly true or false for readiness` (unset or unparsable) or `Telegram is enabled, so set TELEGRAM_ALERTS_TESTED=true after a real alert test or set TELEGRAM_ENABLED=false` | `readiness.py:94,230-254` |
| 8 | `api_keys_loaded_from_env_only` | `BINANCE_API_KEY` and `BINANCE_API_SECRET` both non-blank in the process environment; pass text `API key and secret are present in the readiness environment` | `BINANCE_API_KEY and BINANCE_API_SECRET must both be present in the process environment; use placeholders only in examples` | `readiness.py:95,257-270` |
| 9 | `live_trading_enabled_intent` | `LIVE_TRADING` is **true** | boolean failure text | `readiness.py:96` |
| 10 | `paper_trading_disabled_for_live` | `PAPER_TRADING` is false | boolean failure text | `readiness.py:97` |
| 11 | `manual_readiness_confirmation` | `READINESS_CHECK_PASSED` is true | boolean failure text | `readiness.py:98` |
| 12 | `withdrawals_disabled_confirmation` | `API_WITHDRAWALS_DISABLED` is true | boolean failure text | `readiness.py:99` |
| 13 | `max_risk_per_trade_safe` | `MAX_RISK_PER_TRADE` in `(0, 0.005]` or missing | float failure text | `readiness.py:100-105` |
| 14 | `max_daily_loss_safe` | `MAX_DAILY_LOSS` in `(0, 0.02]` or missing | float failure text | `readiness.py:106-111` |
| 15 | `max_leverage_safe` | `MAX_LEVERAGE` in `(0, 3.0]` or missing | float failure text | `readiness.py:112-117` |

The check name `kill_switch_enabled` exists in both checkers with different meaning: in demo it is only `KILL_SWITCH_ENABLED` true (check 10); in live it also requires a non-blank path (check 5). The names `risk_engine_enabled`, `kill_switch_not_active`, `max_risk_per_trade_safe`, `max_daily_loss_safe` and `max_leverage_safe` are shared.

Two of these checks assert the owner's word and cannot verify it: `manual_readiness_confirmation` (11) and `withdrawals_disabled_confirmation` (12) pass on an environment string. The code cannot confirm key permissions; no exchange call exists to do so. `telegram_alerts_tested_or_disabled` passes on `TELEGRAM_ALERTS_TESTED=true` with no evidence, and the Telegram client has no network transport (D-3, G-15).

### 3.3 Failure text shared by the checks

Boolean checks (`demo_readiness.py:250-265`, `readiness.py:168-187`). `<x>` is `true` or `false`.

| Case | Live text | Demo text |
|------|-----------|-----------|
| Pass | `<KEY> is <x>` | `<KEY> is <x>` |
| Key missing | `<KEY> must be <x>; value is missing` | `<KEY> must be <x>; value is missing` |
| Not parseable as a boolean | `<KEY> must be a boolean value (<x> required); got <value>` | `<KEY> must be boolean; got <value>` |
| Wrong value | `<KEY> must be <x>; got <value>` | `<KEY> must be <x>; got <value>` |

Accepted true values are `1 true yes y on`; false values are `0 false no n off`, after trimming and lower-casing (`readiness.py:291-299`).

Float checks (`demo_readiness.py:268-283`, `readiness.py:273-288`):

| Case | Live text | Demo text |
|------|-----------|-----------|
| Pass (`0 < value <= limit`, or key missing) | `<KEY>=<value> within safe limit <limit>` | `<KEY> is within safe limit` |
| Not a number | `<KEY> must be numeric` | `<KEY> must be numeric` |
| `value <= 0` | `<KEY> must be greater than 0; got <value>` | `<KEY> must be greater than 0` |
| `value > limit` | `<KEY>=<value> exceeds safe limit <limit>` | `<KEY> exceeds safe limit <limit>` |

### 3.4 Evidence files the live checker names

| Evidence | Default path | Env override | Size in the working tree | What the check verifies | What it does not verify |
|----------|--------------|--------------|--------------------------|-------------------------|--------------------------|
| Backtest report | `reports/backtest_report.json` | `BACKTEST_REPORT_PATH` | 0 bytes | the path exists and is a file | content, size, JSON validity, freshness, any metric |
| Out-of-sample validation report | `reports/out_of_sample_validation_report.json` | `OOS_VALIDATION_REPORT_PATH` | 0 bytes | same | same |
| Paper trading report | `reports/paper_trading_report.json` | `PAPER_TRADING_REPORT_PATH` | 0 bytes | same | same |

Relative paths resolve against the project root (`readiness.py:157-158`). The decision is `resolved.exists() and resolved.is_file()` and nothing else (`readiness.py:159`).

**Recorded flaw (H-2, D-86, G-1, G-2).** A 0-byte file passes. The report `reports/live_readiness_report.json` in the working tree (generated 2026-06-15, `ready` false) lists all three report-exists checks as passed while the three source files are 0 bytes; it is false only because of other checks (kill switch not configured, `LIVE_TRADING` not true, `PAPER_TRADING` not false, no manual confirmation). The same flaw was executed against three 0-byte temporary files and all three checks passed. No backtest, out-of-sample or paper result has ever been recorded, so a green evidence check today would mean nothing. The local `reports/demo_readiness_report.json` (generated 2026-06-15) shows `ready` true from a local environment; it proves the checker ran, not that a demo runtime exists (D-46, G-3).

### 3.5 What stops live trading today (not readiness)

| Control | Behaviour | Source |
|---------|-----------|--------|
| `LIVE_TRADING` true | `ConfigError("LIVE_TRADING=true is rejected in Phase 1")`; no override, no readiness lookup | `config/settings.py:100,104-105` |
| `TRADING_MODE` or `MODE` equal to `live` | rejected by the mode enum parse before the dedicated branch; the dedicated message `TRADING_MODE=live is not supported in Phase 1` is unreachable | `config/settings.py:99,106-107` (D-79) |
| Base `place_order` | always raises `OrderPlacementDisabled("Real order placement is disabled in Phase 1")`; no subclass overrides it | `exchange/base.py:44-47` |
| Base `cancel_order` | always raises `OrderPlacementDisabled("Real order cancellation is disabled in Phase 1")` | `exchange/base.py:49-52` |
| Adapter | no HTTP, no request signing, no endpoint paths; `fetch_ohlcv` raises `NotImplementedError("Binance Futures OHLCV network fetching is not implemented in Phase 1")` | `exchange/binance_futures.py:67-71` |
| Image and compose | `LIVE_TRADING=false` forced; no live service | `Dockerfile:6,31`, `docker-compose.yaml:3-8` |

The old documents described a live gate of mode, flags, readiness report, no-withdraw key and inactive kill switch (D-10). That gate does not exist. The block above is safe but is not that gate.

### 3.6 Demo and testnet rules enforced at config load

These apply whenever `DEMO_TRADING` is true (D-78), not only for `MODE=demo`. A `DEMO_TRADING=true` setting promotes `TRADING_MODE=paper` to `demo` (`config/settings.py:96-97`).

| Rule | `ConfigError` text (verbatim) | Source |
|------|-------------------------------|--------|
| Paper mode needs the paper flag | `PAPER_TRADING must be true when TRADING_MODE=paper` | `config/settings.py:108-109` |
| Demo mode needs the demo flag | `DEMO_TRADING must be true when MODE=demo` | `config/settings.py:110-111` |
| Demo and live together (unreachable, live raises first) | `DEMO_TRADING=true cannot be combined with LIVE_TRADING=true` | `config/settings.py:112-113` |
| Demo and paper together | `PAPER_TRADING must be false when DEMO_TRADING=true` | `config/settings.py:114-115` |
| Demo needs keys | `BINANCE_API_KEY and BINANCE_API_SECRET are required for demo mode` | `config/settings.py:140-141` |
| Keys come as a pair | `BINANCE_API_KEY and BINANCE_API_SECRET must be provided together` | `config/settings.py:136-137` |
| Demo needs testnet | `BINANCE_TESTNET must be true when MODE=demo` | `config/settings.py:142-143` |
| Demo needs a testnet endpoint | `Demo mode requires a Binance Futures testnet endpoint` | `config/settings.py:144-145` |
| Demo needs the risk engine | `RISK_ENGINE_ENABLED must be true in demo mode` | `config/settings.py:178-179` |
| Demo needs the kill switch on | `KILL_SWITCH_ENABLED must be true in demo mode` | `config/settings.py:180-181` |
| Demo needs a kill-switch path | `KILL_SWITCH_PATH is required in demo mode` | `config/settings.py:182-183` |
| Demo needs the stop-loss flag | `STOP_LOSS_REQUIRED must be true in demo mode` | `config/settings.py:184-185` |
| Demo risk cap | `MAX_RISK_PER_TRADE must be greater than 0 and no more than 0.005 in demo mode` | `config/settings.py:186-187` |
| Demo daily-loss cap | `MAX_DAILY_LOSS must be greater than 0 and no more than 0.02 in demo mode` | `config/settings.py:188-189` |
| Demo leverage cap | `MAX_LEVERAGE must be greater than 0 and no more than 3 in demo mode` | `config/settings.py:190-191` |
| Adapter testnet guard | `Demo/testnet mode requires the Binance Futures testnet endpoint` | `exchange/binance_futures.py:38-39` |

**Recorded flaw (D-13, G-10).** The testnet URL guard, in both the config check and the adapter, lower-cases the value and tests that `testnet.binancefuture.com` is a substring (`config/settings.py:345-347`, `exchange/binance_futures.py:74-78`). A lookalike host such as `https://testnet.binancefuture.com.example.org`, or a URL that carries that text in a query string, passes. The adapter applies the guard only when `testnet=True`. The risk is latent today because the adapter does no network I/O. The required behaviour is an exact scheme and host match. This is `Planned`.

**Recorded flaw (D-2, H-14, G-4).** `.env.example` as shipped fails `load_config` with `BINANCE_API_KEY and BINANCE_API_SECRET are required for demo mode`, so demo readiness check 1 fails on a copy of the example file.

### 3.7 Old configuration text: carried and dropped

| Old text (CONFIGURATION.md and RISK_POLICY.md) | Status | Finding |
|-----------------------------------------------|--------|---------|
| Demo needs `MODE=demo`, `DEMO_TRADING=true`, `BINANCE_TESTNET=true`, `LIVE_TRADING=false`, `PAPER_TRADING=false`, testnet endpoint, keys, risk engine, kill switch with a path and inactive file, `STOP_LOSS_REQUIRED=true`, limits at or below 0.005, 0.02 and 3 | Carried; matches the 18 checks and the config-load rules | none |
| "Demo mode rejects production Binance URLs" | Changed: a substring match that accepts lookalike hosts | D-13 |
| `DEMO_TRADING` applies only to `MODE=demo` | Changed: applies in any mode and promotes paper to demo | D-78 |
| Demo is a working testnet mode | Dropped: no network I/O; the app never builds an adapter | D-46, G-3 |
| Live readiness list (three reports, risk engine, kill switch, inactive file, Telegram, keys, `LIVE_TRADING=true`, `PAPER_TRADING=false`, `READINESS_CHECK_PASSED`, `API_WITHDRAWALS_DISABLED`, three limits) | Carried exactly as the 15 checks above | none |
| Readiness reads `.env`-style values | Changed: live readiness reads only process environment | D-45 |
| Kill-switch file "must be absent" | Carried; a directory at the path also counts as active | D-80 |
| Live trading allowed only after the readiness report passes | Dropped as a control: advisory, never consulted, and unreachable green | D-10, H-2, H-3, G-2 |
| `reports/*_report.json` as proof of evidence | Dropped: the three files are 0 bytes | D-86, G-1 |
| "Passing readiness does not place orders" and "the application still rejects live startup" | Carried | none |

## 4. Alternatives Considered

| Alternative | Why not (as built) |
|-------------|--------------------|
| Make readiness a startup gate that the entrypoint and config load consult | The intended design, not built (G-2). `Planned`. |
| Validate evidence content (valid JSON, non-empty, required metrics, thresholds from the BRD, freshness) | Not built (H-2). `Planned`. |
| Reject 0-byte and invalid-JSON evidence files immediately | The smallest fix, not built (H-2). `Planned`. |
| Let live readiness pass without `LIVE_TRADING=true` | The checker asserts live intent, which the app refuses to load (H-3); a separate approval mechanism is needed. `Planned`. |
| Exact scheme-and-host match for the testnet URL | Not built (D-13, G-10). `Planned`. |
| One shared environment source for both checkers | Not built; they differ (D-45). Open. |
| Verify withdrawal permission by an exchange call | Not possible today: no exchange call exists. `Planned`. |

## 5. Safety, Privacy & Performance

**Safety.**

- Neither checker can enable live trading, open a connection or place an order. They read the environment and the file system and write one JSON file.
- The real safety control is the unconditional config-load block and the disabled order methods (section 3.5), not these reports.
- A green report must not be read as permission. Today it would be meaningless: empty evidence passes, owner assertions pass on a string, and the live-ready state is unreachable for a loadable configuration (H-2, H-3).
- Never place real keys in `.env.example`, `config.yaml` or any tracked file. The demo secret scan (check 18) is a backstop that lists no paths and has pattern gaps; it does not replace review.

**Privacy.** The reports contain check names, booleans and reason strings. Reasons can include resolved local file paths (`Found <path>`, kill-switch path) but never key values. The live checker reads `BINANCE_API_KEY` and `BINANCE_API_SECRET` only to test that they are non-blank. The real `.env` was not opened for this RFC (U-16).

**Performance.** Each checker does a handful of file-existence tests, plus, for demo check 18, a read of every tracked text file. No benchmark exists and none is claimed.

**Evidence of behaviour (tests).** 15 readiness tests cover the live and demo checkers, report export and the config rules. The 0-byte pass was executed against temporary files during this reconciliation, but no committed test pins it as a defect, and there is no test that rejects an empty evidence file (G-28).

## 6. Execution Status

| Capability | Status | Evidence |
|-----------|--------|----------|
| Demo readiness checker (18 checks), report export, exit codes | Built | `demo_readiness.py:43-111` |
| Live readiness checker (15 checks), report export, exit codes | Built | `readiness.py:66-147` |
| Demo and live config rules at load | Built | `config/settings.py:96-191` |
| Evidence content validation (non-empty, valid, thresholds) | Planned | H-2, D-86, G-1 |
| Readiness consulted by startup or config load | Planned | D-10, G-2 |
| A live-ready state reachable by a loadable configuration | Planned | H-3 |
| Exact-host testnet check | Planned | D-13, G-10 |
| Demo runtime (an adapter doing network I/O) | Planned | D-46, G-17 |
| Live trading (PRD-F12) | Planned, blocked | Config-load rejection and disabled order methods (section 3.5) |

## 7. Risks & Open Items

### 7.1 Conditions that must all hold before PRD-F12 could be proposed

These are proposals for the owner to accept or change. They do not enable live trading, and no live proposal exists. Meeting them would only allow a proposal to be written; the decision is a separate owner decision recorded as a change record.

1. **Evidence exists and is meaningful.** Non-empty, cost-inclusive backtest and out-of-sample reports that meet the thresholds the BRD defines as BRD-M1 to BRD-M8, and a non-empty paper report from a stable paper run (G-1, G-11, G-12). The readiness check must reject empty or invalid files (H-2).
2. **A runtime exists.** A real entrypoint that dispatches by mode, real market data, and a demo/testnet run against an adapter that does network I/O (G-3, G-13, G-17).
3. **Readiness is meaningful and consulted.** Evidence content is validated, the result gates startup, and the live-ready state is reachable without a config the app rejects (G-2, H-3).
4. **The kill switch is effective.** Armed by default from settings, with automatic triggers on the loss limits, a documented reset and a close-or-reduce action ([RFC-002](rfc-silverbot-risk-kill-switch.md); G-6).
5. **Risk limits are unified and persisted.** One source of truth capped at the documented 0.005 per trade, 0.02 daily loss and 3 leverage, with state surviving a restart (G-5, G-7).
6. **The testnet guard is exact.** Scheme and host match, not a substring (G-10).
7. **Alerting is real and tested.** A working Telegram transport with a recorded alert test (G-15).
8. **Key handling is settled.** Keys only from the environment, withdrawals disabled on the exchange key and confirmed by the owner, no secret in any tracked file.
9. **ML is either off or hardened.** The NaN flaw fixed and the filter wired and tested if used ([RFC-003](rfc-silverbot-ml-filter-gate.md); G-8, G-9).
10. **Owner decisions are recorded.** Capital, risk budget, jurisdiction and venue account (OI-1, OI-6, OI-10 in the BRD), and an explicit written owner approval.

Until all ten hold, PRD-F12 stays `Planned, blocked`.

### 7.2 Open items

| Ref | Item | Status |
|-----|------|--------|
| G-1 | Evidence reports are 0 bytes; no performance statement is possible (D-86, H-2). | Open |
| G-2 | Readiness is unreliable and unused (H-2, H-3, D-10). | Open |
| G-3 | No running runtime; the entrypoint is a startup-only stub (D-1, H-4). | Open |
| G-4 | `.env.example` fails `load_config` as shipped (D-2, H-14). | Open |
| G-10 | Testnet URL guard is a substring match (D-13). | Open |
| G-15 | Telegram has no real transport, so the "alerts tested" check proves nothing (D-3). | Open |
| G-17 | Exchange order placement, signing and account endpoints are stubs. | Planned |
| G-24 | Config quirks that affect readiness inputs: `MODE` overrides `TRADING_MODE`, `DEMO_TRADING` promotes paper, differing readiness env sources (D-42, D-45, D-78). | Open |
| U-20 | Behaviour of the demo secret scan outside a git work tree. | Open |
| Intended venue | Which exchange account and region the owner intends to use. | Owner input required |

## 8. Self-Check

- [x] The demo list has 18 checks and the live list has 15, in code order, with names and failure text copied verbatim.
- [x] The three evidence files and the default and override paths match `readiness.py:76-90`.
- [x] The 0-byte-passes flaw is recorded with H-2, D-86 and G-1, and the unreachable live-ready state with H-3.
- [x] The substring testnet check is recorded with D-13 and G-10.
- [x] Live trading is labelled `Planned, blocked`; the ten conditions in section 7.1 are proposals, not approvals.
- [x] Each carried, changed or dropped old rule in section 3.7 carries a `D-#` or `H-#` where it differs.
- [ ] A readiness gate that validates evidence content and is consulted at startup exists in code (not yet; Planned).
