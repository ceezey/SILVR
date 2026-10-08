"""Historical market data fetch orchestration."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from silver_bot.exchange import ExchangeAdapter
from silver_bot.models import Candle


class HistoricalOHLCVFetcher:
    """Validate and fetch OHLCV data through an exchange adapter."""

    def __init__(self, exchange: ExchangeAdapter) -> None:
        self._exchange = exchange

    async def fetch(
        self,
        *,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        limit: int = 1000,
    ) -> Sequence[Candle]:
        """Fetch historical candles for a symbol and time range."""

        if not symbol.strip():
            raise ValueError("symbol is required")
        if not timeframe.strip():
            raise ValueError("timeframe is required")
        if start >= end:
            raise ValueError("start must be before end")
        if limit <= 0:
            raise ValueError("limit must be positive")

        return await self._exchange.fetch_ohlcv(
            symbol=symbol.upper(),
            timeframe=timeframe,
            start=start,
            end=end,
            limit=limit,
        )
