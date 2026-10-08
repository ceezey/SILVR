"""Core typed domain models shared across Phase 1 components."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class SignalDirection(str, Enum):
    """Rule-based strategy output."""

    LONG = "LONG"
    SHORT = "SHORT"
    NO_TRADE = "NO_TRADE"


class TradeSide(str, Enum):
    """Trade side."""

    BUY = "BUY"
    SELL = "SELL"


class TradeStatus(str, Enum):
    """Trade lifecycle status."""

    PLANNED = "PLANNED"
    REJECTED = "REJECTED"
    PAPER_OPEN = "PAPER_OPEN"
    PAPER_CLOSED = "PAPER_CLOSED"


@dataclass(frozen=True, slots=True)
class Candle:
    """OHLCV market candle."""

    symbol: str
    timeframe: str
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: datetime | None = None

    def __post_init__(self) -> None:
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("Candle high/low must contain open and close")
        if self.volume < 0:
            raise ValueError("Candle volume cannot be negative")


@dataclass(frozen=True, slots=True)
class TradingSignal:
    """Strategy decision with mandatory rejection reason for no-trade setups."""

    symbol: str
    direction: SignalDirection
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str | None = None
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None

    def __post_init__(self) -> None:
        if self.direction == SignalDirection.NO_TRADE and not self.reason:
            raise ValueError("NO_TRADE signals require a rejection reason")


@dataclass(frozen=True, slots=True)
class Trade:
    """Planned or paper trade record."""

    symbol: str
    side: TradeSide
    status: TradeStatus
    quantity: float
    entry_price: float
    stop_loss: float
    take_profit: float
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("Trade quantity must be positive")
        if self.stop_loss == self.entry_price:
            raise ValueError("Stop loss cannot equal entry price")


@dataclass(frozen=True, slots=True)
class LogEvent:
    """Structured operational log event for persistence."""

    level: str
    message: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    context: dict[str, Any] = field(default_factory=dict)
