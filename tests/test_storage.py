from datetime import date

import pytest

from conftest import execute
from silvr.risk import RiskState, RiskStateError
from silvr.storage import PostgresStorage


def initialized(database_url: str) -> PostgresStorage:
    storage = PostgresStorage(database_url)
    storage.initialize()
    return storage


def test_database_initialization_creates_tables(database_url: str) -> None:
    assert initialized(database_url).table_names() == {
        "candles",
        "paper_trades",
        "paper_events",
        "ml_predictions",
        "risk_state",
    }


def test_initialize_is_idempotent(database_url: str) -> None:
    storage = initialized(database_url)
    storage.save_risk_state(RiskState(current_day=date(2026, 1, 2), trades_today=2))

    storage.initialize()

    assert storage.load_risk_state().trades_today == 2


def test_repr_hides_the_database_url() -> None:
    assert "secret-password" not in repr(PostgresStorage("postgresql://bot:secret-password@db/silvr"))


def test_risk_state_round_trip(database_url: str) -> None:
    storage = initialized(database_url)
    state = RiskState(
        current_day=date(2026, 1, 2),
        daily_realized_pnl=-75.5,
        consecutive_losses=2,
        trades_today=3,
        open_positions=1,
    )

    storage.save_risk_state(state)
    storage.save_risk_state(state)

    assert storage.load_risk_state() == state
    assert storage.count_rows("risk_state") == 1


def test_risk_state_missing_row_returns_none(database_url: str) -> None:
    assert initialized(database_url).load_risk_state() is None


def test_load_risk_state_without_schema_raises(database_url: str) -> None:
    with pytest.raises(RiskStateError):
        PostgresStorage(database_url).load_risk_state()


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE risk_state SET consecutive_losses = -1",
        "UPDATE risk_state SET trades_today = -2",
        "UPDATE risk_state SET current_day = 'not-a-date'",
        "UPDATE risk_state SET daily_realized_pnl = 'NaN'",
        "UPDATE risk_state SET daily_realized_pnl = 'Infinity'",
    ],
)
def test_corrupt_risk_state_raises(database_url: str, sql: str) -> None:
    storage = initialized(database_url)
    storage.save_risk_state(RiskState(current_day=date(2026, 1, 2)))
    execute(database_url, sql)

    with pytest.raises(RiskStateError):
        storage.load_risk_state()


def test_count_rows_rejects_unknown_table(database_url: str) -> None:
    with pytest.raises(ValueError):
        initialized(database_url).count_rows("pg_class")
