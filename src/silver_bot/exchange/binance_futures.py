"""Binance Futures adapter.

The adapter fetches public historical candles through ccxt and never places,
changes or cancels orders: ``place_order`` and ``cancel_order`` keep raising
``OrderPlacementDisabled``.

Credential rule: an API key and secret are attached to the ccxt client only when
the configured host is the Binance Futures testnet. Against any other host the
client is built without credentials, so only public endpoints are reachable and
a key can never be sent to a production or look-alike host.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Sequence
from urllib.parse import urlsplit

import ccxt
import ccxt.async_support as ccxt_async

from silver_bot.config import AppConfig
from silver_bot.config.settings import BINANCE_FUTURES_TESTNET_HOST, is_binance_futures_testnet_url
from silver_bot.data.csv_loader import timeframe_interval
from silver_bot.exchange.base import ExchangeAdapter
from silver_bot.models import Candle
from silver_bot.utils.logging import get_logger


BINANCE_FUTURES_PRODUCTION_BASE_URL = "https://fapi.binance.com"
BINANCE_FUTURES_TESTNET_BASE_URL = "https://testnet.binancefuture.com"

MAX_NETWORK_RETRIES = 3
_BACKOFF_BASE_SECONDS = 1.0

# Every REST endpoint group of the ccxt binanceusdm client (ccxt 4.5.x) and its path. When the
# client carries credentials, all of them are pointed at the testnet host so that no signed
# request, including one ccxt might make on its own, can reach another host.
_TESTNET_API_PATHS = {
    "fapiPublic": "/fapi/v1",
    "fapiPublicV2": "/fapi/v2",
    "fapiPublicV3": "/fapi/v3",
    "fapiPrivate": "/fapi/v1",
    "fapiPrivateV2": "/fapi/v2",
    "fapiPrivateV3": "/fapi/v3",
    "fapiData": "/futures/data",
    "public": "/api/v3",
    "private": "/api/v3",
    "v1": "/api/v1",
    "sapi": "/sapi/v1",
    "sapiV2": "/sapi/v2",
    "sapiV3": "/sapi/v3",
    "sapiV4": "/sapi/v4",
    "dapiPublic": "/dapi/v1",
    "dapiPrivate": "/dapi/v1",
    "dapiPrivateV2": "/dapi/v2",
    "dapiData": "/futures/data",
    "eapiPublic": "/eapi/v1",
    "eapiPrivate": "/eapi/v1",
    "papi": "/papi/v1",
    "papiV2": "/papi/v2",
}

_logger = get_logger(__name__)


async def _backoff_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


class BinanceFuturesAdapter(ExchangeAdapter):
    """Binance Futures adapter: public candle fetching only, no order placement."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_secret: str | None = None,
        testnet: bool = False,
        base_url: str | None = None,
        client_factory: Callable[[dict[str, Any]], Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.base_url = base_url or (
            BINANCE_FUTURES_TESTNET_BASE_URL if testnet else BINANCE_FUTURES_PRODUCTION_BASE_URL
        )
        if self.testnet and not is_binance_futures_testnet_url(self.base_url):
            raise ValueError("Demo/testnet mode requires the Binance Futures testnet endpoint")
        self._client_factory = client_factory or ccxt_async.binanceusdm
        self._clock = clock or (lambda: datetime.now(UTC))
        if (api_key or api_secret) and not self._credentials_allowed():
            _logger.warning(
                "API credentials were supplied for a non-testnet host; ignoring them. "
                "Credentials are only ever sent to %s.",
                BINANCE_FUTURES_TESTNET_HOST,
            )

    @classmethod
    def from_config(cls, config: AppConfig) -> "BinanceFuturesAdapter":
        """Build an adapter from validated application config."""

        return cls(
            api_key=config.api_key,
            api_secret=config.api_secret,
            testnet=config.binance_testnet,
            base_url=config.binance_base_url,
        )

    def _credentials_allowed(self) -> bool:
        return is_binance_futures_testnet_url(self.base_url)

    def _client_options(self) -> dict[str, Any]:
        """Build the ccxt client options; credentials and testnet URLs only for the testnet host."""

        options: dict[str, Any] = {"enableRateLimit": True}
        if self._credentials_allowed():
            if self.api_key:
                options["apiKey"] = self.api_key
            if self.api_secret:
                options["secret"] = self.api_secret
            # CD-10: do not rely on set_sandbox_mode; point every endpoint at the testnet host.
            base = BINANCE_FUTURES_TESTNET_BASE_URL
            options["urls"] = {
                "api": {name: f"{base}{path}" for name, path in _TESTNET_API_PATHS.items()}
            }
        return options

    def _build_client(self) -> Any:
        options = self._client_options()
        client = self._client_factory(options)
        if "apiKey" in options or "secret" in options:
            _require_testnet_only_urls(client)
        return client

    async def fetch_ohlcv(
        self,
        *,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        limit: int = 1000,
    ) -> Sequence[Candle]:
        """Fetch closed historical candles in ascending order for ``[start, end)``.

        Only public market data is requested. Candles that have not closed yet at
        fetch time are dropped so a forming candle can never leak into a backtest.
        """

        if start >= end:
            raise ValueError("start must be before end")
        if limit <= 0:
            raise ValueError("limit must be positive")
        ccxt_symbol = _to_ccxt_symbol(symbol)
        interval = timeframe_interval(timeframe)
        interval_ms = interval // timedelta(milliseconds=1)
        start_ms = _to_ms(start)
        end_ms = _to_ms(end)
        now_ms = _to_ms(self._clock())

        client = self._build_client()
        try:
            rows: dict[int, list[Any]] = {}
            since = start_ms
            while since < end_ms:
                page = await _fetch_page_with_retry(client, ccxt_symbol, timeframe, since, limit)
                if not page:
                    break
                newest = max(int(row[0]) for row in page)
                for row in page:
                    rows.setdefault(int(row[0]), row)
                next_since = newest + interval_ms
                if next_since <= since:
                    break
                since = next_since
        finally:
            await client.close()

        epoch = datetime(1970, 1, 1, tzinfo=UTC)
        candles: list[Candle] = []
        for open_ms in sorted(rows):
            if open_ms < start_ms or open_ms >= end_ms or open_ms + interval_ms > now_ms:
                continue
            _, open_, high, low, close, volume = rows[open_ms][:6]
            open_time = epoch + timedelta(milliseconds=open_ms)
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    open_time=open_time,
                    open=float(open_),
                    high=float(high),
                    low=float(low),
                    close=float(close),
                    volume=float(volume),
                    close_time=open_time + interval - timedelta(milliseconds=1),
                )
            )
        return candles


def _to_ms(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return (value - datetime(1970, 1, 1, tzinfo=UTC)) // timedelta(milliseconds=1)


def _to_ccxt_symbol(symbol: str) -> str:
    """Map ``BTCUSDT`` to the ccxt linear-swap symbol ``BTC/USDT:USDT``."""

    base, quote = symbol[:-4], symbol[-4:]
    if quote != "USDT" or not base.isalnum():
        raise ValueError(f"Only USDT-margined symbols such as BTCUSDT are supported, got {symbol!r}")
    return f"{base}/USDT:USDT"


async def _fetch_page_with_retry(
    client: Any, ccxt_symbol: str, timeframe: str, since: int, limit: int
) -> list[list[Any]]:
    attempt = 0
    while True:
        try:
            return await client.fetch_ohlcv(ccxt_symbol, timeframe, since=since, limit=limit)
        except ccxt.NetworkError:
            if attempt >= MAX_NETWORK_RETRIES:
                raise
            attempt += 1
            await _backoff_sleep(_BACKOFF_BASE_SECONDS * 2 ** (attempt - 1))


def _require_testnet_only_urls(client: Any) -> None:
    """Fail closed if a credentialed client could reach any host except the testnet."""

    api_urls = (getattr(client, "urls", None) or {}).get("api", {})
    for name, url in api_urls.items():
        if isinstance(url, str) and urlsplit(url).hostname != BINANCE_FUTURES_TESTNET_HOST:
            raise ValueError(f"Refusing to attach credentials: endpoint {name!r} is not the testnet host")
