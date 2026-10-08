from pathlib import Path

from silver_bot.storage import SQLiteStorage


def test_database_initialization_creates_phase_one_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "silver_bot.sqlite3"
    storage = SQLiteStorage(database_path)

    storage.initialize()

    assert database_path.exists()
    assert {"candles", "signals", "trades", "logs", "ml_predictions"}.issubset(storage.table_names())
