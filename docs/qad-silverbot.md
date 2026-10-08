# QA and Test Plan (QAD)

**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Version:** 0.1
**Owner:** Cian Jake Francisco
**Status:** Draft
**Last updated:** 2026-10-08
**Last reconciled:** 2026-10-08 against code at commit `62037d1`

This document is the test plan for Silver Bot. It maps all 108 existing tests to scenarios (`QAD-T#`) and to the features in [prd-silverbot.md](prd-silverbot.md) (`PRD-F#`), lists the scenarios no test covers, and sets the release criteria for each mode gate (backtest, paper, demo, live). It absorbs the release-gate parts of the old `BACKTESTING.md`. Test counts and behaviours come from the fact inventory for this reconciliation and from the baseline run in section 2. Gaps are `G-#` rows in [scrutiny-silverbot.md](scrutiny-silverbot.md); drift findings are in [audit-docs-drift.md](audit-docs-drift.md). Live trading is `Planned, blocked` (PRD-F12); nothing here enables it. Related documents: [aia-silverbot.md](aia-silverbot.md), [ops-silverbot.md](ops-silverbot.md), [clr-silverbot.md](clr-silverbot.md), [build-silverbot.md](build-silverbot.md) and the [index](index.md).

Source documents: [brd-silverbot.md](brd-silverbot.md) (success metrics `BRD-M#`), [sdd-silverbot.md](sdd-silverbot.md), [rfc-silverbot-signal-engine.md](rfc-silverbot-signal-engine.md), [rfc-silverbot-risk-kill-switch.md](rfc-silverbot-risk-kill-switch.md), [rfc-silverbot-ml-filter-gate.md](rfc-silverbot-ml-filter-gate.md) and [rfc-silverbot-readiness-gates.md](rfc-silverbot-readiness-gates.md) (RFC-004, the mode-gate conditions).

## 1. Testing Strategy & Scope

**Strategy.** Tests are pytest unit and component tests that run offline. Exchange access is never needed because the adapter does no network I/O (G-13, G-17); order placement and cancellation are blocked and raise `OrderPlacementDisabled`. No test needs a real API key; tests that exercise credentials use dummy strings and assert they never appear in logs or reports. Telegram is exercised through an in-memory client, not a network call. Tests build their own data (synthetic candles, temporary files), so none depends on a prior run.

**In scope.** Every module under `src/silver_bot/` that the 19 test files import: strategy, backtest, risk, paper execution, config, readiness, demo readiness, exchange adapter, storage, ML (dataset, training, registry, calibration, promotion, filter) and monitoring. The Docker, compose, systemd and `.dockerignore` files are checked as text.

**Out of scope today.** The entrypoint `main()`, `health.py`, `prepare-host.sh` and the logrotate file have no tests (G-28). Network behaviour, real fills, restart behaviour and performance cannot be tested because they do not exist yet (G-3, G-13, G-17). These are recorded as Not covered rows in section 3.8, not hidden.

**Principles (from AGENTS.md and the PRD).**

- The risk engine and kill switch are mandatory; tests must prove rejection paths, not only success paths.
- A test that proves something unsafe is blocked is worth more than one that proves a feature works; section 3.3 is the priority section.
- Every rejected setup carries a reason, and tests assert the reason text.
- ML tests prove the filter can only approve, reject or reduce risk.
- No strategy performance claim is made from these tests. They run on synthetic data and prove behaviour, not edge (section 3.7).

## 2. Test Environments & Data

| Environment | Purpose | How |
|---|---|---|
| Local virtual environment | The only environment that runs the suite today | `/c/TRADING BOT/.venv/Scripts/python -m pytest -q` (Git Bash path on the owner's Windows machine) |
| Fixtures | Isolation | pytest `tmp_path` for databases, kill-switch files, reports and logs; `pytest.raises` for error cases; no `conftest.py`, no network, no real `.env` |
| Config | Collection | `pyproject.toml`: `pythonpath = ["src"]`, `testpaths = ["tests"]`, `addopts = "-ra"`; Python 3.11 or newer; `pytest>=8.0` in the `dev` extra |
| Binance testnet | Manual only, and not possible yet | There is no network code (G-13, G-17); see section 4 |
| Continuous integration | None configured | Open |

**Data.** All tests use synthetic candles and in-code fixtures. No historical dataset ships with the repository, and the owner has not yet chosen a data source (OI-8 in the BRD). Real-data runs are therefore not part of this suite (section 3.7).

**Baseline result (verbatim).** Run on 2026-10-08 with `/c/TRADING BOT/.venv/Scripts/python -m pytest -q` at the reconciled commit:

```text
........................................................................ [ 66%]
....................................                                     [100%]
108 passed in 1.57s
```

The count is 108 test functions in 19 files (`^def test_` over `tests/`). The elapsed time is a single observation, not a benchmark.

Rows below cite tests as `tests/<file>.py::<name>`; every cited name was checked to exist (section 8).

## 3. Test Matrix

Each row is `QAD-T#` | scenario | feature | the automated test, or `Not covered (G-#)`. A Not covered row is a scenario the PRD or an RFC says should hold but that no test pins; every one has a gap id and is listed again in section 3.8. A test may prove more than one scenario; where two rows cite the same test it is because the test asserts both. Scenario counts: 153 rows, of which 108 are automated and 45 are Not covered.

### 3.1 Happy path (46 scenarios)

| QAD-T# | Scenario | PRD-F# | Automated by (`tests/<file>.py::<name>`) or Not covered |
|---|---|---|---|
| QAD-T1 | Complete bullish setup in an enabled session returns LONG with entry, stop, take profit, RR and session | PRD-F1 | `tests/test_silver_bullet_strategy.py::test_strategy_generates_long_signal_for_complete_silver_bullet_setup` |
| QAD-T2 | Mirrored bearish setup returns SHORT | PRD-F1 | `tests/test_silver_bullet_strategy.py::test_strategy_generates_short_signal_for_complete_silver_bullet_setup` |
| QAD-T3 | 14:30 UTC in June is inside new_york_am (daylight time, local start hour 10) | PRD-F1 | `tests/test_strategy_sessions.py::test_new_york_session_detection_is_timezone_aware` |
| QAD-T4 | 15:30 UTC in January is inside new_york_am (standard time) | PRD-F1 | `tests/test_strategy_sessions.py::test_new_york_session_detection_handles_standard_time` |
| QAD-T5 | Swing, liquidity level, bullish sweep and market structure shift are detected in sequence | PRD-F1 | `tests/test_strategy_modules.py::test_swing_liquidity_sweep_and_market_structure_shift_detection` |
| QAD-T6 | Bullish Fair Value Gap bounds and displacement score are detected | PRD-F1 | `tests/test_strategy_modules.py::test_fair_value_gap_and_displacement_detection` |
| QAD-T7 | No FVG exists until the confirming third candle | PRD-F1 | `tests/test_strategy_modules.py::test_fvg_detection_waits_for_confirming_third_candle` |
| QAD-T8 | Only the first touch of an FVG counts as retracement | PRD-F1 | `tests/test_strategy_modules.py::test_fvg_retracement_only_counts_first_touch` |
| QAD-T9 | Bullish higher-timeframe bias is reported for a bullish sequence | PRD-F1 | `tests/test_strategy_modules.py::test_higher_timeframe_bias_detection` |
| QAD-T10 | 1% risk on a known stop distance gives size 20, risk 100 and RR 2 | PRD-F3 | `tests/test_risk_engine.py::test_valid_position_sizing` |
| QAD-T11 | Backtest takes a take-profit trade and exports trades.csv, equity_curve.csv, backtest_report.json and rejected_signals.csv | PRD-F2 | `tests/test_backtest_engine.py::test_backtest_records_winning_trade_and_exports` |
| QAD-T12 | Backtest takes a stop-loss trade and records a loss of one risk unit | PRD-F2 | `tests/test_backtest_engine.py::test_backtest_records_losing_trade` |
| QAD-T13 | Non-zero fees lower net profit | PRD-F2 | `tests/test_backtest_engine.py::test_fees_reduce_net_profit` |
| QAD-T14 | Non-zero slippage lowers net profit | PRD-F2 | `tests/test_backtest_engine.py::test_slippage_reduces_net_profit` |
| QAD-T15 | Partial take profit at 1R closes part of the position and moves the stop to breakeven | PRD-F2 | Not covered (G-32) |
| QAD-T16 | Running the same candles twice gives identical backtest results | PRD-F2 | Not covered (G-32) |
| QAD-T17 | Paper run opens and closes one winning trade, stores one trade and at least four events, builds a daily paper report and sends four in-memory Telegram messages | PRD-F4, PRD-F7, PRD-F10 | `tests/test_paper_trading.py::test_paper_trading_opens_closes_stores_and_alerts` |
| QAD-T18 | Reconnecting market stream recovers from one mock connection failure in two attempts | PRD-F4 | `tests/test_paper_trading.py::test_reconnecting_market_stream_recovers_from_mock_failure` |
| QAD-T19 | Default configuration is paper mode, live false, paper true, ML off, thresholds 0.60 and 0.55 | PRD-F9 | `tests/test_config.py::test_default_config_is_safe` |
| QAD-T20 | .env overrides mode, database path and symbol while live stays false | PRD-F9 | `tests/test_config.py::test_env_file_overrides_defaults_without_enabling_live` |
| QAD-T21 | A .env file with a UTF-8 BOM loads | PRD-F9 | `tests/test_config.py::test_env_file_allows_utf8_bom` |
| QAD-T22 | YAML nested section aliases (trading, exchange, ml) load | PRD-F9 | `tests/test_config.py::test_config_yaml_aliases_are_loaded` |
| QAD-T23 | Safe demo environment loads with mode demo, testnet true, live false | PRD-F5, PRD-F9 | `tests/test_config.py::test_demo_config_passes_with_safe_values` |
| QAD-T24 | Demo configuration builds an adapter on the testnet base URL | PRD-F5 | `tests/test_exchange.py::test_binance_adapter_uses_testnet_url_in_demo_mode` |
| QAD-T25 | Demo readiness is ready with no failed check for a safe demo environment | PRD-F5, PRD-F8 | `tests/test_demo_readiness.py::test_demo_readiness_passes_with_safe_values` |
| QAD-T26 | Live readiness is ready when every condition is met (advisory report only; never enables live) | PRD-F8 | `tests/test_readiness.py::test_live_readiness_passes_when_all_required_conditions_are_met` |
| QAD-T27 | Readiness report exports JSON with ready and each check | PRD-F8 | `tests/test_readiness.py::test_readiness_report_export` |
| QAD-T28 | Storage initialisation creates the Phase 1 tables | PRD-F10 | `tests/test_storage.py::test_database_initialization_creates_phase_one_tables` |
| QAD-T29 | All sub-packages import (package boundaries intact) | PRD-F9 | `tests/test_imports.py::test_phase_one_package_boundaries_import` |
| QAD-T30 | Daily report holds trades, rejections, pnl, drawdown, win rate, average R, best and worst trade, rule failures and ML decisions, and exports JSON | PRD-F7 | `tests/test_monitoring_reports.py::test_daily_report_generation_and_exports` |
| QAD-T31 | Weekly report, journal and dashboard JSON are built and exported | PRD-F7 | `tests/test_monitoring_reports.py::test_weekly_report_generation_journal_and_dashboard_export` |
| QAD-T32 | Enabled alerter with an in-memory client sends all 12 message types | PRD-F7 | `tests/test_monitoring_reports.py::test_telegram_mocked_send_behavior` |
| QAD-T33 | Dataset builder makes one row with a winning label (1) and session features | PRD-F6 | `tests/test_ml_dataset.py::test_dataset_builder_creates_one_setup_row_with_winning_label` |
| QAD-T34 | Dataset builder labels a losing outcome 0 | PRD-F6 | `tests/test_ml_dataset.py::test_dataset_builder_creates_losing_label` |
| QAD-T35 | Time-based split keeps chronological order (6/2/2 on ten rows) | PRD-F6 | `tests/test_ml_dataset.py::test_time_based_split_preserves_chronological_order` |
| QAD-T36 | Calibration report computes Brier score, ECE and bin statistics | PRD-F6 | `tests/test_ml_calibration.py::test_calibration_report_calculates_brier_bins_and_ece` |
| QAD-T37 | Calibration report exports calibration_report.json and calibration_bins.csv | PRD-F6 | `tests/test_ml_calibration.py::test_calibration_report_exports_json_and_csv` |
| QAD-T38 | Baseline training saves model artifact, feature list and metrics with a note that the final test is held out | PRD-F6 | `tests/test_ml_training_registry.py::test_baseline_training_saves_logistic_model_artifacts` |
| QAD-T39 | Registry registers two models, switches the active model and loads the artifact | PRD-F6 | `tests/test_ml_training_registry.py::test_model_registry_registers_loads_and_switches_active_model` |
| QAD-T40 | ML filter approves a probability at or above the minimum (multiplier 1.0) | PRD-F6 | `tests/test_ml_probability_filter.py::test_ml_filter_approves_signal_above_min_probability` |
| QAD-T41 | ML filter reduces risk between the thresholds (multiplier 0.5) | PRD-F6 | `tests/test_ml_probability_filter.py::test_ml_filter_reduces_risk_between_thresholds` |
| QAD-T42 | Disabled ML filter leaves the signal unchanged | PRD-F6 | `tests/test_ml_probability_filter.py::test_ml_filter_disabled_leaves_signal_unchanged` |
| QAD-T43 | An ML prediction is stored in ml_predictions | PRD-F6, PRD-F10 | `tests/test_ml_probability_filter.py::test_ml_prediction_is_stored_in_database` |
| QAD-T44 | Backtest trade carries the ML probability and a reduced position size | PRD-F2, PRD-F6 | `tests/test_ml_probability_filter.py::test_backtest_includes_ml_probability_and_reduces_risk` |
| QAD-T45 | A candidate that passes the promotion policy is promoted and the decision is exported | PRD-F6 | `tests/test_ml_promotion.py::test_candidate_model_is_promoted_when_policy_passes` |
| QAD-T46 | With no active model a valid candidate is promoted | PRD-F6 | `tests/test_ml_promotion.py::test_no_active_model_fallback_promotes_valid_candidate` |

### 3.2 Sad path: expected rejections and negative outcomes (41 scenarios)

| QAD-T# | Scenario | PRD-F# | Automated by (`tests/<file>.py::<name>`) or Not covered |
|---|---|---|---|
| QAD-T47 | Candle outside every enabled window returns NO_TRADE "Outside enabled Silver Bullet session" | PRD-F1 | `tests/test_silver_bullet_strategy.py::test_strategy_rejects_outside_session_with_clear_reason` |
| QAD-T48 | No retracement into the FVG returns NO_TRADE "No retracement into matching Fair Value Gap" | PRD-F1 | `tests/test_silver_bullet_strategy.py::test_strategy_rejects_when_latest_candle_has_not_retraced_into_fvg` |
| QAD-T49 | Quality score below minimum, or reward-to-risk below minimum, returns NO_TRADE naming the reason | PRD-F1 | Not covered (G-32) |
| QAD-T50 | A disabled custom session does not activate | PRD-F1 | `tests/test_strategy_sessions.py::test_sessions_are_configurable_and_disabled_sessions_do_not_activate` |
| QAD-T51 | Session settings from environment or yaml reach the strategy | PRD-F1, PRD-F9 | Not covered (G-18) |
| QAD-T52 | Backtest outside the session takes no trade and records the rejection reason | PRD-F2 | `tests/test_backtest_engine.py::test_backtest_records_no_trade_rejections` |
| QAD-T53 | A limit order whose entry is never touched is not filled | PRD-F2 | `tests/test_backtest_engine.py::test_limit_order_not_filled_if_price_never_reaches_entry` |
| QAD-T54 | Default backtest costs are non-zero (slippage and spread) | PRD-F2 | Not covered (G-11) |
| QAD-T55 | Reward-to-risk below the configured minimum is rejected by the risk engine | PRD-F3 | `tests/test_risk_engine.py::test_low_reward_to_risk_is_rejected` |
| QAD-T56 | Default (disabled) alerter sends nothing, even with a client | PRD-F7 | `tests/test_monitoring_reports.py::test_telegram_disabled_behavior` |
| QAD-T57 | Paper run with the default alerter sends no Telegram message | PRD-F4, PRD-F7 | `tests/test_paper_trading.py::test_paper_trading_telegram_disabled_by_default` |
| QAD-T58 | Live readiness blocks when the three evidence reports are missing | PRD-F8 | `tests/test_readiness.py::test_live_readiness_blocks_when_required_reports_are_missing` |
| QAD-T59 | Live readiness requires the Telegram test flag when Telegram is enabled | PRD-F8 | `tests/test_readiness.py::test_live_readiness_requires_telegram_test_when_enabled` |
| QAD-T60 | ML filter rejects a probability below the reduce-risk threshold (multiplier 0) | PRD-F6 | `tests/test_ml_probability_filter.py::test_ml_filter_rejects_signal_below_reduce_risk_threshold` |
| QAD-T61 | Promotion rejects a candidate with a worse validation metric | PRD-F6 | `tests/test_ml_promotion.py::test_candidate_model_rejected_due_to_worse_validation_metric` |
| QAD-T62 | Promotion rejects a candidate whose test score degrades | PRD-F6 | `tests/test_ml_promotion.py::test_candidate_model_rejected_due_to_test_score_degradation` |
| QAD-T63 | Promotion rejects a candidate with a poor Brier score | PRD-F6 | `tests/test_ml_promotion.py::test_candidate_model_rejected_due_to_poor_calibration` |
| QAD-T64 | Promotion rejects a candidate with too few samples | PRD-F6 | `tests/test_ml_promotion.py::test_candidate_model_rejected_due_to_insufficient_samples` |
| QAD-T65 | Promotion rejects a tied candidate that fails the calibration policy | PRD-F6 | `tests/test_ml_promotion.py::test_tied_candidate_with_policy_failure_is_rejected` |
| QAD-T66 | With no candidate metrics the current model is kept | PRD-F6 | `tests/test_ml_promotion.py::test_no_candidate_metrics_keeps_current_model` |
| QAD-T67 | Audit file that cannot be written does not crash a trading loop | PRD-F7 | Not covered (G-32) |
| QAD-T68 | Application log record is structured JSON with context fields | PRD-F7 | Not covered (G-16) |
| QAD-T69 | Telegram alert reaches Telegram over the network | PRD-F7 | Not covered (G-15) |
| QAD-T70 | Daily and weekly reports are produced without manual calls | PRD-F7 | Not covered (G-16) |
| QAD-T71 | Pending order that never fills is cancelled and its risk capacity released | PRD-F4 | Not covered (G-21) |
| QAD-T72 | Polling stream yields only closed candles | PRD-F4 | Not covered (G-13) |
| QAD-T73 | A paper session requested through the entrypoint runs the paper engine | PRD-F4 | Not covered (G-3) |
| QAD-T74 | Stored candles are read back for a date range | PRD-F10 | Not covered (G-14) |
| QAD-T75 | Signals and trades tables are filled when signals and trades occur | PRD-F10 | Not covered (G-14) |
| QAD-T76 | A valid date range returns normalised candles | PRD-F10 | Not covered (G-13) |
| QAD-T77 | Fetched data is stored with gaps and quality reported | PRD-F10 | Not covered (G-13) |
| QAD-T78 | Chronological split into training, validation and final-test slices is available to evidence runs | PRD-F2 | Not covered (G-12) |
| QAD-T79 | Final test set is not used when parameters are tuned (enforced in code) | PRD-F2 | Not covered (G-12) |
| QAD-T80 | Evidence run writes a non-empty out-of-sample report with pass/fail criteria | PRD-F2 | Not covered (G-1) |
| QAD-T81 | Full strategy run candle by candle never lets a future candle influence a decision | PRD-F1 | Not covered (G-29) |
| QAD-T82 | Demo mode connects to the testnet and places testnet orders | PRD-F5 | Not covered (G-17) |
| QAD-T83 | The bot service stays running as a paper bot instead of exiting and restarting | PRD-F11 | Not covered (G-3) |
| QAD-T84 | Startup with a rejected configuration logs "configuration rejected" and exits 2 | PRD-F11 | Not covered (G-28) |
| QAD-T85 | Startup with a valid configuration records bot_started and bot_stopped and exits 0 | PRD-F11 | Not covered (G-28) |
| QAD-T86 | Health command exits 2 on a rejected configuration | PRD-F11 | Not covered (G-28) |
| QAD-T87 | Host preparation script and systemd unit create the silverbot user and writable bind mounts | PRD-F11 | Not covered (G-26) |

### 3.3 Unsafe and abuse cases (42 scenarios)

Unsafe configuration, live-trading attempts, missing stop loss, kill switch active, secret leakage, lookahead and deployment files that could enable live. This is the priority section: any failure here is severity S1 (section 5).

| QAD-T# | Scenario | PRD-F# | Automated by (`tests/<file>.py::<name>`) or Not covered |
|---|---|---|---|
| QAD-T88 | LIVE_TRADING=true is rejected at config load | PRD-F9, PRD-F12 | `tests/test_config.py::test_live_trading_flag_is_rejected` |
| QAD-T89 | TRADING_MODE=live is rejected at config load | PRD-F9, PRD-F12 | `tests/test_config.py::test_live_mode_is_rejected` |
| QAD-T90 | Demo mode with the production Binance URL is rejected | PRD-F5 | `tests/test_config.py::test_demo_config_rejects_production_binance_url` |
| QAD-T91 | Demo mode with LIVE_TRADING=true is rejected | PRD-F5, PRD-F12 | `tests/test_config.py::test_demo_config_rejects_live_trading_flag` |
| QAD-T92 | Demo mode with BINANCE_TESTNET=false is rejected | PRD-F5 | `tests/test_config.py::test_demo_config_rejects_disabled_testnet_flag` |
| QAD-T93 | A real order placement request raises OrderPlacementDisabled | PRD-F5, PRD-F12 | `tests/test_exchange.py::test_binance_adapter_rejects_real_order_placement` |
| QAD-T94 | A real order cancellation request raises OrderPlacementDisabled | PRD-F5, PRD-F12 | `tests/test_exchange.py::test_binance_adapter_rejects_real_order_cancellation` |
| QAD-T95 | Adapter built with testnet=True and the production URL raises "testnet endpoint" | PRD-F5 | `tests/test_exchange.py::test_binance_adapter_rejects_production_url_for_testnet_mode` |
| QAD-T96 | Look-alike host containing the testnet name as a substring is rejected by the URL guard | PRD-F5 | Not covered (G-10) |
| QAD-T97 | Missing stop loss is rejected ("Stop loss is required") | PRD-F3 | `tests/test_risk_engine.py::test_missing_stop_loss_is_rejected` |
| QAD-T98 | Stop loss on the wrong side is rejected ("Invalid stop loss for trade direction") | PRD-F3 | `tests/test_risk_engine.py::test_invalid_stop_loss_is_rejected` |
| QAD-T99 | Daily loss at the limit locks the engine out | PRD-F3 | `tests/test_risk_engine.py::test_daily_loss_lockout` |
| QAD-T100 | Three consecutive losses lock the engine out | PRD-F3 | `tests/test_risk_engine.py::test_consecutive_loss_lockout` |
| QAD-T101 | Max trades per day locks the engine out | PRD-F3 | `tests/test_risk_engine.py::test_max_trades_lockout` |
| QAD-T102 | Max open positions locks the engine out | PRD-F3 | `tests/test_risk_engine.py::test_max_open_positions_lockout` |
| QAD-T103 | Leverage above the cap is rejected | PRD-F3 | `tests/test_risk_engine.py::test_maximum_leverage_rejection` |
| QAD-T104 | Kill-switch file makes the risk engine reject first ("Kill switch is active") | PRD-F3 | `tests/test_risk_engine.py::test_kill_switch_active` |
| QAD-T105 | Kill-switch file during a backtest produces a "Risk rejected: Kill switch is active" record | PRD-F2, PRD-F3 | `tests/test_backtest_engine.py::test_backtest_logs_risk_rejection_when_kill_switch_active` |
| QAD-T106 | Kill-switch file during a paper run opens no trade, records KILL_SWITCH_ACTIVE and sends an alert | PRD-F3, PRD-F4 | `tests/test_paper_trading.py::test_paper_trading_kill_switch_alert_and_risk_rejection` |
| QAD-T107 | Default-constructed risk engine arms the kill switch without a supplied path | PRD-F3 | Not covered (G-6) |
| QAD-T108 | A loss-limit breach trips the kill switch automatically and closes open positions | PRD-F3 | Not covered (G-6) |
| QAD-T109 | Risk engine uses the Settings limits and cannot be set above 0.5% per trade | PRD-F3, PRD-F9 | Not covered (G-5) |
| QAD-T110 | Daily loss, consecutive loss and trade counts survive a restart | PRD-F3 | Not covered (G-7) |
| QAD-T111 | Demo readiness fails on a production endpoint | PRD-F5, PRD-F8 | `tests/test_demo_readiness.py::test_demo_readiness_rejects_production_endpoint` |
| QAD-T112 | Demo readiness fails when the risk engine, kill switch or stop-loss requirement is disabled | PRD-F3, PRD-F8 | `tests/test_demo_readiness.py::test_demo_readiness_fails_if_risk_kill_switch_or_stop_loss_disabled` |
| QAD-T113 | Demo readiness fails when the kill-switch file is active | PRD-F3, PRD-F8 | `tests/test_demo_readiness.py::test_demo_readiness_fails_if_kill_switch_file_is_active` |
| QAD-T114 | Demo readiness fails unsafe risk limits (risk 0.02, daily loss 0.05, leverage 25) | PRD-F8 | `tests/test_demo_readiness.py::test_demo_readiness_fails_unsafe_risk_limits` |
| QAD-T115 | Demo readiness report contains no API key or secret value | PRD-F7, PRD-F8 | `tests/test_demo_readiness.py::test_demo_readiness_report_does_not_print_secrets` |
| QAD-T116 | Live readiness blocks unsafe live flags | PRD-F8, PRD-F12 | `tests/test_readiness.py::test_live_readiness_blocks_unsafe_live_flags` |
| QAD-T117 | Live readiness blocks missing API keys and unconfirmed withdrawal restriction | PRD-F8, PRD-F12 | `tests/test_readiness.py::test_live_readiness_blocks_missing_api_keys_and_withdrawal_confirmation` |
| QAD-T118 | Live readiness blocks unsafe risk limits | PRD-F8, PRD-F12 | `tests/test_readiness.py::test_live_readiness_blocks_unsafe_risk_limits` |
| QAD-T119 | Live readiness blocks when the kill-switch file is active | PRD-F3, PRD-F8 | `tests/test_readiness.py::test_live_readiness_blocks_when_kill_switch_file_is_active` |
| QAD-T120 | A 0-byte or invalid evidence report fails the readiness check | PRD-F8 | Not covered (G-2) |
| QAD-T121 | Live startup consults the readiness report | PRD-F8, PRD-F12 | Not covered (G-2) |
| QAD-T122 | API keys, secrets and Telegram token are redacted from the audit log and absent from the file | PRD-F7 | `tests/test_monitoring_reports.py::test_structured_log_generation_and_secret_redaction` |
| QAD-T123 | Demo credentials are redacted from the demo-readiness audit event | PRD-F7, PRD-F8 | `tests/test_monitoring_reports.py::test_demo_credentials_are_redacted_from_logs` |
| QAD-T124 | Dockerfile defaults to paper mode with LIVE_TRADING=false and no live command | PRD-F11, PRD-F12 | `tests/test_deployment_files.py::test_dockerfile_defaults_to_safe_paper_mode` |
| QAD-T125 | .dockerignore excludes .env files, logs, data, models, reports and SQLite files | PRD-F11 | `tests/test_deployment_files.py::test_dockerignore_excludes_secrets_and_runtime_state` |
| QAD-T126 | Compose forces LIVE_TRADING false, mounts runtime volumes and sets no live mode | PRD-F11, PRD-F12 | `tests/test_deployment_files.py::test_compose_mounts_runtime_volumes_and_has_no_live_default` |
| QAD-T127 | systemd unit runs compose paper bot and never sets live mode | PRD-F11, PRD-F12 | `tests/test_deployment_files.py::test_systemd_service_runs_compose_paper_bot` |
| QAD-T128 | Liquidity sweep ignores a level not known before the sweep (no lookahead) | PRD-F1 | `tests/test_strategy_modules.py::test_liquidity_sweep_ignores_levels_not_known_before_sweep` |
| QAD-T129 | Market structure shift is None until the break candle exists (no lookahead) | PRD-F1 | `tests/test_strategy_modules.py::test_market_structure_shift_does_not_use_future_break_candle` |

### 3.4 Invalid configuration (11 scenarios)

| QAD-T# | Scenario | PRD-F# | Automated by (`tests/<file>.py::<name>`) or Not covered |
|---|---|---|---|
| QAD-T130 | API key without a secret is rejected ("provided together") | PRD-F9 | `tests/test_config.py::test_partial_binance_credentials_are_rejected` |
| QAD-T131 | Database path with parent traversal is rejected | PRD-F9 | `tests/test_config.py::test_database_path_cannot_escape_workspace_by_parent_traversal` |
| QAD-T132 | Database path that is an existing directory is rejected | PRD-F9 | `tests/test_config.py::test_database_path_cannot_be_existing_directory` |
| QAD-T133 | Reduce-risk threshold above the minimum probability is rejected | PRD-F6, PRD-F9 | `tests/test_config.py::test_ml_thresholds_must_be_valid` |
| QAD-T134 | Bad symbol, timeframe or exchange name is rejected | PRD-F9 | `tests/test_config.py::test_symbol_timeframe_and_exchange_are_validated` |
| QAD-T135 | ML registry path with parent traversal is rejected | PRD-F6, PRD-F9 | `tests/test_config.py::test_ml_registry_path_cannot_escape_workspace` |
| QAD-T136 | OHLCV request with start equal to end raises "start must be before end" before any network work | PRD-F10 | `tests/test_exchange.py::test_binance_ohlcv_skeleton_validates_date_range_before_network_work` |
| QAD-T137 | Readiness reasons say how to fix a missing report path and an invalid boolean | PRD-F8 | `tests/test_readiness.py::test_readiness_messages_explain_missing_report_and_invalid_boolean` |
| QAD-T138 | Shipped .env.example copied to .env loads | PRD-F9 | Not covered (G-4) |
| QAD-T139 | Risk limits above 0.5% per trade, 2% daily loss or 3x leverage are rejected outside demo mode | PRD-F9 | Not covered (G-5) |
| QAD-T140 | NO_TRADE signal built without a reason raises "NO_TRADE signals require a reason" | PRD-F1 | Not covered (G-32) |

### 3.5 ML adversarial: leakage, out-of-range probabilities, missing model (13 scenarios)

The ML filter may only approve, reject or reduce risk (PRD-F6, RFC-003). These rows attack that boundary. The known flaw is that a NaN probability approves (H-1, G-8); the test for the correct behaviour does not exist yet.

| QAD-T# | Scenario | PRD-F# | Automated by (`tests/<file>.py::<name>`) or Not covered |
|---|---|---|---|
| QAD-T141 | Feature names contain no future-leakage keyword; the validator raises "future leakage" on a leaking name | PRD-F6 | `tests/test_ml_dataset.py::test_feature_names_do_not_include_future_leakage_columns` |
| QAD-T142 | Candidate optimised on the final test set is rejected | PRD-F6 | `tests/test_ml_promotion.py::test_candidate_rejected_if_final_test_was_used_for_optimization` |
| QAD-T143 | Calibration rejects mismatched lengths, out-of-range probabilities and non-binary labels | PRD-F6 | `tests/test_ml_calibration.py::test_calibration_report_rejects_invalid_inputs` |
| QAD-T144 | Missing registry or no active model falls back to the rule-based signal (APPROVE, probability None) | PRD-F6 | `tests/test_ml_probability_filter.py::test_ml_filter_missing_model_falls_back_to_rule_based_signal` |
| QAD-T145 | Model returns NaN: the signal is rejected | PRD-F6 | Not covered (G-8) |
| QAD-T146 | Model returns a probability outside [0, 1]: it is clamped before the decision | PRD-F6 | Not covered (G-32) |
| QAD-T147 | Stale model (registered but outdated artifact) is detected and not used | PRD-F6 | Not covered (G-28) |
| QAD-T148 | Corrupt or unreadable model artifact falls back safely | PRD-F6 | Not covered (G-28) |
| QAD-T149 | Registering a model with a missing artifact, feature list or metrics file raises FileNotFoundError | PRD-F6 | Not covered (G-32) |
| QAD-T150 | Untrusted pickle artifact is not executed | PRD-F6 | Not covered (G-23) |
| QAD-T151 | Split has purge or embargo, and higher-timeframe features do not look ahead | PRD-F6 | Not covered (G-22) |
| QAD-T152 | A model written to the registry by any route is activated only after promotion policy passes | PRD-F6 | Not covered (G-22) |
| QAD-T153 | ML_FILTER_ENABLED and thresholds in settings reach the filter at startup | PRD-F6, PRD-F9 | Not covered (G-9) |

### 3.6 Traceability: PRD-F1 to PRD-F12

A scenario that lists several features appears under each. "Automated" rows have at least one named test; "Not covered" rows are in section 3.8.

| PRD-F# | Feature | Automated QAD-T# | Not-covered QAD-T# (see 3.8) |
|---|---|---|---|
| PRD-F1 | Signal engine | QAD-T1, QAD-T2, QAD-T3, QAD-T4, QAD-T5, QAD-T6, QAD-T7, QAD-T8, QAD-T9, QAD-T47, QAD-T48, QAD-T50, QAD-T128, QAD-T129 | QAD-T49, QAD-T51, QAD-T81, QAD-T140 |
| PRD-F2 | Backtester | QAD-T11, QAD-T12, QAD-T13, QAD-T14, QAD-T44, QAD-T52, QAD-T53, QAD-T105 | QAD-T15, QAD-T16, QAD-T54, QAD-T78, QAD-T79, QAD-T80 |
| PRD-F3 | Risk engine and kill switch | QAD-T10, QAD-T55, QAD-T97, QAD-T98, QAD-T99, QAD-T100, QAD-T101, QAD-T102, QAD-T103, QAD-T104, QAD-T105, QAD-T106, QAD-T112, QAD-T113, QAD-T119 | QAD-T107, QAD-T108, QAD-T109, QAD-T110 |
| PRD-F4 | Paper trading | QAD-T17, QAD-T18, QAD-T57, QAD-T106 | QAD-T71, QAD-T72, QAD-T73 |
| PRD-F5 | Demo/testnet mode | QAD-T23, QAD-T24, QAD-T25, QAD-T90, QAD-T91, QAD-T92, QAD-T93, QAD-T94, QAD-T95, QAD-T111 | QAD-T82, QAD-T96 |
| PRD-F6 | ML probability filter | QAD-T33, QAD-T34, QAD-T35, QAD-T36, QAD-T37, QAD-T38, QAD-T39, QAD-T40, QAD-T41, QAD-T42, QAD-T43, QAD-T44, QAD-T45, QAD-T46, QAD-T60, QAD-T61, QAD-T62, QAD-T63, QAD-T64, QAD-T65, QAD-T66, QAD-T133, QAD-T135, QAD-T141, QAD-T142, QAD-T143, QAD-T144 | QAD-T145, QAD-T146, QAD-T147, QAD-T148, QAD-T149, QAD-T150, QAD-T151, QAD-T152, QAD-T153 |
| PRD-F7 | Monitoring and alerting | QAD-T17, QAD-T30, QAD-T31, QAD-T32, QAD-T56, QAD-T57, QAD-T115, QAD-T122, QAD-T123 | QAD-T67, QAD-T68, QAD-T69, QAD-T70 |
| PRD-F8 | Readiness gates | QAD-T25, QAD-T26, QAD-T27, QAD-T58, QAD-T59, QAD-T111, QAD-T112, QAD-T113, QAD-T114, QAD-T115, QAD-T116, QAD-T117, QAD-T118, QAD-T119, QAD-T123, QAD-T137 | QAD-T120, QAD-T121 |
| PRD-F9 | Safe configuration | QAD-T19, QAD-T20, QAD-T21, QAD-T22, QAD-T23, QAD-T29, QAD-T88, QAD-T89, QAD-T130, QAD-T131, QAD-T132, QAD-T133, QAD-T134, QAD-T135 | QAD-T51, QAD-T109, QAD-T138, QAD-T139, QAD-T153 |
| PRD-F10 | Market data and storage | QAD-T17, QAD-T28, QAD-T43, QAD-T136 | QAD-T74, QAD-T75, QAD-T76, QAD-T77 |
| PRD-F11 | Deployment | QAD-T124, QAD-T125, QAD-T126, QAD-T127 | QAD-T83, QAD-T84, QAD-T85, QAD-T86, QAD-T87 |
| PRD-F12 | Live trading (Planned, blocked) | QAD-T88, QAD-T89, QAD-T91, QAD-T93, QAD-T94, QAD-T116, QAD-T117, QAD-T118, QAD-T124, QAD-T126, QAD-T127 | QAD-T121 |

**PRD-F12 (live trading, Planned, blocked).** There is no live code to test. What the suite proves is that live is blocked: QAD-T88, QAD-T89, QAD-T91, QAD-T93, QAD-T94, QAD-T116, QAD-T117, QAD-T118, QAD-T124, QAD-T126, QAD-T127. These cover the config-load rejection of `LIVE_TRADING=true` and `TRADING_MODE=live`, the disabled order methods, the safe Docker, compose and systemd defaults, and the readiness checkers failing unsafe live inputs. The readiness checkers are advisory only (no code consults them), so they are not a live gate (G-2). Not covered for PRD-F12: QAD-T121.

### 3.7 Strategy Evidence (measured, not asserted)

No strategy performance claim is made anywhere in this suite. The three evidence reports (`reports/backtest_report.json`, `reports/out_of_sample_validation_report.json`, `reports/paper_trading_report.json`) are 0 bytes (G-1). The 108 tests run on synthetic data and prove behaviour, not edge. Every metric below is therefore not yet measured. Thresholds are owned by the BRD (BRD-M1 to BRD-M10); this table only records what must be measured and where it will come from.

| Metric | Success metric | Source of the measurement | Status |
|---|---|---|---|
| Profit factor after costs | BRD-M1 | `profit_factor` in the backtest report (`backtest/metrics.py`) | Not yet measured (G-1) |
| Expectancy after costs | BRD-M2 | `expectancy` in the backtest report | Not yet measured (G-1) |
| Maximum drawdown | BRD-M4 | `max_drawdown`, `max_drawdown_percent`; tolerance is Owner input required (OI-3) | Not yet measured (G-1) |
| Trade count in the evidence run | BRD-M5 | `total_trades`; the minimum is Owner input required (OI-9) | Not yet measured (G-1) |
| Cost realism: slippage and spread recorded and non-zero | BRD-M3 | `slippage_bps` and `spread_bps` in the report config; backtest defaults are 0 (G-11) | Not yet measured (G-11) |
| Result not carried by one trade or one short period | BRD-M6 | Trade journal and `session_performance`; the definition is Open | Not yet measured (G-1) |
| Out-of-sample result | BRD-M7 | Out-of-sample report; criteria Open; the split helper is unwired and not enforced (G-12) | Not yet measured (G-12) |
| Walk-forward stability | BRD-M7 | No walk-forward exists | Not yet measured (G-12) |
| Monte Carlo drawdown range | BRD-M4 | No Monte Carlo exists | Not yet measured (G-12) |
| Parameter sensitivity | BRD-M6 | No sensitivity tooling exists | Not yet measured (G-12) |
| Paper run matches backtest behaviour | BRD-M8 | `paper_trading_report.json` against the backtest report; tolerance Open | Not yet measured (G-1) |
| ML filter adds value over unfiltered trades | None (ML is optional) | Held-out comparison; no model is shipped (G-9) | Not yet measured (G-9) |

**BRD-M3 measurement requirement.** The basis-point values for slippage and spread are Open in the BRD. This plan does not set them. It requires that (1) the evidence run states both values in the report configuration, (2) both are non-zero, (3) the values are chosen before the run and justified, ideally from paper or demo fills, and (4) the result is re-run with both values raised to show whether the sign of the result flips (sensitivity to cost). An evidence report that records zero for either value does not satisfy BRD-M3 and cannot support any release gate.

### 3.8 Uncovered Scenarios Register

Every Not covered row from 3.1 to 3.5 is listed here once. 45 scenarios have no test. Each is tracked by an existing gap. Scenarios whose PRD acceptance criteria name no specific gap are tracked by G-32 (uncovered test scenarios) in [scrutiny-silverbot.md](scrutiny-silverbot.md). Closing a row means writing the test, changing the cell in section 3 to the test name, and removing the row here.

The five PRD acceptance criteria that name no specific gap are AC-01.5 (QAD-T49), AC-01.6 (QAD-T140), AC-04.8 (QAD-T15), AC-04.9 (QAD-T16) and AC-13.3 (QAD-T67); all are tracked by G-32.

| QAD-T# | Scenario | PRD-F# | Tracked by | PRD acceptance criterion |
|---|---|---|---|---|
| QAD-T15 | Partial take profit at 1R closes part of the position and moves the stop to breakeven | PRD-F2 | G-32 | AC-04.8 |
| QAD-T16 | Running the same candles twice gives identical backtest results | PRD-F2 | G-32 | AC-04.9 |
| QAD-T49 | Quality score below minimum, or reward-to-risk below minimum, returns NO_TRADE naming the reason | PRD-F1 | G-32 | AC-01.5 |
| QAD-T51 | Session settings from environment or yaml reach the strategy | PRD-F1, PRD-F9 | G-18 | - |
| QAD-T54 | Default backtest costs are non-zero (slippage and spread) | PRD-F2 | G-11 | - |
| QAD-T67 | Audit file that cannot be written does not crash a trading loop | PRD-F7 | G-32 | AC-13.3 |
| QAD-T68 | Application log record is structured JSON with context fields | PRD-F7 | G-16 | - |
| QAD-T69 | Telegram alert reaches Telegram over the network | PRD-F7 | G-15 | - |
| QAD-T70 | Daily and weekly reports are produced without manual calls | PRD-F7 | G-16 | - |
| QAD-T71 | Pending order that never fills is cancelled and its risk capacity released | PRD-F4 | G-21 | - |
| QAD-T72 | Polling stream yields only closed candles | PRD-F4 | G-13 | - |
| QAD-T73 | A paper session requested through the entrypoint runs the paper engine | PRD-F4 | G-3 | - |
| QAD-T74 | Stored candles are read back for a date range | PRD-F10 | G-14 | - |
| QAD-T75 | Signals and trades tables are filled when signals and trades occur | PRD-F10 | G-14 | - |
| QAD-T76 | A valid date range returns normalised candles | PRD-F10 | G-13 | - |
| QAD-T77 | Fetched data is stored with gaps and quality reported | PRD-F10 | G-13 | - |
| QAD-T78 | Chronological split into training, validation and final-test slices is available to evidence runs | PRD-F2 | G-12 | - |
| QAD-T79 | Final test set is not used when parameters are tuned (enforced in code) | PRD-F2 | G-12 | - |
| QAD-T80 | Evidence run writes a non-empty out-of-sample report with pass/fail criteria | PRD-F2 | G-1 | - |
| QAD-T81 | Full strategy run candle by candle never lets a future candle influence a decision | PRD-F1 | G-29 | - |
| QAD-T82 | Demo mode connects to the testnet and places testnet orders | PRD-F5 | G-17 | - |
| QAD-T83 | The bot service stays running as a paper bot instead of exiting and restarting | PRD-F11 | G-3 | - |
| QAD-T84 | Startup with a rejected configuration logs "configuration rejected" and exits 2 | PRD-F11 | G-28 | - |
| QAD-T85 | Startup with a valid configuration records bot_started and bot_stopped and exits 0 | PRD-F11 | G-28 | - |
| QAD-T86 | Health command exits 2 on a rejected configuration | PRD-F11 | G-28 | - |
| QAD-T87 | Host preparation script and systemd unit create the silverbot user and writable bind mounts | PRD-F11 | G-26 | - |
| QAD-T96 | Look-alike host containing the testnet name as a substring is rejected by the URL guard | PRD-F5 | G-10 | - |
| QAD-T107 | Default-constructed risk engine arms the kill switch without a supplied path | PRD-F3 | G-6 | - |
| QAD-T108 | A loss-limit breach trips the kill switch automatically and closes open positions | PRD-F3 | G-6 | - |
| QAD-T109 | Risk engine uses the Settings limits and cannot be set above 0.5% per trade | PRD-F3, PRD-F9 | G-5 | - |
| QAD-T110 | Daily loss, consecutive loss and trade counts survive a restart | PRD-F3 | G-7 | - |
| QAD-T120 | A 0-byte or invalid evidence report fails the readiness check | PRD-F8 | G-2 | - |
| QAD-T121 | Live startup consults the readiness report | PRD-F8, PRD-F12 | G-2 | - |
| QAD-T138 | Shipped .env.example copied to .env loads | PRD-F9 | G-4 | - |
| QAD-T139 | Risk limits above 0.5% per trade, 2% daily loss or 3x leverage are rejected outside demo mode | PRD-F9 | G-5 | - |
| QAD-T140 | NO_TRADE signal built without a reason raises "NO_TRADE signals require a reason" | PRD-F1 | G-32 | AC-01.6 |
| QAD-T145 | Model returns NaN: the signal is rejected | PRD-F6 | G-8 | - |
| QAD-T146 | Model returns a probability outside [0, 1]: it is clamped before the decision | PRD-F6 | G-32 | - |
| QAD-T147 | Stale model (registered but outdated artifact) is detected and not used | PRD-F6 | G-28 | - |
| QAD-T148 | Corrupt or unreadable model artifact falls back safely | PRD-F6 | G-28 | - |
| QAD-T149 | Registering a model with a missing artifact, feature list or metrics file raises FileNotFoundError | PRD-F6 | G-32 | - |
| QAD-T150 | Untrusted pickle artifact is not executed | PRD-F6 | G-23 | - |
| QAD-T151 | Split has purge or embargo, and higher-timeframe features do not look ahead | PRD-F6 | G-22 | - |
| QAD-T152 | A model written to the registry by any route is activated only after promotion policy passes | PRD-F6 | G-22 | - |
| QAD-T153 | ML_FILTER_ENABLED and thresholds in settings reach the filter at startup | PRD-F6, PRD-F9 | G-9 | - |

By gap: G-1: QAD-T80; G-2: QAD-T120, QAD-T121; G-3: QAD-T73, QAD-T83; G-4: QAD-T138; G-5: QAD-T109, QAD-T139; G-6: QAD-T107, QAD-T108; G-7: QAD-T110; G-8: QAD-T145; G-9: QAD-T153; G-10: QAD-T96; G-11: QAD-T54; G-12: QAD-T78, QAD-T79; G-13: QAD-T72, QAD-T76, QAD-T77; G-14: QAD-T74, QAD-T75; G-15: QAD-T69; G-16: QAD-T68, QAD-T70; G-17: QAD-T82; G-18: QAD-T51; G-21: QAD-T71; G-22: QAD-T151, QAD-T152; G-23: QAD-T150; G-26: QAD-T87; G-28: QAD-T84, QAD-T85, QAD-T86, QAD-T147, QAD-T148; G-29: QAD-T81; G-32: QAD-T15, QAD-T16, QAD-T49, QAD-T67, QAD-T140, QAD-T146, QAD-T149.

## 4. Automation vs Manual

**Automated (pytest, runs offline).** All 108 automated scenarios in section 3, covering strategy, backtest, risk, paper run, config, readiness, exchange guards, storage, ML, monitoring and deployment-file text. Run it with `/c/TRADING BOT/.venv/Scripts/python -m pytest -q`.

**Manual checks.** None of these can be performed today; each names what blocks it. They become release-gate items in section 6 once their blockers close.

| Check | When | Pass condition | Status |
|---|---|---|---|
| Testnet dry start | Before the demo gate | Bot starts in demo mode, connects to the testnet only, places no order outside the testnet, writes `bot_started` and `bot_stopped` | Planned; blocked by G-3, G-13, G-17 (no runtime, no network I/O) |
| Telegram test message | Before the demo gate and before any live proposal | A real message reaches the owner's chat; `TELEGRAM_ALERTS_TESTED` is set only after it | Planned; blocked by G-15 (no transport) |
| Kill-switch drill | Before the paper gate is passed | Create the kill-switch file while the bot runs; no new trade opens, an alert is sent, and the reset steps are written down and followed | Planned; blocked by G-3 (no running bot) and G-6 (inert by default, no reset tooling) |
| Evidence report review | At each gate | The owner reads the report, checks it is non-empty and that the cost values are recorded (BRD-M3) | Planned; blocked by G-1 |
| Secret scan of tracked files | Before every commit that touches config | No key, token or `.env` content is tracked | Partly automated (demo readiness check 18, behaviour outside git Open, U-20); run by the owner today |
| Deployment dry run on the host | Before an unattended run | `silverbot` user, bind mounts and health check work on the host | Planned; blocked by G-26, G-27 |

## 5. Bug Triage Protocol

Severity is set by safety impact, not by how often the defect appears.

| Severity | Definition | Examples (current open items) | Response |
|---|---|---|---|
| S1 | A defect in a control that stops capital loss or live trading: the risk engine, kill switch, stop-loss requirement, loss limits, the live block at config load, the mode gates and readiness gates, secret handling, or ML bypassing the risk engine. Any risk or live-gate bug is S1. | G-5 (risk limits not unified), G-6 (kill switch inert by default), G-7 (risk state lost on restart), G-8 (NaN approves), G-10 (testnet guard substring), G-2 (readiness passes 0-byte files) | Stop other work. The affected mode gate stays closed. Add a failing test first, then fix, then run the full suite. No merge with an open S1. |
| S2 | A defect that makes evidence wrong or misleading: cost model, lookahead, metrics, validation, report content. | G-11 (zero default costs), G-12 (no out-of-sample enforcement), G-19, G-20 | Fix before the next evidence run. Reports made with the defect are discarded. |
| S3 | A defect in a non-safety function: monitoring, deployment, storage, configuration quirks that fail closed. | G-4, G-14 to G-16, G-24 to G-27 | Fix in normal order. |
| S4 | Documentation or cosmetic. | G-31 | Fix when convenient. |

**Rules.**

- Every S1 and S2 fix lands with a test that fails before the fix and passes after (a Not covered row becomes an automated row in section 3).
- A defect found by an unexpected run (paper, demo or testnet) is reproduced as a test where possible before it is fixed.
- A bug that is only in the docs is recorded in [audit-docs-drift.md](audit-docs-drift.md) as a `D-#`, not here.
- Triage targets and timelines are Owner input required (not set in this draft).

## 6. Release Criteria per Mode Gate

Modes advance in one direction: backtest, then paper, then demo, then live. A gate opens only when every item in its list is true and recorded. These lists are sourced from [RFC-004](rfc-silverbot-readiness-gates.md) (section 7.1 conditions and the readiness checkers), the old `BACKTESTING.md` ("Backtest Before ML / Paper / Live Trading", pass and fail criteria, red flags) and the BRD success metrics. The RFC-004 conditions are proposals for the owner to accept or change; they are not approvals. Thresholds come from the BRD; where the BRD marks a value Owner input required or Open, the gate cannot pass until it is set.

Nothing below is checked today. The current state of each item is shown in the status column.

### 6.1 Gate 1: backtest (entering and leaving)

Prerequisites to start evidence runs (old "Backtest Before Paper Trading"):

| Item | Status |
|---|---|
| Strategy engine works, with lookahead tests passing (QAD-T128, QAD-T129) | Built; whole-strategy lookahead not proven (G-29) |
| Risk engine works (QAD-T97, QAD-T99 and related) | Built; unified limits and persistence missing (G-5, G-7) |
| Backtester works with costs (QAD-T13, QAD-T14) | Built; zero default costs (G-11) |
| Logs are clear and rejections carry reasons | Built for strategy and risk reasons |
| Historical data source chosen and data loaded (OI-8) | Owner input required; fetch is a stub (G-13) |

Exit criteria (leave backtest, enter paper). All must hold, from a non-empty report:

- [ ] Backtest and out-of-sample reports exist, are non-empty and are valid (G-1). The readiness check must reject empty files (H-2).
- [ ] Costs are included, with non-zero slippage and spread recorded in the report configuration (BRD-M3, G-11).
- [ ] Profit factor meets BRD-M1 (at least 1.2) and expectancy meets BRD-M2 (positive), both after costs. These are minimum research thresholds, not profit guarantees (old `BACKTESTING.md`).
- [ ] Maximum drawdown is within the owner's tolerance (BRD-M4, OI-3) and the trade count meets the owner's minimum (BRD-M5, OI-9).
- [ ] The result is not carried by one trade or one short period (BRD-M6; definition to be written).
- [ ] The out-of-sample result is acceptable under criteria written before the run (BRD-M7), with the final test set untouched during tuning (G-12).
- [ ] No red flag from the old guide applies: profit does not disappear after fees or slippage; not one profitable month; not one trade creating most of the profit; trade count not too small; drawdown not too large. A bad backtest means no paper trading.
- [ ] A walk-forward result shows stability across periods, if walk-forward is built (G-12; otherwise the omission is recorded as an accepted limit by the owner).
- [ ] ML is not trained until the rule-based strategy produces clean historical setup labels (old "Backtest Before ML"); the ML filter stays off until then (RFC-003).

### 6.2 Gate 2: paper (entering and leaving)

Entering paper requires a runtime that runs the paper engine through the entrypoint (G-3, QAD-T73) and a market data source (G-13). Exit criteria (leave paper, enter demo):

- [ ] A non-empty paper trading report exists from a stable run (G-1, RFC-004 condition 1).
- [ ] Paper behaviour matches backtest behaviour within a tolerance written down in advance (BRD-M8; tolerance Open). The old guide lists "paper trading does not match backtest behaviour" as a red flag.
- [ ] The kill-switch drill has been performed (section 4) and the kill switch is armed by default with automatic triggers and a documented reset (RFC-004 condition 4, G-6).
- [ ] Risk limits come from one source capped at 0.005 per trade, 0.02 daily loss and 3x leverage, and risk state survives a restart (RFC-004 condition 5, G-5, G-7).
- [ ] No order was placed without a stop loss and none bypassed the risk engine (BRD-M10, zero); checked in the audit log.
- [ ] Daily and weekly reports are produced without manual calls (G-16).
- [ ] The full suite passes (baseline: 108 passed) and no S1 or S2 bug is open (section 5).

### 6.3 Gate 3: demo (Binance Futures testnet; entering and leaving)

Entering demo requires the demo readiness checker to report ready (18 checks, RFC-004 section 3.1; QAD-T25) and the demo config rules to load (QAD-T23). Exit criteria (leave demo, allow a live proposal to be written):

- [ ] A demo runtime exists that does network I/O against the testnet only, with an exact scheme-and-host URL guard (RFC-004 conditions 2 and 6, G-10, G-17).
- [ ] The testnet dry start and the Telegram test message in section 4 have been performed, and `TELEGRAM_ALERTS_TESTED` was set only after a real message arrived (RFC-004 condition 7, G-15).
- [ ] Demo fills are compared with the cost assumptions; slippage and spread values for later evidence runs are taken from them (BRD-M3).
- [ ] Testnet behaviour is not treated as live behaviour: the testnet book is thin, so demo validates plumbing, not performance (scrutiny section 4).
- [ ] Key handling is settled: keys only from the environment, withdrawals disabled on the exchange key and confirmed by the owner, no secret in any tracked file (RFC-004 condition 8).
- [ ] If ML is used, the NaN flaw is fixed and the filter is wired and tested; otherwise ML stays off (RFC-004 condition 9, G-8, G-9).

### 6.4 Gate 4: live (Planned, blocked; PRD-F12)

Live trading is Planned, blocked. No live code exists and no input reaches a live mode (QAD-T88, QAD-T89, QAD-T91, QAD-T93, QAD-T94, QAD-T116, QAD-T117, QAD-T118, QAD-T124, QAD-T126, QAD-T127 prove this). This gate is not open for this release. It could be proposed only when all ten RFC-004 section 7.1 conditions hold (evidence, runtime, meaningful and consulted readiness, effective kill switch, unified and persisted risk limits, exact testnet guard, real alerting, settled key handling, hardened or disabled ML, recorded owner decisions with explicit written owner approval). Even then it is a separate owner decision recorded as a change record, not something a passing checker grants.

Release items sourced from the old "Backtest Before Live Trading" list, none met today:

- [ ] Backtest passes, out-of-sample test passes, walk-forward is acceptable, paper trading is stable (gates 1 and 2).
- [ ] Kill switch is tested (QAD-T104 and the drill in section 4).
- [ ] Telegram alerts are tested (section 4).
- [ ] The risk engine blocks unsafe trades (QAD-T97, QAD-T98, QAD-T103).
- [ ] The live readiness checker reports ready AND the readiness report is meaningful and consulted at startup (G-2). A green report alone is not permission.

A bad backtest means no live trading; a good backtest does not guarantee profit.

## 7. ML Evaluation

ML is optional and may only approve, reject or reduce risk (PRD-F6, [RFC-003](rfc-silverbot-ml-filter-gate.md)). The AIA ([aia-silverbot.md](aia-silverbot.md)) owns the model lifecycle and risk register; this section records how the coded evaluation is tested.

**Metrics as coded** (descriptions of what the code computes, not results):

| Area | What the code computes | Tests |
|---|---|---|
| Training metrics | Accuracy, precision, recall, F1, positive rate and ROC-AUC at a fixed 0.5 threshold; the test split is created but not scored (D-39, G-22) | QAD-T38 |
| Calibration | Brier score and expected calibration error over equal-width bins (default 10); a report only, no calibrator is fitted | QAD-T36, QAD-T37 |
| Promotion policy | Primary metric accuracy; maximum Brier score and minimum sample count limits; test degradation and final-test misuse checks; narrower than the original plan (D-36) | QAD-T45, QAD-T61, QAD-T62, QAD-T63, QAD-T64, QAD-T65, QAD-T46, QAD-T66, QAD-T142 |
| Filter decisions | Approve at or above the minimum probability, reduce risk between the thresholds, reject below the reduce-risk threshold, pass through when disabled or no model | QAD-T40, QAD-T41, QAD-T60, QAD-T42, QAD-T144 |

**Leakage tests.** Feature names are screened for leakage keywords (QAD-T141); splits are chronological with no shuffle (QAD-T35); a candidate optimised on the final test set is rejected (QAD-T142); the strategy and structure code is tested for lookahead (QAD-T128, QAD-T129). Leakage control is name-based, and there is no purge or embargo, so leakage through higher-timeframe features is possible and untested (G-22, section 3.5).

**Required before any model could be trusted** (all Not covered today): NaN output handling (G-8), out-of-range probability handling (G-32), stale and corrupt artifact handling (G-28), untrusted pickle load (G-23), purge or embargo and higher-timeframe lookahead (G-22), registry activation bypassing promotion (G-22). A model must also beat the unfiltered rule-based trades on a held-out set (section 3.7) before it is described as useful. No model is shipped, so no ML evidence exists.

## 8. Self-Check

- [x] Every one of the 108 test functions in `tests/*.py` appears in at least one QAD-T# row (verified by script; result in the task report: 108 of 108).
- [x] Every `tests/<file>.py::<name>` reference names a test that exists (verified by grep for `def <name>`).
- [x] Every Not covered row cites an existing `G-#` and is listed in section 3.8 (45 rows).
- [x] Section 3.7 records zero measured performance numbers; every metric is Not yet measured with a `G-#`.
- [x] PRD-F1 to PRD-F12 each appear in the traceability table, and PRD-F12 is labelled Planned, blocked.
- [x] Release criteria for the four mode gates cite RFC-004 and the old backtesting guide, and nothing is checked that is not true today.
- [x] No placeholder tokens, no em dashes, and links point only to existing files.
- [ ] Every Not covered row in section 3.8 has been closed by a test (open; tracked by the G-# column).
