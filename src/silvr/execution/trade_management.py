"""Basic paper trade management."""

from __future__ import annotations

from silvr.backtest.models import ExitReason
from silvr.models import Candle, SignalDirection


class BasicTradeManager:
    """Detect stop-loss and take-profit hits on confirmed candles."""

    def exit_reason(
        self,
        *,
        direction: SignalDirection,
        stop_loss: float,
        take_profit: float,
        candle: Candle,
    ) -> ExitReason | None:
        """Return exit reason using conservative stop-first same-candle behavior."""

        if direction == SignalDirection.LONG:
            if candle.low <= stop_loss:
                return ExitReason.STOP_LOSS
            if candle.high >= take_profit:
                return ExitReason.TAKE_PROFIT
            return None
        if direction == SignalDirection.SHORT:
            if candle.high >= stop_loss:
                return ExitReason.STOP_LOSS
            if candle.low <= take_profit:
                return ExitReason.TAKE_PROFIT
        return None
