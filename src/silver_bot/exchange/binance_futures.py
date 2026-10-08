"""Binance Futures adapter skeleton.

This adapter defines the boundary for future Binance Futures integration. It
does not place orders or make network calls in Phase 1.
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from silver_bot.config import AppConfig
from silver_bot.exchange.base import ExchangeAdapter
from silver_bot.models import Candle


BINANCE_FUTURES_PRODUCTION_BASE_URL = "https://fapi.binance.com"
BINANCE_FUTURES_TESTNET_BASE_URL = "https://testnet.binancefuture.com"


class BinanceFuturesAdapter(ExchangeAdapter):
    """Safe Binance Futures adapter skeleton."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_secret: str | None = None,
        testnet: bool = False,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.base_url = base_url or (
            BINANCE_FUTURES_TESTNET_BASE_URL if testnet else BINANCE_FUTURES_PRODUCTION_BASE_URL
        )
        if self.testnet and not is_binance_futures_testnet_url(self.base_url):
            raise ValueError("Demo/testnet mode requires the Binance Futures testnet endpoint")

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
        """Fetch historical OHLCV candles.

        Network-backed fetching will be implemented after the safe scaffold and
        test harness are in place.
        """

        if start >= end:
            raise ValueError("start must be before end")
        if limit <= 0:
            raise ValueError("limit must be positive")
        raise NotImplementedError("Binance Futures OHLCV network fetching is not implemented in Phase 1")


def is_binance_futures_testnet_url(value: str) -> bool:
    """Return whether a URL points at the Binance Futures testnet host."""

    normalized = value.strip().lower()
    return "testnet.binancefuture.com" in normalized
