# Docs vs Code Drift Audit (AUDIT)

**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Version:** 0.1
**Owner:** Cian Jake Francisco
**Status:** Draft
**Last updated:** 2026-10-08
**Last reconciled:** 2026-10-08 against code at commit `62037d1`

This audit records findings, not decisions. It compares the old root documents (README.md, AGENTS.md, ARCHITECTURE.md, BACKTESTING.md, CONFIGURATION.md, DEPLOYMENT.md, ML_MODEL.md, RISK_POLICY.md, STRATEGY_NOTES.md, PROGRESS.md, TODO.md) with the code at the reconciled commit. Code wins: where they disagree, the finding states what the code does. Each finding closes in the canonical doc named on its **Resolved in** line; until that doc is written the finding stays open. Finding ids `D-1` to `D-86` are frozen and cited by later documents. Severity: HIGH weakens or fakes a safety gate or makes a core claim false; MEDIUM misleads results or operations; LOW is cosmetic or contained. Counts: 14 HIGH, 37 MEDIUM, 35 LOW (86 total). Code paths are relative to `src/silver_bot/` unless they start with a root filename. Code hazards that contradict no old document are listed separately under "Code hazards (not doc drift)".


## HIGH

### D-1. Entrypoint is a startup-only stub; docs describe a running bot

- **Old doc said:** README.md:301-304 `TRADING_MODE=backtest ... python main.py` runs a backtest; README.md:306-308 runs paper trading; README.md:334-338 starts demo mode; DEPLOYMENT.md:267 service starts the bot which "defaults to paper mode"; DEPLOYMENT.md:346-357 paper ready when "bot runs continuously", "daily report works"
- **Code does:** `main.py:14-50` ignores mode, initialises SQLite, writes bot_started and bot_stopped to logs/audit.jsonl and returns 0; no exchange, stream, strategy, backtest or order code runs; the `bot` compose service therefore exits and restarts (docker-compose.yaml:31-32)
- **Resolved in:** OPS (runbook, container and service behaviour) and SDD (entrypoint and runtime wiring); PRD-F11 status in PRD section 3

### D-2. `.env.example` fails load_config as written

- **Old doc said:** README.md:23-25 and 268-270, CONFIGURATION.md:9-13, `.env.example:1` "Keep these values for normal paper deployment" with PAPER_TRADING=true, DEMO_TRADING=false
- **Code does:** `.env.example:5-6` sets PAPER_TRADING=false and DEMO_TRADING=true; settings.py:96-97 promotes paper to demo; settings.py:140-141 then raises "BINANCE_API_KEY and BINANCE_API_SECRET are required for demo mode" (executed, confirmed)
- **Resolved in:** SDD (configuration section: keys, load order, validation) and OPS (environment setup)

### D-3. Telegram alerts cannot reach a network

- **Old doc said:** DEPLOYMENT.md:7-11 recommended stack "VPS + Docker + systemd + Telegram alerts"; DEPLOYMENT.md:285, 336-337, 353 "Telegram alerts work/tested"
- **Code does:** `monitoring/telegram.py:25-32,96-103` only a Protocol and InMemoryTelegramClient; bot_token never read; `main.py:27-50` never builds an alerter
- **Resolved in:** SDD (monitoring and alerting section) and OPS (alerting runbook); PRD-F7 status in PRD section 3

### D-4. ML env keys have no runtime effect

- **Old doc said:** ML_MODEL.md:322-331 filter configurable via ML_FILTER_ENABLED etc.
- **Code does:** settings parse the keys (settings.py:151-169) but nothing builds `MLFilterConfig` from them; `execution/paper_trading.py:53` uses `MLProbabilityFilter()` (disabled default); only `backtest/models.py:41` references MLFilterConfig
- **Resolved in:** AIA (model lifecycle and filter wiring) and SDD (ML section); PRD-F6 status in PRD section 3

### D-5. Backtest cost defaults are 0 bps

- **Old doc said:** BACKTESTING.md:194, 210 slippage example 1-5 bps, spread 1-3 bps ("conservative")
- **Code does:** `backtest/models.py:34-35` slippage_bps=0.0, spread_bps=0.0 (verified)
- **Resolved in:** SDD (backtest and validation section) and QAD (backtest and validation scenarios); PRD-F2 status in PRD section 3

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

- **Old doc said:** ARCHITECTURE.md:547-556 live requires mode==live, LIVE_TRADING, PAPER_TRADING false, readiness, no-withdraw key, kill switch inactive; README.md:17-19, 366 live only after readiness checklist; PROGRESS.md:272 "live trading blocked unless all readiness checks pass in the report"
- **Code does:** `config/settings.py:104-107` blocks live unconditionally; no code reads any readiness report; `exchange/base.py:44-47`
- **Resolved in:** SDD (exchange and readiness section) and CLR (live-trading controls); PRD-F5, PRD-F8 and PRD-F12 in PRD section 3

### D-11. Risk caps not unified

- **Old doc said:** RISK_POLICY.md:50-62 enforced set; RISK_POLICY.md:99-121 MAX_RISK_PER_TRADE <= 0.005
- **Code does:** `risk/models.py:29` RiskConfig allows up to 0.05; Settings risk limits (demo-only checks, settings.py:186-190) never wired into RiskConfig (`backtest/engine.py:41`, `execution/paper_trading.py:49`)
- **Resolved in:** SDD (risk engine and kill switch section) and RFC-002 (risk and compliance); PRD-F3 status in PRD section 3

### D-12. Kill switch inert by default

- **Old doc said:** RISK_POLICY.md:142, AGENTS.md "kill switch validation" mandatory
- **Code does:** `risk/models.py:26` kill_switch_path None; `execution/paper_trading.py:49` default engine has no path
- **Resolved in:** SDD (risk engine and kill switch section) and RFC-002 (risk and compliance); PRD-F3 status in PRD section 3

### D-13. Testnet URL check is substring

- **Old doc said:** CONFIGURATION.md:57, 221-222 "rejects production URLs"
- **Code does:** `config/settings.py:345-347`, `exchange/binance_futures.py:74-78` lookalike hosts such as testnet.binancefuture.com.example.org pass the testnet-only guard (re-rated HIGH: weakens a safety gate; latent today because the adapter does no network I/O)
- **Resolved in:** SDD (exchange and readiness section) and CLR (live-trading controls); PRD-F5, PRD-F8 and PRD-F12 in PRD section 3

### D-86. Evidence reports are 0 bytes yet readiness reports them as present

- **Old doc said:** `reports/live_readiness_report.json` (generated 2026-06-15) lists `backtest_report_exists`, `out_of_sample_validation_report_exists` and `paper_trading_report_exists` as `"passed": true` ("Found reports\<name>.json"); README.md:17-19 and PROGRESS.md:272 make live trading conditional on that evidence
- **Code does:** `reports/backtest_report.json`, `reports/out_of_sample_validation_report.json` and `reports/paper_trading_report.json` are all 0 bytes; `readiness.py:150-165` checks existence only (see H-2); no backtest, out-of-sample or paper result has ever been recorded
- **Resolved in:** SDD (exchange and readiness section) and CLR (live-trading controls); PRD-F5, PRD-F8 and PRD-F12 in PRD section 3


## MEDIUM

### D-14. Sessions not config-driven

- **Old doc said:** STRATEGY_NOTES.md:41-61 sessions "stored in config", YAML `silver_bullet_sessions`
- **Code does:** `strategy/sessions.py:11-15` hardcoded DEFAULT_SESSIONS; no code builds SilverBulletStrategyConfig (`backtest/engine.py:39`, `execution/paper_trading.py:48`)
- **Resolved in:** SDD (strategy engine section); PRD-F1 status in PRD section 3

### D-15. No `use_htf_bias` flag

- **Old doc said:** STRATEGY_NOTES.md:444 `use_htf_bias = true`
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
- **Resolved in:** SDD (risk engine and kill switch section) and RFC-002 (risk and compliance); PRD-F3 status in PRD section 3

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

- **Old doc said:** README.md:288-290 `pip install -r requirements.txt`
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

- **Old doc said:** CONFIGURATION.md:74, 69-82, 403-427; `.env.example:30-31`
- **Code does:** `readiness.py:74,168-187` reads only process env, no boolean defaults; demo_readiness reads `.env` (demo_readiness.py:51-53)
- **Resolved in:** SDD (configuration section: keys, load order, validation) and OPS (environment setup)

### D-46. Demo mode not real

- **Old doc said:** CONFIGURATION.md:198-201; PROGRESS.md:286
- **Code does:** adapter does no network I/O; app never builds an adapter (`exchange/binance_futures.py:71`, `main.py:14-50`)
- **Resolved in:** SDD (exchange and readiness section) and CLR (live-trading controls); PRD-F5, PRD-F8 and PRD-F12 in PRD section 3

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
- **Resolved in:** SDD (risk engine and kill switch section) and RFC-002 (risk and compliance); PRD-F3 status in PRD section 3

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
- **Code does:** `risk/models.py:19`, `risk/engine.py:49` absolute price units
- **Resolved in:** SDD (risk engine and kill switch section) and RFC-002 (risk and compliance); PRD-F3 status in PRD section 3

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

- **Old doc said:** README.md:369-390; DEPLOYMENT.md:16 `*.log`
- **Code does:** only `logs/audit.jsonl` produced (`main.py:29`)
- **Resolved in:** SDD (monitoring and reporting section); PRD-F7 status in PRD section 3


## Code hazards (not doc drift)

These were found while reading code and contradict no old document. Recorded, not fixed: code changes are out of scope for this pass. Each HIGH and MEDIUM hazard has a gap row in docs/scrutiny-silverbot.md section 3. Hazards are closed by a later code-change plan, not by documentation.


### H-1. NaN model probability becomes 1.0 and approves a signal

- **Severity:** HIGH
- **Evidence:** `ml/filter.py:179`: `max(0.0, min(1.0, nan))` evaluates to 1.0 (executed). A broken model output would approve a trade; the risk engine still applies afterwards.
- **Gap row:** G-8 in docs/scrutiny-silverbot.md section 3
- **Status:** Recorded, not fixed: code changes are out of scope for this pass.


### H-2. Live readiness "report exists" passes a 0-byte file

- **Severity:** HIGH
- **Evidence:** `readiness.py:150-165`; committed `reports/backtest_report.json`, `reports/out_of_sample_validation_report.json` and `reports/paper_trading_report.json` are 0 bytes yet three report checks pass (executed). See also D-86.
- **Gap row:** G-1, G-2 in docs/scrutiny-silverbot.md section 3
- **Status:** Recorded, not fixed: code changes are out of scope for this pass.


### H-3. A ready live report needs settings the app refuses to load

- **Severity:** MEDIUM
- **Evidence:** `readiness.py:96-97` requires LIVE_TRADING=true and PAPER_TRADING=false; `config/settings.py:104-105` rejects both. The live readiness report can never be fully green for a loadable configuration.
- **Gap row:** G-2 in docs/scrutiny-silverbot.md section 3
- **Status:** Recorded, not fixed: code changes are out of scope for this pass.


### H-4. Entrypoint exits 0 immediately; supervisors restart it in a loop

- **Severity:** MEDIUM
- **Evidence:** `main.py:50` returns after the start and stop audit events; `docker-compose.yaml:32` (restart: unless-stopped) and `deploy/systemd/silver-bot.service:13` (Restart=always) loop it.
- **Gap row:** G-3 in docs/scrutiny-silverbot.md section 3
- **Status:** Recorded, not fixed: code changes are out of scope for this pass.


### H-5. Settings risk limits are not wired into RiskConfig; RiskConfig allows 5% per trade

- **Severity:** HIGH
- **Evidence:** `risk/models.py:29` allows risk_per_trade up to 0.05; `config/settings.py:186-190` limits are checked in demo mode only and never reach RiskConfig. See D-11.
- **Gap row:** G-5 in docs/scrutiny-silverbot.md section 3
- **Status:** Recorded, not fixed: code changes are out of scope for this pass.


### H-6. Strategy config is never built from settings

- **Severity:** MEDIUM
- **Evidence:** `backtest/engine.py:39` and `execution/paper_trading.py:48` call `SilverBulletStrategyEngine()` with defaults everywhere.
- **Gap row:** G-18 in docs/scrutiny-silverbot.md section 3
- **Status:** Recorded, not fixed: code changes are out of scope for this pass.


### H-7. Default slippage and spread are 0 in backtests, flattering results

- **Severity:** MEDIUM
- **Evidence:** `backtest/models.py:34-35`. See D-5.
- **Gap row:** G-11 in docs/scrutiny-silverbot.md section 3
- **Status:** Recorded, not fixed: code changes are out of scope for this pass.


### H-8. Pickle artifact load is arbitrary code execution if registry or artifacts are untrusted

- **Severity:** MEDIUM
- **Evidence:** `ml/registry.py:126-131`.
- **Gap row:** G-23 in docs/scrutiny-silverbot.md section 3
- **Status:** Recorded, not fixed: code changes are out of scope for this pass.


### H-9. Kill switch checks file existence only, is inert by default, never auto-triggers and does not close positions

- **Severity:** HIGH
- **Evidence:** `risk/kill_switch.py:11-17`; `execution/paper_trading.py:49` builds a default engine with no path. See D-12 and D-22.
- **Gap row:** G-6 in docs/scrutiny-silverbot.md section 3
- **Status:** Recorded, not fixed: code changes are out of scope for this pass.


### H-10. Pending order reservation leaks risk capacity if never filled

- **Severity:** LOW
- **Evidence:** `backtest/engine.py:205,220-221`; `execution/paper_trading.py:267`.
- **Gap row:** G-21 in docs/scrutiny-silverbot.md section 3
- **Status:** Recorded, not fixed: code changes are out of scope for this pass.


### H-11. Risk state is in memory only; a restart resets daily-loss and consecutive-loss counters

- **Severity:** HIGH
- **Evidence:** `risk/models.py:47-63`. Combined with the H-4 restart loop, restarts would reset those gates repeatedly.
- **Gap row:** G-7 in docs/scrutiny-silverbot.md section 3
- **Status:** Recorded, not fixed: code changes are out of scope for this pass.


### H-12. Polling stream may yield a still-forming candle once; reconnect wrapper catches only ConnectionError

- **Severity:** MEDIUM
- **Evidence:** `data/stream.py:64,107-111`.
- **Gap row:** G-13 in docs/scrutiny-silverbot.md section 3
- **Status:** Recorded, not fixed: code changes are out of scope for this pass.


### H-13. No test covers NaN model output, stale model, corrupt artifact, `main()` or `health.py`

- **Severity:** MEDIUM
- **Evidence:** Test inventory: 19 files, 108 tests (facts sheet 06, test gaps).
- **Gap row:** G-28 in docs/scrutiny-silverbot.md section 3
- **Status:** Recorded, not fixed: code changes are out of scope for this pass.


### H-14. `.env.example` fails `load_config` as shipped

- **Severity:** HIGH
- **Evidence:** `.env.example:5-6` sets PAPER_TRADING=false and DEMO_TRADING=true, which `config/settings.py:96-97,140-141` turns into a demo configuration that demands API keys. Same root cause as D-2.
- **Gap row:** G-4 in docs/scrutiny-silverbot.md section 3
- **Status:** Recorded, not fixed: code changes are out of scope for this pass.


## Clean

Areas checked that matched the old documents (no finding raised):

- Backtest fee defaults: BACKTESTING.md:178-183 (maker 0.0002, taker 0.0005) match `backtest/models.py:32-33`.
- AGENTS.md ML rules (ML may approve, reject or reduce risk only) match `ml/filter.py` and the paper loop; an unpromoted model still cannot raise risk (see the D-37 note).
- AGENTS.md risk rules are a subset of the 14 gates in `risk/engine.py:30-87`.
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
- [x] Every hazard H-1 to H-14 has severity, evidence and a gap row pointing into docs/scrutiny-silverbot.md.
- [x] Severity counts in the opening paragraph (14 HIGH, 37 MEDIUM, 35 LOW) match the headings.
- [x] No bot code, config or test file was changed to produce this audit.
- [ ] Each finding is closed in its named canonical doc (open until those documents are written and reviewed).
