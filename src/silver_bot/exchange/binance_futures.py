"""Binance Futures adapter.

Market data only; the adapter never places, changes or cancels orders:
``place_order`` and ``cancel_order`` keep raising ``OrderPlacementDisabled``.
The base URL must be exactly the production or testnet host.

- ``fetch_ohlcv`` (paper and demo polling) sends one unsigned GET to the public
  klines endpoint, never sends an API key and refuses redirects.
- ``fetch_ohlcv_history`` and ``fetch_funding_rates`` (backtest data download) use
  ccxt. Credential rule: an API key and secret are attached to the ccxt client only
  when the configured host is the Binance Futures testnet, with every endpoint pointed
  at that host. Against any other host the client is built without credentials, so
  only public endpoints are reachable and a key can never be sent to a production or
  look-alike host.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Sequence
from urllib.parse import urlencode, urlsplit

import ccxt
import ccxt.async_support as ccxt_async

from silver_bot.config import AppConfig
from silver_bot.config.settings import BINANCE_FUTURES_TESTNET_HOST, is_binance_futures_testnet_url
from silver_bot.data.csv_loader import parse_kline_row, timeframe_interval
from silver_bot.data.funding import FundingRate
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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects, so a request never leaves the validated host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirect)


def _urllib_get(url: str) -> bytes:
    """GET a URL with no credentials and return the body."""

    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with _OPENER.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read()


def is_binance_futures_production_url(url: str) -> bool:
    """Return true only for exactly https://fapi.binance.com (optional port 443)."""

    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and (parts.hostname or "").lower() == "fapi.binance.com"
        and parts.username is None
        and parts.password is None
        and port in (None, 443)
    )


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


async def _backoff_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


class BinanceFuturesAdapter(ExchangeAdapter):
    """Binance Futures adapter: public market data only, no order placement."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_secret: str | None = None,
        testnet: bool = False,
        base_url: str | None = None,
        http_get: Callable[[str], bytes] | None = None,
        client_factory: Callable[[dict[str, Any]], Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        # api_key/api_secret are accepted for config compatibility but never stored or sent:
        # every request here is public market data.
        self.testnet = testnet
        self.base_url = base_url or (
            BINANCE_FUTURES_TESTNET_BASE_URL if testnet else BINANCE_FUTURES_PRODUCTION_BASE_URL
        )
        if self.testnet and not is_binance_futures_testnet_url(self.base_url):
            raise ValueError("Demo/testnet mode requires the Binance Futures testnet endpoint")
        _require_binance_futures_host(self.base_url)
        self._http_get = http_get or _urllib_get
        self._client_factory = client_factory or ccxt_async.binanceusdm
        self._clock = clock or (lambda: datetime.now(UTC))

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
                "startTime": _to_ms(start),
                "endTime": _to_ms(end) - 1,
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

    def _client_options(self) -> dict[str, Any]:
        """Build the ccxt client options: never any credentials; testnet URLs only for the testnet host."""

        # fetchCurrencies off: public candles need no currency list (that call is signed sapi).
        options: dict[str, Any] = {"enableRateLimit": True, "options": {"fetchCurrencies": False}}
        if is_binance_futures_testnet_url(self.base_url):
            # CD-10: do not rely on set_sandbox_mode; point every endpoint at the testnet host.
            base = BINANCE_FUTURES_TESTNET_BASE_URL
            options["urls"] = {
                "api": {name: f"{base}{path}" for name, path in _TESTNET_API_PATHS.items()}
            }
        return options

    def _build_client(self) -> Any:
        _require_binance_futures_host(self.base_url)
        options = self._client_options()
        client = self._client_factory(options)
        if "urls" in options:
            _require_testnet_only_urls(client)
        return client

    async def fetch_ohlcv_history(
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

    async def fetch_funding_rates(
        self, *, symbol: str, start: datetime, end: datetime, limit: int = 1000
    ) -> list[FundingRate]:
        """Fetch public funding-rate history in ascending order for ``[start, end)``."""

        if start >= end:
            raise ValueError("start must be before end")
        if limit <= 0:
            raise ValueError("limit must be positive")
        ccxt_symbol = _to_ccxt_symbol(symbol)
        start_ms = _to_ms(start)
        end_ms = _to_ms(end)

        client = self._build_client()
        try:
            rows: dict[int, float] = {}
            since = start_ms
            while since < end_ms:
                page = await _fetch_funding_page_with_retry(client, ccxt_symbol, since, limit)
                if not page:
                    break
                newest = max(int(row["timestamp"]) for row in page)
                for row in page:
                    rows.setdefault(int(row["timestamp"]), float(row["fundingRate"]))
                if newest + 1 <= since:
                    break
                since = newest + 1
        finally:
            await client.close()

        epoch = datetime(1970, 1, 1, tzinfo=UTC)
        return [
            FundingRate(epoch + timedelta(milliseconds=ts), rows[ts])
            for ts in sorted(rows)
            if start_ms <= ts < end_ms
        ]


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


async def _fetch_funding_page_with_retry(
    client: Any, ccxt_symbol: str, since: int, limit: int
) -> list[dict[str, Any]]:
    attempt = 0
    while True:
        try:
            return await client.fetch_funding_rate_history(ccxt_symbol, since=since, limit=limit)
        except ccxt.NetworkError:
            if attempt >= MAX_NETWORK_RETRIES:
                raise
            attempt += 1
            await _backoff_sleep(_BACKOFF_BASE_SECONDS * 2 ** (attempt - 1))


def _require_testnet_only_urls(client: Any) -> None:
    """Fail closed if a testnet-pinned client could reach any host except the testnet."""

    api_urls = (getattr(client, "urls", None) or {}).get("api", {})
    for name, url in api_urls.items():
        if isinstance(url, str) and urlsplit(url).hostname != BINANCE_FUTURES_TESTNET_HOST:
            raise ValueError(f"Refusing client: endpoint {name!r} is not the testnet host")


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


def _require_binance_futures_host(base_url: str) -> None:
    if not (is_binance_futures_testnet_url(base_url) or is_binance_futures_production_url(base_url)):
        raise ValueError("Binance Futures base URL must be the production or testnet endpoint")
