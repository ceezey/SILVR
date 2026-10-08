# HIGH Safety Fixes, Batch 1: Design Spec

**Date:** 2026-10-09
**Status:** Approved design; spec awaiting owner review
**Owner:** Cian Jake Francisco (ceezey)
**Branch:** `dev` (base commit `67ea459`)
**Baseline:** `python -m pytest -q` passes 109 tests at `67ea459`

---

## 1. Intent

### What the owner asked for

- Fix the code issues the docs already record, starting with the HIGH-severity safety gaps.
- Use a parallel agent workflow where possible.
- Do development on `dev`; `main` is for deployment and production.

### Scope

Eight HIGH gaps from [scrutiny-silverbot.md](../../scrutiny-silverbot.md) section 3: G-2, G-4, G-5, G-6, G-7, G-8, G-10, G-11.

Out of scope for this batch: G-1 (needs real data runs, not code), G-3 entrypoint, G-12 validation, G-13 market data, G-15 Telegram transport, H-3 (making a live-ready report loadable moves toward live; it stays documented), closing open positions when the kill switch trips (G-21 executor work), and exceptions raised while loading or calling a model (they still propagate).

### Decisions made during brainstorming

| # | Question | Decision |
|---|----------|----------|
| HD-1 | Batch scope | The 8 small safety fixes above. |
| HD-2 | Risk-per-trade cap | Hard 0.5% (`0.005`) everywhere, backtests included. |
| HD-3 | Kill switch | Wire from settings, fail closed, auto-trip on loss limits. No position close. |
| HD-4 | Risk-state persistence | A `risk_state` table in the existing SQLite database. |
| HD-5 | Backtest cost defaults | `slippage_bps=5.0`, `spread_bps=3.0`. |

### Invariants

- Every change tightens or adds a fail-closed path. None loosens a risk, kill-switch, readiness or live gate.
- `LIVE_TRADING=true` and `TRADING_MODE=live` stay rejected at load. PRD-F12 stays `Planned, blocked`.
- Nothing is pushed to a remote.

## 2. Behaviour per Gap

Paths are relative to `src/silver_bot/` unless they start with a root filename.

### G-8. Non-finite model probability (H-1)

- **Today:** `ml/filter.py:166-178` returns `max(0.0, min(1.0, probability))`. `min(1.0, nan)` is `1.0`, so a NaN prediction approves the signal.
- **Change:** `_predict_probability` returns the raw float. `evaluate` returns `MLDecision.REJECT`, `risk_multiplier=0.0`, `probability=None` and the reason `ML model returned an invalid probability` when the value is NaN, positive or negative infinity, below 0 or above 1. Valid values in [0, 1] keep today's threshold logic.
- **Tests:** NaN, `inf`, `-inf`, `-0.1` and `1.3` each reject; `0.0` and `1.0` keep their current decisions.

### G-10. Testnet URL guard is a substring match (D-13)

- **Today:** `config/settings.py:345-347` and `exchange/binance_futures.py:74-78` both return `"testnet.binancefuture.com" in value`.
- **Change:** one implementation in `config/settings.py`, using `urllib.parse.urlsplit`. It passes only when the scheme is `https` and `hostname` equals `testnet.binancefuture.com` exactly (case-insensitive; no userinfo). `exchange/binance_futures.is_binance_futures_testnet_url` delegates to it, so callers keep the same name.
- **Tests:** accept `https://testnet.binancefuture.com` and `https://testnet.binancefuture.com/fapi`; reject `https://testnet.binancefuture.com.evil.com`, `https://evil.com/?x=testnet.binancefuture.com`, `https://user@testnet.binancefuture.com`, `http://testnet.binancefuture.com` and `https://fapi.binance.com`.

### G-4. `.env.example` fails to load (D-2, H-14)

- **Today:** `.env.example:5-6` sets `PAPER_TRADING=false`, `DEMO_TRADING=true`; load promotes paper to demo, then rejects missing API keys.
- **Change:** `PAPER_TRADING=true`, `DEMO_TRADING=false`, matching the file's own "normal paper deployment" comment. The commented demo block is unchanged.
- **Tests:** `load_config(env_path=".env.example", yaml_path=tmp_path / "missing.yaml", environ={})` returns `TradingMode.PAPER` with `paper_trading=True`.

### G-2. Readiness passes a 0-byte report (H-2, D-86)

- **Today:** `readiness.py:126-141` `_file_exists` passes any existing file.
- **Change:** the three report checks pass only when the file exists, is non-empty, and parses as a JSON object (a `dict`). Failure messages say which condition failed. Check names (`backtest_report_exists` and the other two) stay the same so report consumers do not break. `demo_readiness.py` has no report-content checks and is unchanged.
- **Tests:** 0-byte file fails; `not json` fails; `[]` fails; `{}` passes.

### G-5. Risk caps not unified (D-11, H-5)

- **Today:** `RiskConfig` accepts `risk_per_trade` up to `0.05` (`risk/models.py:29`). `load_config` caps `MAX_RISK_PER_TRADE` at `0.005` only in demo mode. No code builds `RiskConfig` from `AppConfig`.
- **Change:**
  - `RiskConfig.__post_init__` rejects `risk_per_trade` outside `(0, 0.005]`.
  - `load_config` rejects `MAX_RISK_PER_TRADE` outside `(0, 0.005]` in every mode. The demo-only bounds for `MAX_DAILY_LOSS` (0.02) and `MAX_LEVERAGE` (3) stay demo-only.
  - New `risk/factory.py` with `build_risk_engine(config: AppConfig, storage: SQLiteStorage | None = None) -> RiskManagementEngine`. It maps `max_risk_per_trade`, `max_daily_loss` and `max_leverage` into `RiskConfig`, passes `kill_switch_path` when `kill_switch_enabled` is true, and attaches the SQLite state store when `storage` is given. The other `RiskConfig` fields keep their defaults.
- **Caveat:** no runtime path calls `build_risk_engine` yet, because the entrypoint is the G-3 stub. G-3 must call it. The docs must say so.
- **Tests:** `RiskConfig(risk_per_trade=0.006)` raises; `load_config` with `MAX_RISK_PER_TRADE=0.01` in paper mode raises `ConfigError`; `build_risk_engine` carries the three caps and the kill-switch path. The existing tests at `tests/test_risk_engine.py:25` (1%) and `:103` (5%) are changed to stay under the cap, and their assertions keep testing the same rule.

### G-6. Kill switch inert, existence-only, never trips (D-12, D-22, H-9)

- **Today:** `risk/kill_switch.py` returns `path is not None and path.exists()`. Engines default to no path. Nothing writes the file.
- **Change:**
  - `load_config` rejects `KILL_SWITCH_ENABLED=true` with a blank `KILL_SWITCH_PATH` in every mode (demo already requires both).
  - `KillSwitch.is_active()` returns `True` when the path exists, when it is a directory, or when checking it raises `OSError`. With no path it returns `False` (backtests).
  - New `KillSwitch.trip(reason: str) -> None` creates parent directories and writes the file as JSON: `{"reason": "Max daily loss limit reached", "tripped_at": "2026-10-09T14:00:00+00:00"}` (UTC ISO-8601 timestamp). With no path it does nothing.
  - `RiskManagementEngine` calls `trip` when `evaluate` hits the max-daily-loss or max-consecutive-losses rejection (the latter covers a streak loaded from persisted state), and when `release_trade` brings `consecutive_losses` to `max_consecutive_losses`. A second trip keeps the first reason. The reason names the limit. The halt then outlasts the day roll and a restart until the owner deletes the file.
- **Tests:** a directory path is active; an `OSError` from the check is active; a tripped file exists and holds valid JSON with both keys; three losing releases trip the switch; the daily-loss rejection trips it; with no path, `trip` writes nothing.

### G-7. Risk state resets on restart (H-11)

- **Today:** `RiskState` lives only in memory.
- **Change:**
  - `storage/sqlite.py` adds `risk_state` (`id INTEGER PRIMARY KEY CHECK (id = 1)`, `current_day TEXT`, `daily_realized_pnl REAL NOT NULL`, `consecutive_losses INTEGER NOT NULL`, `trades_today INTEGER NOT NULL`, `open_positions INTEGER NOT NULL`, `updated_at TEXT NOT NULL`) in `initialize`, plus `load_risk_state() -> RiskState | None` and `save_risk_state(state: RiskState) -> None`. `load_risk_state` raises `RiskStateError` on a row with wrong types, negative counts or a bad date.
  - `RiskManagementEngine` takes an optional `state_store` (a Protocol with `load_risk_state` and `save_risk_state`). At construction it loads the saved state if one exists. It saves after every `reserve_trade` and `release_trade`, and in `evaluate` when the day rolls. If loading raises, the engine starts locked: every `evaluate` returns `Risk state could not be loaded; trading halted`.
  - Without a store (backtests, existing tests) behaviour is unchanged.
- **Known trade-off:** `open_positions` survives a restart but paper positions do not. After a crash with an open trade the engine stays blocked until the owner resets the row. OPS documents the reset.
- **Tests:** state saved by one engine is loaded by a new engine on the same database; a corrupt row locks the engine; no store means no persistence.

### G-11. Backtest costs default to 0 bps (D-5, H-7)

- **Today:** `backtest/models.py:34-35` default `slippage_bps=0.0`, `spread_bps=0.0`.
- **Change:** defaults become `slippage_bps=5.0`, `spread_bps=3.0`. Validation is unchanged.
- **Tests:** a default `BacktestConfig()` has 5.0 and 3.0. Existing tests that assert exact P&L pass `slippage_bps=0.0, spread_bps=0.0` explicitly so their assertions stay valid.

## 3. Execution

### Lanes

G-5, G-6 and G-7 all edit `risk/engine.py` and `risk/models.py`, so one agent per gap would conflict. Four lanes split the work so that no two lanes edit the same file, except the noted `settings.py` overlap.

| Lane | Gaps | Files |
|---|---|---|
| A, risk core | G-5, then G-6, then G-7, in order | `risk/*`, new `risk/factory.py`, `storage/sqlite.py`, `config/settings.py` (cap and kill-switch rules in `load_config`), tests |
| B, ML | G-8 | `ml/filter.py`, `tests/test_ml_probability_filter.py` |
| C, config surface | G-10, G-4 | `config/settings.py` (`_is_binance_testnet_url` only), `exchange/binance_futures.py`, `.env.example`, tests |
| D, backtest and readiness | G-11, G-2 | `backtest/models.py`, `readiness.py`, tests |

Lanes A and C both touch `config/settings.py` in different functions. Merge A first, then C, and resolve any textual conflict by hand.

### Orchestration

1. Each lane runs as its own agent in a separate git worktree, branched from `dev`, on branches `fix/risk-core`, `fix/ml-invalid-prob`, `fix/config-surface` and `fix/backtest-readiness`.
2. Each lane follows TDD: a failing test that reproduces the hazard, then the fix. It ends with the full `python -m pytest -q` suite passing and commits on its branch.
3. The orchestrator merges into `dev` in the order A, B, C, D and re-runs the full suite after each merge.
4. One docs agent updates the suite to match the merged code (section 4) and re-materializes.
5. The four safety reviewers (`live-trading-gate-guardian`, `risk-bypass-checker`, `lookahead-leakage-auditor`, `restraint-guardian`) review the combined diff from `67ea459` in parallel. Their findings are verified before any fix is applied.

Agent count: 4 lanes, 1 docs agent and 4 reviewers, so 9 agents.

## 4. Documentation Updates

Done after the merge, against the merged code:

- [scrutiny-silverbot.md](../../scrutiny-silverbot.md): set each of the 8 gaps to `Closed` with the commit, or `Partial` with the remaining work (G-5 and G-6 stay partial until G-3 calls `build_risk_engine`; G-6 also lacks position close).
- [audit-docs-drift.md](../../audit-docs-drift.md): a resolution note on H-1, H-2, H-5, H-7, H-9, H-11, H-14 and D-2, D-5, D-11, D-12, D-13, D-86.
- [sdd-silverbot.md](../../sdd-silverbot.md): section 3.2 (`risk_state` table), 3.4 (new load rules), 5.3 (kill switch), 5.5 (cap), 8 (invalid-probability rejection).
- [rfc-silverbot-risk-kill-switch.md](../../rfc-silverbot-risk-kill-switch.md) and [rfc-silverbot-ml-filter-gate.md](../../rfc-silverbot-ml-filter-gate.md): as-built sections.
- [qad-silverbot.md](../../qad-silverbot.md): the new test scenarios.
- [ops-silverbot.md](../../ops-silverbot.md): how to clear a tripped kill switch and how to reset the `risk_state` row.
- [build-silverbot.md](../../build-silverbot.md) section 3: update the D-11 deprecation row; then `python tools/materialize_docs.py`.
- [index.md](../../index.md): health-check hazard list, change log, and the process-records table and count (this spec and its plan). README safe defaults.

## 5. Acceptance

- `python -m pytest -q` passes on `dev` after the merge, with more than 109 tests.
- `python tools/materialize_docs.py --check` reports no changes.
- Each of the 8 gaps has at least one test that fails on `67ea459` and passes after the fix.
- All four safety reviewers report no unresolved blocking finding.
- `LIVE_TRADING=true` is still rejected at load (existing test still passes).
