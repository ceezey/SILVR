"""Live market data stream interfaces for paper trading."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from silver_bot.exchange import ExchangeAdapter
from silver_bot.models import Candle


class MarketDataStream(ABC):
    """Asynchronous candle stream interface."""

    @abstractmethod
    async def candles(self) -> AsyncIterator[Candle]:
        """Yield candles as they become available."""


@dataclass(frozen=True, slots=True)
class ReconnectPolicy:
    """Reconnect settings for stream wrappers."""

    max_reconnects: int = 3
    reconnect_delay_seconds: float = 0.0


class MockMarketDataStream(MarketDataStream):
    """Deterministic stream for tests and local dry runs."""

    def __init__(self, candles: Sequence[Candle], *, fail_after: int | None = None) -> None:
        self._candles = list(candles)
        self._fail_after = fail_after

    async def candles(self) -> AsyncIterator[Candle]:
        for index, candle in enumerate(self._candles):
            if self._fail_after is not None and index == self._fail_after:
                raise ConnectionError("mock stream failure")
            yield candle


class ReconnectingMarketDataStream(MarketDataStream):
    """Reconnects a stream factory after transient stream failures."""

    def __init__(
        self,
        stream_factory: Callable[[], MarketDataStream],
        *,
        policy: ReconnectPolicy | None = None,
    ) -> None:
        self._stream_factory = stream_factory
        self._policy = policy or ReconnectPolicy()

    async def candles(self) -> AsyncIterator[Candle]:
        attempts = 0
        while attempts <= self._policy.max_reconnects:
            try:
                async for candle in self._stream_factory().candles():
                    yield candle
                return
            except ConnectionError:
                attempts += 1
                if attempts > self._policy.max_reconnects:
                    raise
                if self._policy.reconnect_delay_seconds > 0:
                    await asyncio.sleep(self._policy.reconnect_delay_seconds)


class BinancePollingMarketDataStream(MarketDataStream):
    """Polling-based Binance Futures candle stream skeleton.

    The stream uses the exchange adapter's OHLCV fetch method. The current
    Binance adapter remains non-networked until an explicit market-data phase
    implements real fetching.
    """

    def __init__(
        self,
        exchange: ExchangeAdapter,
        *,
        symbol: str,
        timeframe: str,
        poll_interval_seconds: float = 60.0,
        limit: int = 2,
    ) -> None:
        self.exchange = exchange
        self.symbol = symbol
        self.timeframe = timeframe
        self.poll_interval_seconds = poll_interval_seconds
        self.limit = limit

    async def candles(self) -> AsyncIterator[Candle]:
        seen_open_times: set[datetime] = set()
        while True:
            end = datetime.now(timezone.utc)
            start = end - timedelta(minutes=max(self.limit, 2))
            fetched = await self.exchange.fetch_ohlcv(
                symbol=self.symbol,
                timeframe=self.timeframe,
                start=start,
                end=end,
                limit=self.limit,
            )
            for candle in fetched:
                if candle.open_time in seen_open_times:
                    continue
                seen_open_times.add(candle.open_time)
                yield candle
            await asyncio.sleep(self.poll_interval_seconds)
