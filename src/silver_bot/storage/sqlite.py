"""SQLite storage layer for local research and paper trading data."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Iterable

from silver_bot.models import Candle, LogEvent


class SQLiteStorage:
    """Small SQLite persistence layer."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def initialize(self) -> None:
        """Create the database schema if it does not exist."""

        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS candles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    open_time TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    close_time TEXT,
                    UNIQUE(symbol, timeframe, open_time)
                );
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    reason TEXT,
                    entry_price REAL,
                    stop_loss REAL,
                    take_profit REAL
                );
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    status TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    context_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS paper_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    session_name TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_time TEXT NOT NULL,
                    exit_time TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    position_size REAL NOT NULL,
                    risk_amount REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    realized_r REAL NOT NULL,
                    fees REAL NOT NULL,
                    slippage REAL NOT NULL,
                    exit_reason TEXT NOT NULL,
                    setup_quality_score INTEGER NOT NULL,
                    notes TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS paper_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    message TEXT NOT NULL,
                    context_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ml_predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT NOT NULL,
                    model_version TEXT,
                    model_name TEXT,
                    probability REAL,
                    threshold REAL NOT NULL,
                    reduce_risk_threshold REAL NOT NULL,
                    decision TEXT NOT NULL,
                    risk_multiplier REAL NOT NULL,
                    reason TEXT NOT NULL,
                    features_snapshot TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def save_candles(self, candles: Iterable[Candle]) -> int:
        """Insert or replace candles and return the number processed."""

        rows = [
            (
                candle.symbol,
                candle.timeframe,
                candle.open_time.isoformat(),
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
                candle.close_time.isoformat() if candle.close_time else None,
            )
            for candle in candles
        ]
        if not rows:
            return 0

        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO candles (
                    symbol, timeframe, open_time, open, high, low, close, volume, close_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def save_log(self, event: LogEvent) -> None:
        """Persist a structured log event."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO logs (level, message, created_at, context_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    event.level,
                    event.message,
                    event.created_at.isoformat(),
                    json.dumps(event.context, sort_keys=True),
                ),
            )

    def save_paper_trade(self, trade: object) -> None:
        """Persist a completed paper trade record."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO paper_trades (
                    trade_id, symbol, timeframe, session_name, direction,
                    entry_time, exit_time, entry_price, exit_price, stop_loss,
                    take_profit, position_size, risk_amount, realized_pnl,
                    realized_r, fees, slippage, exit_reason, setup_quality_score, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    getattr(trade, "trade_id"),
                    getattr(trade, "symbol"),
                    getattr(trade, "timeframe"),
                    getattr(trade, "session_name"),
                    getattr(trade, "direction"),
                    getattr(trade, "entry_time").isoformat(),
                    getattr(trade, "exit_time").isoformat(),
                    getattr(trade, "entry_price"),
                    getattr(trade, "exit_price"),
                    getattr(trade, "stop_loss"),
                    getattr(trade, "take_profit"),
                    getattr(trade, "position_size"),
                    getattr(trade, "risk_amount"),
                    getattr(trade, "realized_pnl"),
                    getattr(trade, "realized_r"),
                    getattr(trade, "fees"),
                    getattr(trade, "slippage"),
                    getattr(getattr(trade, "exit_reason"), "value", getattr(trade, "exit_reason")),
                    getattr(trade, "setup_quality_score"),
                    getattr(trade, "notes"),
                ),
            )

    def save_paper_event(
        self,
        *,
        event_type: str,
        symbol: str,
        timestamp: str,
        message: str,
        context: dict,
    ) -> None:
        """Persist a paper-trading lifecycle event."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO paper_events (event_type, symbol, timestamp, message, context_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_type, symbol, timestamp, message, json.dumps(context, sort_keys=True)),
            )

    def save_ml_prediction(self, prediction: object) -> None:
        """Persist an ML probability-filter decision."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ml_predictions (
                    signal_id, model_version, model_name, probability, threshold,
                    reduce_risk_threshold, decision, risk_multiplier, reason,
                    features_snapshot, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    getattr(prediction, "signal_id"),
                    getattr(prediction, "model_id"),
                    getattr(prediction, "model_name"),
                    getattr(prediction, "probability"),
                    getattr(prediction, "threshold"),
                    getattr(prediction, "reduce_risk_threshold"),
                    getattr(getattr(prediction, "decision"), "value", getattr(prediction, "decision")),
                    getattr(prediction, "risk_multiplier"),
                    getattr(prediction, "reason"),
                    json.dumps(getattr(prediction, "features_snapshot"), sort_keys=True),
                    getattr(prediction, "created_at").isoformat(),
                ),
            )

    def count_rows(self, table_name: str) -> int:
        """Return row count for known local tables."""

        allowed = {"paper_trades", "paper_events", "ml_predictions", "candles", "signals", "trades", "logs"}
        if table_name not in allowed:
            raise ValueError("unknown table name")
        with self._connect() as connection:
            row = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        return int(row[0])

    def table_names(self) -> set[str]:
        """Return user table names, primarily for tests and diagnostics."""

        with self._connect() as connection:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        return {row[0] for row in rows}

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()
