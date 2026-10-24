"""Backtest domain models.

Strategy window (CD-8): every strategy component reads a bounded tail of the
candles (liquidity lookback 30 plus swing lookback 3, ATR 5, bias 5, ML recent
window 5), so the engine hands the strategy and the ML filter only the last
`strategy_window` candles, which keeps a multi-year 1m run linear in time.
`MIN_STRATEGY_WINDOW = 64` is the smallest window that still covers the largest
fixed look-back: liquidity 30 plus swing 3 plus ATR 5 is 38, plus a margin.

The FVG step, `latest_unmitigated_fvg`, scans the whole slice it is given, but it is
equivalence-safe: a signal requires `fvg.candle_index > sweep.candle_index`, and the
search is newest-first, so a gap older than the window cannot be the one that
produces a signal. If such a gap were the only match, both the windowed and the
full-history run reject with the same reason.

The one exception is `detect_market_structure_shift`
(`silver_bot/strategy/structure.py`), which uses the most recent opposite-side
swing anywhere in the history. On 1m data a swing (a high above the previous 3
highs) older than one day is not expected, but it is possible in theory. The
equivalence tests in `tests/test_backtest_window.py` are the evidence, and a
real-data check repeats them. If either finds a difference, report it to the
owner (spec 3.7); do not change strategy code to fit the window.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from silver_bot.ml import MLFilterConfig
from silver_bot.models import SignalDirection
from silver_bot.risk import RiskConfig, RiskDecision
from silver_bot.strategy import SilverBulletSignal


DEFAULT_STRATEGY_WINDOW = 1440
MIN_STRATEGY_WINDOW = 64


class ExitReason(str, Enum):
    """Supported simulated trade exit reasons."""

    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    BREAKEVEN_STOP = "breakeven_stop"
    END_OF_DATA = "end_of_data"
    KILL_SWITCH = "kill_switch"


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    """Configuration for historical simulation only.

    `strategy_window` is how many of the most recent candles the strategy and the ML
    filter see at each step: `None` is the whole history, the default is 1440 (one
    day of 1m candles), and values below 64 are rejected. See the module docstring
    for why 1440 is safe and where its limit is.
    """

    initial_balance: float = 10_000.0
    risk: RiskConfig = field(default_factory=RiskConfig)
    maker_fee: float = 0.0002
    taker_fee: float = 0.0005
    slippage_bps: float = 5.0
    spread_bps: float = 3.0
    enable_partial_tp: bool = False
    partial_tp_r: float = 1.0
    partial_tp_fraction: float = 0.5
    move_stop_to_breakeven_after_partial: bool = True
    export_dir: Path | None = None
    ml_filter: MLFilterConfig = field(default_factory=MLFilterConfig)
    strategy_window: int | None = DEFAULT_STRATEGY_WINDOW

    def __post_init__(self) -> None:
        if self.initial_balance <= 0:
            raise ValueError("initial_balance must be positive")
        if self.maker_fee < 0 or self.taker_fee < 0:
            raise ValueError("fees cannot be negative")
        if self.slippage_bps < 0 or self.spread_bps < 0:
            raise ValueError("slippage and spread cannot be negative")
        if not 0 < self.partial_tp_fraction <= 1:
            raise ValueError("partial_tp_fraction must be greater than 0 and no more than 1")
        if self.partial_tp_r <= 0:
            raise ValueError("partial_tp_r must be positive")
        if self.strategy_window is not None and self.strategy_window < MIN_STRATEGY_WINDOW:
            raise ValueError(f"strategy_window must be None or at least {MIN_STRATEGY_WINDOW}")


@dataclass(slots=True)
class PendingOrder:
    """Simulated limit order created by a strategy signal."""

    signal: SilverBulletSignal
    created_at: datetime
    risk_decision: RiskDecision
    ml_probability: float | None = None
    ml_decision: str | None = None
    expires_at: datetime | None = None


@dataclass(slots=True)
class OpenPosition:
    """Internal open position state."""

    signal: SilverBulletSignal
    direction: SignalDirection
    entry_time: datetime
    entry_price: float
    stop_loss: float
    take_profit: float
    quantity: float
    entry_fee: float
    remaining_quantity: float
    risk_amount: float
    partial_realized_pnl: float = 0.0
    partial_fees: float = 0.0
    partial_taken: bool = False
    max_favorable_excursion: float = 0.0
    max_adverse_excursion: float = 0.0
    ml_probability: float | None = None
    ml_decision: str | None = None


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


@dataclass(frozen=True, slots=True)
class RejectedSignalRecord:
    """Rejected signal audit record."""

    timestamp: datetime
    symbol: str
    timeframe: str
    reason: str
    ml_probability: float | None = None
    ml_decision: str | None = None


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Backtest output bundle."""

    trades: list[TradeRecord]
    equity_curve: list[EquityPoint]
    rejected_signals: list[RejectedSignalRecord]
    metrics: dict[str, Any]
    export_paths: dict[str, Path] = field(default_factory=dict)
