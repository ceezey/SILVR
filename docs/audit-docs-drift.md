# Docs vs Code Drift Audit (AUDIT)

**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Version:** 0.1
**Owner:** Cian Jake Francisco
**Status:** Draft
**Last updated:** 2026-10-09
**Last reconciled:** 2026-10-08 against code at commit `62037d1`; the batch 1 **Resolved:** lines are checked against `70ccaec`; the batch 2 **Resolved:** lines (D-1, D-4, D-33, D-46, H-4) are checked 2026-10-09 against `099085b`; the H-4 **Resolved:** line is re-checked 2026-10-09 against `5c781fc` (exit 2 no longer restarts)

This audit records findings, not decisions. It compares the old root documents (README.md, AGENTS.md, ARCHITECTURE.md, BACKTESTING.md, CONFIGURATION.md, DEPLOYMENT.md, ML_MODEL.md, RISK_POLICY.md, STRATEGY_NOTES.md, PROGRESS.md, TODO.md) with the code at the reconciled commit. Code wins: where they disagree, the finding states what the code does. Each finding closes in the canonical doc named on its **Resolved in** line; until that doc is written the finding stays open. Finding ids `D-1` to `D-86` are frozen and cited by later documents. Severity: HIGH weakens or fakes a safety gate or makes a core claim false; MEDIUM misleads results or operations; LOW is cosmetic or contained. Counts: 14 HIGH, 37 MEDIUM, 35 LOW (86 total). Code paths are relative to `src/silver_bot/` unless they start with a root filename. Code hazards that contradict no old document are listed separately under "Code hazards (not doc drift)". Two registers follow the hazards: the stub register (S-1 to S-34) and the unknowns register (U-1 to U-21); the ids are cited by other suite documents. Findings and hazards fixed in code after the reconciled commit carry a **Resolved:** line naming the fix commit; the Old doc said and Code does lines stay as recorded at `62037d1`.


## HIGH

### D-1. Entrypoint is a startup-only stub; docs describe a running bot

- **Old doc said:** README.md:332 `TRADING_MODE=backtest ... python main.py` runs a backtest; README.md:338 runs paper trading; README.md:351 starts demo mode; DEPLOYMENT.md:267 service starts the bot which "defaults to paper mode"; DEPLOYMENT.md:346-357 paper ready when "bot runs continuously", "daily report works"
- **Code does:** `main.py:14-50` ignores mode, initialises SQLite, writes bot_started and bot_stopped to logs/audit.jsonl and returns 0; no exchange, stream, strategy, backtest or order code runs; the `bot` compose service therefore exits and restarts (docker-compose.yaml:31-32)
- **Resolved in:** OPS (runbook, container and service behaviour) and SDD (entrypoint and runtime wiring); PRD-F11 status in PRD section 3
- **Resolved:** Partial, `099085b` (G-3 entrypoint batch 2, with `e5baec7`, `f84557e` and `f6bc017`). `main()` now dispatches on the mode (`main.py:83-91`): backtest mode loads Binance kline CSV files from `--candles` and runs `run_backtest`, which writes six reports and returns 0 (`main.py:94-112`, `backtest/runner.py:60-124`); paper and demo log and audit `mode_unavailable` and return 78 (`main.py:25-26,89-91`); compose `backtest` and `research` pass `--candles /app/data/candles` (`docker-compose.yaml:73,84`) and the `bot` service is no longer restarted (H-4). Tests: `tests/test_main.py:42,51,85`. Remaining: no paper or demo runtime (G-13, G-17).

### D-2. `.env.example` fails load_config as written

- **Old doc said:** README.md:23-25 and 268-270, CONFIGURATION.md:9-13, `.env.example:1` "Keep these values for normal paper deployment" with PAPER_TRADING=true, DEMO_TRADING=false
- **Code does:** `.env.example:6-7` sets PAPER_TRADING=false and DEMO_TRADING=true; settings.py:96-97 promotes paper to demo; settings.py:140-141 then raises "BINANCE_API_KEY and BINANCE_API_SECRET are required for demo mode" (executed, confirmed)
- **Resolved in:** SDD (configuration section: keys, load order, validation) and OPS (environment setup)
- **Resolved:** Fixed in `c6d909d` (G-4, HIGH safety fixes batch 1, merged to `dev` at `70ccaec`). `.env.example:6-7` now sets PAPER_TRADING=true and DEMO_TRADING=false; `tests/test_config.py:258` `test_shipped_env_example_loads_as_paper` loads the shipped file as paper mode.

### D-3. Telegram alerts cannot reach a network

- **Old doc said:** DEPLOYMENT.md:7-11 recommended stack "VPS + Docker + systemd + Telegram alerts"; DEPLOYMENT.md:285, 336-337, 353 "Telegram alerts work/tested"
- **Code does:** `monitoring/telegram.py:25-32,96-103` only a Protocol and InMemoryTelegramClient; bot_token never read; `main.py:27-50` never builds an alerter
- **Resolved in:** SDD (monitoring and alerting section) and OPS (alerting runbook); PRD-F7 status in PRD section 3

### D-4. ML env keys have no runtime effect

- **Old doc said:** ML_MODEL.md:322-331 filter configurable via ML_FILTER_ENABLED etc.
- **Code does:** settings parse the keys (settings.py:151-169) but nothing builds `MLFilterConfig` from them; `execution/paper_trading.py:53` uses `MLProbabilityFilter()` (disabled default); only `backtest/models.py:41` references MLFilterConfig
- **Resolved in:** AIA (model lifecycle and filter wiring) and SDD (ML section); PRD-F6 status in PRD section 3
- **Resolved:** Partial, `f84557e` (G-9). `build_backtest_config` builds `MLFilterConfig` from `ML_FILTER_ENABLED`, `ML_REGISTRY_PATH`, `ML_MIN_PROBABILITY` and `ML_REDUCE_RISK_THRESHOLD` for CLI backtests (`backtest/runner.py:50-55`; `tests/test_backtest_runner.py:144`). Remaining: the paper loop still uses `MLProbabilityFilter()` with defaults (`execution/paper_trading.py:53`).

### D-5. Backtest cost defaults are 0 bps

- **Old doc said:** BACKTESTING.md:194, 210 slippage example 1-5 bps, spread 1-3 bps ("conservative")
- **Code does:** `backtest/models.py:34-35` slippage_bps=0.0, spread_bps=0.0 (verified)
- **Resolved in:** SDD (backtest and validation section) and QAD (backtest and validation scenarios); PRD-F2 status in PRD section 3
- **Resolved:** Fixed in `59ed6d5` (G-11, HIGH safety fixes batch 1, merged to `dev` at `70ccaec`). `backtest/models.py:34-35` now defaults to slippage_bps=5.0 and spread_bps=3.0; `tests/test_backtest_engine.py:181` `test_backtest_cost_defaults_are_conservative`. Whether these values match real fills is unverified (no fill data exists).

### D-6. Multi-symbol, multi-session, walk-forward, sensitivity and Monte Carlo do not exist

- **Old doc said:** BACKTESTING.md:45-55 backtester "should support" these; ARCHITECTURE.md:330-331 "Run walk-forward validation", "Run Monte Carlo tests"; ARCHITECTURE.md:339-340 walk_forward.py, monte_carlo.py
- **Code does:** `backtest/engine.py:45` single-run engine; `backtest/validation.py:20-58` only chronological split and sort check
- **Resolved in:** SDD (backtest and validation section) and QAD (backtest and validation scenarios); PRD-F2 status in PRD section 3

### D-7. Data module has no normaliser, quality report or repository

- **Old doc said:** ARCHITECTURE.md:212-214, 218-222 gap detection, quality reports, normalizer.py, quality.py, repository.py
- **Code does:** only `data/fetcher.py` and `data/stream.py` exist
- **Resolved in:** SDD (data and storage section); PRD-F10 status in PRD section 3

### D-8. Historical fetch cannot return data

- **Old doc said:** ARCHITECTURE.md:209 "Fetch historical OHLCV data"
- **Code does:** fetcher is a thin wrapper; `exchange/binance_futures.py:71` raises NotImplementedError "Binance Futures OHLCV network fetching is not implemented in Phase 1" (verified)
- **Resolved in:** SDD (data and storage section); PRD-F10 status in PRD section 3

### D-9. Storage module far smaller than described

- **Old doc said:** ARCHITECTURE.md:389-393 holds orders, performance metrics, audit records; files database.py, models.py, repositories.py, migrations.py
- **Code does:** one file `storage/sqlite.py`; seven tables; no orders or metrics table; no migrations; `signals` and `trades` have no writer
- **Resolved in:** SDD (data and storage section); PRD-F10 status in PRD section 3

### D-10. Live gate claims; readiness never consulted

- **Old doc said:** ARCHITECTURE.md:547-556 live requires mode==live, LIVE_TRADING, PAPER_TRADING false, readiness, no-withdraw key, kill switch inactive; README.md:221, 367 live only after readiness checklist; PROGRESS.md:272 "live trading blocked unless all readiness checks pass in the report"
- **Code does:** `config/settings.py:104-107` blocks live unconditionally; no code reads any readiness report; `exchange/base.py:44-47`
- **Resolved in:** SDD (exchange and readiness section) and CLR (live-trading controls); PRD-F5, PRD-F8 and PRD-F12 in PRD section 3

### D-11. Risk caps not unified

- **Old doc said:** RISK_POLICY.md:50-62 enforced set; RISK_POLICY.md:99-121 MAX_RISK_PER_TRADE <= 0.005
- **Code does:** `risk/models.py:29` RiskConfig allows up to 0.05; Settings risk limits (demo-only checks, settings.py:186-190) never wired into RiskConfig (`backtest/engine.py:41`, `execution/paper_trading.py:49`)
- **Resolved in:** SDD (risk engine and kill switch section) and RFC-002 (risk and kill switch); PRD-F3 status in PRD section 3
- **Resolved:** Partial, `5e4acc5` (G-5, HIGH safety fixes batch 1, merged to `dev` at `70ccaec`). `RiskConfig` rejects risk_per_trade outside (0, 0.005] (`risk/models.py:10,32-33`); `load_config` rejects MAX_RISK_PER_TRADE outside (0, 0.005] in every mode (`config/settings.py:180-181`); `build_risk_engine` maps MAX_RISK_PER_TRADE, MAX_DAILY_LOSS, MAX_LEVERAGE and the kill-switch path into `RiskConfig` (`risk/factory.py:15-28`). Remaining: no runtime path calls `build_risk_engine` until the G-3 entrypoint exists; the backtest and paper engines still build their own `RiskConfig`; MAX_DAILY_LOSS and MAX_LEVERAGE bounds stay demo-only (`config/settings.py:191-194`).

### D-12. Kill switch inert by default

- **Old doc said:** RISK_POLICY.md:61, 139, AGENTS.md "kill switch validation" mandatory
- **Code does:** `risk/models.py:26` kill_switch_path None; `execution/paper_trading.py:49` default engine has no path
- **Resolved in:** SDD (risk engine and kill switch section) and RFC-002 (risk and kill switch); PRD-F3 status in PRD section 3
- **Resolved:** Partial, `08c81ad` and `5e4acc5` (G-6, HIGH safety fixes batch 1, merged to `dev` at `70ccaec`). `load_config` rejects KILL_SWITCH_ENABLED=true with a blank KILL_SWITCH_PATH in every mode (`config/settings.py:174-175`); `build_risk_engine` passes the path when enabled (`risk/factory.py:26`). Remaining: `RiskConfig.kill_switch_path` still defaults to None (`risk/models.py:29`) and no runtime path calls `build_risk_engine` until G-3.

### D-13. Testnet URL check is substring

- **Old doc said:** CONFIGURATION.md:57, 221-222 "rejects production URLs"
- **Code does:** `config/settings.py:345-347`, `exchange/binance_futures.py:74-78` lookalike hosts such as testnet.binancefuture.com.example.org pass the testnet-only guard (re-rated HIGH: weakens a safety gate; latent today because the adapter does no network I/O)
- **Resolved in:** SDD (exchange and readiness section) and CLR (live-trading controls); PRD-F5, PRD-F8 and PRD-F12 in PRD section 3
- **Resolved:** Fixed in `0a76564` (G-10, HIGH safety fixes batch 1, merged to `dev` at `70ccaec`). One guard, `config/settings.py:348-365` `is_binance_futures_testnet_url`, passes only scheme `https`, hostname exactly `testnet.binancefuture.com` (case-insensitive), no userinfo and port 443 or none; `exchange/binance_futures.py:13,39` imports it. Tests: `tests/test_exchange.py:98,117,121`, `tests/test_config.py:244`.

### D-86. Evidence reports are 0 bytes yet readiness reports them as present

- **Old doc said:** `reports/live_readiness_report.json` (generated 2026-06-15) lists `backtest_report_exists`, `out_of_sample_validation_report_exists` and `paper_trading_report_exists` as `"passed": true` ("Found reports\<name>.json"); README.md:221 and PROGRESS.md:272 make live trading conditional on that evidence
- **Code does:** `reports/backtest_report.json`, `reports/out_of_sample_validation_report.json` and `reports/paper_trading_report.json` are all 0 bytes; `readiness.py:150-165` checks existence only (see H-2); no backtest, out-of-sample or paper result has ever been recorded
- **Resolved in:** QAD (strategy evidence section), BRD §7 (success metrics), SDD (exchange and readiness section) and CLR (live-trading controls); PRD-F2 and PRD-F8 in PRD section 3
- **Resolved:** Partial, `88220e6` (G-2, HIGH safety fixes batch 1, merged to `dev` at `70ccaec`). The three report checks now fail an empty, unreadable, non-JSON or non-object file (`readiness.py:150-177`), so a 0-byte report no longer passes. Remaining: the three reports are still 0 bytes and no evidence has been recorded (G-1); the check does not validate report content beyond "is a JSON object".


## MEDIUM

### D-14. Sessions not config-driven

- **Old doc said:** STRATEGY_NOTES.md:41-61 sessions "stored in config", YAML `silver_bullet_sessions`
- **Code does:** `strategy/sessions.py:11-15` hardcoded DEFAULT_SESSIONS; no code builds SilverBulletStrategyConfig (`backtest/engine.py:39`, `execution/paper_trading.py:48`)
- **Resolved in:** SDD (strategy engine section); PRD-F1 status in PRD section 3

### D-15. No `use_htf_bias` flag

- **Old doc said:** STRATEGY_NOTES.md:443 `use_htf_bias = true`
- **Code does:** `strategy/silver_bullet.py:193` always applies bias, falls back to execution candles
- **Resolved in:** SDD (strategy engine section); PRD-F1 status in PRD section 3

### D-16. MSS definition differs

- **Old doc said:** STRATEGY_NOTES.md:345-347 break of a recent lower high after sweep
- **Code does:** `strategy/structure.py:68-76` last BUY_SIDE swing, not restricted to lower highs or post-sweep
- **Resolved in:** SDD (strategy engine section); PRD-F1 status in PRD section 3

### D-17. Scoring weights differ

- **Old doc said:** STRATEGY_NOTES.md:381-389 "Liquidity sweep quality: 20", "Spread/volatility condition: 5"
- **Code does:** `strategy/scoring.py:26` liquidity constant 20; `:40` volatility 5 whenever ATR>0; spread ignored
- **Resolved in:** SDD (strategy engine section); PRD-F1 status in PRD section 3

### D-18. No trade invalidation logic

- **Old doc said:** STRATEGY_NOTES.md:397-410 invalidation rules
- **Code does:** none in `strategy/`
- **Resolved in:** SDD (strategy engine section); PRD-F1 status in PRD section 3

### D-19. No spread, ATR-regime, news, open-trade no-trade filters

- **Old doc said:** STRATEGY_NOTES.md:412-431
- **Code does:** only the gates in `strategy/silver_bullet.py:67-209`
- **Resolved in:** SDD (strategy engine section); PRD-F1 status in PRD section 3

### D-20. Direction enum value

- **Old doc said:** ARCHITECTURE.md:478-484 LONG / SHORT / NONE
- **Code does:** `models.py:14-16` NO_TRADE
- **Resolved in:** SDD (strategy engine section); PRD-F1 status in PRD section 3

### D-21. Signal fields differ

- **Old doc said:** ARCHITECTURE.md:457-476 signal_id, risk_reward, ml_probability, status, created_at, reason
- **Code does:** `strategy/models.py:170-188` risk_reward_ratio, generated_at, explanation; no signal_id, ml_probability, status
- **Resolved in:** SDD (strategy engine section); PRD-F1 status in PRD section 3

### D-22. Risk module does not trigger kill switch

- **Old doc said:** ARCHITECTURE.md:273 "Trigger kill switch"
- **Code does:** `risk/kill_switch.py:8-17` read-only file-exists check
- **Resolved in:** SDD (risk engine and kill switch section) and RFC-002 (risk and kill switch); PRD-F3 status in PRD section 3
- **Resolved:** Partial, `08c81ad` (G-6, HIGH safety fixes batch 1, merged to `dev` at `70ccaec`). `KillSwitch.trip` writes the file (`risk/kill_switch.py:53-60`); the engine trips it on the daily-loss and consecutive-loss limits (`risk/engine.py:83,86,129`). Remaining: no position close (G-21) and no reset tooling beyond deleting the file.

### D-23. Execution responsibilities overstated

- **Old doc said:** ARCHITECTURE.md:295-299 live orders, partial fills, rejected orders, cancel stale orders
- **Code does:** paper only; `execution/paper_executor.py:110-132`, `execution/__init__.py:1-4`
- **Resolved in:** SDD (execution section); PRD-F4 status in PRD section 3

### D-24. Trade management is stop/TP only in execution

- **Old doc said:** ARCHITECTURE.md:298 manage entries, stop loss, take profit
- **Code does:** partial TP and breakeven only in `backtest/engine.py:299-352`; `execution/trade_management.py:9-33`
- **Resolved in:** SDD (execution section); PRD-F4 status in PRD section 3

### D-25. daily_summary.csv not produced

- **Old doc said:** BACKTESTING.md:320-329
- **Code does:** `backtest/reporting.py:20-25` four files only
- **Resolved in:** SDD (backtest and validation section) and QAD (backtest and validation scenarios); PRD-F2 status in PRD section 3

### D-26. Required metrics missing

- **Old doc said:** BACKTESTING.md:361-384 median_r, largest/average win/loss
- **Code does:** `backtest/metrics.py:30-46` absent; streaks named max_consecutive_*
- **Resolved in:** SDD (backtest and validation section) and QAD (backtest and validation scenarios); PRD-F2 status in PRD section 3

### D-27. Per-session metrics lack max_drawdown

- **Old doc said:** BACKTESTING.md:398-406
- **Code does:** `backtest/metrics.py:73-79`
- **Resolved in:** SDD (backtest and validation section) and QAD (backtest and validation scenarios); PRD-F2 status in PRD section 3

### D-28. No symbol-specific metrics

- **Old doc said:** BACKTESTING.md:409-420
- **Code does:** not computed
- **Resolved in:** SDD (backtest and validation section) and QAD (backtest and validation scenarios); PRD-F2 status in PRD section 3

### D-29. No risk-hit metrics

- **Old doc said:** BACKTESTING.md:422-433
- **Code does:** not computed
- **Resolved in:** SDD (backtest and validation section) and QAD (backtest and validation scenarios); PRD-F2 status in PRD section 3

### D-30. Exit reasons limited to four

- **Old doc said:** BACKTESTING.md:305-317 partial_take_profit, session_end, manual_exit, kill_switch, opposite_signal, invalidated_setup
- **Code does:** `backtest/models.py:17-23` stop_loss, take_profit, breakeven_stop, end_of_data
- **Resolved in:** SDD (backtest and validation section) and QAD (backtest and validation scenarios); PRD-F2 status in PRD section 3

### D-31. Unsupported simulation behaviours

- **Old doc said:** BACKTESTING.md:152-172 trailing stop, session-end exit, market/confirmation entries, daily/consecutive/max-trades
- **Code does:** none in engine; limits only through injected risk engine (`backtest/engine.py:157-166`)
- **Resolved in:** SDD (backtest and validation section) and QAD (backtest and validation scenarios); PRD-F2 status in PRD section 3

### D-32. Stop move not recorded

- **Old doc said:** BACKTESTING.md:299
- **Code does:** `backtest/engine.py:357-358` silent
- **Resolved in:** SDD (backtest and validation section) and QAD (backtest and validation scenarios); PRD-F2 status in PRD section 3

### D-33. Final test set not enforced

- **Old doc said:** BACKTESTING.md:13-22, 126
- **Code does:** `backtest/validation.py:23-46` split helper only; not called by engine
- **Resolved in:** SDD (backtest and validation section) and QAD (backtest and validation scenarios); PRD-F2 status in PRD section 3
- **Resolved:** Partial, `f84557e` (G-12). `run_backtest` calls `chronological_split` (0.6 / 0.2 / 0.2), runs each segment in a fresh engine, tunes nothing and records `parameters_tuned: false` (`backtest/runner.py:76-98`; `tests/test_backtest_runner.py:75`). Remaining: no code stops a caller tuning on the final test set.

### D-34. No Parquet, no candle load

- **Old doc said:** ARCHITECTURE.md:209, 211 save to Parquet or SQLite, load for backtesting
- **Code does:** `storage/sqlite.py:117` save only; no candle SELECT
- **Resolved in:** SDD (data and storage section); PRD-F10 status in PRD section 3

### D-35. Signals and trades never stored

- **Old doc said:** ARCHITECTURE.md:387-389
- **Code does:** `storage/sqlite.py:41-61` tables unused; writes go to paper_trades (:165)
- **Resolved in:** SDD (data and storage section); PRD-F10 status in PRD section 3

### D-36. Promotion criteria narrower

- **Old doc said:** ML_MODEL.md:289-296 OOS improvement, drawdown, trade count, calibration
- **Code does:** `ml/promotion.py:73-182` accuracy, test degradation, Brier, sample count only
- **Resolved in:** AIA (model lifecycle and filter wiring) and SDD (ML section); PRD-F6 status in PRD section 3

### D-37. Promotion not enforced on registry

- **Old doc said:** ML_MODEL.md:380-391
- **Code does:** `ml/registry.py:40-116` set_active and register_model(active_status=True) need no promotion result. Safety note: ML can only approve unchanged, reject or reduce risk and never bypasses the risk engine, so an unpromoted model cannot raise risk; kept MEDIUM
- **Resolved in:** AIA (model lifecycle and filter wiring) and SDD (ML section); PRD-F6 status in PRD section 3

### D-38. Fewer features than documented

- **Old doc said:** ML_MODEL.md:86-161 liquidity, FVG, displacement, MSS, HTF bias, spread, volatility regime
- **Code does:** `ml/features.py:35-59` 23 features
- **Resolved in:** AIA (model lifecycle and filter wiring) and SDD (ML section); PRD-F6 status in PRD section 3

### D-39. Leakage control is name-based

- **Old doc said:** ML_MODEL.md:198-214
- **Code does:** `ml/features.py:148-157` keyword check; `ml/dataset.py:87-90` HTF candles unsliced
- **Resolved in:** AIA (model lifecycle and filter wiring) and SDD (ML section); PRD-F6 status in PRD section 3

### D-40. requirements.txt missing

- **Old doc said:** README.md:302 `pip install -r requirements.txt`
- **Code does:** no file; `pyproject.toml:10` `dependencies = []`
- **Resolved in:** SDD (configuration section: keys, load order, validation) and OPS (environment setup)

### D-41. Safe-defaults key names not real

- **Old doc said:** README.md:268-278 MAX_CONSECUTIVE_LOSSES, MAX_TRADES_PER_DAY, USE_ML_FILTER, ALLOW_MARKET_ORDERS, REQUIRE_STOP_LOSS
- **Code does:** not read by load_config; real names ML_FILTER_ENABLED, STOP_LOSS_REQUIRED
- **Resolved in:** SDD (configuration section: keys, load order, validation) and OPS (environment setup)

### D-42. MODE overrides TRADING_MODE

- **Old doc said:** CONFIGURATION.md:45 MODE "Alias for TRADING_MODE"
- **Code does:** `config/settings.py:94-95` MODE wins over any source
- **Resolved in:** SDD (configuration section: keys, load order, validation) and OPS (environment setup)

### D-43. Root yaml keys after a section are ignored

- **Old doc said:** CONFIGURATION.md:96-110; config.example.yaml:10-11; config.yaml:6-7
- **Code does:** `config/settings.py:286-300` section persists, so `database_path` becomes TRADING_DATABASE_PATH (ignored); defaults coincide
- **Resolved in:** SDD (configuration section: keys, load order, validation) and OPS (environment setup)

### D-44. yaml `risk.engine_enabled` ignored

- **Old doc said:** CONFIGURATION.md:130-136; config.example.yaml:22
- **Code does:** flattens to RISK_ENGINE_ENGINE_ENABLED; alias only RISK_ENGINE_ENABLED (settings.py:328)
- **Resolved in:** SDD (configuration section: keys, load order, validation) and OPS (environment setup)

### D-45. Readiness env sources

- **Old doc said:** CONFIGURATION.md:74, 69-82, 403-427; `.env.example:31-32`
- **Code does:** `readiness.py:74,168-187` reads only process env, no boolean defaults; demo_readiness reads `.env` (demo_readiness.py:51-53)
- **Resolved in:** SDD (configuration section: keys, load order, validation) and OPS (environment setup)

### D-46. Demo mode not real

- **Old doc said:** CONFIGURATION.md:198-201; PROGRESS.md:286
- **Code does:** adapter does no network I/O; app never builds an adapter (`exchange/binance_futures.py:71`, `main.py:14-50`)
- **Resolved in:** SDD (exchange and readiness section) and CLR (live-trading controls); PRD-F5, PRD-F8 and PRD-F12 in PRD section 3
- **Resolved:** Partial, `099085b` (G-3). Demo mode no longer exits 0 as if it had run: `main()` logs and audits `mode_unavailable` (`mode not available yet: needs market data (G-13)`) and returns 78 (`main.py:89-91`; `tests/test_main.py:51` `test_demo_mode_exits_78`). Remaining: the adapter still does no network I/O and nothing builds it at runtime (G-13, G-17).

### D-47. Telegram items marked done in TODO.md

- **Old doc said:** TODO.md:66, 86-87 [x] alerts, status alerts, error alerts
- **Code does:** error() never invoked; no real transport (`monitoring/telegram.py:90`)
- **Resolved in:** SDD (monitoring and alerting section) and OPS (alerting runbook); PRD-F7 status in PRD section 3

### D-48. Daily report marked done but unwired

- **Old doc said:** TODO.md:67, 88 [x]
- **Code does:** builders exist (`monitoring/reports.py:18,52`); no caller
- **Resolved in:** SDD (monitoring and reporting section); PRD-F7 status in PRD section 3

### D-49. Dashboard is JSON export only

- **Old doc said:** TODO.md:90 [x] "Add dashboard"
- **Code does:** `monitoring/dashboard.py:10-33`
- **Resolved in:** SDD (monitoring and reporting section); PRD-F7 status in PRD section 3

### D-50. silverbot user never created

- **Old doc said:** DEPLOYMENT.md:230-288 systemd and VPS steps
- **Code does:** unit runs `User=silverbot Group=docker` (`deploy/systemd/silver-bot.service:15-16`); `deploy/scripts/prepare-host.sh:1-13` does not create it
- **Resolved in:** OPS (deployment runbook) and SDD (deployment section); PRD-F11 status in PRD section 3


## LOW

### D-51. Candle close_time optional

- **Old doc said:** ARCHITECTURE.md:441-455 required
- **Code does:** `models.py:47` optional
- **Resolved in:** SDD (strategy engine section); PRD-F1 status in PRD section 3

### D-52. scoring.py unlisted

- **Old doc said:** ARCHITECTURE.md:243-254
- **Code does:** `strategy/scoring.py` exists
- **Resolved in:** SDD (strategy engine section); PRD-F1 status in PRD section 3

### D-53. Sweep needs prior close

- **Old doc said:** STRATEGY_NOTES.md:249-253
- **Code does:** `strategy/liquidity.py:64,76` also requires previous close on the correct side
- **Resolved in:** SDD (strategy engine section); PRD-F1 status in PRD section 3

### D-54. Displacement definition

- **Old doc said:** STRATEGY_NOTES.md:316-341 volume, structure break, creates FVG
- **Code does:** `strategy/displacement.py:73-77` body/ATR/close-extreme only
- **Resolved in:** SDD (strategy engine section); PRD-F1 status in PRD section 3

### D-55. Counter-bias flag name

- **Old doc said:** STRATEGY_NOTES.md:373 "reversal mode"
- **Code does:** `strategy/models.py:167` allow_counter_bias
- **Resolved in:** SDD (strategy engine section); PRD-F1 status in PRD section 3

### D-56. Fallback target

- **Old doc said:** STRATEGY_NOTES.md:143-145, 211-212 minimum 2R
- **Code does:** `strategy/silver_bullet.py:174` uses configurable minimum_rr
- **Resolved in:** SDD (strategy engine section); PRD-F1 status in PRD section 3

### D-57. Target sources

- **Old doc said:** STRATEGY_NOTES.md:134-139 previous session/day highs
- **Code does:** `strategy/liquidity.py:96-108` swings only
- **Resolved in:** SDD (strategy engine section); PRD-F1 status in PRD section 3

### D-58. Entry options

- **Old doc said:** STRATEGY_NOTES.md:96-105 options A-D
- **Code does:** `strategy/silver_bullet.py:160` FVG midpoint only
- **Resolved in:** SDD (strategy engine section); PRD-F1 status in PRD section 3

### D-59. Stop options

- **Old doc said:** STRATEGY_NOTES.md:113-121 options A-C
- **Code does:** `strategy/silver_bullet.py:161-165` swept price +/- buffer only
- **Resolved in:** SDD (strategy engine section); PRD-F1 status in PRD section 3

### D-60. Risk file layout

- **Old doc said:** ARCHITECTURE.md:277-282 position_sizing.py, limits.py, validators.py
- **Code does:** engine.py, kill_switch.py, models.py
- **Resolved in:** SDD (risk engine and kill switch section) and RFC-002 (risk and kill switch); PRD-F3 status in PRD section 3

### D-61. Execution file layout

- **Old doc said:** ARCHITECTURE.md:305-311 executor.py, live_executor.py, orders.py, fills.py
- **Code does:** paper_executor.py, paper_trading.py, models.py, trade_management.py
- **Resolved in:** SDD (execution section); PRD-F4 status in PRD section 3

### D-62. ML reduce-risk bound

- **Old doc said:** RISK_POLICY.md:90 can only shrink
- **Code does:** paper loop applies multiplier unclamped (`execution/paper_trading.py:252-259`); bounded by MLFilterConfig validation (0,1] (`ml/filter.py:42-43`); backtest clamps [0,1]
- **Resolved in:** AIA (model lifecycle and filter wiring) and SDD (ML section); PRD-F6 status in PRD section 3

### D-63. Stop distance units

- **Old doc said:** RISK_POLICY.md:130-132
- **Code does:** `risk/models.py:19`, `risk/engine.py:54` absolute price units
- **Resolved in:** SDD (risk engine and kill switch section) and RFC-002 (risk and kill switch); PRD-F3 status in PRD section 3

### D-64. simulator.py

- **Old doc said:** ARCHITECTURE.md:337
- **Code does:** simulation inside engine.py
- **Resolved in:** SDD (backtest and validation section) and QAD (backtest and validation scenarios); PRD-F2 status in PRD section 3

### D-65. Fill on touch

- **Old doc said:** BACKTESTING.md:229 price trades through entry
- **Code does:** `backtest/engine.py:268` touch fills
- **Resolved in:** SDD (backtest and validation section) and QAD (backtest and validation scenarios); PRD-F2 status in PRD section 3

### D-66. Per-candle loop

- **Old doc said:** BACKTESTING.md:131-148 incremental state
- **Code does:** `backtest/engine.py:106` re-evaluates full prefix
- **Resolved in:** SDD (backtest and validation section) and QAD (backtest and validation scenarios); PRD-F2 status in PRD section 3

### D-67. Trade log columns

- **Old doc said:** BACKTESTING.md:331-358
- **Code does:** CSV also has timeframe and ml_decision (`backtest/models.py:96,117`)
- **Resolved in:** SDD (backtest and validation section) and QAD (backtest and validation scenarios); PRD-F2 status in PRD section 3

### D-68. Baseline models

- **Old doc said:** ML_MODEL.md:167-174 XGBoost/LightGBM
- **Code does:** `ml/training.py:129,176-185` logistic plus optional sklearn RF/GB
- **Resolved in:** AIA (model lifecycle and filter wiring) and SDD (ML section); PRD-F6 status in PRD section 3

### D-69. Metrics

- **Old doc said:** ML_MODEL.md:220-242 PR-AUC, trading metrics
- **Code does:** `ml/training.py:244-252` absent
- **Resolved in:** AIA (model lifecycle and filter wiring) and SDD (ML section); PRD-F6 status in PRD section 3

### D-70. Threshold example

- **Old doc said:** ML_MODEL.md:246-262 0.65 approve
- **Code does:** `ml/filter.py:31,134` 0.60 (ML_MODEL.md:336-339 matches)
- **Resolved in:** AIA (model lifecycle and filter wiring) and SDD (ML section); PRD-F6 status in PRD section 3

### D-71. Registry fields

- **Old doc said:** ML_MODEL.md:268-281 model_version, validation_period, test_period
- **Code does:** `ml/registry.py:14-31` model_id, validation_start/end_date; dates never populated
- **Resolved in:** AIA (model lifecycle and filter wiring) and SDD (ML section); PRD-F6 status in PRD section 3

### D-72. Stored prediction version

- **Old doc said:** ML_MODEL.md:345-355
- **Code does:** `storage/sqlite.py:236` model_version column holds model_id
- **Resolved in:** AIA (model lifecycle and filter wiring) and SDD (ML section); PRD-F6 status in PRD section 3

### D-73. No purge or embargo

- **Old doc said:** ML_MODEL.md:180-196
- **Code does:** `ml/dataset.py:171-183`
- **Resolved in:** AIA (model lifecycle and filter wiring) and SDD (ML section); PRD-F6 status in PRD section 3

### D-74. ML file layout

- **Old doc said:** ARCHITECTURE.md:362-371 train.py, evaluate.py, predict.py
- **Code does:** training.py, calibration.py, promotion.py, filter.py
- **Resolved in:** AIA (model lifecycle and filter wiring) and SDD (ML section); PRD-F6 status in PRD section 3

### D-75. ML responsibilities

- **Old doc said:** ARCHITECTURE.md:353-360 evaluate, load for inference
- **Code does:** no end-to-end pipeline; inference in filter.py
- **Resolved in:** AIA (model lifecycle and filter wiring) and SDD (ML section); PRD-F6 status in PRD section 3

### D-76. ML prediction fields

- **Old doc said:** ARCHITECTURE.md:521-534 prediction_id, model_version
- **Code does:** `ml/filter.py:46-60` no prediction_id
- **Resolved in:** AIA (model lifecycle and filter wiring) and SDD (ML section); PRD-F6 status in PRD section 3

### D-77. Load order wording

- **Old doc said:** PROGRESS.md:119 defaults, .env, yaml, env
- **Code does:** `config/settings.py:67-93` defaults, yaml, .env, env (CONFIGURATION.md:3-5 correct)
- **Resolved in:** SDD (configuration section: keys, load order, validation) and OPS (environment setup)

### D-78. DEMO_TRADING scope

- **Old doc said:** CONFIGURATION.md:49 true only for MODE=demo
- **Code does:** `config/settings.py:96-97,112-115,140-191` applies in any mode and promotes paper
- **Resolved in:** SDD (configuration section: keys, load order, validation) and OPS (environment setup)

### D-79. Live-mode message

- **Old doc said:** CONFIGURATION.md:46; PROGRESS.md:120
- **Code does:** `config/settings.py:99,106-107` effective message is "TRADING_MODE must be one of: backtest, demo, paper"; explicit branch is dead code
- **Resolved in:** SDD (configuration section: keys, load order, validation) and OPS (environment setup)

### D-80. Kill switch directory counts

- **Old doc said:** CONFIGURATION.md:75-76, 351-353
- **Code does:** `readiness.py:221` exists() so a directory counts as active
- **Resolved in:** SDD (configuration section: keys, load order, validation) and OPS (environment setup)

### D-81. Structured logging

- **Old doc said:** TODO.md:84 [x]
- **Code does:** `utils/logging.py:13` plain text; only audit JSONL is JSON
- **Resolved in:** SDD (monitoring and reporting section); PRD-F7 status in PRD section 3

### D-82. Health check undocumented

- **Old doc said:** DEPLOYMENT.md:335
- **Code does:** defined only in `Dockerfile:28-29`; compose has none
- **Resolved in:** OPS (deployment runbook) and SDD (deployment section); PRD-F11 status in PRD section 3

### D-83. Install path implicit

- **Old doc said:** DEPLOYMENT.md:157-161
- **Code does:** unit and logrotate hard-code /opt/silver-bot (`silver-bot.service:9,11`; `logrotate/silver-bot:1`)
- **Resolved in:** OPS (deployment runbook) and SDD (deployment section); PRD-F11 status in PRD section 3

### D-84. Image name

- **Old doc said:** DEPLOYMENT.md:100, 116 ict-silver-bullet-bot
- **Code does:** `docker-compose.yaml:13` silver-bot:local
- **Resolved in:** OPS (deployment runbook) and SDD (deployment section); PRD-F11 status in PRD section 3

### D-85. Log glob

- **Old doc said:** README.md:387 and DEPLOYMENT.md:215-219 mount `logs` for runtime logs; DEPLOYMENT.md:286 installs log rotation, implying application `*.log` files
- **Code does:** only `logs/audit.jsonl` produced (`main.py:29`)
- **Resolved in:** SDD (monitoring and reporting section); PRD-F7 status in PRD section 3


## Code hazards (not doc drift)

These were found while reading code and contradict no old document. Recorded, not fixed: code changes are out of scope for this pass. Each HIGH and MEDIUM hazard has a gap row in [scrutiny-silverbot.md](scrutiny-silverbot.md) section 3. Hazards are closed by a later code-change plan, not by documentation. The HIGH safety fixes batch 1 ([plan](superpowers/plans/2026-10-09-high-safety-fixes.md), merged to `dev` at `70ccaec`) fixed H-1, H-2, H-7 and H-14 and partly fixed H-5, H-9, H-11 and H-13; the G-3 entrypoint batch 2 ([plan](superpowers/plans/2026-10-09-g3-entrypoint.md), code complete on `dev` at `099085b`) fixed H-4; each carries a **Resolved:** line.


### H-1. NaN model probability becomes 1.0 and approves a signal

- **Severity:** HIGH
- **Evidence:** `ml/filter.py:179`: `max(0.0, min(1.0, nan))` evaluates to 1.0 (executed). A broken model output would approve a trade; the risk engine still applies afterwards.
- **Gap row:** G-8 in [scrutiny-silverbot.md](scrutiny-silverbot.md) section 3
- **Status:** Fixed in `8e66054`.
- **Resolved:** `_predict_probability` returns the raw value (`ml/filter.py:193`); `evaluate` rejects a NaN, infinite or out-of-[0, 1] probability with risk_multiplier 0.0, probability None and reason "ML model returned an invalid probability" (`ml/filter.py:134-146`). Tests: `tests/test_ml_probability_filter.py:197` `test_ml_filter_rejects_invalid_probability`, `:210` `test_ml_filter_boundary_probabilities_keep_threshold_logic`. Exceptions raised while loading or calling a model still propagate.


### H-2. Live readiness "report exists" passes a 0-byte file

- **Severity:** HIGH
- **Evidence:** `readiness.py:150-165`; committed `reports/backtest_report.json`, `reports/out_of_sample_validation_report.json` and `reports/paper_trading_report.json` are 0 bytes yet three report checks pass (executed). See also D-86.
- **Gap row:** G-1, G-2 in [scrutiny-silverbot.md](scrutiny-silverbot.md) section 3
- **Status:** Fixed in `88220e6`.
- **Resolved:** `_report_check` (`readiness.py:150-177`) passes only a readable, non-empty file that parses as a JSON object; check names are unchanged. Tests: `tests/test_readiness.py:160` `test_live_readiness_rejects_unusable_report` (empty, whitespace, `not json`, `[]`), `:171` `test_live_readiness_accepts_report_with_utf8_bom`. The reports themselves are still 0 bytes (G-1), so live readiness now fails those three checks.


### H-3. A ready live report needs settings the app refuses to load

- **Severity:** MEDIUM
- **Evidence:** `readiness.py:96-97` requires LIVE_TRADING=true and PAPER_TRADING=false; `config/settings.py:104-105` rejects both. The live readiness report can never be fully green for a loadable configuration.
- **Gap row:** G-2 in [scrutiny-silverbot.md](scrutiny-silverbot.md) section 3
- **Status:** Recorded, not fixed: code changes are out of scope for this pass.


### H-4. Entrypoint exits 0 immediately; supervisors restart it in a loop

- **Severity:** MEDIUM
- **Evidence:** `main.py:50` returns after the start and stop audit events; `docker-compose.yaml:32` (restart: unless-stopped) and `deploy/systemd/silver-bot.service:13` (Restart=always) loop it.
- **Gap row:** G-3 in [scrutiny-silverbot.md](scrutiny-silverbot.md) section 3
- **Status:** Fixed in `f6bc017` and `099085b`; exit 2 added to the no-restart list in `5c781fc`.
- **Resolved:** Paper and demo mode return 78 (`main.py:25,89-91`). The unit runs `docker compose ... up bot --exit-code-from bot`, so systemd sees the bot's exit code instead of compose's 0, and `RestartPreventExitStatus=2 78` stops it restarting on 78 (`deploy/systemd/silver-bot.service:11,15`); compose `bot` has `restart: "no"`, so systemd is the only supervisor (`docker-compose.yaml:32`). Tests: `tests/test_deployment_files.py:61` `test_systemd_propagates_exit_code_and_stops_on_mode_unavailable`, `:68` `test_compose_bot_does_not_self_restart`, `tests/test_main.py:42` `test_paper_mode_exits_78_and_audits`. Since `5c781fc` exit 2 (rejected arguments, configuration or candle data) is not restarted either (`deploy/systemd/silver-bot.service:15`); `Restart=always` still restarts any other code, such as 1 for a crash, every 10 s (`:13-14`).


### H-5. Settings risk limits are not wired into RiskConfig; RiskConfig allows 5% per trade

- **Severity:** HIGH
- **Evidence:** `risk/models.py:29` allows risk_per_trade up to 0.05; `config/settings.py:186-190` limits are checked in demo mode only and never reach RiskConfig. See D-11.
- **Gap row:** G-5 in [scrutiny-silverbot.md](scrutiny-silverbot.md) section 3
- **Status:** Partial, `5e4acc5`.
- **Resolved:** `RiskConfig` caps risk_per_trade at 0.005 (`risk/models.py:10,32-33`); `load_config` caps MAX_RISK_PER_TRADE at 0.005 in every mode (`config/settings.py:180-181`); `build_risk_engine` (`risk/factory.py:15-28`) wires the settings caps into `RiskConfig`. Remaining: nothing calls `build_risk_engine` at runtime until G-3. Tests: `tests/test_risk_engine.py:129,134,138,162`, `tests/test_config.py:228`.


### H-6. Strategy config is never built from settings

- **Severity:** MEDIUM
- **Evidence:** `backtest/engine.py:39` and `execution/paper_trading.py:48` call `SilverBulletStrategyEngine()` with defaults everywhere.
- **Gap row:** G-18 in [scrutiny-silverbot.md](scrutiny-silverbot.md) section 3
- **Status:** Recorded, not fixed: code changes are out of scope for this pass.


### H-7. Default slippage and spread are 0 in backtests, flattering results

- **Severity:** MEDIUM
- **Evidence:** `backtest/models.py:34-35`. See D-5.
- **Gap row:** G-11 in [scrutiny-silverbot.md](scrutiny-silverbot.md) section 3
- **Status:** Fixed in `59ed6d5`.
- **Resolved:** `backtest/models.py:34-35` defaults are slippage_bps=5.0 and spread_bps=3.0; `tests/test_backtest_engine.py:181` `test_backtest_cost_defaults_are_conservative`. A caller can still pass 0.0 explicitly.


### H-8. Pickle artifact load is arbitrary code execution if registry or artifacts are untrusted

- **Severity:** MEDIUM
- **Evidence:** `ml/registry.py:126-131`.
- **Gap row:** G-23 in [scrutiny-silverbot.md](scrutiny-silverbot.md) section 3
- **Status:** Recorded, not fixed: code changes are out of scope for this pass.


### H-9. Kill switch checks file existence only, is inert by default, never auto-triggers and does not close positions

- **Severity:** HIGH
- **Evidence:** `risk/kill_switch.py:11-17`; `execution/paper_trading.py:49` builds a default engine with no path. See D-12 and D-22.
- **Gap row:** G-6 in [scrutiny-silverbot.md](scrutiny-silverbot.md) section 3
- **Status:** Partial, `08c81ad`.
- **Resolved:** `KillSwitch.is_active` fails closed: active when the path exists (file or directory), when `os.stat` raises any `OSError` other than not-found, or when the nearest existing ancestor is not a directory (`risk/kill_switch.py:22-51`). `trip` writes `{"reason", "tripped_at"}` JSON and keeps the first reason (`risk/kill_switch.py:53-60`); the engine trips on the daily-loss and consecutive-loss limits (`risk/engine.py:83,86,129`). Remaining: the engine default path is still None outside `build_risk_engine`, which has no runtime caller until G-3; no position close; no reset tooling beyond deleting the file ([ops-silverbot.md](ops-silverbot.md)).


### H-10. Pending order reservation leaks risk capacity if never filled

- **Severity:** LOW
- **Evidence:** `backtest/engine.py:205,220-221`; `execution/paper_trading.py:267`.
- **Gap row:** G-21 in [scrutiny-silverbot.md](scrutiny-silverbot.md) section 3
- **Status:** Recorded, not fixed: code changes are out of scope for this pass.


### H-11. Risk state is in memory only; a restart resets daily-loss and consecutive-loss counters

- **Severity:** HIGH
- **Evidence:** `risk/models.py:47-63`. Combined with the H-4 restart loop, restarts would reset those gates repeatedly.
- **Gap row:** G-7 in [scrutiny-silverbot.md](scrutiny-silverbot.md) section 3
- **Status:** Partial, `2d7f713`.
- **Resolved:** `storage/sqlite.py:117-125` adds the single-row `risk_state` table; `save_risk_state` and `load_risk_state` (`storage/sqlite.py:261-319`) persist it and raise `RiskStateError` on an unreadable row. `RiskManagementEngine` loads it at construction, saves after `reserve_trade`, `release_trade` and a day roll, and rejects every request with "Risk state could not be loaded; trading halted" if loading fails (`risk/engine.py:28-46,115,127-133`). Remaining: only an engine built with a store persists; `build_risk_engine` attaches one but has no runtime caller until G-3. `open_positions` survives a restart while paper positions do not, so a crash with an open trade needs a manual reset ([ops-silverbot.md](ops-silverbot.md)).


### H-12. Polling stream may yield a still-forming candle once; reconnect wrapper catches only ConnectionError

- **Severity:** MEDIUM
- **Evidence:** `data/stream.py:64,107-111`.
- **Gap row:** G-13 in [scrutiny-silverbot.md](scrutiny-silverbot.md) section 3
- **Status:** Recorded, not fixed: code changes are out of scope for this pass.


### H-13. No test covers NaN model output, stale model, corrupt artifact, `main()` or `health.py`

- **Severity:** MEDIUM
- **Evidence:** Test inventory: 19 files, 108 tests (facts sheet 06, test gaps).
- **Gap row:** G-28 in [scrutiny-silverbot.md](scrutiny-silverbot.md) section 3
- **Status:** Partial, `8e66054`.
- **Resolved:** NaN, infinite and out-of-range model output is now tested (`tests/test_ml_probability_filter.py:197`). Stale model, corrupt artifact, `main()` and `health.py` remain untested.


### H-14. `.env.example` fails `load_config` as shipped

- **Severity:** HIGH
- **Evidence:** `.env.example:6-7` sets PAPER_TRADING=false and DEMO_TRADING=true, which `config/settings.py:96-97,140-141` turns into a demo configuration that demands API keys. Same root cause as D-2.
- **Gap row:** G-4 in [scrutiny-silverbot.md](scrutiny-silverbot.md) section 3
- **Status:** Fixed in `c6d909d`.
- **Resolved:** `.env.example:6-7` sets PAPER_TRADING=true and DEMO_TRADING=false; `tests/test_config.py:258` `test_shipped_env_example_loads_as_paper`.


## Stub register (S-#)

Stubs, partial and missing items found while reading the code, with ids as recorded in the fact index. Each row names the gap in [scrutiny-silverbot.md](scrutiny-silverbot.md) section 3 that tracks it.

| S-# | What is stubbed or partial | Evidence (file:line) | Gap (G-#) |
|---|---|---|---|
| S-1 | Binance OHLCV fetch raises NotImplementedError | `exchange/binance_futures.py:71` | G-13 |
| S-2 | Order placement and cancellation always raise OrderPlacementDisabled | `exchange/base.py:44-52` | G-17 |
| S-3 | No request signing, REST, websockets, account endpoints | `exchange/binance_futures.py:32-33` | G-13, G-17 |
| S-4 | No WebSocket stream; no REST fallback except the self-declared skeleton polling class | `data/stream.py:72-78` | G-13 |
| S-5 | Polling stream depends on S-1 and would fail with NotImplementedError (not retried by reconnect wrapper) | `data/stream.py:64,100` | G-13 |
| S-6 | MockMarketDataStream is the only working stream (canned data) | `data/stream.py:31-42` | G-13 |
| S-7 | HistoricalOHLCVFetcher: no pagination, rate limit, retry, gap detection, persistence | `data/fetcher.py:38-44` | G-13 |
| S-8 | `main()` has no mode dispatch, no subcommands, no paper/backtest/demo runtime | `main.py:14-50` | G-3 |
| S-9 | PaperTradingEngine has no production entry point | grep of `src/` (definition `execution/paper_trading.py:31` only) | G-3 |
| S-10 | BacktestEngine, validation suite and fetcher not wired into any entry point | grep of `src/` | G-3 |
| S-11 | Walk-forward, Monte Carlo, sensitivity, multi-symbol, pass/fail criteria absent; OOS split helper unwired | `backtest/validation.py:1-58` | G-12 |
| S-12 | Missing backtest outputs: daily_summary.csv, median/largest/average win-loss, symbol and risk-hit metrics, per-session drawdown | `backtest/reporting.py:20-25`, `backtest/metrics.py:30-46` | G-20 |
| S-13 | Backtest lacks trailing stop, session-end exit, market/confirmation entry, extra exit reasons, funding, gap fills, unrealized drawdown | `backtest/models.py:17-23`, `backtest/engine.py:314,326` | G-20 |
| S-14 | SQLite `signals` and `trades` tables unused; no migrations; no candle read API | `storage/sqlite.py:41-61` | G-14 |
| S-15 | Strategy config not wired to settings | `backtest/engine.py:39`, `execution/paper_trading.py:48` | G-18 |
| S-16 | Strategy: liquidity from swings only; no invalidation; no spread/ATR/news filters; no entry/SL/TP option selectors; crude HTF bias; midnight-spanning sessions unsupported | `strategy/liquidity.py:37`, `strategy/silver_bullet.py:67-209`, `strategy/sessions.py:43-45` | G-19 |
| S-17 | Redundant strategy code: MSS direction check cannot fire; fallback "No complete setup after sweep" effectively unreachable | `strategy/silver_bullet.py:149-150,107` | G-19 |
| S-18 | Risk: no emergency shutdown, no kill-switch trigger/reset tooling, no automatic triggers. Resolved in part: automatic trip added in `08c81ad` (`risk/kill_switch.py:53-60`); shutdown and reset tooling still absent | `risk/kill_switch.py:8-17` (at `62037d1`) | G-6 |
| S-19 | Execution: no partial TP/breakeven/trailing/time exit; no stale-order cancel/expiry/partial fills; gap-through-stop not modelled; ERROR event never emitted | `execution/trade_management.py:9-33`, `execution/models.py:22` | G-21 |
| S-20 | Live executor and live trading: absent, rejected by config | `config/settings.py:104-107` | G-17 |
| S-21 | ML offline pipeline (dataset, train, calibrate, promote, register) has no entry point | `ml/__init__.py:7-46` | G-9, G-22 |
| S-22 | ML settings-to-filter wiring missing | `execution/paper_trading.py:53` | G-9 |
| S-23 | No shipped model; `models/` empty | directory listing | G-9 |
| S-24 | Calibration report-only; training emits no test_metrics/calibration; no staleness/drift/regime/alt labels | `ml/calibration.py`, `ml/training.py:218-223` | G-22 |
| S-25 | Demo-mode runtime: config and readiness exist, no runtime | `main.py:14-50` | G-3 |
| S-26 | Live readiness is report-only, not consulted; "report exists" is existence-only. Resolved in part: report content check (non-empty JSON object) added in `88220e6` (`readiness.py:150-177`); still not consulted | `readiness.py:1-5,159` (at `62037d1`) | G-2 |
| S-27 | Health check only validates config; live branch unreachable | `health.py:11-17` | G-27 |
| S-28 | config.yaml parser is a minimal line parser; risk limits unchecked outside demo | `config/settings.py:281-301,170-191` | G-24 |
| S-29 | requirements.txt absent; no runtime dependencies declared (scikit-learn optional and undeclared) | `pyproject.toml:10-15` | G-25 |
| S-30 | Telegram: no real transport; not wired in `main()`; daily_report() and error() never called | `monitoring/telegram.py:9-32,80-91` | G-15 |
| S-31 | Reports (daily, weekly, journal, dashboard JSON) have builders only; no caller; no dashboard UI | `monitoring/reports.py:18,52,92,140`, `monitoring/dashboard.py` | G-16 |
| S-32 | App log is plain text; extra fields not rendered | `utils/logging.py:13` | G-16 |
| S-33 | Deploy hardening missing: compose healthcheck, read_only/cap_drop/limits, systemd sandboxing | `docker-compose.yaml`, `deploy/systemd/silver-bot.service` | G-26 |
| S-34 | Untested: health.py, main.py, prepare-host.sh, logrotate; sheet 06 lists further gaps | sheet 06 "Test gaps" | G-28 |

## Unknowns register (U-#)

Questions the code and old documents do not answer. Tag: owner (only the owner can answer), open (answerable from code, documents or tests), resolved (answered, kept for traceability). Owner unknowns are collected in BRD §8 ([brd-silverbot.md](brd-silverbot.md)).

| U-# | Question | Tag (owner / open / resolved) | Gap (G-#) |
|---|---|---|---|
| U-1 | Is the repeated restart of the `bot` container after `main()` exits intentional? (no doc explains it) | owner | G-30 (owner input, BRD §8 in [brd-silverbot.md](brd-silverbot.md)) |
| U-2 | Is `config.yaml` expected inside the container? (.dockerignore:4 excludes it; Dockerfile does not copy it) | owner | G-30 (owner input, BRD §8 in [brd-silverbot.md](brd-silverbot.md)) |
| U-3 | Which component is intended to build `MLFilterConfig` from `AppConfig` for paper runs? | owner | G-30 (owner input, BRD §8 in [brd-silverbot.md](brd-silverbot.md)) |
| U-4 | How is `ReconnectPolicy` meant to be configured from `AppConfig` (no config key)? | owner | G-30 (owner input, BRD §8 in [brd-silverbot.md](brd-silverbot.md)) |
| U-5 | Does any script outside `src/` (scripts/, root) build non-default strategy, risk or paper-engine configs? | open | G-29 |
| U-6 | Does `higher_timeframe_candles` leak future data into dataset features and labels (dataset passes the full HTF series unsliced)? Needs strategy HTF audit | open | G-29, G-22 |
| U-7 | Is `SilverBulletStrategyEngine.evaluate` free of lookahead internally? | open | G-29 |
| U-8 | Is tzdata guaranteed in deployment (python:3.11-slim; fallback DST path at `strategy/sessions.py:31-33`)? | open | G-29 |
| U-9 | Does the bind-mounted `./data` (mode 700, host owner) work with container user `silverbot` (UID not pinned)? Depends on host UID | open | G-29, G-26 |
| U-10 | Does `.env.example` contain every key referenced by compose and readiness? | open | G-29 |
| U-11 | Is CONFIGURATION.md complete (TODO.md:105)? | open | G-29 |
| U-12 | Does compose `env_file: required: false` need a minimum Compose version? | open | G-29, G-26 |
| U-13 | Do scikit-learn-dependent ML tests run in CI (sklearn is optional)? | open | G-29, G-25 |
| U-14 | Does `docs/` hold newer ML documentation (deliberately not read)? | open | G-29 |
| U-15 | Do other modules consume AppConfig risk_engine_enabled, kill_switch_*, max_*, exchange_name, symbol, timeframe? | open | G-29 |
| U-16 | Does the real `.env` load cleanly and which mode does it select? (not opened by design; demo report 2026-06-15 was ready=true) | open | G-29 |
| U-17 | Does any caller invoke `BinanceFuturesAdapter.from_config` at runtime? | open | G-29 |
| U-18 | Can `signal.session_name` be None in practice (engine falls back to "unknown")? | open | G-29 |
| U-19 | Where are kill-switch file semantics (location, content, KILL_SWITCH_PATH default) documented? | open | G-29 |
| U-20 | Does `.git` presence matter to the secret scan's `_git_tracked_files` when git reports no repository? | open | G-29 |
| U-21 | RESOLVED, kept for traceability: ML `risk_multiplier` is bounded (0,1] by MLFilterConfig validation (`ml/filter.py:42-43`), so the paper loop's unclamped multiply cannot raise risk | resolved | None (resolved) |

## Clean

Areas checked that matched the old documents (no finding raised):

- Backtest fee defaults: BACKTESTING.md:178-183 (maker 0.0002, taker 0.0005) match `backtest/models.py:32-33`.
- AGENTS.md ML rules (ML may approve, reject or reduce risk only) match `ml/filter.py` and the paper loop; an unpromoted model still cannot raise risk (see the D-37 note).
- AGENTS.md risk rules are a subset of the 14 gates in `risk/engine.py:34-92`.
- README.md:387-388 (`.env` is not copied into the image) matches `Dockerfile:15-17`.
- CONFIGURATION.md:3-5 configuration load order (defaults, config.yaml, .env, process env) matches `config/settings.py:67-93`.
- ML_MODEL.md:336-339 default thresholds (0.60 approve, 0.55 reduce) match `ml/filter.py`.
- Safe defaults in the Dockerfile and compose files (paper mode, LIVE_TRADING=false, Telegram off, ML off) match the documented default mode; live trading is rejected at config load (`config/settings.py:104-107`).
- Test inventory: 19 test files and 108 tests, counted by `^def test_` grep; no old document claims a different total.

## Process finding

No automated check existed for docs-vs-code drift before this pass. The old documents drifted through eleven phases of code-first work with PROGRESS.md and TODO.md checkboxes as the only record, and 14 HIGH findings accumulated without a signal. The documentation checker used for this suite (`check_docs.py`: links, leaks, smells, placeholders, voice, trace) covers links, leaks and traceability only, not semantics; it cannot detect that a document describes behaviour the code does not have. Recommended: a reconciliation pass at each phase end, with `Last reconciled` commit hashes updated and this audit re-run. A code-level drift test (for example asserting documented default values against `RiskConfig` and `BacktestConfig`) is Planned, not built.

## Self-Check

- [x] Every `D-n` from D-1 to D-86 has its own `###` heading with Old doc said, Code does and Resolved in lines.
- [x] The empty evidence reports appear as a HIGH finding (D-86) and as hazard H-2.
- [x] Every hazard H-1 to H-14 has severity, evidence and a gap row pointing into [scrutiny-silverbot.md](scrutiny-silverbot.md).
- [x] Severity counts in the opening paragraph (14 HIGH, 37 MEDIUM, 35 LOW) match the headings.
- [x] No bot code, config or test file was changed to produce this audit.
- [x] The stub register has 34 rows (S-1 to S-34) and the unknowns register 21 rows (U-1 to U-21), each pointing at a G-# (owner unknowns at G-30 and BRD §8).
- [ ] Each finding is closed in its named canonical doc (open until those documents are written and reviewed).
