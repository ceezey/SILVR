# Request for Comments (RFC) / Tech Spec

**Title:** Risk Engine and Kill Switch: the mandatory gate between a signal and an order
**Project:** Silver Bot (ICT Silver Bullet trading bot)
**RFC ID:** `silverbot-rfc-002`
**Version:** 0.1
**Author:** Cian Jake Francisco
**Status:** Draft
**Last updated:** 2026-10-08
**Last reconciled:** 2026-10-08 against code at commit `62037d1`
**PRD Reference:** [prd-silverbot.md](prd-silverbot.md) PRD-F3 (with PRD-F4 for the paper loop that calls it)
**SDD Reference:** [sdd-silverbot.md](sdd-silverbot.md) §4.1 (runtime sequences), §5.3 (kill switch), §5.4 (stop-loss requirement), §5.5 (leverage cap and position limits)

This RFC is the single source of the risk rules, defaults, rejection reasons and kill-switch behaviour. It replaces the old `RISK_POLICY.md`. Where the old policy and the code disagree, the code wins and the disagreement is cited as a `D-#` or `H-#` finding in [audit-docs-drift.md](audit-docs-drift.md). All `file:line` references are relative to `src/silver_bot/` and describe the code at the reconciled commit.

## 1. Context & Objective

Every trade candidate produced by the strategy ([RFC-001](rfc-silverbot-signal-engine.md)) must pass the risk engine before any simulated order exists. The risk engine sizes the position and applies a fixed list of gates. It returns an approved or rejected decision with an explicit reason (`risk/models.py:79-87`). It is mandatory in both the backtest loop and the paper loop (`backtest/engine.py:157`, `execution/paper_trading.py:207`).

Objectives:

1. State every gate in evaluation order with its condition, default and verbatim reason.
2. State the kill switch exactly as built: what trips it, what it blocks, and what it does not do.
3. Record, without softening, where the limits are not unified or not enforced (G-5, G-6, G-7).

Standing safety rules carried from the old policy and the project instructions (these are rules for the project; the enforcement status of each is in section 6):

- Never enable live trading by default, place real orders without live mode, hardcode keys, use martingale, average down, trade without a stop loss, bypass the risk engine, bypass the kill switch, let ML place trades, increase risk because of ML output, or optimise on the final test set.
- Default mode is paper or backtest. Allowed runtime modes are `paper`, `backtest` and `demo`; live is rejected at config load (`config/settings.py:100,104-105`).

No performance claim is made. The evidence reports are 0 bytes (G-1).

## 2. Proposed Solution, as built

`RiskManagementEngine.evaluate(request)` is a pure sequential check. It first rolls the trading day, then runs the 14 gates in the order of section 3.2. The first failing gate returns a rejected `RiskDecision` and no later gate runs (`risk/engine.py:25-87`).

Two further methods keep the engine's counters:

- `reserve_trade(day)` rolls the day, then increments `trades_today` and `open_positions`.
- `release_trade(realized_pnl, day)` rolls the day, decrements `open_positions` (never below 0), adds the PnL to `daily_realized_pnl`, increments `consecutive_losses` on a loss, resets it to 0 on a win and leaves it unchanged on a flat result (`risk/engine.py:89-105`).

`roll_day` resets `daily_realized_pnl` and `trades_today` when the signal day differs from the current day. It does **not** reset `consecutive_losses` or `open_positions` (`risk/models.py:57-63`).

Where it is called:

| Caller | Order around the risk engine | Source |
|--------|------------------------------|--------|
| Backtest | strategy, then ML filter (reject stops here), then `risk.evaluate`, then ML risk multiplier (reduce only), then `reserve_trade` | `backtest/engine.py:128,157,196,205` |
| Paper loop | strategy, then ML filter (reject stops here), then `risk.evaluate`, then ML risk multiplier (reduce only), then `submit_limit_order`, then `reserve_trade` | `execution/paper_trading.py:140,207,252,267` |

The default engine in both callers is built with a default `RiskConfig`, which has **no kill-switch path** (`backtest/engine.py:41`, `execution/paper_trading.py:49`). Settings values for risk are validated at config load but are never turned into a `RiskConfig` anywhere in `src/` (G-5, D-11, H-5).

## 3. Technical Details & Contracts

### 3.1 `RiskConfig` defaults and validation (`risk/models.py:11-44`)

`RiskConfig` is a frozen dataclass. Defaults are research and backtest defaults.

| Field | Default | Validation (raises `ValueError` with this text) | Source |
|-------|---------|-----------------------------------------------|--------|
| `risk_per_trade` | 0.005 | outside `(0, 0.05]`: `risk_per_trade must be greater than 0 and no more than 5%` | `risk/models.py:18,29-30` |
| `minimum_stop_distance` | 0.01 | `<= 0`: `minimum_stop_distance must be positive` (absolute price units) | `risk/models.py:19,31-32` |
| `minimum_reward_to_risk` | 2.0 | `<= 0`: `minimum_reward_to_risk must be positive` | `risk/models.py:20,33-34` |
| `max_daily_loss` | 0.02 | outside `(0, 1]`: `max_daily_loss must be greater than 0 and no more than 100%` | `risk/models.py:21,35-36` |
| `max_consecutive_losses` | 3 | `< 1`: `max_consecutive_losses must be at least 1` | `risk/models.py:22,37-38` |
| `max_trades_per_day` | 3 | `< 1`: `max_trades_per_day must be at least 1` | `risk/models.py:23,39-40` |
| `max_open_positions` | 1 | `< 1`: `max_open_positions must be at least 1` | `risk/models.py:24,41-42` |
| `max_leverage` | 3.0 | `<= 0`: `max_leverage must be positive` | `risk/models.py:25,43-44` |
| `kill_switch_path` | `None` | none; `None` means the kill switch is never active | `risk/models.py:26`, `risk/engine.py:23` |

The risk-per-trade ceiling inside `RiskConfig` is **0.05 (5 percent)**, ten times the documented default of 0.005. The Settings cap of 0.005 applies only in demo mode and is not connected to `RiskConfig` (section 3.5; G-5).

### 3.2 Gates in evaluation order (`risk/engine.py:25-87`)

Direction is `request.direction.upper()`. Any value other than `LONG` or `SHORT` gives a stop distance of 0 and is rejected at gate 6 (`risk/engine.py:41-48,107-113`).

| # | Gate | Rejects when | Reason string (verbatim) | Source |
|---|------|--------------|--------------------------|--------|
| 1 | Kill switch | the kill-switch file exists | `Kill switch is active` | `risk/engine.py:30-31` |
| 2 | Equity | `equity <= 0` | `Account equity must be positive` | `risk/engine.py:32-33` |
| 3 | Entry present | `entry_price is None` | `Entry price is required` | `risk/engine.py:34-35` |
| 4 | Stop present | `stop_loss is None` | `Stop loss is required` | `risk/engine.py:36-37` |
| 5 | Take profit present | `take_profit is None` | `Take profit is required` | `risk/engine.py:38-39` |
| 6 | Stop side | stop distance `<= 0` (stop on the wrong side, or direction not LONG or SHORT) | `Invalid stop loss for trade direction` | `risk/engine.py:47-48` |
| 7 | Minimum stop distance | `stop_distance < minimum_stop_distance` | `Stop-loss distance below configured minimum` | `risk/engine.py:49-50` |
| 8 | Take-profit side | reward distance `<= 0` | `Invalid take profit for trade direction` | `risk/engine.py:57-58` |
| 9 | Reward-to-risk | `reward_distance / stop_distance < minimum_reward_to_risk` | `Reward-to-risk below configured minimum` | `risk/engine.py:60-61` |
| 10 | Daily loss | `daily_realized_pnl <= -(equity * max_daily_loss)` | `Max daily loss limit reached` | `risk/engine.py:63-65` |
| 11 | Consecutive losses | `consecutive_losses >= max_consecutive_losses` | `Max consecutive losses limit reached` | `risk/engine.py:66-67` |
| 12 | Trades per day | `trades_today >= max_trades_per_day` | `Max trades per day limit reached` | `risk/engine.py:68-69` |
| 13 | Open positions | `open_positions >= max_open_positions` | `Max open positions limit reached` | `risk/engine.py:70-71` |
| 14 | Leverage | `notional / equity > max_leverage` (sizing is computed first) | `Maximum leverage exceeded` | `risk/engine.py:73-78` |
| - | Approve | all gates passed | `Risk approved` | `risk/engine.py:80-87` |

Reward-to-risk and leverage values are attached to a rejection only when already computed; earlier gates return 0.0 for them (`risk/engine.py:123-135`).

Rules that follow from the code:

- **Daily-loss base.** The limit is measured against the **current request equity**, not start-of-day equity: `equity * max_daily_loss` (`risk/engine.py:63-64`). The check uses `<=`, so reaching exactly the limit blocks.
- **Distances.** Stop distance and reward distance are direction-aware (LONG: `entry - stop` and `take_profit - entry`; SHORT: `stop - entry` and `entry - take_profit`) and are in absolute price units (`risk/engine.py:107-121`; D-63).
- **A stop loss is mandatory.** Gates 4, 6 and 7 together reject a missing stop, a wrong-side stop and a too-close stop.
- **No martingale or averaging down.** Position size depends only on equity, `risk_per_trade` and stop distance; no gate or method increases size after a loss (`risk/engine.py:73-76`).

### 3.3 Position sizing (`risk/engine.py:73-76`)

```text
risk_amount   = equity * risk_per_trade
position_size = risk_amount / stop_distance
notional      = position_size * entry_price
leverage      = notional / equity
```

An approved `RiskDecision` carries `position_size`, `risk_amount`, `reward_to_risk` and `leverage` with reason `Risk approved` (`risk/engine.py:80-87`). Sizing does not round to an exchange quantity step, minimum notional or lot size, and does not include fees. The paper executor charges fees on top of the risk amount (`execution/paper_executor.py:119-122`).

### 3.4 ML interaction with risk

ML runs **before** the risk engine and can only stop a signal or later shrink an approved size. It never raises risk:

- ML `REJECT` ends the signal before `risk.evaluate` (`backtest/engine.py:133`, `execution/paper_trading.py:181`).
- ML `REDUCE_RISK` is applied **after** risk approval by multiplying `position_size`, `risk_amount` and `leverage` by the multiplier. The backtest clamps the multiplier to `[0, 1]` (`backtest/engine.py:493-506`). The paper loop applies the multiplier as-is, relying on `MLFilterConfig` validation `0 < m <= 1` (`execution/paper_trading.py:252-259`, `ml/filter.py:42-43`; D-62). Full ML rules are in [RFC-003](rfc-silverbot-ml-filter-gate.md).

### 3.5 Where the limits come from, and where they disagree

| Limit | `RiskConfig` (enforced by the engine) | `Settings` / env (config load) | Readiness checkers |
|-------|---------------------------------------|--------------------------------|--------------------|
| Risk per trade | default 0.005, accepts up to 0.05 | `MAX_RISK_PER_TRADE` default 0.005; rejected above 0.005 **only when `DEMO_TRADING` is true** (`config/settings.py:186-187`) | pass when `<= 0.005` (`readiness.py:19`) |
| Daily loss | default 0.02, accepts up to 1.0 | `MAX_DAILY_LOSS` default 0.02; above 0.02 rejected in demo only (`config/settings.py:188-189`) | pass when `<= 0.02` |
| Leverage | default 3.0, any positive value | `MAX_LEVERAGE` default 3; above 3 rejected in demo only (`config/settings.py:190-191`) | pass when `<= 3.0` |
| Kill switch | `kill_switch_path` default `None` | `KILL_SWITCH_ENABLED` default false; `KILL_SWITCH_PATH` default empty; both required in demo (`config/settings.py:180-183`) | enabled and path set required |

The Settings fields are validated at load but never passed to `RiskConfig` (`config/settings.py:50-53,186-190`; `backtest/engine.py:41`; `execution/paper_trading.py:49`). Outside demo mode a Settings value above the cap is accepted with no error. Consequence: the documented 0.5 percent cap is enforced by default values only, not by a unified check (D-11, H-5, G-5).

### 3.6 Kill switch (`risk/kill_switch.py:8-17`)

| Property | As built | Source |
|----------|----------|--------|
| Trigger | None automatic. The switch is active if and only if `path is not None` and the file at `path` exists, with any content (a directory also counts) | `risk/kill_switch.py:17`; D-80 |
| File | The path comes from `RiskConfig.kill_switch_path` (default `None`) unless a `KillSwitch` instance is injected. `Settings.kill_switch_path` is never passed in | `risk/engine.py:23`; H-9 |
| Default | Inert: with no path the switch is never active, so the default backtest and paper engines have no working kill switch | `risk/models.py:26`; `execution/paper_trading.py:49` |
| Check timing | On every `evaluate`, as gate 1, before any other check; not latched | `risk/engine.py:30-31` |
| Effect | Rejects new entries with `Kill switch is active`. Open paper positions keep being managed; the stream is not stopped | `execution/paper_trading.py:68-108` |
| Creation | No code creates the file. The owner creates it by hand | D-22 |
| Reset | Delete the file by hand; no command exists | D-80, G-6 |
| Alerting | The paper loop records one `KILL_SWITCH_ACTIVE` event and sends one alert per run (`_kill_alert_sent`), and a risk rejection whose reason equals `Kill switch is active` is recorded as `KILL_SWITCH_ACTIVE` with a `kill_switch_active` audit entry | `execution/paper_trading.py:57,74-84,217-251` |
| Emergency shutdown | **Does not exist.** No function closes positions, cancels orders or stops the process; the switch only blocks new entries | `risk/kill_switch.py:8-17`; `execution/paper_trading.py:59-122` |

The paper-loop alert text is sent through the Telegram client, which has no network transport (D-3, G-15), so in practice the alert reaches only the in-memory record.

### 3.7 Risk state and persistence

`RiskState` holds `current_day`, `daily_realized_pnl`, `consecutive_losses`, `trades_today` and `open_positions` in memory only (`risk/models.py:47-55`). A restart resets the daily-loss and consecutive-loss counters (H-11, G-7). The entrypoint currently exits immediately and supervisors restart it (H-4), which would reset the counters on each restart if a risk-bearing loop were wired.

A pending order that is never filled keeps its reservation: `reserve_trade` runs at order creation, `release_trade` only on close, so an unfilled order counts against `max_open_positions` and `trades_today` indefinitely, and the paper fill model has no expiry or cancel (H-10; `execution/paper_trading.py:267`, `execution/paper_executor.py:110-132`).

### 3.8 Non-risk checks in the paper loop

These are not risk gates but also stop a candidate before an order exists:

| Check | Reason / text (verbatim) | Source |
|-------|--------------------------|--------|
| ML reject (event type `RISK_REJECTED`) | `ML rejected: <ml reason>` | `execution/paper_trading.py:186`, `backtest/engine.py:139` |
| ML reduce suffix on the approved reason | `<risk reason>; ML reduced risk` | `execution/paper_trading.py:258`, `backtest/engine.py:505` |
| Order submitted without approval | `risk_decision must be approved before paper order submission` | `execution/paper_executor.py:50-53` |
| Order missing price levels | `paper order requires entry, stop loss, and take profit` | `execution/paper_executor.py:50-53` |

### 3.9 Old policy rules: carried and dropped

| Old rule (RISK_POLICY.md) | Status | Finding |
|---------------------------|--------|---------|
| Seven mandatory gates (sizing, stop-loss, RR, daily loss, consecutive loss, max trades, kill switch) | Carried; the engine enforces a superset of 14 (adds equity, entry and take-profit presence, minimum stop distance, take-profit side, open positions, leverage) | none |
| Demo gate: `MAX_RISK_PER_TRADE <= 0.005`, `MAX_DAILY_LOSS <= 0.02`, `MAX_LEVERAGE <= 3` | Carried as a config-load check **in demo mode only**; not wired to `RiskConfig` | D-11, H-5 |
| "Kill switch validation" is mandatory | Dropped as stated: the switch is inert unless a path is supplied to `RiskConfig` | D-12, H-9 |
| Risk module triggers the kill switch | Dropped: nothing triggers or creates it | D-22 |
| ML reduce risk "can only shrink" size, risk amount and leverage | Carried with a note: bound by config validation in the paper loop, clamped in the backtest | D-62 |
| Stop-loss distance validation | Carried; distance is in absolute price units, default 0.01, not a percentage or ATR multiple | D-63 |
| "Trade before readiness checks pass" is forbidden | Dropped as an enforced control: readiness reports are advisory and no code reads them | D-10, G-2 |
| Safe defaults `LIVE_TRADING=false`, `PAPER_TRADING=true`, `DEMO_TRADING=false` | Carried: they are the `load_config` defaults (`config/settings.py:68-71`) | none |
| Backtest routes every candidate through the risk engine and logs rejections | Carried (`backtest/engine.py:157`) | none |

## 4. Alternatives Considered

| Alternative | Why not (as built) |
|-------------|--------------------|
| Risk limits taken from `Settings` and passed into `RiskConfig` | The desired design, not built (G-5). One source of truth is Planned. |
| Kill switch armed by default, with automatic triggers on the daily-loss and consecutive-loss limits | Not built (G-6). Today a breached daily limit only blocks new entries. Planned. |
| Persisted risk state across restarts | Not built (G-7). Planned. |
| Daily loss measured on start-of-day equity | The code uses current equity (`risk/engine.py:63-64`). This is a different, looser measure after profits; the choice is Open. |
| Latching the kill switch | Not built: the switch re-reads the file on every call, so deleting the file re-enables entries immediately. Open. |
| Closing or reducing open exposure on a trip | Not built; no emergency shutdown exists. Planned. |
| Stop distance as a percentage or ATR multiple | Not built (D-63); absolute price units are used. |

## 5. Safety, Privacy & Performance

**Safety.**

- The risk engine has no exchange access and cannot place orders. It cannot be bypassed by ML: ML runs before it and can only reject or shrink (section 3.4).
- The only real-order methods raise `OrderPlacementDisabled`, and live is rejected at config load, so a risk approval cannot reach a real exchange (`exchange/base.py:44-52`, `config/settings.py:104-105`).
- The default kill-switch state is the weakest point: it is inert by default and manual only (G-6). Anyone relying on it must supply a path to `RiskConfig` and create the file by hand.
- Risk limits are only as strict as the `RiskConfig` the caller builds; the default 0.005 is safe but the accepted ceiling of 0.05 is not (G-5).

**Privacy.** The engine handles numbers only and holds no keys or personal data.

**Performance.** Each evaluation is constant-time arithmetic plus one file-existence check. No benchmark exists and none is claimed.

**Evidence of behaviour (tests).** `tests/test_risk_engine.py` has 10 tests: valid sizing (size 20, risk 100, RR 2 at 1 percent risk), wrong-side stop, missing stop, low RR, daily-loss lockout, consecutive-loss lockout, max-trades lockout, max-open-positions lockout, leverage rejection and kill-switch active. `tests/test_paper_trading.py` covers the `KILL_SWITCH_ACTIVE` event and alert. There are no direct tests for `RiskConfig` invalid values, the minimum-stop-distance gate, the equity gate, the entry and take-profit presence gates, `release_trade` semantics, or `roll_day` behaviour across days (G-28).

## 6. Execution Status

| Capability | Status | Evidence |
|-----------|--------|----------|
| 14-gate risk engine with sizing and verbatim reasons | Built | `risk/engine.py:25-87`; 10 risk tests |
| `RiskConfig` validation | Built | `risk/models.py:28-44` |
| File-existence kill switch with paper-loop event and alert | Built | `risk/kill_switch.py:11-17`; `execution/paper_trading.py:74-84` |
| Kill switch armed by default | Planned | `RiskConfig.kill_switch_path` is `None` (G-6) |
| Automatic kill-switch triggers | Planned | None exist (D-22) |
| Emergency shutdown (close positions, stop the loop) | Planned | None exists (G-6) |
| Kill-switch creation and reset tooling | Planned | Manual file edit only |
| Settings-to-`RiskConfig` wiring and one risk cap | Planned | Not wired (G-5, D-11, H-5) |
| Persisted risk state | Planned | In memory only (G-7, H-11) |
| Release of stale pending-order reservations | Planned | H-10 |
| Gap-through-stop handling in execution | Planned | Exits fill at the exact stop or target (G-21) |
| Risk engine used by a running paper or demo process | Partial | `PaperTradingEngine` is not constructed anywhere in `src/` outside tests; the entrypoint is a stub (G-3, H-4) |

## 7. Risks & Open Items

| Ref | Item | Status |
|-----|------|--------|
| G-5 | Risk limits not unified: Settings limits never reach `RiskConfig`; `RiskConfig` allows 5 percent per trade (D-11, H-5). Position sizing can exceed the documented cap. | Open |
| G-6 | Kill switch inert by default, existence-only, no automatic trigger, no position close, no reset tooling (D-12, D-22, H-9, D-80). | Open |
| G-7 | Risk state is in memory; a restart resets daily and consecutive loss counters (H-11). | Open |
| G-21 | Execution gaps: no gap-through-stop, no stale-order cancel, pending-order reservation can leak capacity (H-10). | Open |
| G-3 | No running runtime calls the engine end to end (H-4). | Open |
| G-28 | Test-gap family: no tests for `RiskConfig` invalid values, several gates and `release_trade`. | Open |
| Daily-loss base | Whether the limit should use start-of-day equity. | Open |
| Latching | Whether a tripped switch should require an explicit reset step rather than file deletion alone. | Open |
| Risk budget | The owner's capital and risk budget are not recorded. | Owner input required (OI-register in the BRD) |

## 8. Self-Check

- [x] All 14 gates are listed in code order with verbatim reasons and `risk/engine.py` lines.
- [x] Every `RiskConfig` default and validation message in section 3.1 matches `risk/models.py:18-44`.
- [x] The kill switch is described as inert by default, file-exists only, with no automatic trigger and no emergency shutdown.
- [x] The 5 percent `RiskConfig` ceiling versus the demo-only 0.005 Settings cap is stated (G-5, D-11).
- [x] Each dropped or changed old-policy rule in section 3.9 carries a `D-#` or `H-#`.
- [x] Status labels in section 6 are Built, Partial or Planned, each with evidence.
- [ ] A unified risk cap and an armed-by-default kill switch exist in code (not yet; Planned).
