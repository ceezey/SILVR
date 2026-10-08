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
