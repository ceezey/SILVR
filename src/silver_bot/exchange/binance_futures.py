"""Binance Futures adapter.

Market data only: `fetch_ohlcv` reads the public klines endpoint, which needs
no API key, and no key is ever sent. Order placement and cancellation stay
disabled (the base class raises `OrderPlacementDisabled`).
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime
from typing import Sequence
from urllib.parse import urlencode

from silver_bot.config import AppConfig
from silver_bot.config.settings import is_binance_futures_testnet_url
from silver_bot.data.csv_loader import parse_kline_row, timeframe_interval
from silver_bot.exchange.base import ExchangeAdapter
from silver_bot.models import Candle


BINANCE_FUTURES_PRODUCTION_BASE_URL = "https://fapi.binance.com"
BINANCE_FUTURES_TESTNET_BASE_URL = "https://testnet.binancefuture.com"
KLINES_PATH = "/fapi/v1/klines"
MAX_KLINES_LIMIT = 1500
REQUEST_TIMEOUT_SECONDS = 10.0
# Binance kline intervals; anything else is rejected before a request is made.
BINANCE_INTERVALS = frozenset(
    {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w"}
)


def _urllib_get(url: str) -> bytes:
    """GET a URL with no credentials and return the body."""

    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read()


class BinanceFuturesAdapter(ExchangeAdapter):
    """Safe Binance Futures adapter skeleton."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_secret: str | None = None,
        testnet: bool = False,
        base_url: str | None = None,
        http_get: Callable[[str], bytes] | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.base_url = base_url or (
            BINANCE_FUTURES_TESTNET_BASE_URL if testnet else BINANCE_FUTURES_PRODUCTION_BASE_URL
        )
        if self.testnet and not is_binance_futures_testnet_url(self.base_url):
            raise ValueError("Demo/testnet mode requires the Binance Futures testnet endpoint")
        self._http_get = http_get or _urllib_get

    @classmethod
    def from_config(cls, config: AppConfig) -> "BinanceFuturesAdapter":
        """Build an adapter from validated application config."""

        return cls(
            api_key=config.api_key,
            api_secret=config.api_secret,
            testnet=config.binance_testnet,
            base_url=config.binance_base_url,
        )

    async def fetch_ohlcv(
        self,
        *,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        limit: int = 1000,
    ) -> Sequence[Candle]:
        """Fetch candles opening in [start, end) from the public klines endpoint.

        Transport failures and HTTP 429 or 5xx raise `ConnectionError` so a
        reconnecting stream can retry; other HTTP errors and malformed rows
        raise `ValueError`. The newest candle may still be forming; callers
        that need closed candles filter on `close_time`.
        """

        if start >= end:
            raise ValueError("start must be before end")
        if limit <= 0:
            raise ValueError("limit must be positive")
        if timeframe not in BINANCE_INTERVALS:
            raise ValueError(f"Unsupported Binance interval: {timeframe!r}")
        query = urlencode(
            {
                "symbol": symbol,
                "interval": timeframe,
                "startTime": int(start.timestamp() * 1000),
                "endTime": int(end.timestamp() * 1000) - 1,
                "limit": min(limit, MAX_KLINES_LIMIT),
            }
        )
        url = f"{self.base_url.rstrip('/')}{KLINES_PATH}?{query}"
        try:
            body = await asyncio.to_thread(self._http_get, url)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 or exc.code >= 500:
                raise ConnectionError(f"Binance klines HTTP {exc.code}") from exc
            raise ValueError(f"Binance klines request rejected: HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ConnectionError(f"Binance klines request failed: {exc}") from exc
        return _parse_klines(body, symbol=symbol, timeframe=timeframe)


def _parse_klines(body: bytes, *, symbol: str, timeframe: str) -> list[Candle]:
    try:
        rows = json.loads(body)
    except ValueError as exc:
        raise ValueError("Binance klines response is not JSON") from exc
    if not isinstance(rows, list):
        raise ValueError("Binance klines response is not a list")
    interval = timeframe_interval(timeframe)
    candles = []
    for index, row in enumerate(rows):
        if not isinstance(row, list):
            raise ValueError(f"Binance kline {index} is not a list")
        candle = parse_kline_row([str(cell) for cell in row], where=f"kline {index}", symbol=symbol, timeframe=timeframe)
        if candle.close_time - candle.open_time != interval:
            raise ValueError(f"Binance kline {index} does not span one {timeframe} interval")
        candles.append(candle)
    return sorted(candles, key=lambda candle: candle.open_time)
