"""Abstract exchange adapter contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Sequence

from silver_bot.models import Candle, TradeSide


class OrderPlacementDisabled(RuntimeError):
    """Raised when code attempts real order placement in a disabled phase."""


@dataclass(frozen=True, slots=True)
class OrderRequest:
    """Order request shape reserved for future paper/live execution."""

    symbol: str
    side: TradeSide
    quantity: Decimal
    stop_loss: Decimal
    take_profit: Decimal


class ExchangeAdapter(ABC):
    """Exchange abstraction used by data and execution layers."""

    @abstractmethod
    async def fetch_ohlcv(
        self,
        *,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        limit: int = 1000,
    ) -> Sequence[Candle]:
        """Fetch historical OHLCV candles."""

    async def place_order(self, request: OrderRequest) -> None:
        """Reject real order placement until a later explicit live-trading phase."""

        raise OrderPlacementDisabled("Real order placement is disabled in Phase 1")

    async def cancel_order(self, *, symbol: str, order_id: str) -> None:
        """Reject real order cancellation until live execution is explicitly built."""

        raise OrderPlacementDisabled("Real order cancellation is disabled in Phase 1")
