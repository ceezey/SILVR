import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from silver_bot.config import load_config
from silver_bot.exchange import BinanceFuturesAdapter, OrderPlacementDisabled, OrderRequest
from silver_bot.exchange.binance_futures import BINANCE_FUTURES_TESTNET_BASE_URL
from silver_bot.models import TradeSide


def test_binance_adapter_rejects_real_order_placement() -> None:
    adapter = BinanceFuturesAdapter()
    request = OrderRequest(
        symbol="BTCUSDT",
        side=TradeSide.BUY,
        quantity=Decimal("0.01"),
        stop_loss=Decimal("65000"),
        take_profit=Decimal("67000"),
    )

    with pytest.raises(OrderPlacementDisabled):
        asyncio.run(adapter.place_order(request))


def test_binance_adapter_rejects_real_order_cancellation() -> None:
    adapter = BinanceFuturesAdapter()

    with pytest.raises(OrderPlacementDisabled):
        asyncio.run(adapter.cancel_order(symbol="BTCUSDT", order_id="unsafe-live-order"))


def test_binance_ohlcv_skeleton_validates_date_range_before_network_work() -> None:
    adapter = BinanceFuturesAdapter()
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)

    with pytest.raises(ValueError, match="start must be before end"):
        asyncio.run(
            adapter.fetch_ohlcv(
                symbol="BTCUSDT",
                timeframe="1m",
                start=timestamp,
                end=timestamp,
            )
        )


def test_binance_adapter_uses_testnet_url_in_demo_mode(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "MODE=demo",
                "DEMO_TRADING=true",
                "BINANCE_TESTNET=true",
                "LIVE_TRADING=false",
                "PAPER_TRADING=false",
                "BINANCE_API_KEY=testnet-key",
                "BINANCE_API_SECRET=testnet-secret",
                "RISK_ENGINE_ENABLED=true",
                "KILL_SWITCH_ENABLED=true",
                "KILL_SWITCH_PATH=KILL_SWITCH",
                "STOP_LOSS_REQUIRED=true",
                "MAX_RISK_PER_TRADE=0.005",
                "MAX_DAILY_LOSS=0.02",
                "MAX_LEVERAGE=3",
            ]
        ),
        encoding="utf-8",
    )
    config = load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})

    adapter = BinanceFuturesAdapter.from_config(config)

    assert adapter.testnet is True
    assert adapter.base_url == BINANCE_FUTURES_TESTNET_BASE_URL


def test_binance_adapter_rejects_production_url_for_testnet_mode() -> None:
    with pytest.raises(ValueError, match="testnet endpoint"):
        BinanceFuturesAdapter(testnet=True, base_url="https://fapi.binance.com")


from silver_bot.exchange import is_binance_futures_testnet_url


@pytest.mark.parametrize(
    "url",
    [
        "https://testnet.binancefuture.com",
        "https://testnet.binancefuture.com/fapi",
        "HTTPS://TESTNET.BINANCEFUTURE.COM",
        "https://testnet.binancefuture.com:443",
        "  https://testnet.binancefuture.com  ",
    ],
)
def test_testnet_url_accepts_exact_host(url: str) -> None:
    assert is_binance_futures_testnet_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://testnet.binancefuture.com.evil.com",
        "https://evil.com/?x=testnet.binancefuture.com",
        "https://user@testnet.binancefuture.com",
        "http://testnet.binancefuture.com",
        "https://fapi.binance.com",
        "https://testnet.binancefuture.com:8443",
        "https://testnet.binancefuture.com.",
        "https://testnet.binancefuture.com:notaport",
        "testnet.binancefuture.com",
        "",
    ],
)
def test_testnet_url_rejects_lookalikes(url: str) -> None:
    assert is_binance_futures_testnet_url(url) is False


def test_adapter_rejects_lookalike_testnet_host() -> None:
    with pytest.raises(ValueError, match="testnet endpoint"):
        BinanceFuturesAdapter(testnet=True, base_url="https://testnet.binancefuture.com.evil.com")


# --- fetch_ohlcv_history (ccxt-backed, public candles only) -----------------------------------------

from datetime import timedelta
from urllib.parse import urlsplit

import ccxt

from silver_bot.exchange import binance_futures as bf

_MINUTE_MS = 60_000
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_T0_MS = int(_T0.timestamp() * 1000)


def _row(index: int) -> list[float]:
    price = 100.0 + index
    return [_T0_MS + index * _MINUTE_MS, price, price + 1, price - 1, price + 0.5, 10.0]


class FakeClient:
    """Records options and serves pages; never touches the network."""

    def __init__(self, options, pages=None, failures=None) -> None:
        self.options = options
        self.pages = list(pages or [])
        self.failures = list(failures or [])
        self.calls: list[tuple] = []
        self.closed = False

    async def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
        self.calls.append((symbol, timeframe, since, limit))
        if self.failures:
            raise self.failures.pop(0)
        return self.pages.pop(0) if self.pages else []

    async def fetch_funding_rate_history(self, symbol, since=None, limit=None):
        self.calls.append((symbol, since, limit))
        if self.failures:
            raise self.failures.pop(0)
        return self.pages.pop(0) if self.pages else []

    async def close(self) -> None:
        self.closed = True


def _adapter(pages=None, failures=None, now=None, **kwargs):
    holder: dict = {}

    def factory(options):
        holder["client"] = FakeClient(options, pages, failures)
        return holder["client"]

    adapter = BinanceFuturesAdapter(
        client_factory=factory,
        clock=lambda: now or _T0 + timedelta(days=30),
        **kwargs,
    )
    return adapter, holder


def _fetch(adapter, *, start=_T0, end=_T0 + timedelta(days=10), limit=1500, symbol="BTCUSDT"):
    return asyncio.run(
        adapter.fetch_ohlcv_history(symbol=symbol, timeframe="1m", start=start, end=end, limit=limit)
    )


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    async def instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(bf, "_backoff_sleep", instant, raising=False)


def test_fetch_pages_until_end() -> None:
    pages = [
        [_row(i) for i in range(0, 1500)],
        [_row(i) for i in range(1500, 3000)],
        [_row(i) for i in range(3000, 3200)],
    ]
    end = _T0 + timedelta(minutes=3200)
    adapter, holder = _adapter(pages)

    candles = _fetch(adapter, end=end)

    assert len(candles) == 3200
    assert candles[0].open_time == _T0
    assert all(a.open_time < b.open_time for a, b in zip(candles, candles[1:]))
    assert all(c.open_time < end for c in candles)
    client = holder["client"]
    assert {c[0] for c in client.calls} == {"BTC/USDT:USDT"}
    assert client.calls[0][1:] == ("1m", _T0_MS, 1500)
    assert client.calls[1][2] == _T0_MS + 1500 * _MINUTE_MS
    assert client.closed is True


def test_fetch_drops_rows_at_or_after_end() -> None:
    adapter, _ = _adapter([[_row(i) for i in range(0, 10)]])

    candles = _fetch(adapter, end=_T0 + timedelta(minutes=5))

    assert [c.open_time for c in candles] == [_T0 + timedelta(minutes=i) for i in range(5)]


def test_fetch_drops_duplicates_and_forming_candle() -> None:
    pages = [
        [_row(i) for i in range(0, 5)],
        [_row(i) for i in range(4, 10)],  # overlaps at the page edge
    ]
    # Candle 9 closes at minute 10; at minute 9.5 it is still forming.
    now = _T0 + timedelta(minutes=9, seconds=30)
    adapter, _ = _adapter(pages, now=now)

    candles = _fetch(adapter, limit=5)

    assert [c.open_time for c in candles] == [_T0 + timedelta(minutes=i) for i in range(9)]


def test_candle_closing_exactly_now_is_kept() -> None:
    adapter, _ = _adapter([[_row(i) for i in range(0, 3)]], now=_T0 + timedelta(minutes=3))

    assert len(_fetch(adapter)) == 3


def test_close_time_matches_loader_convention() -> None:
    adapter, _ = _adapter([[_row(0), _row(1)]])

    candles = _fetch(adapter)

    for candle in candles:
        assert candle.close_time == candle.open_time + timedelta(minutes=1) - timedelta(milliseconds=1)
    assert candles[0].symbol == "BTCUSDT"
    assert candles[0].timeframe == "1m"
    assert candles[0].open_time.tzinfo is not None


def test_no_credentials_for_production_host() -> None:
    adapter, holder = _adapter([[_row(0)]], api_key="k", api_secret="s")

    _fetch(adapter)

    options = holder["client"].options
    assert options["enableRateLimit"] is True
    assert "apiKey" not in options
    assert "secret" not in options
    assert "urls" not in options


def test_credentials_ignored_with_warning_for_non_testnet_host(caplog) -> None:
    with caplog.at_level("WARNING"):
        adapter, holder = _adapter([[_row(0)]], api_key="k", api_secret="s")
    _fetch(adapter)

    assert any("credentials" in r.getMessage().lower() for r in caplog.records)
    assert "apiKey" not in holder["client"].options


def test_credentials_and_testnet_urls_for_testnet() -> None:
    adapter, holder = _adapter(
        [[_row(0)]],
        api_key="k",
        api_secret="s",
        testnet=True,
        base_url=BINANCE_FUTURES_TESTNET_BASE_URL,
    )

    _fetch(adapter)

    options = holder["client"].options
    assert options["apiKey"] == "k"
    assert options["secret"] == "s"
    api_urls = options["urls"]["api"]
    assert api_urls
    assert {urlsplit(url).hostname for url in api_urls.values()} == {"testnet.binancefuture.com"}


def test_testnet_host_without_testnet_flag_still_overrides_urls() -> None:
    # Credentials are attached whenever the host is the testnet, so URLs must follow.
    adapter, holder = _adapter(
        [[_row(0)]], api_key="k", api_secret="s", base_url=BINANCE_FUTURES_TESTNET_BASE_URL
    )

    _fetch(adapter)

    options = holder["client"].options
    assert options["apiKey"] == "k"
    assert {urlsplit(u).hostname for u in options["urls"]["api"].values()} == {
        "testnet.binancefuture.com"
    }


def test_real_ccxt_client_has_only_testnet_urls_when_credentialed() -> None:
    adapter = BinanceFuturesAdapter(
        api_key="k", api_secret="s", testnet=True, base_url=BINANCE_FUTURES_TESTNET_BASE_URL
    )

    client = adapter._build_client()
    try:
        hosts = {urlsplit(url).hostname for url in client.urls["api"].values()}
        assert client.apiKey == "k"
    finally:
        asyncio.run(client.close())

    assert hosts == {"testnet.binancefuture.com"}


def test_real_ccxt_client_has_no_credentials_by_default() -> None:
    adapter = BinanceFuturesAdapter(api_key="k", api_secret="s")

    client = adapter._build_client()
    try:
        assert not client.apiKey
        assert not client.secret
        assert client.enableRateLimit is True
    finally:
        asyncio.run(client.close())


def test_network_error_retried_then_raised() -> None:
    adapter, holder = _adapter(failures=[ccxt.NetworkError("boom")] * 4)

    with pytest.raises(ccxt.NetworkError):
        _fetch(adapter)

    assert len(holder["client"].calls) == 4
    assert holder["client"].closed is True


def test_network_error_retried_then_succeeds() -> None:
    adapter, holder = _adapter(
        [[_row(0), _row(1)]], failures=[ccxt.RequestTimeout("t"), ccxt.NetworkError("n")]
    )

    candles = _fetch(adapter)

    assert len(candles) == 2
    assert len(holder["client"].calls) >= 3


def test_client_closed_on_error() -> None:
    adapter, holder = _adapter(failures=[ValueError("bad")])

    with pytest.raises(ValueError):
        _fetch(adapter)

    assert holder["client"].closed is True
    assert len(holder["client"].calls) == 1


@pytest.mark.parametrize("symbol", ["BTCUSD", "BTCBUSD", "USDT", "BTC/USDT", ""])
def test_non_usdt_symbol_rejected(symbol: str) -> None:
    adapter, holder = _adapter()

    with pytest.raises(ValueError, match="USDT"):
        _fetch(adapter, symbol=symbol)

    assert "client" not in holder


def test_fetch_validates_range_and_limit_before_building_client() -> None:
    adapter, holder = _adapter()

    with pytest.raises(ValueError, match="start must be before end"):
        _fetch(adapter, start=_T0, end=_T0)
    with pytest.raises(ValueError, match="limit must be positive"):
        _fetch(adapter, limit=0)

    assert "client" not in holder


def test_order_methods_still_disabled_with_injected_client() -> None:
    adapter, holder = _adapter()

    with pytest.raises(OrderPlacementDisabled):
        asyncio.run(adapter.cancel_order(symbol="BTCUSDT", order_id="x"))

    assert "client" not in holder


@pytest.mark.parametrize("credentialed", [True, False])
def test_real_ccxt_client_does_not_fetch_currencies(credentialed: bool) -> None:
    # ccxt load_markets would otherwise send a signed sapi request (unsupported on the testnet).
    kwargs = (
        {"api_key": "k", "api_secret": "s", "testnet": True, "base_url": BINANCE_FUTURES_TESTNET_BASE_URL}
        if credentialed
        else {}
    )
    client = BinanceFuturesAdapter(**kwargs)._build_client()
    try:
        assert client.options["fetchCurrencies"] is False
        assert len(client.options) > 1  # ccxt default options were merged, not replaced
    finally:
        asyncio.run(client.close())


# --- fetch_funding_rates (public funding history) -------------------------------------------------

_FUNDING_MS = 8 * 3600 * 1000


def _funding_row(index: int, offset_ms: int = 7) -> dict:
    return {"timestamp": _T0_MS + index * _FUNDING_MS + offset_ms, "fundingRate": 0.0001 * index}


def _fetch_funding(adapter, *, start=_T0, end=_T0 + timedelta(days=10), symbol="BTCUSDT", **kwargs):
    return asyncio.run(adapter.fetch_funding_rates(symbol=symbol, start=start, end=end, **kwargs))


def test_fetch_funding_pages_and_bounds() -> None:
    pages = [
        [_funding_row(i) for i in range(0, 3)],
        [_funding_row(i) for i in range(2, 5)],  # overlaps at the page edge
        [_funding_row(i) for i in range(5, 6)],
    ]
    # Row 0 is before start; rows 4 and 5 are at or after end (row 4 is 32h + 7ms, end is 32h).
    start = _T0 + timedelta(milliseconds=8)
    end = _T0 + timedelta(hours=32)
    adapter, holder = _adapter(pages)

    rates = _fetch_funding(adapter, start=start, end=end, limit=3)

    assert [r.time for r in rates] == [
        _T0 + timedelta(hours=8, milliseconds=7),
        _T0 + timedelta(hours=16, milliseconds=7),
        _T0 + timedelta(hours=24, milliseconds=7),
    ]
    assert [r.rate for r in rates] == pytest.approx([0.0001, 0.0002, 0.0003])
    client = holder["client"]
    assert client.calls[0] == ("BTC/USDT:USDT", _T0_MS + 8, 3)
    assert client.calls[1][1] == _T0_MS + 2 * _FUNDING_MS + 7 + 1
    assert client.closed is True


def test_funding_uses_no_credentials_for_production() -> None:
    adapter, holder = _adapter([[_funding_row(0)]], api_key="k", api_secret="s")

    _fetch_funding(adapter)

    options = holder["client"].options
    assert "apiKey" not in options and "secret" not in options and "urls" not in options


def test_funding_network_error_retried_then_raised_and_client_closed() -> None:
    adapter, holder = _adapter(failures=[ccxt.NetworkError("boom")] * 4)

    with pytest.raises(ccxt.NetworkError):
        _fetch_funding(adapter)

    assert len(holder["client"].calls) == 4
    assert holder["client"].closed is True


def test_funding_validates_range_limit_and_symbol_before_building_client() -> None:
    adapter, holder = _adapter()

    with pytest.raises(ValueError, match="start must be before end"):
        _fetch_funding(adapter, start=_T0, end=_T0)
    with pytest.raises(ValueError, match="limit"):
        _fetch_funding(adapter, limit=0)
    with pytest.raises(ValueError, match="USDT"):
        _fetch_funding(adapter, symbol="BTCUSD")
    assert "client" not in holder


def test_ccxt_paths_refuse_a_host_changed_after_construction() -> None:
    adapter, holder = _adapter()
    adapter.base_url = "https://fapi.binance.com.evil.com"

    with pytest.raises(ValueError, match="production or testnet"):
        _fetch_funding(adapter)
    with pytest.raises(ValueError, match="production or testnet"):
        _fetch(adapter)
    assert "client" not in holder
