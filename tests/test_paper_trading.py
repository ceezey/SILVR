import json
import asyncio
from datetime import UTC, datetime, timedelta

from silver_bot.data import MockMarketDataStream, ReconnectPolicy, ReconnectingMarketDataStream
from silver_bot.execution import PaperEventType, PaperTradingEngine
from silver_bot.models import Candle
from silver_bot.monitoring import (
    InMemoryTelegramClient,
    TelegramAlertConfig,
    TelegramAlerter,
)
from silver_bot.monitoring.reports import build_daily_paper_report
from silver_bot.risk import RiskConfig, RiskManagementEngine
from silver_bot.storage import PostgresStorage
from silver_bot.strategy import SilverBulletStrategyConfig, SilverBulletStrategyEngine


def candle(index: int, open_: float, high: float, low: float, close: float) -> Candle:
    opened = datetime(2026, 1, 2, 15, 0, tzinfo=UTC) + timedelta(minutes=index)
    return Candle(
        symbol="BTCUSDT",
        timeframe="1m",
        open_time=opened,
        close_time=opened + timedelta(minutes=1),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1000,
    )


def valid_long_setup() -> list[Candle]:
    return [
        candle(0, 110, 115, 109, 112),
        candle(1, 112, 118, 111, 116),
        candle(2, 116, 140, 114, 119),
        candle(3, 119, 120, 105, 107),
        candle(4, 107, 108, 99, 101),
        candle(5, 101, 102, 98, 100),
        candle(6, 100, 115, 99.5, 113),
        candle(7, 113, 145, 110, 142),
        candle(8, 112, 115, 105, 112),
    ]


def strategy() -> SilverBulletStrategyEngine:
    return SilverBulletStrategyEngine(
        SilverBulletStrategyConfig(
            swing_lookback=2,
            atr_period=3,
            minimum_rr=2.0,
            minimum_signal_score=70,
        )
    )


def test_paper_trading_opens_closes_stores_and_alerts(database_url) -> None:
    candles = [*valid_long_setup(), candle(9, 112, 141, 105, 140)]
    storage = PostgresStorage(database_url)
    telegram_client = InMemoryTelegramClient()
    alerter = TelegramAlerter(
        TelegramAlertConfig(enabled=True, chat_id="chat"),
        client=telegram_client,
    )
    engine = PaperTradingEngine(
        stream=MockMarketDataStream(candles),
        strategy=strategy(),
        storage=storage,
        alerter=alerter,
    )

    result = asyncio.run(engine.run())
    report = build_daily_paper_report(result)

    assert result.closed_trades == 1
    assert result.trades[0].realized_pnl > 0
    assert storage.count_rows("paper_trades") == 1
    assert storage.count_rows("paper_events") >= 4
    assert report["closed_trades"] == 1
    assert any("Paper bot started" in message for _, message in telegram_client.messages)
    assert any("Signal detected" in message for _, message in telegram_client.messages)
    assert any("Paper trade opened" in message for _, message in telegram_client.messages)
    assert any("Paper trade closed" in message for _, message in telegram_client.messages)


def test_paper_trading_telegram_disabled_by_default() -> None:
    telegram_client = InMemoryTelegramClient()
    alerter = TelegramAlerter(client=telegram_client)
    engine = PaperTradingEngine(
        stream=MockMarketDataStream(valid_long_setup()),
        strategy=strategy(),
        alerter=alerter,
    )

    asyncio.run(engine.run())

    assert telegram_client.messages == []


def test_paper_trading_kill_switch_alert_and_risk_rejection(tmp_path) -> None:
    kill_file = tmp_path / "KILL_SWITCH"
    kill_file.write_text("stop", encoding="utf-8")
    telegram_client = InMemoryTelegramClient()
    alerter = TelegramAlerter(
        TelegramAlertConfig(enabled=True, chat_id="chat"),
        client=telegram_client,
    )
    engine = PaperTradingEngine(
        stream=MockMarketDataStream([*valid_long_setup(), candle(9, 112, 141, 105, 140)]),
        strategy=strategy(),
        risk=RiskManagementEngine(RiskConfig(kill_switch_path=kill_file)),
        alerter=alerter,
    )

    result = asyncio.run(engine.run())

    assert result.closed_trades == 0
    assert any(event.event_type == PaperEventType.KILL_SWITCH_ACTIVE for event in result.events)
    assert any("Kill switch active" in message for _, message in telegram_client.messages)


def test_reconnecting_market_stream_recovers_from_mock_failure() -> None:
    attempts = {"count": 0}
    expected = [candle(0, 100, 101, 99, 100)]

    def factory() -> MockMarketDataStream:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return MockMarketDataStream(expected, fail_after=0)
        return MockMarketDataStream(expected)

    stream = ReconnectingMarketDataStream(
        factory,
        policy=ReconnectPolicy(max_reconnects=1, reconnect_delay_seconds=0),
    )
    candles = []
    async def collect() -> list[Candle]:
        output = []
        async for item in stream.candles():
            output.append(item)
        return output

    candles = asyncio.run(collect())

    assert candles == expected
    assert attempts["count"] == 2


class TripAfterStream(MockMarketDataStream):
    """Mock stream that creates the kill-switch file after yielding `trip_after` candles."""

    def __init__(self, candles, *, kill_file, trip_after: int) -> None:
        super().__init__(candles)
        self.kill_file = kill_file
        self.trip_after = trip_after

    async def candles(self):
        index = 0
        async for item in super().candles():
            if index == self.trip_after:
                self.kill_file.write_text("stop", encoding="utf-8")
            yield item
            index += 1


def test_kill_switch_closes_open_paper_position(tmp_path) -> None:
    kill_file = tmp_path / "KILL_SWITCH"
    candles = [*valid_long_setup(), candle(9, 112, 113, 105, 110), candle(10, 110, 112, 108, 111)]
    risk = RiskManagementEngine(RiskConfig(kill_switch_path=kill_file))
    engine = PaperTradingEngine(
        stream=TripAfterStream(candles, kill_file=kill_file, trip_after=10),
        strategy=strategy(),
        risk=risk,
    )

    result = asyncio.run(engine.run())

    assert result.closed_trades == 1
    trade = result.trades[0]
    assert trade.exit_reason.value == "kill_switch"
    assert trade.exit_time == candles[-1].open_time
    assert trade.realized_pnl > 0
    assert risk.state.open_positions == 0
    assert engine.executor.has_active_trade is False


def test_kill_switch_cancels_pending_paper_order(tmp_path) -> None:
    kill_file = tmp_path / "KILL_SWITCH"
    candles = [*valid_long_setup(), candle(9, 116, 125, 116, 120)]
    risk = RiskManagementEngine(RiskConfig(kill_switch_path=kill_file))
    engine = PaperTradingEngine(
        stream=TripAfterStream(candles, kill_file=kill_file, trip_after=9),
        strategy=strategy(),
        risk=risk,
    )

    result = asyncio.run(engine.run())

    assert result.closed_trades == 0
    assert any(event.event_type == PaperEventType.PAPER_ORDER_CANCELLED for event in result.events)
    assert risk.state.open_positions == 0
    assert engine.executor.has_active_trade is False


def test_unfilled_paper_order_is_cancelled_when_session_window_ends() -> None:
    risk = RiskManagementEngine()
    engine = PaperTradingEngine(
        stream=MockMarketDataStream([*valid_long_setup(), candle(9, 116, 125, 116, 120), candle(60, 121, 130, 121, 128)]),
        strategy=strategy(),
        risk=risk,
    )

    result = asyncio.run(engine.run())

    cancelled = [event for event in result.events if event.event_type == PaperEventType.PAPER_ORDER_CANCELLED]
    assert len(cancelled) == 1
    assert "session window ended" in cancelled[0].message
    assert risk.state.open_positions == 0


def test_history_seeds_the_strategy_without_evaluating_it() -> None:
    setup = valid_long_setup()
    engine = PaperTradingEngine(
        stream=MockMarketDataStream([setup[-1], candle(9, 112, 141, 105, 140)]),
        strategy=strategy(),
        history=setup[:-1],
    )

    result = asyncio.run(engine.run())

    assert result.candles_processed == 2
    assert result.closed_trades == 1


def test_on_trade_closed_and_report_writer(tmp_path) -> None:
    from silver_bot.config import AppConfig
    from silver_bot.execution.runtime import write_paper_report

    seen = []
    engine = PaperTradingEngine(
        stream=MockMarketDataStream([*valid_long_setup(), candle(9, 112, 141, 105, 140)]),
        strategy=strategy(),
        on_trade_closed=lambda result: seen.append(result.closed_trades),
    )
    result = asyncio.run(engine.run())
    path = tmp_path / "reports" / "paper_trading_report.json"

    write_paper_report(path, result, config=AppConfig(), started_at=datetime(2026, 1, 2, tzinfo=UTC), initial_equity=10_000.0)

    report = json.loads(path.read_text(encoding="utf-8"))
    assert seen == [1]
    assert engine.result is result
    assert report["mode"] == "paper"
    assert report["closed_trades"] == 1
    assert report["metrics"]["total_trades"] == 1
    assert report["ending_equity"] == result.equity
    assert not (tmp_path / "reports" / "paper_trading_report.json.tmp").exists()
