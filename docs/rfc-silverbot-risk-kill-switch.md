# Request for Comments (RFC) / Tech Spec

**Title:** Risk Engine and Kill Switch: the mandatory gate between a signal and an order
**Project:** Silver Bot (ICT Silver Bullet trading bot)
**RFC ID:** `silverbot-rfc-002`
**Version:** 0.1
**Author:** Cian Jake Francisco
**Status:** Draft
**Last updated:** 2026-10-14
**Last reconciled:** 2026-10-09 against code at commit `70ccaec` (HIGH safety fixes batch 1: `5e4acc5` G-5, `08c81ad` G-6, `2d7f713` G-7); sections 2, 3.5, 3.6, 3.7 and 4 to 8 re-checked 2026-10-09 against `099085b` (G-3 entrypoint batch 2: `4726cb5` `build_risk_config`, `f84557e` simulated per-run kill switch); sections 3.6, 3.7, 3.9 and 4 to 8 re-checked 2026-10-14 against `40ea0b1` (PRD-F2 to PRD-F5 batch: `cf8d41f` armed path-less switch and paper flatten, `973cd82` paper runtime calling `build_risk_engine(config, storage)` and stale-order expiry)
**PRD Reference:** [prd-silverbot.md](prd-silverbot.md) PRD-F3 (with PRD-F4 for the paper loop that calls it)
**SDD Reference:** [sdd-silverbot.md](sdd-silverbot.md) §4.1 (runtime sequences), §5.3 (kill switch), §5.4 (stop-loss requirement), §5.5 (leverage cap and position limits)

This RFC is the single source of the risk rules, defaults, rejection reasons and kill-switch behaviour. It replaces the old `RISK_POLICY.md`. Where the old policy and the code disagree, the code wins and the disagreement is cited as a `D-#` or `H-#` finding in [audit-docs-drift.md](audit-docs-drift.md). All `file:line` references are relative to `src/silver_bot/` and describe the code at the reconciled commit.

## 1. Context & Objective

Every trade candidate produced by the strategy ([RFC-001](rfc-silverbot-signal-engine.md)) must pass the risk engine before any simulated order exists. The risk engine sizes the position and applies a fixed list of gates. It returns an approved or rejected decision with an explicit reason (`risk/models.py:94-102`). It is mandatory in both the backtest loop and the paper loop (`backtest/engine.py:173`, `execution/paper_trading.py:229`).

Objectives:

1. State every gate in evaluation order with its condition, default and verbatim reason.
2. State the kill switch exactly as built: what trips it, what it blocks, and what it does not do.
3. Record, without softening, where the limits are not unified or not enforced (G-5, G-6, G-7; each Partial since batch 1).

Standing safety rules carried from the old policy and the project instructions (these are rules for the project; the enforcement status of each is in section 6):

- Never enable live trading by default, place real orders without live mode, hardcode keys, use martingale, average down, trade without a stop loss, bypass the risk engine, bypass the kill switch, let ML place trades, increase risk because of ML output, or optimise on the final test set.
- Default mode is paper or backtest. Allowed runtime modes are `paper`, `backtest` and `demo`; live is rejected at config load (`config/settings.py:101,105-106`).

No performance claim is made. The evidence reports are 0 bytes (G-1).

## 2. Proposed Solution, as built

`RiskManagementEngine.evaluate(request)` is a sequential check. If the engine was given a state store and loading it failed, it rejects every request with `Risk state could not be loaded; trading halted` (`risk/engine.py:41-42`). Otherwise it rolls the trading day (saving state if the day changed), then runs the 14 gates in the order of section 3.2. The first failing gate returns a rejected `RiskDecision` and no later gate runs (`risk/engine.py:38-107`). Gates 10 and 11 also trip the kill switch (section 3.6).

Two further methods keep the engine's counters:

- `reserve_trade(day)` rolls the day, then increments `trades_today` and `open_positions`, then saves state (`risk/engine.py:109-115`).
- `release_trade(realized_pnl, day)` rolls the day, decrements `open_positions` (never below 0), adds the PnL to `daily_realized_pnl`, increments `consecutive_losses` on a loss, resets it to 0 on a win and leaves it unchanged on a flat result. If the streak reaches `max_consecutive_losses` it trips the kill switch. It then saves state (`risk/engine.py:117-127`).
- Saving is a no-op without a store, and after a failed load (`risk/engine.py:131-133`).

`roll_day` resets `daily_realized_pnl` and `trades_today` when the signal day differs from the current day. It does **not** reset `consecutive_losses` or `open_positions` (`risk/models.py:60-66`).

Where it is called:

| Caller | Order around the risk engine | Source |
|--------|------------------------------|--------|
| Backtest | strategy, then ML filter (reject stops here), then `risk.evaluate`, then ML risk multiplier (reduce only), then `reserve_trade` | `backtest/engine.py:144,173,212,222` |
| Paper loop | strategy, then ML filter (reject stops here), then `risk.evaluate`, then ML risk multiplier (reduce only), then `submit_limit_order`, then `reserve_trade` | `execution/paper_trading.py:162,229,274,290` |

The default engine in both callers is built with a default `RiskConfig`, which has **no kill-switch path** and no state store (`backtest/engine.py:48`, `execution/paper_trading.py:57`). A CLI backtest does not use that default: `run_backtest` gives each engine a `BacktestConfig` whose `risk` comes from settings with a simulated kill-switch path (section 3.6).

`build_risk_config(config: AppConfig) -> RiskConfig` (`risk/factory.py:15-23`, `4726cb5`) is the one place that turns settings into a `RiskConfig`. It maps `max_risk_per_trade`, `max_daily_loss` and `max_leverage` and passes `kill_switch_path` only when `kill_switch_enabled` is true; the other `RiskConfig` fields keep their defaults. `build_risk_engine(config: AppConfig, storage: SQLiteStorage | None = None)` (`risk/factory.py:26-33`, `5e4acc5`) wraps it and attaches `storage` (already initialised) as the state store; its behaviour did not change (`tests/test_risk_engine.py:384` asserts `build_risk_engine(config).config == build_risk_config(config)`). Callers: `build_backtest_config` (`backtest/runner.py:39-67`) takes `build_risk_config(config)` and replaces only `kill_switch_path` with the run's simulated path, so CLI backtests run with the settings caps. The paper and demo runtime calls `build_risk_engine(config, storage)` (`execution/runtime.py:76`, `973cd82`), so paper and demo run with the settings caps, the settings kill switch and persisted risk state. A `PaperTradingEngine` built without a `risk` argument (tests only) still builds a default engine (G-5, G-6, G-7 Partial).

## 3. Technical Details & Contracts

### 3.1 `RiskConfig` defaults and validation (`risk/models.py:14-47`)

`RiskConfig` is a frozen dataclass. Defaults are research and backtest defaults.

| Field | Default | Validation (raises `ValueError` with this text) | Source |
|-------|---------|-----------------------------------------------|--------|
| `risk_per_trade` | 0.005 | outside `(0, 0.005]` (`MAX_RISK_PER_TRADE = 0.005`): `risk_per_trade must be greater than 0 and no more than 0.5%` | `risk/models.py:10,21,32-33` |
| `minimum_stop_distance` | 0.01 | `<= 0`: `minimum_stop_distance must be positive` (absolute price units) | `risk/models.py:22,34-35` |
| `minimum_reward_to_risk` | 2.0 | `<= 0`: `minimum_reward_to_risk must be positive` | `risk/models.py:23,36-37` |
| `max_daily_loss` | 0.02 | outside `(0, 1]`: `max_daily_loss must be greater than 0 and no more than 100%` | `risk/models.py:24,38-39` |
| `max_consecutive_losses` | 3 | `< 1`: `max_consecutive_losses must be at least 1` | `risk/models.py:25,40-41` |
| `max_trades_per_day` | 3 | `< 1`: `max_trades_per_day must be at least 1` | `risk/models.py:26,42-43` |
| `max_open_positions` | 1 | `< 1`: `max_open_positions must be at least 1` | `risk/models.py:27,44-45` |
| `max_leverage` | 3.0 | `<= 0`: `max_leverage must be positive` | `risk/models.py:28,46-47` |
| `kill_switch_path` | `None` | none; `None` means the kill switch is never active | `risk/models.py:29`, `risk/engine.py:27` |

The risk-per-trade ceiling inside `RiskConfig` is **0.005 (0.5 percent)**, equal to the default, in every context including backtests (`5e4acc5`; before it the ceiling was 0.05). `tests/test_risk_engine.py:129` `test_risk_per_trade_above_half_percent_is_rejected` and `:134` `test_risk_per_trade_at_half_percent_is_allowed` pin both sides.

### 3.2 Gates in evaluation order (`risk/engine.py:38-107`)

Direction is `request.direction.upper()`. Any value other than `LONG` or `SHORT` gives a stop distance of 0 and is rejected at gate 6 (`risk/engine.py:59-66,135-141`).

| # | Gate | Rejects when | Reason string (verbatim) | Source |
|---|------|--------------|--------------------------|--------|
| 0 | State load | a state store was given and `load_risk_state` raised | `Risk state could not be loaded; trading halted` | `risk/engine.py:30-34,41-42` |
| 1 | Kill switch | `KillSwitch.is_active()` is true (section 3.6) | `Kill switch is active` | `risk/engine.py:48-49` |
| 2 | Equity | `equity <= 0` | `Account equity must be positive` | `risk/engine.py:50-51` |
| 3 | Entry present | `entry_price is None` | `Entry price is required` | `risk/engine.py:52-53` |
| 4 | Stop present | `stop_loss is None` | `Stop loss is required` | `risk/engine.py:54-55` |
| 5 | Take profit present | `take_profit is None` | `Take profit is required` | `risk/engine.py:56-57` |
| 6 | Stop side | stop distance `<= 0` (stop on the wrong side, or direction not LONG or SHORT) | `Invalid stop loss for trade direction` | `risk/engine.py:65-66` |
| 7 | Minimum stop distance | `stop_distance < minimum_stop_distance` | `Stop-loss distance below configured minimum` | `risk/engine.py:67-68` |
| 8 | Take-profit side | reward distance `<= 0` | `Invalid take profit for trade direction` | `risk/engine.py:75-76` |
| 9 | Reward-to-risk | `reward_distance / stop_distance < minimum_reward_to_risk` | `Reward-to-risk below configured minimum` | `risk/engine.py:78-79` |
| 10 | Daily loss | `daily_realized_pnl <= -(equity * max_daily_loss)`; also trips the kill switch | `Max daily loss limit reached` | `risk/engine.py:81-84` |
| 11 | Consecutive losses | `consecutive_losses >= max_consecutive_losses`; also trips the kill switch | `Max consecutive losses limit reached` | `risk/engine.py:85-87` |
| 12 | Trades per day | `trades_today >= max_trades_per_day` | `Max trades per day limit reached` | `risk/engine.py:88-89` |
| 13 | Open positions | `open_positions >= max_open_positions` | `Max open positions limit reached` | `risk/engine.py:90-91` |
| 14 | Leverage | `notional / equity > max_leverage` (sizing is computed first) | `Maximum leverage exceeded` | `risk/engine.py:93-98` |
| - | Approve | all gates passed | `Risk approved` | `risk/engine.py:100-107` |

Reward-to-risk and leverage values are attached to a rejection only when already computed; earlier gates return 0.0 for them (`risk/engine.py:151-163`).

Rules that follow from the code:

- **Daily-loss base.** The limit is measured against the **current request equity**, not start-of-day equity: `equity * max_daily_loss` (`risk/engine.py:81-82`). The check uses `<=`, so reaching exactly the limit blocks.
- **Distances.** Stop distance and reward distance are direction-aware (LONG: `entry - stop` and `take_profit - entry`; SHORT: `stop - entry` and `entry - take_profit`) and are in absolute price units (`risk/engine.py:135-149`; D-63).
- **A stop loss is mandatory.** Gates 4, 6 and 7 together reject a missing stop, a wrong-side stop and a too-close stop.
- **No martingale or averaging down.** Position size depends only on equity, `risk_per_trade` and stop distance; no gate or method increases size after a loss (`risk/engine.py:93-96`).

### 3.3 Position sizing (`risk/engine.py:93-96`)

```text
risk_amount   = equity * risk_per_trade
position_size = risk_amount / stop_distance
notional      = position_size * entry_price
leverage      = notional / equity
```

An approved `RiskDecision` carries `position_size`, `risk_amount`, `reward_to_risk` and `leverage` with reason `Risk approved` (`risk/engine.py:100-107`). Sizing does not round to an exchange quantity step, minimum notional or lot size, and does not include fees. The paper executor charges fees on top of the risk amount (`execution/paper_executor.py:172-175`).

### 3.4 ML interaction with risk

ML runs **before** the risk engine and can only stop a signal or later shrink an approved size. It never raises risk:

- ML `REJECT` ends the signal before `risk.evaluate` (`backtest/engine.py:149`, `execution/paper_trading.py:203`).
- ML `REDUCE_RISK` is applied **after** risk approval by multiplying `position_size`, `risk_amount` and `leverage` by the multiplier. The backtest clamps the multiplier to `[0, 1]` (`backtest/engine.py:510-523`). The paper loop applies the multiplier as-is, relying on `MLFilterConfig` validation `0 < m <= 1` (`execution/paper_trading.py:274-281`, `ml/filter.py:43-44`; D-62). Full ML rules are in [RFC-003](rfc-silverbot-ml-filter-gate.md).

### 3.5 Where the limits come from, and where they disagree

| Limit | `RiskConfig` (enforced by the engine) | `Settings` / env (config load) | Readiness checkers |
|-------|---------------------------------------|--------------------------------|--------------------|
| Risk per trade | default 0.005, accepts up to 0.005 | `MAX_RISK_PER_TRADE` default 0.005; outside `(0, 0.005]` rejected **in every mode** (`config/settings.py:180-181`) | pass when `<= 0.005` (`readiness.py:19`) |
| Daily loss | default 0.02, accepts up to 1.0 | `MAX_DAILY_LOSS` default 0.02; above 0.02 rejected in demo only (`config/settings.py:191-192`) | pass when `<= 0.02` |
| Leverage | default 3.0, any positive value | `MAX_LEVERAGE` default 3; above 3 rejected in demo only (`config/settings.py:193-194`) | pass when `<= 3.0` |
| Kill switch | `kill_switch_path` default `None` | `KILL_SWITCH_ENABLED` default false; `KILL_SWITCH_PATH` default empty; enabled without a path rejected in every mode (`config/settings.py:174-175`); both required in demo (`config/settings.py:185-188`) | enabled and path set required |

The Settings fields reach `RiskConfig` only through `build_risk_config` (`risk/factory.py:18-23`). CLI backtests use it through `build_backtest_config` (`backtest/runner.py:53`; `tests/test_backtest_runner.py:146`); the paper and demo runtime uses it through `build_risk_engine` (`execution/runtime.py:76`, `973cd82`); a `PaperTradingEngine` built without a `risk` argument still uses the defaults (`execution/paper_trading.py:57`). The 0.5 percent per-trade cap is now enforced twice, at config load and in `RiskConfig`, so no path can size above it (`tests/test_config.py:228`, `tests/test_risk_engine.py:129`). `MAX_DAILY_LOSS` and `MAX_LEVERAGE` are still bounded only in demo mode at load; `RiskConfig` accepts any daily loss in (0, 1] and any positive leverage (D-11, H-5, G-5 Partial). `tests/test_risk_engine.py:138` `test_build_risk_engine_carries_settings_caps` and `:162` `test_build_risk_engine_ignores_kill_switch_path_when_disabled` and `:384` `test_build_risk_config_maps_settings` pin the mapping.

### 3.6 Kill switch (`risk/kill_switch.py:12-68`)

| Property | As built | Source |
|----------|----------|--------|
| Active when | Fail closed. With `path` None: active once `trip` has been called on that instance (in memory, lost when the process ends). Otherwise active when `os.stat(path)` succeeds (a file with any content, or a directory), when it raises any `OSError` other than `FileNotFoundError` (for example permission denied), or when the file is missing and the nearest existing ancestor is not a directory. The ancestor check exists because Windows reports a regular-file parent as "path not found" rather than `NotADirectoryError` | `risk/kill_switch.py:24-53`; D-80 |
| Automatic trip | `trip(reason)` creates parent directories and writes `{"reason": <reason>, "tripped_at": <UTC ISO-8601>}` as sorted-key JSON. If the switch is already active it writes nothing, so the first reason is kept. With no path it records the reason in `tripped_reason` instead, so the instance halts in memory (`cf8d41f`). The engine calls it on gate 10 (`Max daily loss limit reached`), gate 11 (`Max consecutive losses limit reached`, which also covers a streak loaded from `risk_state`) and in `release_trade` when the streak reaches the limit. A failed write raises `OSError` out of the engine call; `release_trade` saves `risk_state` first, so the loss and released position are persisted even then (`tests/test_risk_engine.py::test_loss_is_persisted_even_if_kill_switch_trip_fails`) | `risk/kill_switch.py:55-68`; `risk/engine.py:83,86,128-129` |
| File | The path comes from `RiskConfig.kill_switch_path` (default `None`) unless a `KillSwitch` instance is injected. `build_risk_config` passes `Settings.kill_switch_path` when `KILL_SWITCH_ENABLED=true`; the paper and demo runtime uses it through `build_risk_engine` (`973cd82`) | `risk/engine.py:27`; `risk/factory.py:22`; `execution/runtime.py:76` |
| Default | Armed in memory (`cf8d41f`): with no path a gate 10 or 11 trip halts that engine instance until it is discarded; nothing is written, so the halt does not survive a restart | `risk/kill_switch.py:20-29,55-66`; `risk/models.py:29`; `tests/test_risk_engine.py::test_default_engine_kill_switch_is_armed` |
| Backtests: simulated per run (ED-5) | Every engine run in `run_backtest`, the full period and each of the three out-of-sample segments, gets its own `KILL_SWITCH` path inside a fresh `tempfile.TemporaryDirectory()`, set by `replace(build_risk_config(config), kill_switch_path=...)`. It is on even when `KILL_SWITCH_ENABLED=false`, trips on gates 10 and 11 like the real file, and a trip blocks every later entry in that simulated run. The real `KILL_SWITCH_PATH` is never given to a backtest engine, so a real kill file neither blocks a backtest nor is modified by one. `_read_trip` reads the file before the directory is deleted and reports `tripped`, `reason` and `tripped_at` (an unreadable file reports `tripped: true` with null reason): in `backtest_run.json` under `kill_switch` with `mode: simulated_per_run`, and in each segment of `out_of_sample_validation_report.json`. Decision ED-5 in the [G-3 entrypoint spec](superpowers/specs/2026-10-09-g3-entrypoint-design.md) | `backtest/runner.py:53,148,159-188,191-205`; `tests/test_backtest_runner.py:110,123,131` |
| Check timing | On every `evaluate`, after the state-load check and the day roll, as gate 1; not latched in memory, but a tripped file outlasts the day roll and a restart | `risk/engine.py:41-49` |
| Effect | Rejects new entries with `Kill switch is active`. In the paper loop an active switch also flattens: an open paper position closes at the candle close with exit reason `KILL_SWITCH` and a pending paper order is cancelled with its reservation released (`cf8d41f`). The stream is not stopped and the process keeps running | `execution/paper_trading.py:88-101`; `execution/paper_executor.py:126-162` |
| Creation | The owner by hand, or `trip` on gates 10 and 11 | D-22 (Partial) |
| Reset | Read the JSON reason, then delete the file by hand with the bot stopped; no command exists ([ops-silverbot.md](ops-silverbot.md)) | G-6 |
| Alerting | The paper loop records one `KILL_SWITCH_ACTIVE` event and sends one alert per run (`_kill_alert_sent`), and a risk rejection whose reason equals `Kill switch is active` is recorded as `KILL_SWITCH_ACTIVE` with a `kill_switch_active` audit entry | `execution/paper_trading.py:67,85-86,239-273` |
| Emergency shutdown | **Partial.** Paper positions and pending paper orders are flattened (above); nothing stops the process, and there is no exchange position to close because no real order path exists (G-21) | `execution/paper_executor.py:126-162`; `execution/paper_trading.py:88-101` |

The paper-loop alert text is sent through the Telegram client, which has no network transport (D-3, G-15), so in practice the alert reaches only the in-memory record.

### 3.7 Risk state and persistence

`RiskState` holds `current_day`, `daily_realized_pnl`, `consecutive_losses`, `trades_today` and `open_positions` (`risk/models.py:50-58`). Since `2d7f713` it can persist:

- `RiskStateStore` is a Protocol with `load_risk_state() -> RiskState | None` and `save_risk_state(state)` (`risk/models.py:73-78`). `SQLiteStorage` implements it with a single-row `risk_state` table (`storage/sqlite.py:117-125,261-319`; columns in [SDD §3.2](sdd-silverbot.md)).
- With `state_store` set and no explicit `state`, the engine loads the row at construction. No row means a fresh `RiskState`. Any exception from the load (including `RiskStateError` for a bad date, a non-finite PnL, a negative or non-integer count, or an `sqlite3.Error`) locks the engine: every `evaluate` returns `Risk state could not be loaded; trading halted` and nothing is saved (`risk/engine.py:28-36,41-42,131-133`). The cause is logged at ERROR as `risk state could not be loaded; trading halted: <error>` (`risk/engine.py:35`).
- The engine saves after `reserve_trade`, after `release_trade`, and in `evaluate` when the day rolls.
- Without a store (backtests, including every CLI backtest run and segment, and a `PaperTradingEngine` built with no `risk` argument) state is in memory only, as before. The paper and demo runtime attaches the SQLite store (`execution/runtime.py:76`, `973cd82`).

Remaining (G-7 Partial): `run_paper_session` calls `build_risk_engine(config, storage)` (`973cd82`), so a paper or demo restart reloads the counters. `open_positions` survives a restart but paper positions do not, so after a crash with an open trade gate 13 rejects every new trade until the owner resets the row ([ops-silverbot.md](ops-silverbot.md)).

Stale pending orders (H-10, fixed in `973cd82`): `reserve_trade` still runs at order creation, but a pending order that has not filled by its `expires_at` (the end of its Silver Bullet window) is cancelled, and the paper loop calls `release_trade(realized_pnl=0.0)` on the cancel, so the reservation no longer leaks. The backtest engine expires orders the same way with an `order_cancelled` audit entry (`backtest/engine.py:85-92`; `execution/paper_executor.py:93-99`; `execution/paper_trading.py:128-130`; `tests/test_paper_trading.py::test_unfilled_paper_order_is_cancelled_when_session_window_ends`).

### 3.8 Non-risk checks in the paper loop

These are not risk gates but also stop a candidate before an order exists:

| Check | Reason / text (verbatim) | Source |
|-------|--------------------------|--------|
| ML reject (event type `RISK_REJECTED`) | `ML rejected: <ml reason>` | `execution/paper_trading.py:208`, `backtest/engine.py:155` |
| ML reduce suffix on the approved reason | `<risk reason>; ML reduced risk` | `execution/paper_trading.py:280`, `backtest/engine.py:522` |
| Order submitted without approval | `risk_decision must be approved before paper order submission` | `execution/paper_executor.py:57-60` |
| Order missing price levels | `paper order requires entry, stop loss, and take profit` | `execution/paper_executor.py:57-60` |

### 3.9 Old policy rules: carried and dropped

| Old rule (RISK_POLICY.md) | Status | Finding |
|---------------------------|--------|---------|
| Seven mandatory gates (sizing, stop-loss, RR, daily loss, consecutive loss, max trades, kill switch) | Carried; the engine enforces a superset of 14 (adds equity, entry and take-profit presence, minimum stop distance, take-profit side, open positions, leverage) | none |
| Demo gate: `MAX_RISK_PER_TRADE <= 0.005`, `MAX_DAILY_LOSS <= 0.02`, `MAX_LEVERAGE <= 3` | Carried. `MAX_RISK_PER_TRADE <= 0.005` is checked in every mode and in `RiskConfig`; the other two in demo only. `build_risk_config` wires all three; CLI backtests and the paper and demo runtime use it (`973cd82`) | D-11, H-5 (Partial) |
| "Kill switch validation" is mandatory | Partly carried: fail-closed check, and an enabled switch needs a path in every mode; with no path it is armed in memory only (`cf8d41f`) | D-12, H-9 (Partial) |
| Risk module triggers the kill switch | Carried since `08c81ad`: gates 10 and 11 and `release_trade` call `trip` | D-22 (Partial: paper flatten since `cf8d41f`; no process stop) |
| ML reduce risk "can only shrink" size, risk amount and leverage | Carried with a note: bound by config validation in the paper loop, clamped in the backtest | D-62 |
| Stop-loss distance validation | Carried; distance is in absolute price units, default 0.01, not a percentage or ATR multiple | D-63 |
| "Trade before readiness checks pass" is forbidden | Dropped as an enforced control: readiness reports are advisory and no code reads them | D-10, G-2 |
| Safe defaults `LIVE_TRADING=false`, `PAPER_TRADING=true`, `DEMO_TRADING=false` | Carried: they are the `load_config` defaults (`config/settings.py:69-72`) | none |
| Backtest routes every candidate through the risk engine and logs rejections | Carried (`backtest/engine.py:173`) | none |

## 4. Alternatives Considered

| Alternative | Why not (as built) |
|-------------|--------------------|
| Risk limits taken from `Settings` and passed into `RiskConfig` | Built as `build_risk_engine` (`5e4acc5`) and split out as `build_risk_config` (`4726cb5`); CLI backtests use the latter; the paper and demo runtime calls the former (`execution/runtime.py:76`, `973cd82`). |
| Kill switch armed by default, with automatic triggers on the daily-loss and consecutive-loss limits | Triggers built (`08c81ad`). The file switch is armed when `build_risk_config` runs with `KILL_SWITCH_ENABLED=true`; with no path the switch is armed in memory (`cf8d41f`). CLI backtests always run a simulated per-run switch instead (`f84557e`). |
| Backtests use the real kill-switch file, or run with no kill switch | Rejected (ED-5). With the real file, a simulated loss would write the real halt file and an owner's halt file would block every backtest; a design that ran backtests with no kill-switch path was rejected before ED-5. A per-run switch in a temporary directory keeps the trip behaviour and touches nothing outside the run. |
| Persisted risk state across restarts | Built as the `risk_state` table (`2d7f713`); used by a store-backed engine, which the paper and demo runtime builds (`973cd82`). |
| Persisting `open_positions` reconciled against actual positions | Not built: the paper executor keeps positions in memory, so the saved count can outlive them. Manual reset is the workaround (OPS). Planned with G-21. |
| Daily loss measured on start-of-day equity | The code uses current equity (`risk/engine.py:81-82`). This is a different, looser measure after profits; the choice is Open. |
| Latching the kill switch | Not built in memory: the switch re-reads the file on every call, so deleting the file re-enables entries immediately. A trip writes the file, so an automatic halt persists until the owner deletes it. |
| Closing or reducing open exposure on a trip | Built for paper only (`cf8d41f`): the paper loop flattens on an active switch. Stopping the process on a trip is not built. |
| Stop distance as a percentage or ATR multiple | Not built (D-63); absolute price units are used. |

## 5. Safety, Privacy & Performance

**Safety.**

- The risk engine has no exchange access and cannot place orders. It cannot be bypassed by ML: ML runs before it and can only reject or shrink (section 3.4).
- The only real-order methods raise `OrderPlacementDisabled`, and live is rejected at config load, so a risk approval cannot reach a real exchange (`exchange/base.py:44-52`, `config/settings.py:105-106`).
- With no path the kill switch is armed in memory only (`cf8d41f`): a trip halts that engine instance but is lost on restart. A file path reaches `RiskConfig` through `build_risk_config` (settings, used by the paper and demo runtime) or `run_backtest` (a simulated path) (G-6). With a path it fails closed and trips itself on the loss limits. A backtest cannot read, create or delete the real kill-switch file.
- Risk per trade cannot exceed 0.005 in any `RiskConfig` (G-5). Daily-loss and leverage limits are only as strict as the `RiskConfig` the caller builds.

**Privacy.** The engine handles numbers only and holds no keys or personal data.

**Performance.** Each evaluation is constant-time arithmetic plus one or a few `os.stat` calls, and one SQLite write when a store is attached and the day rolls. No benchmark exists and none is claimed.

**Evidence of behaviour (tests).** `tests/test_risk_engine.py` has 32 test functions. The original 10: valid sizing (size 10, risk 50, RR 2 at 0.5 percent risk), wrong-side stop, missing stop, low RR, daily-loss lockout, consecutive-loss lockout, max-trades lockout, max-open-positions lockout, leverage rejection (now at 0.5 percent risk with `max_leverage=0.4`) and kill-switch active. Added in batch 1: the 0.5 percent cap (`:129`, `:134`), `build_risk_engine` mapping (`:138`, `:162`, `:324`), fail-closed kill switch (`:172` directory, `:179` `OSError`, `:188` file parent, `:195` missing file inactive), trip payload and first reason (`:199`, `:210`), no-path switch armed in memory (`:219`, changed in `cf8d41f`) and the default engine armed (`:230`, added in `cf8d41f`), auto-trip on three losing releases (`:243`) and on the daily-loss rejection (`:257`), state across an engine restart (`:274`, `:292`), corrupt state halts (`:305`) and no store means no persistence (`:334`). Added in the batch 1 review: the loss is saved before a failing trip (`:341`) and a load error is logged (`:361`). Added in batch 2: `build_risk_config` mapping (`:384`). `tests/test_backtest_runner.py` covers the simulated kill switch: the real file is never used or changed (`:110`), the switch is on with `KILL_SWITCH_ENABLED=false` (`:123`), trip records are read and reported (`:131`, `:92`), and settings caps reach the backtest `RiskConfig` (`:146`). `tests/test_storage.py:36-69` covers the `risk_state` table, round trip, missing row and four corrupt rows. `tests/test_paper_trading.py` covers the `KILL_SWITCH_ACTIVE` event and alert, the flatten of an open position and a pending order (`test_kill_switch_closes_open_paper_position`, `test_kill_switch_cancels_pending_paper_order`) and stale-order expiry (`test_unfilled_paper_order_is_cancelled_when_session_window_ends`). There are still no direct tests for the minimum-stop-distance gate, the equity gate, the entry and take-profit presence gates, or `roll_day` behaviour across days (G-28).

## 6. Execution Status

| Capability | Status | Evidence |
|-----------|--------|----------|
| 14-gate risk engine with sizing and verbatim reasons | Built | `risk/engine.py:38-107`; 32 risk test functions |
| `RiskConfig` validation, 0.5 percent per-trade cap | Built | `risk/models.py:10,31-47`; `5e4acc5` |
| Fail-closed file kill switch with paper-loop event and alert | Built | `risk/kill_switch.py:24-53`; `execution/paper_trading.py:88-101`; `08c81ad` |
| Automatic kill-switch trip on daily-loss and consecutive-loss limits | Built | `risk/kill_switch.py:55-68`; `risk/engine.py:83,86,129`; `08c81ad` |
| Kill switch armed from settings | Built | `build_risk_config` passes the path (`risk/factory.py:22`); the paper and demo runtime builds its engine with it (`execution/runtime.py:76`, `973cd82`); with no path the switch is armed in memory (`cf8d41f`) |
| Simulated per-run kill switch in backtests | Built | `backtest/runner.py:159-188`; `f84557e`; ED-5 |
| Emergency shutdown (close positions, stop the loop) | Partial | Paper flatten on an active switch (`execution/paper_executor.py:126-162`, `cf8d41f`); no process stop (G-6, G-21) |
| Kill-switch reset tooling | Planned | Manual file delete only ([ops-silverbot.md](ops-silverbot.md)) |
| Settings-to-`RiskConfig` wiring | Partial | `build_risk_config` (`risk/factory.py:15-23`, `4726cb5`) used by CLI backtests; `build_risk_engine` (`risk/factory.py:26-33`) called by the paper and demo runtime (`execution/runtime.py:76`, `973cd82`) |
| Persisted risk state | Partial | `risk_state` table and engine store (`2d7f713`); attached by the paper and demo runtime (`973cd82`); `open_positions` can outlive a paper position after a crash (G-7) |
| Release of stale pending-order reservations | Built | Expiry at window end with `release_trade(0.0)` (`execution/paper_executor.py:93-99`, `execution/paper_trading.py:128-130`, `backtest/engine.py:85-92`; `973cd82`); H-10 fixed |
| Gap-through-stop handling in execution | Planned | Exits fill at the exact stop or target (G-21) |
| Risk engine used by a running backtest | Built | `python -m silver_bot --candles PATH` in backtest mode (`main.py:155-173`, `099085b`) |
| Risk engine used by a running paper or demo process | Built | `run_paper_session` builds `PaperTradingEngine` with `build_risk_engine(config, storage)` (`execution/runtime.py:42-97`, `973cd82`); `main.py:114-148` runs it for paper and demo. No live network run is recorded (G-3) |

## 7. Risks & Open Items

| Ref | Item | Status |
|-----|------|--------|
| G-5 | Per-trade risk capped at 0.5 percent in `RiskConfig` and at load; `build_risk_config` maps settings and CLI backtests use it. The paper and demo runtime uses it since `973cd82`. Remaining: daily-loss and leverage bounds demo-only at load. | Partial (`5e4acc5`) |
| G-6 | Fail-closed check and auto-trip built; backtests run a simulated per-run switch. Since `cf8d41f` the path-less switch is armed in memory and the paper loop flattens on a trip; since `973cd82` the paper and demo runtime arms the file switch from settings. Remaining: no process stop, no reset tooling beyond deleting the file. | Partial (`cf8d41f`) |
| G-7 | `risk_state` persistence built. The paper and demo runtime attaches the store since `973cd82` (backtests are in memory by design). Remaining: `open_positions` can outlive paper positions after a crash and needs a manual reset. | Partial (`973cd82`) |
| G-21 | Execution gaps: stale-order expiry and reservation release built (H-10 fixed, `973cd82`); kill-switch flatten in paper (`cf8d41f`). Remaining: no gap-through-stop. | Partial (`973cd82`) |
| G-3 | Backtest runtime built (`099085b`). Paper and demo runtime built (`973cd82`): `run_paper_session` calls `build_risk_engine(config, storage)`. Remaining: no recorded live network run. H-4 fixed (`f6bc017`). | Partial (`973cd82`) |
| G-28 | Test-gap family: no tests for the minimum-stop-distance, equity and price-presence gates or `roll_day` across days. | Open |
| Daily-loss base | Whether the limit should use start-of-day equity. | Open |
| Latching | Whether a tripped switch should require an explicit reset step rather than file deletion alone. | Open |
| Daily-loss and leverage caps | Whether `MAX_DAILY_LOSS <= 0.02` and `MAX_LEVERAGE <= 3` should apply in every mode like the per-trade cap. | Open |
| Risk budget | The owner's capital and risk budget are not recorded. | Owner input required (OI-register in the BRD) |

## 8. Self-Check

- [x] All 14 gates are listed in code order with verbatim reasons and `risk/engine.py` lines.
- [x] Every `RiskConfig` default and validation message in section 3.1 matches `risk/models.py:21-47`.
- [x] The kill switch is described as armed in memory by default (no path), fail closed when a path is set, auto-tripping on gates 10 and 11, flattening paper exposure, with no process stop.
- [x] The 0.005 cap in both `RiskConfig` and `load_config`, `build_risk_config` and its backtest caller, and the paper and demo runtime caller of `build_risk_engine`, are stated (G-5, D-11).
- [x] The simulated per-run kill switch for backtests (ED-5) is stated with where its trips are reported.
- [x] Each dropped or changed old-policy rule in section 3.9 carries a `D-#` or `H-#`.
- [x] Status labels in section 6 are Built, Partial or Planned, each with evidence.
- [x] A unified per-trade risk cap exists in code (`5e4acc5`).
- [x] A paper runtime builds its engine from settings with the kill switch armed and state persisted (`execution/runtime.py:76`, `973cd82`).
