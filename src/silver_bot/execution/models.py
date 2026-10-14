"""Paper execution models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from silver_bot.backtest.models import TradeRecord
from silver_bot.risk import RiskDecision
from silver_bot.strategy import SilverBulletSignal


class PaperEventType(str, Enum):
    """Paper-trading lifecycle event types."""

    SIGNAL_DETECTED = "signal_detected"
    RISK_REJECTED = "risk_rejected"
    PAPER_ORDER_CREATED = "paper_order_created"
    PAPER_ORDER_CANCELLED = "paper_order_cancelled"
    PAPER_TRADE_OPENED = "paper_trade_opened"
    PAPER_TRADE_CLOSED = "paper_trade_closed"
    ERROR = "error"
    KILL_SWITCH_ACTIVE = "kill_switch_active"


@dataclass(frozen=True, slots=True)
class PaperExecutionConfig:
    """Paper execution simulation settings."""

    maker_fee: float = 0.0002
    taker_fee: float = 0.0005
    slippage_bps: float = 1.0
    spread_bps: float = 1.0

    def __post_init__(self) -> None:
        if self.maker_fee < 0 or self.taker_fee < 0:
            raise ValueError("fees cannot be negative")
        if self.slippage_bps < 0 or self.spread_bps < 0:
            raise ValueError("slippage and spread cannot be negative")


@dataclass(frozen=True, slots=True)
class PaperOrder:
    """Simulated pending limit order."""

    signal: SilverBulletSignal
    risk_decision: RiskDecision
    created_at: datetime
    ml_probability: float | None = None
    ml_decision: str | None = None
    expires_at: datetime | None = None


@dataclass(slots=True)
class PaperPosition:
    """Open paper position."""

    order: PaperOrder
    entry_time: datetime
    entry_price: float
    stop_loss: float
    take_profit: float
    quantity: float
    entry_fee: float
    risk_amount: float
    max_favorable_excursion: float = 0.0
    max_adverse_excursion: float = 0.0


@dataclass(frozen=True, slots=True)
class PaperLifecycleEvent:
    """Paper-trading lifecycle event."""

    event_type: PaperEventType
    symbol: str
    timestamp: datetime
    message: str
    trade: TradeRecord | None = None
    context: dict | None = None
