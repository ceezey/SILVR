"""Backtest domain models: the simulated account config, trade records and equity points."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from silvr.risk import RiskConfig


class ExitReason(str, Enum):
    """Supported simulated trade exit reasons."""

    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    END_OF_DATA = "end_of_data"
    KILL_SWITCH = "kill_switch"


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    """Configuration for historical simulation only."""

    initial_balance: float = 10_000.0
    risk: RiskConfig = field(default_factory=RiskConfig)
    maker_fee: float = 0.0002
    taker_fee: float = 0.0005
    slippage_bps: float = 5.0
    spread_bps: float = 3.0

    def __post_init__(self) -> None:
        if self.initial_balance <= 0:
            raise ValueError("initial_balance must be positive")
        if self.maker_fee < 0 or self.taker_fee < 0:
            raise ValueError("fees cannot be negative")
        if self.slippage_bps < 0 or self.spread_bps < 0:
            raise ValueError("slippage and spread cannot be negative")


@dataclass(frozen=True, slots=True)
class TradeRecord:
    """Completed simulated trade."""

    trade_id: int
    symbol: str
    timeframe: str
    session_name: str
    direction: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    position_size: float
    risk_amount: float
    realized_pnl: float
    realized_r: float
    fees: float
    slippage: float
    max_favorable_excursion: float
    max_adverse_excursion: float
    exit_reason: ExitReason
    setup_quality_score: int
    notes: str = ""
    ml_probability: float | None = None
    ml_decision: str | None = None
    funding: float = 0.0  # net funding paid; negative when received


@dataclass(frozen=True, slots=True)
class EquityPoint:
    """Equity curve point."""

    timestamp: datetime
    equity: float
    realized_pnl: float
    drawdown: float
