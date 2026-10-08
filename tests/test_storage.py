import sqlite3
from datetime import date
from pathlib import Path

import pytest

from silver_bot.risk import RiskState, RiskStateError
from silver_bot.storage import SQLiteStorage


def test_database_initialization_creates_phase_one_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "silver_bot.sqlite3"
    storage = SQLiteStorage(database_path)

    storage.initialize()

    assert database_path.exists()
    assert {"candles", "signals", "trades", "logs", "ml_predictions"}.issubset(storage.table_names())


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
