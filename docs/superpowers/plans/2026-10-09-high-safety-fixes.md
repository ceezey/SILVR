# HIGH Safety Fixes, Batch 1: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close HIGH gaps G-2, G-4, G-5, G-6, G-7, G-8, G-10 and G-11 in code with tests, then make the docs suite match.

**Architecture:** Four independent lanes (A risk core, B ML, C config surface, D backtest and readiness) run in parallel git worktrees branched from `dev`. Each lane is TDD and ends with a green full suite and a commit on its own branch. The orchestrator merges A, B, C, D into `dev`, then one docs task and four safety reviews run on the merged result.

**Tech Stack:** Python 3.11+ (tests run on 3.14), standard library only, `sqlite3`, `urllib.parse`, pytest 8+.

**Spec:** [docs/superpowers/specs/2026-10-09-high-safety-fixes-design.md](../specs/2026-10-09-high-safety-fixes-design.md)

## Global Constraints

- Paths are relative to the repo root. Source lives in `src/silver_bot/`.
- Run tests with `python -m pytest -q` from the repo root. Baseline at `67ea459`: 109 passed.
- No new dependencies. `pyproject.toml` `dependencies = []` stays empty.
- Every change tightens or adds a fail-closed path. Never loosen a risk, kill-switch, readiness or live gate.
- `LIVE_TRADING=true` and `TRADING_MODE=live` stay rejected at load.
- Risk-per-trade hard cap: `0.005` everywhere.
- Backtest cost defaults: `slippage_bps=5.0`, `spread_bps=3.0`.
- Commit only the files a task names. Never `git add -A` or `git add .`: the working tree holds untracked owner files (`BRAND.md`, `DESIGN.md`) that must not be committed.
- Commit messages end with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Do not push. Do not edit materialized files (`AGENTS.md`, `MODEL_CARD.md`, `.claude/agents/*.md`) by hand.
- Suite docs: no em dashes, no performance claims, no placeholder tokens (see `docs/voice-silverbot.md`).

## Review Focus

- A report file that holds only whitespace or a UTF-8 BOM before valid JSON: whitespace-only must fail as empty; a BOM followed by `{}` must pass (Task D2).
- A kill-switch path whose parent is a regular file, so `stat` raises `NotADirectoryError`: must count as active (Task A2).
- A testnet URL with an explicit port, mixed case or a trailing dot: `HTTPS://TESTNET.BINANCEFUTURE.COM` passes; `:8443` and `testnet.binancefuture.com.` fail (Task C1).
- A `risk_state` row written by an older run with a text value in an integer column: must lock the engine, not coerce (Task A3).
- A second trip after the switch is already tripped: must keep the first reason and timestamp (Task A2).

---

## Lane A: risk core (branch `fix/risk-core`). Tasks A1, A2, A3 run in order.

### Task A1: G-5, hard 0.5% cap and `build_risk_engine`

**Files:**
- Modify: `src/silver_bot/risk/models.py` (`RiskConfig.__post_init__`)
- Modify: `src/silver_bot/config/settings.py` (`load_config`, the `max_risk_per_trade` parse and the demo block)
- Create: `src/silver_bot/risk/factory.py`
- Modify: `src/silver_bot/risk/__init__.py`
- Test: `tests/test_risk_engine.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `silver_bot.risk.models.MAX_RISK_PER_TRADE: float = 0.005`; `silver_bot.risk.build_risk_engine(config: AppConfig) -> RiskManagementEngine` (A3 adds a `storage` parameter).

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_risk_engine.py`:

```python
import pytest

from silver_bot.config import load_config
from silver_bot.risk import build_risk_engine


def test_risk_per_trade_above_half_percent_is_rejected() -> None:
    with pytest.raises(ValueError, match="risk_per_trade"):
        RiskConfig(risk_per_trade=0.006)


def test_risk_per_trade_at_half_percent_is_allowed() -> None:
    assert RiskConfig(risk_per_trade=0.005).risk_per_trade == 0.005


def test_build_risk_engine_carries_settings_caps(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "MAX_RISK_PER_TRADE=0.004",
                "MAX_DAILY_LOSS=0.01",
                "MAX_LEVERAGE=2",
                "KILL_SWITCH_ENABLED=true",
                f"KILL_SWITCH_PATH={tmp_path / 'KILL_SWITCH'}",
            ]
        ),
        encoding="utf-8",
    )
    config = load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})

    engine = build_risk_engine(config)

    assert engine.config.risk_per_trade == 0.004
    assert engine.config.max_daily_loss == 0.01
    assert engine.config.max_leverage == 2
    assert engine.kill_switch.path == tmp_path / "KILL_SWITCH"


def test_build_risk_engine_ignores_kill_switch_path_when_disabled(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(f"KILL_SWITCH_PATH={tmp_path / 'KILL_SWITCH'}\n", encoding="utf-8")
    config = load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})

    engine = build_risk_engine(config)

    assert engine.kill_switch.path is None
```

Append to `tests/test_config.py`:

```python
def test_max_risk_per_trade_above_cap_is_rejected_in_paper_mode(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("MAX_RISK_PER_TRADE=0.01\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="MAX_RISK_PER_TRADE"):
        load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})
```

- [ ] **Step 2: Bring the two existing tests under the cap.** In `tests/test_risk_engine.py`, `test_valid_position_sizing` becomes:

```python
def test_valid_position_sizing() -> None:
    engine = RiskManagementEngine(RiskConfig(risk_per_trade=0.005))

    decision = engine.evaluate(request())

    assert decision.approved is True
    assert decision.position_size == 10
    assert decision.risk_amount == 50
    assert decision.reward_to_risk == 2
```

and `test_maximum_leverage_rejection` uses `RiskConfig(risk_per_trade=0.005, max_leverage=0.4)` (position 50, notional 5000, leverage 0.5 > 0.4). Its assertions are unchanged.

- [ ] **Step 3: Run to verify failure.** `python -m pytest -q tests/test_risk_engine.py tests/test_config.py`. Expected: import error for `build_risk_engine`, and the cap tests fail.

- [ ] **Step 4: Implement.** In `src/silver_bot/risk/models.py`, above `RiskConfig`:

```python
MAX_RISK_PER_TRADE = 0.005
```

and replace the first check in `RiskConfig.__post_init__`:

```python
        if not 0 < self.risk_per_trade <= MAX_RISK_PER_TRADE:
            raise ValueError("risk_per_trade must be greater than 0 and no more than 0.5%")
```

In `src/silver_bot/config/settings.py` `load_config`, directly after `max_leverage = _parse_float(...)` and before `if demo_trading:`, add:

```python
    if not 0 < max_risk_per_trade <= 0.005:
        raise ConfigError("MAX_RISK_PER_TRADE must be greater than 0 and no more than 0.005")
```

and delete the now-redundant demo-only `MAX_RISK_PER_TRADE` check (the two lines starting `if not 0 < max_risk_per_trade <= 0.005:` inside `if demo_trading:`). Keep the demo-only `MAX_DAILY_LOSS` and `MAX_LEVERAGE` checks.

Create `src/silver_bot/risk/factory.py`:

```python
"""Build the risk engine from validated application settings."""

from __future__ import annotations

from silver_bot.config import AppConfig
from silver_bot.risk.engine import RiskManagementEngine
from silver_bot.risk.models import RiskConfig


def build_risk_engine(config: AppConfig) -> RiskManagementEngine:
    """Return a risk engine whose limits and kill switch come from settings."""

    risk_config = RiskConfig(
        risk_per_trade=config.max_risk_per_trade,
        max_daily_loss=config.max_daily_loss,
        max_leverage=config.max_leverage,
        kill_switch_path=config.kill_switch_path if config.kill_switch_enabled else None,
    )
    return RiskManagementEngine(risk_config)
```

In `src/silver_bot/risk/__init__.py` add `from silver_bot.risk.factory import build_risk_engine` and `"build_risk_engine"` to `__all__` (keep it sorted).

- [ ] **Step 5: Run the full suite.** `python -m pytest -q`. Expected: all pass.

- [ ] **Step 6: Commit.**

```bash
git add src/silver_bot/risk/models.py src/silver_bot/risk/factory.py src/silver_bot/risk/__init__.py src/silver_bot/config/settings.py tests/test_risk_engine.py tests/test_config.py
git commit -m "fix(risk): cap risk per trade at 0.5% and build risk engine from settings (G-5)"
```

### Task A2: G-6, fail-closed kill switch with auto-trip

**Files:**
- Modify: `src/silver_bot/risk/kill_switch.py`
- Modify: `src/silver_bot/risk/engine.py` (`evaluate`, `release_trade`)
- Modify: `src/silver_bot/config/settings.py` (`load_config`, kill-switch rule)
- Test: `tests/test_risk_engine.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: `RiskManagementEngine` from A1.
- Produces: `KillSwitch.is_active() -> bool` (fail closed); `KillSwitch.trip(reason: str) -> None`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_risk_engine.py`:

```python
import json
from types import SimpleNamespace

import silver_bot.risk.kill_switch as kill_switch_module


def test_kill_switch_directory_path_is_active(tmp_path) -> None:
    folder = tmp_path / "KILL_SWITCH"
    folder.mkdir()

    assert KillSwitch(folder).is_active() is True


def test_kill_switch_unreadable_path_is_active(tmp_path, monkeypatch) -> None:
    def denied(path):
        raise PermissionError("denied")

    monkeypatch.setattr(kill_switch_module, "os", SimpleNamespace(stat=denied))

    assert KillSwitch(tmp_path / "KILL_SWITCH").is_active() is True


def test_kill_switch_parent_is_a_file_is_active(tmp_path) -> None:
    parent = tmp_path / "not_a_dir"
    parent.write_text("x", encoding="utf-8")

    assert KillSwitch(parent / "KILL_SWITCH").is_active() is True


def test_kill_switch_missing_file_is_inactive(tmp_path) -> None:
    assert KillSwitch(tmp_path / "KILL_SWITCH").is_active() is False


def test_kill_switch_trip_writes_reason_and_timestamp(tmp_path) -> None:
    switch = KillSwitch(tmp_path / "nested" / "KILL_SWITCH")

    switch.trip("Max daily loss limit reached")

    payload = json.loads((tmp_path / "nested" / "KILL_SWITCH").read_text(encoding="utf-8"))
    assert payload["reason"] == "Max daily loss limit reached"
    assert payload["tripped_at"].endswith("+00:00")
    assert switch.is_active() is True


def test_kill_switch_second_trip_keeps_first_reason(tmp_path) -> None:
    switch = KillSwitch(tmp_path / "KILL_SWITCH")
    switch.trip("first")
    switch.trip("second")

    payload = json.loads((tmp_path / "KILL_SWITCH").read_text(encoding="utf-8"))
    assert payload["reason"] == "first"


def test_kill_switch_without_path_trip_is_noop() -> None:
    switch = KillSwitch(None)
    switch.trip("anything")

    assert switch.is_active() is False


def test_consecutive_losses_trip_kill_switch(tmp_path) -> None:
    kill_file = tmp_path / "KILL_SWITCH"
    engine = RiskManagementEngine(RiskConfig(max_consecutive_losses=3, kill_switch_path=kill_file))
    day = date(2026, 1, 2)

    for _ in range(3):
        engine.reserve_trade(day)
        engine.release_trade(realized_pnl=-10, day=day)

    assert kill_file.exists()
    assert json.loads(kill_file.read_text(encoding="utf-8"))["reason"] == "Max consecutive losses limit reached"
    assert engine.evaluate(request()).reason == "Kill switch is active"


def test_daily_loss_rejection_trips_kill_switch(tmp_path) -> None:
    kill_file = tmp_path / "KILL_SWITCH"
    state = RiskState(current_day=date(2026, 1, 2), daily_realized_pnl=-250)
    engine = RiskManagementEngine(RiskConfig(max_daily_loss=0.02, kill_switch_path=kill_file), state=state)

    decision = engine.evaluate(request())

    assert decision.reason == "Max daily loss limit reached"
    assert json.loads(kill_file.read_text(encoding="utf-8"))["reason"] == "Max daily loss limit reached"
```

Append to `tests/test_config.py`:

```python
def test_kill_switch_enabled_without_path_is_rejected_in_paper_mode(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("KILL_SWITCH_ENABLED=true\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="KILL_SWITCH_PATH"):
        load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})
```

- [ ] **Step 2: Run to verify failure.** `python -m pytest -q tests/test_risk_engine.py tests/test_config.py`. Expected: the directory, unreadable, parent-file, trip and auto-trip tests fail; `trip` does not exist.

- [ ] **Step 3: Implement.** Replace `src/silver_bot/risk/kill_switch.py`:

```python
"""File-based safety kill switch."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


class KillSwitch:
    """Manual and automatic trading halt backed by a file.

    The switch fails closed: if the file exists, is a directory, or cannot be
    checked, trading is halted.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None

    def is_active(self) -> bool:
        """Return true when trading must halt."""

        if self.path is None:
            return False
        try:
            os.stat(self.path)
        except FileNotFoundError:
            return False
        except OSError:
            return True
        return True

    def trip(self, reason: str) -> None:
        """Write the kill-switch file; the first trip's reason is kept."""

        if self.path is None or self.is_active():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"reason": reason, "tripped_at": datetime.now(timezone.utc).isoformat()}
        self.path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
```

In `src/silver_bot/risk/engine.py` `evaluate`, change the daily-loss and consecutive-loss branches to trip before rejecting:

```python
        if self.state.daily_realized_pnl <= -max_daily_loss_amount:
            self.kill_switch.trip("Max daily loss limit reached")
            return self._reject("Max daily loss limit reached", reward_to_risk=reward_to_risk)
        if self.state.consecutive_losses >= self.config.max_consecutive_losses:
            self.kill_switch.trip("Max consecutive losses limit reached")
            return self._reject("Max consecutive losses limit reached", reward_to_risk=reward_to_risk)
```

At the end of `release_trade`, after the loss-counter update:

```python
        if self.state.consecutive_losses >= self.config.max_consecutive_losses:
            self.kill_switch.trip("Max consecutive losses limit reached")
```

In `src/silver_bot/config/settings.py` `load_config`, directly after `kill_switch_path = ...` is parsed:

```python
    if kill_switch_enabled and kill_switch_path is None:
        raise ConfigError("KILL_SWITCH_PATH is required when KILL_SWITCH_ENABLED=true")
```

Leave the existing demo-block kill-switch checks in place.

- [ ] **Step 4: Run the full suite.** `python -m pytest -q`. Expected: all pass.

- [ ] **Step 5: Commit.**

```bash
git add src/silver_bot/risk/kill_switch.py src/silver_bot/risk/engine.py src/silver_bot/config/settings.py tests/test_risk_engine.py tests/test_config.py
git commit -m "fix(risk): fail-closed kill switch that trips on loss limits (G-6)"
```

### Task A3: G-7, persist risk state in SQLite

**Files:**
- Modify: `src/silver_bot/risk/models.py` (add `RiskStateError`, `RiskStateStore`)
- Modify: `src/silver_bot/risk/engine.py` (`__init__`, `evaluate`, `reserve_trade`, `release_trade`)
- Modify: `src/silver_bot/risk/factory.py`, `src/silver_bot/risk/__init__.py`
- Modify: `src/silver_bot/storage/sqlite.py` (schema, `load_risk_state`, `save_risk_state`)
- Test: `tests/test_storage.py`, `tests/test_risk_engine.py`

**Interfaces:**
- Consumes: `KillSwitch`, `RiskManagementEngine`, `build_risk_engine` from A1 and A2.
- Produces: `RiskStateError(ValueError)`; `RiskStateStore` Protocol with `load_risk_state() -> RiskState | None` and `save_risk_state(state: RiskState) -> None`; `SQLiteStorage.load_risk_state`, `SQLiteStorage.save_risk_state`; `RiskManagementEngine(..., state_store: RiskStateStore | None = None)`; `build_risk_engine(config: AppConfig, storage: SQLiteStorage | None = None)`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_storage.py`:

```python
import sqlite3
from datetime import date

import pytest

from silver_bot.risk import RiskState, RiskStateError


def initialized(tmp_path: Path) -> SQLiteStorage:
    storage = SQLiteStorage(tmp_path / "silver_bot.sqlite3")
    storage.initialize()
    return storage


def corrupt(storage: SQLiteStorage, sql: str) -> None:
    connection = sqlite3.connect(storage.database_path)
    try:
        connection.execute(sql)
        connection.commit()
    finally:
        connection.close()


def test_risk_state_table_exists(tmp_path: Path) -> None:
    assert "risk_state" in initialized(tmp_path).table_names()


def test_risk_state_round_trip(tmp_path: Path) -> None:
    storage = initialized(tmp_path)
    state = RiskState(
        current_day=date(2026, 1, 2),
        daily_realized_pnl=-75.5,
        consecutive_losses=2,
        trades_today=3,
        open_positions=1,
    )

    storage.save_risk_state(state)

    assert storage.load_risk_state() == state
    assert storage.count_rows("risk_state") == 1


def test_risk_state_missing_row_returns_none(tmp_path: Path) -> None:
    assert initialized(tmp_path).load_risk_state() is None


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE risk_state SET consecutive_losses = -1",
        "UPDATE risk_state SET trades_today = 'abc'",
        "UPDATE risk_state SET current_day = 'not-a-date'",
        "UPDATE risk_state SET daily_realized_pnl = 'x'",
    ],
)
def test_corrupt_risk_state_raises(tmp_path: Path, sql: str) -> None:
    storage = initialized(tmp_path)
    storage.save_risk_state(RiskState(current_day=date(2026, 1, 2)))
    corrupt(storage, sql)

    with pytest.raises(RiskStateError):
        storage.load_risk_state()
```

Append to `tests/test_risk_engine.py`:

```python
from silver_bot.storage import SQLiteStorage


def risk_storage(tmp_path) -> SQLiteStorage:
    storage = SQLiteStorage(tmp_path / "risk.sqlite3")
    storage.initialize()
    return storage


def test_risk_state_survives_engine_restart(tmp_path) -> None:
    storage = risk_storage(tmp_path)
    day = date(2026, 1, 2)
    first = RiskManagementEngine(state_store=storage)
    first.reserve_trade(day)
    first.release_trade(realized_pnl=-50, day=day)

    second = RiskManagementEngine(state_store=storage)

    assert second.state == RiskState(
        current_day=day,
        daily_realized_pnl=-50,
        consecutive_losses=1,
        trades_today=1,
        open_positions=0,
    )


def test_restart_does_not_reset_consecutive_loss_limit(tmp_path) -> None:
    storage = risk_storage(tmp_path)
    day = date(2026, 1, 2)
    first = RiskManagementEngine(RiskConfig(max_consecutive_losses=3), state_store=storage)
    for _ in range(3):
        first.reserve_trade(day)
        first.release_trade(realized_pnl=-10, day=day)

    second = RiskManagementEngine(RiskConfig(max_consecutive_losses=3), state_store=storage)

    assert second.evaluate(request()).reason == "Max consecutive losses limit reached"


def test_corrupt_risk_state_halts_trading(tmp_path) -> None:
    import sqlite3

    storage = risk_storage(tmp_path)
    storage.save_risk_state(RiskState(current_day=date(2026, 1, 2)))
    connection = sqlite3.connect(storage.database_path)
    try:
        connection.execute("UPDATE risk_state SET open_positions = -3")
        connection.commit()
    finally:
        connection.close()

    engine = RiskManagementEngine(state_store=storage)
    decision = engine.evaluate(request())

    assert decision.approved is False
    assert decision.reason == "Risk state could not be loaded; trading halted"


def test_build_risk_engine_attaches_storage(tmp_path) -> None:
    storage = risk_storage(tmp_path)
    config = load_config(env_path=tmp_path / ".env", yaml_path=tmp_path / "missing.yaml", environ={})

    engine = build_risk_engine(config, storage)
    engine.reserve_trade(date(2026, 1, 2))

    assert storage.load_risk_state().trades_today == 1


def test_engine_without_store_does_not_persist(tmp_path) -> None:
    engine = RiskManagementEngine()
    engine.reserve_trade(date(2026, 1, 2))

    assert engine.state_store is None
```

- [ ] **Step 2: Run to verify failure.** `python -m pytest -q tests/test_storage.py tests/test_risk_engine.py`. Expected: import error for `RiskStateError`.

- [ ] **Step 3: Implement the models.** In `src/silver_bot/risk/models.py` add `from typing import Protocol` to the imports, and after `RiskState`:

```python
class RiskStateError(ValueError):
    """Raised when persisted risk state cannot be trusted."""


class RiskStateStore(Protocol):
    """Persistence for RiskState across restarts."""

    def load_risk_state(self) -> RiskState | None: ...

    def save_risk_state(self, state: RiskState) -> None: ...
```

Export `RiskStateError` and `RiskStateStore` from `src/silver_bot/risk/__init__.py` (sorted in `__all__`).

- [ ] **Step 4: Implement storage.** In `src/silver_bot/storage/sqlite.py` add imports:

```python
import math
from datetime import date, datetime, timezone

from silver_bot.risk.models import RiskState, RiskStateError
```

Inside the `initialize` script, after the `ml_predictions` table:

```sql
                CREATE TABLE IF NOT EXISTS risk_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    current_day TEXT,
                    daily_realized_pnl REAL NOT NULL,
                    consecutive_losses INTEGER NOT NULL,
                    trades_today INTEGER NOT NULL,
                    open_positions INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
```

Add methods before `count_rows`:

```python
    def save_risk_state(self, state: RiskState) -> None:
        """Persist the single risk-state row."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO risk_state (
                    id, current_day, daily_realized_pnl, consecutive_losses,
                    trades_today, open_positions, updated_at
                )
                VALUES (1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.current_day.isoformat() if state.current_day else None,
                    state.daily_realized_pnl,
                    state.consecutive_losses,
                    state.trades_today,
                    state.open_positions,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def load_risk_state(self) -> RiskState | None:
        """Return the saved risk state, None if never saved; raise if untrustworthy."""

        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT current_day, daily_realized_pnl, consecutive_losses,
                           trades_today, open_positions
                    FROM risk_state WHERE id = 1
                    """
                ).fetchone()
        except sqlite3.Error as exc:
            raise RiskStateError(f"risk_state could not be read: {exc}") from exc
        if row is None:
            return None
        current_day, pnl, losses, trades, open_positions = row
        try:
            day = date.fromisoformat(current_day) if current_day is not None else None
        except (TypeError, ValueError) as exc:
            raise RiskStateError("risk_state.current_day is not an ISO date") from exc
        if isinstance(pnl, bool) or not isinstance(pnl, (int, float)) or not math.isfinite(pnl):
            raise RiskStateError("risk_state.daily_realized_pnl is not a finite number")
        for name, value in (
            ("consecutive_losses", losses),
            ("trades_today", trades),
            ("open_positions", open_positions),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RiskStateError(f"risk_state.{name} must be a non-negative integer")
        return RiskState(
            current_day=day,
            daily_realized_pnl=float(pnl),
            consecutive_losses=losses,
            trades_today=trades,
            open_positions=open_positions,
        )
```

- [ ] **Step 5: Implement the engine.** In `src/silver_bot/risk/engine.py` import `RiskStateStore` from `silver_bot.risk.models` and change `__init__`:

```python
    def __init__(
        self,
        config: RiskConfig | None = None,
        *,
        state: RiskState | None = None,
        kill_switch: KillSwitch | None = None,
        state_store: RiskStateStore | None = None,
    ) -> None:
        self.config = config or RiskConfig()
        self.kill_switch = kill_switch or KillSwitch(self.config.kill_switch_path)
        self.state_store = state_store
        self.state_load_error: str | None = None
        if state is None and state_store is not None:
            try:
                state = state_store.load_risk_state()
            except Exception as exc:  # fail closed on any unreadable state
                self.state_load_error = str(exc)
        self.state = state or RiskState()
```

At the top of `evaluate`, replace `self.state.roll_day(request.signal_day)` with:

```python
        if self.state_load_error is not None:
            return self._reject("Risk state could not be loaded; trading halted")
        previous_day = self.state.current_day
        self.state.roll_day(request.signal_day)
        if self.state.current_day != previous_day:
            self._save_state()
```

Add `self._save_state()` as the last line of `reserve_trade` and of `release_trade` (after the A2 trip check), and the helper:

```python
    def _save_state(self) -> None:
        if self.state_store is not None and self.state_load_error is None:
            self.state_store.save_risk_state(self.state)
```

- [ ] **Step 6: Extend the factory.** Replace `src/silver_bot/risk/factory.py` body:

```python
"""Build the risk engine from validated application settings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from silver_bot.config import AppConfig
from silver_bot.risk.engine import RiskManagementEngine
from silver_bot.risk.models import RiskConfig

if TYPE_CHECKING:
    from silver_bot.storage import SQLiteStorage


def build_risk_engine(config: AppConfig, storage: SQLiteStorage | None = None) -> RiskManagementEngine:
    """Return a risk engine whose limits and kill switch come from settings.

    `storage` must already be initialized. When given, daily loss, loss streak,
    trade count and open positions persist across restarts.
    """

    risk_config = RiskConfig(
        risk_per_trade=config.max_risk_per_trade,
        max_daily_loss=config.max_daily_loss,
        max_leverage=config.max_leverage,
        kill_switch_path=config.kill_switch_path if config.kill_switch_enabled else None,
    )
    return RiskManagementEngine(risk_config, state_store=storage)
```

The `TYPE_CHECKING` import avoids a cycle: `storage.sqlite` imports `risk.models`, which loads `risk/__init__`, which loads this module.

- [ ] **Step 7: Run the full suite.** `python -m pytest -q`. Expected: all pass. Also run `python -c "import silver_bot.storage; import silver_bot.risk"` and `python -c "import silver_bot.risk; import silver_bot.storage"` to confirm no import cycle in either order.

- [ ] **Step 8: Commit.**

```bash
git add src/silver_bot/risk/models.py src/silver_bot/risk/engine.py src/silver_bot/risk/factory.py src/silver_bot/risk/__init__.py src/silver_bot/storage/sqlite.py tests/test_storage.py tests/test_risk_engine.py
git commit -m "fix(risk): persist risk state in SQLite and halt on corrupt state (G-7)"
```

---

## Lane B: ML (branch `fix/ml-invalid-prob`)

### Task B1: G-8, reject invalid model probabilities

**Files:**
- Modify: `src/silver_bot/ml/filter.py` (`evaluate`, `_predict_probability`)
- Test: `tests/test_ml_probability_filter.py`

**Interfaces:**
- Produces: `MLProbabilityFilter.evaluate` returns `decision=MLDecision.REJECT`, `risk_multiplier=0.0`, `probability=None`, `reason="ML model returned an invalid probability"` for NaN, infinities and values outside [0, 1].

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_ml_probability_filter.py`:

```python
import pytest


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), -0.1, 1.3])
def test_ml_filter_rejects_invalid_probability(tmp_path: Path, bad: float) -> None:
    candles = valid_long_setup()
    signal = strategy().evaluate(candles)

    result = active_filter(tmp_path, bad).evaluate(signal=signal, candles_at_signal=candles)

    assert result.decision == MLDecision.REJECT
    assert result.risk_multiplier == 0.0
    assert result.probability is None
    assert result.reason == "ML model returned an invalid probability"


@pytest.mark.parametrize(("edge", "expected"), [(0.0, MLDecision.REJECT), (1.0, MLDecision.APPROVE)])
def test_ml_filter_boundary_probabilities_keep_threshold_logic(
    tmp_path: Path, edge: float, expected: MLDecision
) -> None:
    candles = valid_long_setup()
    signal = strategy().evaluate(candles)

    result = active_filter(tmp_path, edge).evaluate(signal=signal, candles_at_signal=candles)

    assert result.decision == expected
    assert result.probability == edge
```

- [ ] **Step 2: Run to verify failure.** `python -m pytest -q tests/test_ml_probability_filter.py`. Expected: NaN, `inf` and `1.3` approve today; `-inf` and `-0.1` reject with the wrong reason.

- [ ] **Step 3: Implement.** In `src/silver_bot/ml/filter.py` add `import math`. In `_predict_probability`, replace `return max(0.0, min(1.0, probability))` with `return probability`. In `evaluate`, directly after `probability = self._predict_probability(model, row)`:

```python
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            return MLFilterResult(
                signal_id=signal_id,
                decision=MLDecision.REJECT,
                probability=None,
                threshold=self.config.min_probability,
                reduce_risk_threshold=self.config.reduce_risk_threshold,
                risk_multiplier=0.0,
                model_id=active_entry.model_id,
                model_name=active_entry.model_name,
                reason="ML model returned an invalid probability",
                features_snapshot=features,
            )
```

- [ ] **Step 4: Run the full suite.** `python -m pytest -q`. Expected: all pass.

- [ ] **Step 5: Commit.**

```bash
git add src/silver_bot/ml/filter.py tests/test_ml_probability_filter.py
git commit -m "fix(ml): reject non-finite or out-of-range model probabilities (G-8)"
```

---

## Lane C: config surface (branch `fix/config-surface`)

### Task C1: G-10, exact testnet host check

**Files:**
- Modify: `src/silver_bot/config/settings.py` (`_is_binance_testnet_url` becomes public `is_binance_futures_testnet_url`; its call site in `load_config`)
- Modify: `src/silver_bot/exchange/binance_futures.py` (delete local function, import the config one)
- Test: `tests/test_exchange.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `silver_bot.config.settings.is_binance_futures_testnet_url(value: str) -> bool`, re-exported unchanged as `silver_bot.exchange.is_binance_futures_testnet_url`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_exchange.py`:

```python
from silver_bot.exchange import is_binance_futures_testnet_url


@pytest.mark.parametrize(
    "url",
    [
        "https://testnet.binancefuture.com",
        "https://testnet.binancefuture.com/fapi",
        "HTTPS://TESTNET.BINANCEFUTURE.COM",
        "https://testnet.binancefuture.com:443",
        "  https://testnet.binancefuture.com  ",
    ],
)
def test_testnet_url_accepts_exact_host(url: str) -> None:
    assert is_binance_futures_testnet_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://testnet.binancefuture.com.evil.com",
        "https://evil.com/?x=testnet.binancefuture.com",
        "https://user@testnet.binancefuture.com",
        "http://testnet.binancefuture.com",
        "https://fapi.binance.com",
        "https://testnet.binancefuture.com:8443",
        "https://testnet.binancefuture.com.",
        "https://testnet.binancefuture.com:notaport",
        "testnet.binancefuture.com",
        "",
    ],
)
def test_testnet_url_rejects_lookalikes(url: str) -> None:
    assert is_binance_futures_testnet_url(url) is False


def test_adapter_rejects_lookalike_testnet_host() -> None:
    with pytest.raises(ValueError, match="testnet endpoint"):
        BinanceFuturesAdapter(testnet=True, base_url="https://testnet.binancefuture.com.evil.com")
```

Append to `tests/test_config.py`:

```python
def test_demo_config_rejects_lookalike_testnet_url(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        demo_env() + "\nBINANCE_FUTURES_BASE_URL=https://testnet.binancefuture.com.evil.com\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="testnet endpoint"):
        load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})
```

- [ ] **Step 2: Run to verify failure.** `python -m pytest -q tests/test_exchange.py tests/test_config.py`. Expected: the lookalike cases are accepted today.

- [ ] **Step 3: Implement.** In `src/silver_bot/config/settings.py` add `from urllib.parse import urlsplit` and replace `_is_binance_testnet_url` with:

```python
BINANCE_FUTURES_TESTNET_HOST = "testnet.binancefuture.com"


def is_binance_futures_testnet_url(value: str) -> bool:
    """Return whether a URL is exactly the Binance Futures testnet over https."""

    try:
        parts = urlsplit(value.strip())
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme.lower() == "https"
        and parts.hostname == BINANCE_FUTURES_TESTNET_HOST
        and parts.username is None
        and parts.password is None
        and port in (None, 443)
    )
```

Update the call in `load_config` from `_is_binance_testnet_url(binance_base_url)` to `is_binance_futures_testnet_url(binance_base_url)`.

In `src/silver_bot/exchange/binance_futures.py`, delete the local `is_binance_futures_testnet_url` function and add to the imports:

```python
from silver_bot.config.settings import is_binance_futures_testnet_url
```

`silver_bot/exchange/__init__.py` keeps importing the name from `binance_futures`; no change there.

- [ ] **Step 4: Run the full suite.** `python -m pytest -q`. Expected: all pass.

- [ ] **Step 5: Commit.**

```bash
git add src/silver_bot/config/settings.py src/silver_bot/exchange/binance_futures.py tests/test_exchange.py tests/test_config.py
git commit -m "fix(exchange): require exact https testnet host (G-10)"
```

### Task C2: G-4, shipped `.env.example` loads

**Files:**
- Modify: `.env.example` (lines 5-6)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test.** Append to `tests/test_config.py`:

```python
REPO_ROOT = Path(__file__).resolve().parents[1]


def test_shipped_env_example_loads_as_paper(tmp_path: Path) -> None:
    config = load_config(
        env_path=REPO_ROOT / ".env.example",
        yaml_path=tmp_path / "missing.yaml",
        environ={},
    )

    assert config.mode == TradingMode.PAPER
    assert config.paper_trading is True
    assert config.demo_trading is False
    assert config.live_trading is False
```

- [ ] **Step 2: Run to verify failure.** `python -m pytest -q tests/test_config.py::test_shipped_env_example_loads_as_paper`. Expected: `ConfigError` about demo API keys.

- [ ] **Step 3: Implement.** In `.env.example` change `PAPER_TRADING=false` to `PAPER_TRADING=true` and `DEMO_TRADING=true` to `DEMO_TRADING=false` in the top block only. The commented demo block stays as is.

- [ ] **Step 4: Run the full suite.** `python -m pytest -q`. Expected: all pass.

- [ ] **Step 5: Commit.**

```bash
git add .env.example tests/test_config.py
git commit -m "fix(config): make shipped .env.example load as paper mode (G-4)"
```

---

## Lane D: backtest and readiness (branch `fix/backtest-readiness`)

### Task D1: G-11, non-zero backtest cost defaults

**Files:**
- Modify: `src/silver_bot/backtest/models.py` (`BacktestConfig` defaults)
- Test: `tests/test_backtest_engine.py`

- [ ] **Step 1: Write the failing test.** Append to `tests/test_backtest_engine.py`:

```python
def test_backtest_cost_defaults_are_conservative() -> None:
    config = BacktestConfig()

    assert config.slippage_bps == 5.0
    assert config.spread_bps == 3.0
```

- [ ] **Step 2: Keep exact-P&L tests explicit.** In `tests/test_backtest_engine.py`, the `engine()` helper default becomes `BacktestConfig(maker_fee=0.0, taker_fee=0.0, slippage_bps=0.0, spread_bps=0.0)`, and `test_backtest_records_winning_trade_and_exports` builds `BacktestConfig(maker_fee=0.0, taker_fee=0.0, slippage_bps=0.0, spread_bps=0.0, export_dir=tmp_path)`. These are the only two tests that break under the new defaults (verified by probe at `67ea459`).

- [ ] **Step 3: Run to verify failure.** `python -m pytest -q tests/test_backtest_engine.py::test_backtest_cost_defaults_are_conservative`. Expected: FAIL, `0.0 != 5.0`.

- [ ] **Step 4: Implement.** In `src/silver_bot/backtest/models.py`: `slippage_bps: float = 5.0` and `spread_bps: float = 3.0`.

- [ ] **Step 5: Run the full suite.** `python -m pytest -q`. Expected: all pass.

- [ ] **Step 6: Commit.**

```bash
git add src/silver_bot/backtest/models.py tests/test_backtest_engine.py
git commit -m "fix(backtest): default to 5 bps slippage and 3 bps spread (G-11)"
```

### Task D2: G-2, readiness reports must hold a JSON object

**Files:**
- Modify: `src/silver_bot/readiness.py` (`_file_exists` becomes `_report_check`; its three call sites in `evaluate_live_readiness`)
- Test: `tests/test_readiness.py`

**Interfaces:**
- Produces: check names `backtest_report_exists`, `out_of_sample_validation_report_exists`, `paper_trading_report_exists` unchanged; the missing-file reason still contains `Set <ENV_KEY>`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_readiness.py`:

```python
import pytest


@pytest.mark.parametrize(
    ("content", "fragment"),
    [
        ("", "is empty"),
        ("   \n", "is empty"),
        ("not json", "not valid JSON"),
        ("[]", "JSON object"),
    ],
)
def test_live_readiness_rejects_unusable_report(tmp_path: Path, content: str, fragment: str) -> None:
    create_required_reports(tmp_path)
    (tmp_path / "reports" / "backtest_report.json").write_text(content, encoding="utf-8")

    report = evaluate_live_readiness(project_root=tmp_path, environ=required_env())
    reasons = {item.name: item.reason for item in report.failed_checks}

    assert report.ready is False
    assert fragment in reasons["backtest_report_exists"]


def test_live_readiness_accepts_report_with_utf8_bom(tmp_path: Path) -> None:
    create_required_reports(tmp_path)
    (tmp_path / "reports" / "backtest_report.json").write_text("﻿{}", encoding="utf-8")

    report = evaluate_live_readiness(project_root=tmp_path, environ=required_env())

    assert "backtest_report_exists" not in {item.name for item in report.failed_checks}
```

- [ ] **Step 2: Run to verify failure.** `python -m pytest -q tests/test_readiness.py`. Expected: the empty, whitespace, invalid and list cases pass the check today.

- [ ] **Step 3: Implement.** In `src/silver_bot/readiness.py` replace `_file_exists` with:

```python
def _report_check(
    check_name: str,
    root: Path,
    env: Mapping[str, str],
    env_key: str,
    default_path: str,
) -> ReadinessCheck:
    path = Path(env.get(env_key, default_path))
    resolved = path if path.is_absolute() else root / path
    if not resolved.is_file():
        return ReadinessCheck(
            check_name,
            False,
            f"Missing required report: {resolved}. Set {env_key} to the completed report path.",
        )
    try:
        text = resolved.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        return ReadinessCheck(check_name, False, f"Report {resolved} could not be read: {exc}")
    if not text.strip():
        return ReadinessCheck(check_name, False, f"Report {resolved} is empty. Set {env_key} to a completed report.")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return ReadinessCheck(check_name, False, f"Report {resolved} is not valid JSON.")
    if not isinstance(payload, dict):
        return ReadinessCheck(check_name, False, f"Report {resolved} must contain a JSON object.")
    return ReadinessCheck(check_name, True, f"Found {resolved}")
```

and rename the three `_file_exists(` calls in `evaluate_live_readiness` to `_report_check(`.

- [ ] **Step 4: Run the full suite.** `python -m pytest -q`. Expected: all pass.

- [ ] **Step 5: Commit.**

```bash
git add src/silver_bot/readiness.py tests/test_readiness.py
git commit -m "fix(readiness): require non-empty JSON object reports (G-2)"
```

---

## Integration (orchestrator, on `dev`)

### Task I1: Merge lanes

- [ ] Merge in order with `git merge --no-ff fix/risk-core`, `fix/ml-invalid-prob`, `fix/config-surface`, `fix/backtest-readiness`. Lane A and C both edit `config/settings.py` and `tests/test_config.py`; resolve by keeping both sides.
- [ ] After each merge run `python -m pytest -q`. Expected after the last merge: all pass, more than 109 tests.

### Task I2: Docs pass

Update the suite to match the merged code, citing `file:line` from `dev`:

- [ ] `docs/scrutiny-silverbot.md` section 3: G-2, G-4, G-8, G-10, G-11 to `Closed (<commit>)`; G-5, G-6, G-7 to `Partial` with the remaining work (runtime caller is G-3; G-6 has no position close).
- [ ] `docs/audit-docs-drift.md`: a `Resolved:` line on H-1, H-2, H-5, H-7, H-9, H-11, H-14 and D-2, D-5, D-11, D-12, D-13, D-86.
- [ ] `docs/sdd-silverbot.md`: 3.2 adds the `risk_state` table; 3.4 the global `MAX_RISK_PER_TRADE` and kill-switch-path rules; 5.3 kill switch behaviour; 5.5 the 0.5% cap; 8 invalid-probability rejection; 4.3 the exact host rule.
- [ ] `docs/rfc-silverbot-risk-kill-switch.md`, `docs/rfc-silverbot-ml-filter-gate.md`, `docs/rfc-silverbot-readiness-gates.md`: as-built sections.
- [ ] `docs/qad-silverbot.md`: add the new test scenarios with their test names.
- [ ] `docs/ops-silverbot.md`: steps to clear a tripped kill switch (inspect JSON reason, delete file) and to reset `risk_state` (`DELETE FROM risk_state WHERE id = 1;` with the bot stopped).
- [ ] `docs/build-silverbot.md` section 3: update the D-11 deprecation row. Then `python tools/materialize_docs.py` and `python tools/materialize_docs.py --check`.
- [ ] `docs/index.md`: health-check hazard list, change log, process-records table and counts (this plan and its spec). `README.md` safe defaults paragraph.
- [ ] Commit only the edited docs and materialized files: `docs: reconcile suite with HIGH safety fixes batch 1`.

### Task I3: Safety review

- [ ] Run `live-trading-gate-guardian`, `risk-bypass-checker`, `lookahead-leakage-auditor` and `restraint-guardian` in parallel on `git diff 05c9c11..dev`.
- [ ] Verify each finding against the code before acting. Fix confirmed blocking findings with a test, re-run the suite, and commit.

### Task I4: Final verification

- [ ] `python -m pytest -q` passes.
- [ ] `python tools/materialize_docs.py --check` reports no changes.
- [ ] `git status --short` shows only the owner's untracked files.
