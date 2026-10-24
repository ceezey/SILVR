"""PostgreSQL storage layer for paper and demo trading data."""

from __future__ import annotations

import json
import math
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Iterator, Iterable

import psycopg

from silver_bot.models import Candle
from silver_bot.risk.models import RiskState, RiskStateError


# A black-holed database must not hang the trading loop; the risk engine then halts.
CONNECT_TIMEOUT_SECONDS = 10


class PostgresStorage:
    """Small PostgreSQL persistence layer."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def __repr__(self) -> str:
        return "PostgresStorage(<database_url hidden>)"

    def initialize(self) -> None:
        """Create the database schema if it does not exist."""

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS candles (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    open_time TEXT NOT NULL,
                    open DOUBLE PRECISION NOT NULL,
                    high DOUBLE PRECISION NOT NULL,
                    low DOUBLE PRECISION NOT NULL,
                    close DOUBLE PRECISION NOT NULL,
                    volume DOUBLE PRECISION NOT NULL,
                    close_time TEXT,
                    UNIQUE(symbol, timeframe, open_time)
                );
                CREATE TABLE IF NOT EXISTS paper_trades (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    trade_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    session_name TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_time TEXT NOT NULL,
                    exit_time TEXT NOT NULL,
                    entry_price DOUBLE PRECISION NOT NULL,
                    exit_price DOUBLE PRECISION NOT NULL,
                    stop_loss DOUBLE PRECISION NOT NULL,
                    take_profit DOUBLE PRECISION NOT NULL,
                    position_size DOUBLE PRECISION NOT NULL,
                    risk_amount DOUBLE PRECISION NOT NULL,
                    realized_pnl DOUBLE PRECISION NOT NULL,
                    realized_r DOUBLE PRECISION NOT NULL,
                    fees DOUBLE PRECISION NOT NULL,
                    slippage DOUBLE PRECISION NOT NULL,
                    exit_reason TEXT NOT NULL,
                    setup_quality_score INTEGER NOT NULL,
                    notes TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS paper_events (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    message TEXT NOT NULL,
                    context_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ml_predictions (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    signal_id TEXT NOT NULL,
                    model_version TEXT,
                    model_name TEXT,
                    probability DOUBLE PRECISION,
                    threshold DOUBLE PRECISION NOT NULL,
                    reduce_risk_threshold DOUBLE PRECISION NOT NULL,
                    decision TEXT NOT NULL,
                    risk_multiplier DOUBLE PRECISION NOT NULL,
                    reason TEXT NOT NULL,
                    features_snapshot TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS risk_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    current_day TEXT,
                    daily_realized_pnl DOUBLE PRECISION NOT NULL,
                    consecutive_losses INTEGER NOT NULL,
                    trades_today INTEGER NOT NULL,
                    open_positions INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
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
            connection.cursor().executemany(
                """
                INSERT INTO candles (
                    symbol, timeframe, open_time, open, high, low, close, volume, close_time
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, timeframe, open_time) DO UPDATE SET
                    open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                    close = EXCLUDED.close, volume = EXCLUDED.volume, close_time = EXCLUDED.close_time
                """,
                rows,
            )
        return len(rows)

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
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                VALUES (%s, %s, %s, %s, %s)
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
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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

    def save_risk_state(self, state: RiskState) -> None:
        """Persist the single risk-state row."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO risk_state (
                    id, current_day, daily_realized_pnl, consecutive_losses,
                    trades_today, open_positions, updated_at
                )
                VALUES (1, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    current_day = EXCLUDED.current_day,
                    daily_realized_pnl = EXCLUDED.daily_realized_pnl,
                    consecutive_losses = EXCLUDED.consecutive_losses,
                    trades_today = EXCLUDED.trades_today,
                    open_positions = EXCLUDED.open_positions,
                    updated_at = EXCLUDED.updated_at
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
        except psycopg.Error as exc:
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

    def count_rows(self, table_name: str) -> int:
        """Return row count for known local tables."""

        allowed = {
            "paper_trades",
            "paper_events",
            "ml_predictions",
            "candles",
            "risk_state",
        }
        if table_name not in allowed:
            raise ValueError("unknown table name")
        with self._connect() as connection:
            row = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        return int(row[0])

    def table_names(self) -> set[str]:
        """Return user table names, primarily for tests and diagnostics."""

        with self._connect() as connection:
            rows = connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()"
            ).fetchall()
        return {row[0] for row in rows}

    @contextmanager
    def _connect(self) -> Iterator[psycopg.Connection]:
        # shortcut: one connection per call, no pool; add psycopg_pool if writes pass ~10/s.
        connection = psycopg.connect(self.database_url, connect_timeout=CONNECT_TIMEOUT_SECONDS)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()
