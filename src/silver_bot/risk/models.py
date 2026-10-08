"""Risk-management domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

MAX_RISK_PER_TRADE = 0.005


@dataclass(frozen=True, slots=True)
class RiskConfig:
    """Static risk limits.

    The defaults are conservative research/backtest defaults. They do not enable
    live trading and do not implement martingale or averaging down.
    """

    risk_per_trade: float = 0.005
    minimum_stop_distance: float = 0.01
    minimum_reward_to_risk: float = 2.0
    max_daily_loss: float = 0.02
    max_consecutive_losses: int = 3
    max_trades_per_day: int = 3
    max_open_positions: int = 1
    max_leverage: float = 3.0
    kill_switch_path: Path | None = None

    def __post_init__(self) -> None:
        if not 0 < self.risk_per_trade <= MAX_RISK_PER_TRADE:
            raise ValueError("risk_per_trade must be greater than 0 and no more than 0.5%")
        if self.minimum_stop_distance <= 0:
            raise ValueError("minimum_stop_distance must be positive")
        if self.minimum_reward_to_risk <= 0:
            raise ValueError("minimum_reward_to_risk must be positive")
        if not 0 < self.max_daily_loss <= 1:
            raise ValueError("max_daily_loss must be greater than 0 and no more than 100%")
        if self.max_consecutive_losses < 1:
            raise ValueError("max_consecutive_losses must be at least 1")
        if self.max_trades_per_day < 1:
            raise ValueError("max_trades_per_day must be at least 1")
        if self.max_open_positions < 1:
            raise ValueError("max_open_positions must be at least 1")
        if self.max_leverage <= 0:
            raise ValueError("max_leverage must be positive")


@dataclass(slots=True)
class RiskState:
    """Mutable risk state for a backtest or bot session."""

    current_day: date | None = None
    daily_realized_pnl: float = 0.0
    consecutive_losses: int = 0
    trades_today: int = 0
    open_positions: int = 0

    def roll_day(self, day: date) -> None:
        """Reset daily counters on a new trading day."""

        if self.current_day != day:
            self.current_day = day
            self.daily_realized_pnl = 0.0
            self.trades_today = 0


@dataclass(frozen=True, slots=True)
class RiskRequest:
    """Risk input for a proposed strategy candidate."""

    equity: float
    entry_price: float | None
    stop_loss: float | None
    take_profit: float | None
    direction: str
    signal_day: date


@dataclass(frozen=True, slots=True)
class RiskDecision:
    """Risk approval or rejection."""

    approved: bool
    reason: str
    position_size: float = 0.0
    risk_amount: float = 0.0
    reward_to_risk: float = 0.0
    leverage: float = 0.0
