import asyncio
import io
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from silver_bot.data import BinancePollingMarketDataStream, MarketDataStream, ReconnectPolicy, ReconnectingMarketDataStream
from silver_bot.exchange import BinanceFuturesAdapter
from silver_bot.models import Candle

T0 = datetime(2026, 1, 2, 15, 0, tzinfo=UTC)


def kline(minute: int, close: str = "100") -> list:
    open_ms = int((T0 + timedelta(minutes=minute)).timestamp() * 1000)
    return [open_ms, "100", "101", "99", close, "5", open_ms + 59_999, "0", 0, "0", "0", "0"]


def adapter_returning(*bodies, urls: list | None = None) -> BinanceFuturesAdapter:
    queue = list(bodies)

    def http_get(url: str) -> bytes:
        if urls is not None:
            urls.append(url)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return json.dumps(item).encode()

    return BinanceFuturesAdapter(http_get=http_get)


def fetch(adapter: BinanceFuturesAdapter, timeframe: str = "1m") -> list[Candle]:
    return list(
        asyncio.run(
            adapter.fetch_ohlcv(symbol="BTCUSDT", timeframe=timeframe, start=T0, end=T0 + timedelta(minutes=5), limit=5)
        )
    )


def test_fetch_ohlcv_parses_klines_into_sorted_candles() -> None:
    urls: list[str] = []
    candles = fetch(adapter_returning([kline(1, "101"), kline(0)], urls=urls))

    assert [candle.open_time for candle in candles] == [T0, T0 + timedelta(minutes=1)]
    assert candles[1].close == 101
    assert candles[0].close_time == T0 + timedelta(minutes=1)
    query = parse_qs(urlsplit(urls[0]).query)
    assert urlsplit(urls[0]).path == "/fapi/v1/klines"
    assert query["symbol"] == ["BTCUSDT"]
    assert query["interval"] == ["1m"]
    assert query["startTime"] == [str(int(T0.timestamp() * 1000))]
    assert query["limit"] == ["5"]


def test_fetch_ohlcv_never_sends_api_credentials() -> None:
    urls: list[str] = []

    def http_get(url: str) -> bytes:
        urls.append(url)
        return b"[]"

    adapter = BinanceFuturesAdapter(api_key="key-value", api_secret="secret-value", http_get=http_get)
    asyncio.run(adapter.fetch_ohlcv(symbol="BTCUSDT", timeframe="1m", start=T0, end=T0 + timedelta(minutes=1)))

    assert "key-value" not in urls[0] and "secret-value" not in urls[0]
    assert "signature" not in urls[0]


def test_fetch_ohlcv_rejects_unknown_interval_before_any_request() -> None:
    with pytest.raises(ValueError, match="Unsupported Binance interval"):
        fetch(adapter_returning(), timeframe="7m")


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError("no route"),
        TimeoutError("slow"),
        urllib.error.HTTPError("u", 503, "down", {}, io.BytesIO()),
        urllib.error.HTTPError("u", 429, "slow down", {}, io.BytesIO()),
    ],
)
def test_transient_failures_raise_connection_error(error: Exception) -> None:
    with pytest.raises(ConnectionError):
        fetch(adapter_returning(error))


def test_client_error_raises_value_error() -> None:
    with pytest.raises(ValueError, match="HTTP 400"):
        fetch(adapter_returning(urllib.error.HTTPError("u", 400, "bad", {}, io.BytesIO())))


@pytest.mark.parametrize("body", [{"code": -1121}, ["not a row"], [kline(0)[:3]]])
def test_malformed_response_raises_value_error(body) -> None:
    with pytest.raises(ValueError):
        fetch(adapter_returning(body))


def test_wrong_interval_kline_is_rejected() -> None:
    with pytest.raises(ValueError, match="does not span"):
        fetch(adapter_returning([kline(0)]), timeframe="5m")


class FakeExchange:
    """Serves candles from a list, by requested range, and records requests."""

    def __init__(self, candles: list[Candle]) -> None:
        self.candles = candles
        self.requests: list[tuple[datetime, datetime]] = []

    async def fetch_ohlcv(self, *, symbol, timeframe, start, end, limit=1000):
        self.requests.append((start, end))
        return [candle for candle in self.candles if start <= candle.open_time < end][:limit]


def candle(minute: int) -> Candle:
    opened = T0 + timedelta(minutes=minute)
    return Candle("BTCUSDT", "1m", opened, 100, 101, 99, 100, 5, close_time=opened + timedelta(minutes=1))


async def take(stream: MarketDataStream, count: int) -> list[Candle]:
    output = []
    async for item in stream.candles():
        output.append(item)
        if len(output) == count:
            break
    return output


def test_polling_stream_yields_only_closed_candles_once_in_order() -> None:
    clock = {"now": T0 + timedelta(minutes=3, seconds=30)}
    exchange = FakeExchange([candle(minute) for minute in range(6)])
    stream = BinancePollingMarketDataStream(
        exchange,
        symbol="BTCUSDT",
        timeframe="1m",
        poll_interval_seconds=0,
        after=T0,
        clock=lambda: clock["now"],
    )

    first = asyncio.run(take(stream, 2))
    clock["now"] = T0 + timedelta(minutes=5, seconds=1)
    second = asyncio.run(take(stream, 2))

    # Minute 3 is still forming at 3m30s, so the first poll stops at minute 2.
    assert [item.open_time for item in first] == [T0 + timedelta(minutes=1), T0 + timedelta(minutes=2)]
    assert [item.open_time for item in second] == [T0 + timedelta(minutes=3), T0 + timedelta(minutes=4)]
    assert exchange.requests[-1][0] == T0 + timedelta(minutes=3)


def test_polling_stream_without_history_starts_from_the_recent_window() -> None:
    now = T0 + timedelta(minutes=4, seconds=10)
    exchange = FakeExchange([candle(minute) for minute in range(6)])
    stream = BinancePollingMarketDataStream(
        exchange, symbol="BTCUSDT", timeframe="1m", poll_interval_seconds=0, limit=2, clock=lambda: now
    )

    items = asyncio.run(take(stream, 1))

    assert exchange.requests[0][0] == now - timedelta(minutes=2)
    assert items[0].open_time == T0 + timedelta(minutes=3)


class FlakyStream(MarketDataStream):
    """Yields one new candle per connection, then drops the connection."""

    def __init__(self) -> None:
        self.minute = 0

    async def candles(self):
        yield candle(self.minute)
        self.minute += 1
        raise ConnectionError("drop")


def test_reconnect_budget_resets_after_a_delivered_candle() -> None:
    flaky = FlakyStream()
    stream = ReconnectingMarketDataStream(lambda: flaky, policy=ReconnectPolicy(max_reconnects=1))

    items = asyncio.run(take(stream, 4))

    # Four drops with a budget of one reconnect: each delivered candle refills the budget.
    assert [item.open_time for item in items] == [T0 + timedelta(minutes=minute) for minute in range(4)]


class DeadStream(MarketDataStream):
    async def candles(self):
        raise ConnectionError("down")
        yield  # pragma: no cover


def test_reconnect_gives_up_when_nothing_is_delivered() -> None:
    stream = ReconnectingMarketDataStream(DeadStream, policy=ReconnectPolicy(max_reconnects=2))

    with pytest.raises(ConnectionError):
        asyncio.run(take(stream, 1))


@pytest.mark.parametrize(
    "url",
    ["https://evil.example", "http://fapi.binance.com", "https://fapi.binance.com.evil.com", "https://user@fapi.binance.com"],
)
def test_adapter_rejects_hosts_other_than_binance_futures(url: str) -> None:
    with pytest.raises(ValueError, match="production or testnet endpoint"):
        BinanceFuturesAdapter(base_url=url)


def test_adapter_accepts_production_and_testnet_hosts() -> None:
    assert BinanceFuturesAdapter(base_url="https://fapi.binance.com:443").base_url
    assert BinanceFuturesAdapter(base_url="https://testnet.binancefuture.com").base_url


def test_redirects_are_refused() -> None:
    from silver_bot.exchange.binance_futures import _NoRedirect

    request = urllib.request.Request("https://fapi.binance.com/fapi/v1/klines")
    with pytest.raises(urllib.error.HTTPError, match="redirect refused"):
        _NoRedirect().redirect_request(request, None, 302, "Found", {}, "https://elsewhere.example/")
