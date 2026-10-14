"""Live market data stream interfaces for paper trading."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from silver_bot.data.csv_loader import timeframe_interval
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
                    attempts = 0  # a delivered candle means the connection recovered
                    yield candle
                return
            except ConnectionError:
                attempts += 1
                if attempts > self._policy.max_reconnects:
                    raise
                if self._policy.reconnect_delay_seconds > 0:
                    await asyncio.sleep(self._policy.reconnect_delay_seconds)


class BinancePollingMarketDataStream(MarketDataStream):
    """Poll the exchange klines endpoint and yield each closed candle once.

    Only candles whose `close_time` has passed are yielded (a forming candle is
    never used), in time order. The last yielded open time lives on the
    instance, so a reconnecting wrapper that reuses this instance resumes after
    it instead of replaying, and catches up on candles missed while down.
    """

    def __init__(
        self,
        exchange: ExchangeAdapter,
        *,
        symbol: str,
        timeframe: str,
        poll_interval_seconds: float = 10.0,
        limit: int = 1000,
        after: datetime | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.exchange = exchange
        self.symbol = symbol
        self.timeframe = timeframe
        self.interval = timeframe_interval(timeframe)
        self.poll_interval_seconds = poll_interval_seconds
        self.limit = limit
        self.after = after
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def candles(self) -> AsyncIterator[Candle]:
        while True:
            end = self._clock()
            start = self.after + self.interval if self.after is not None else end - self.interval * self.limit
            if start < end:
                fetched = await self.exchange.fetch_ohlcv(
                    symbol=self.symbol,
                    timeframe=self.timeframe,
                    start=start,
                    end=end,
                    limit=self.limit,
                )
                for candle in sorted(fetched, key=lambda item: item.open_time):
                    if candle.close_time is None or candle.close_time > end:
                        continue
                    if self.after is not None and candle.open_time <= self.after:
                        continue
                    self.after = candle.open_time
                    yield candle
            await asyncio.sleep(self.poll_interval_seconds)
