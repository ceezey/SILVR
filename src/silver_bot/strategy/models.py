"""Strategy-domain models for deterministic ICT Silver Bullet logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum

from silver_bot.models import SignalDirection


class BiasDirection(str, Enum):
    """Higher-timeframe directional bias."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class FairValueGapDirection(str, Enum):
    """Fair Value Gap direction."""

    BULLISH = "bullish"
    BEARISH = "bearish"


class LiquiditySide(str, Enum):
    """Liquidity location relative to price."""

    BUY_SIDE = "buy_side"
    SELL_SIDE = "sell_side"


class SweepDirection(str, Enum):
    """Sweep type used by the Silver Bullet model."""

    BULLISH = "bullish"
    BEARISH = "bearish"


class StructureShiftDirection(str, Enum):
    """Market structure shift direction."""

    BULLISH = "bullish"
    BEARISH = "bearish"


@dataclass(frozen=True, slots=True)
class SessionWindow:
    """Configurable Silver Bullet session window in local session timezone."""

    name: str
    start: time
    end: time
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class SessionState:
    """Current session evaluation."""

    is_active: bool
    name: str | None
    timezone: str
    start_at: datetime | None = None
    end_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SwingPoint:
    """Causal swing point identified without future candles."""

    index: int
    timestamp: datetime
    price: float
    kind: LiquiditySide


@dataclass(frozen=True, slots=True)
class LiquidityLevel:
    """Detected liquidity level."""

    price: float
    side: LiquiditySide
    source: str
    candle_index: int
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class LiquiditySweep:
    """Liquidity sweep event."""

    direction: SweepDirection
    level: LiquidityLevel
    candle_index: int
    timestamp: datetime
    swept_price: float
    close_price: float


@dataclass(frozen=True, slots=True)
class FairValueGap:
    """Three-candle imbalance zone."""

    direction: FairValueGapDirection
    candle_index: int
    lower_bound: float
    upper_bound: float
    midpoint: float
    size: float
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class DisplacementEvent:
    """Strong directional impulse event."""

    direction: FairValueGapDirection
    candle_index: int
    timestamp: datetime
    strength_score: float
    body_size: float
    candle_range: float
    atr: float


@dataclass(frozen=True, slots=True)
class MarketStructureShift:
    """Simple market structure shift confirmation."""

    direction: StructureShiftDirection
    candle_index: int
    timestamp: datetime
    broken_level: float


@dataclass(frozen=True, slots=True)
class SignalQualityBreakdown:
    """Deterministic setup score components."""

    total: int
    session: int = 0
    liquidity: int = 0
    displacement: int = 0
    fvg: int = 0
    htf_alignment: int = 0
    risk_reward: int = 0
    volatility: int = 0


@dataclass(frozen=True, slots=True)
class SilverBulletStrategyConfig:
    """Configurable strategy defaults for Phase 2 research signals."""

    sessions: tuple[SessionWindow, ...] = field(default_factory=tuple)
    session_timezone: str = "America/New_York"
    swing_lookback: int = 3
    liquidity_lookback: int = 30
    minimum_fvg_size: float = 0.0
    atr_period: int = 5
    displacement_body_multiplier: float = 1.2
    displacement_range_multiplier: float = 1.0
    stop_buffer: float = 0.0
    minimum_rr: float = 2.0
    minimum_signal_score: int = 70
    allow_counter_bias: bool = False


@dataclass(frozen=True, slots=True)
class SilverBulletSignal:
    """Strategy output for research/backtesting.

    This is not an executable order and does not bypass future risk checks.
    """

    direction: SignalDirection
    symbol: str
    timeframe: str
    generated_at: datetime
    reason: str | None
    explanation: str
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    risk_reward_ratio: float | None = None
    session_name: str | None = None
    setup_quality_score: int = 0

    def __post_init__(self) -> None:
        if self.direction == SignalDirection.NO_TRADE and not self.reason:
            raise ValueError("NO_TRADE signals require a reason")
        if self.direction != SignalDirection.NO_TRADE:
            required = (
                self.entry_price,
                self.stop_loss,
                self.take_profit,
                self.risk_reward_ratio,
                self.session_name,
            )
            if any(value is None for value in required):
                raise ValueError("Valid strategy signals require entry, stop, target, RR, and session")
