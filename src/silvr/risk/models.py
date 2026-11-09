"""Risk-management domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

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
    profile: str = "default"
    minimum_stop_fraction: float | None = None

    @classmethod
    def trend(cls, **overrides: object) -> RiskConfig:
        """The `trend` profile: many small slices, relative minimum stop, no take-profit."""

        values: dict[str, object] = {
            "profile": "trend",
            "max_trades_per_day": 135,
            "max_open_positions": 135,
            "minimum_stop_fraction": 0.001,
            "max_daily_loss": 0.02,
            "max_leverage": 3.0,
            "risk_per_trade": 0.005,
        }
        values.update(overrides)
        return cls(**values)  # type: ignore[arg-type]

    def __post_init__(self) -> None:
        if self.profile not in ("default", "trend"):
            raise ValueError("profile must be 'default' or 'trend'")
        if self.profile == "trend" and self.minimum_stop_fraction is None:
            raise ValueError("minimum_stop_fraction is required for the trend profile")
        if self.minimum_stop_fraction is not None and self.minimum_stop_fraction <= 0:
            raise ValueError("minimum_stop_fraction must be positive")
        if self.profile == "trend" and not (
            self.max_leverage <= 3.0
            and self.max_daily_loss <= 0.02
            and self.max_trades_per_day <= 135
            and self.max_open_positions <= 135
            and self.minimum_stop_fraction is not None
            and self.minimum_stop_fraction >= 0.001
        ):
            raise ValueError("the trend profile may be tightened but never loosened beyond its spec limits")
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


class RiskStateError(ValueError):
    """Raised when persisted risk state cannot be trusted."""


class RiskStateStore(Protocol):
    """Persistence for RiskState across restarts."""

    def load_risk_state(self) -> RiskState | None: ...

    def save_risk_state(self, state: RiskState) -> None: ...


@dataclass(frozen=True, slots=True)
class RiskRequest:
    """Risk input for a proposed strategy candidate."""

    equity: float
    entry_price: float | None
    stop_loss: float | None
    take_profit: float | None
    direction: str
    signal_day: date
    requested_size: float | None = None


@dataclass(frozen=True, slots=True)
class RiskDecision:
    """Risk approval or rejection."""

    approved: bool
    reason: str
    position_size: float = 0.0
    risk_amount: float = 0.0
    reward_to_risk: float = 0.0
    leverage: float = 0.0
