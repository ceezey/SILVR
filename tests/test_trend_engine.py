"""Trend portfolio engine: day-boundary timing, intraday stops, funding, kill switch and fail-closed data."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest

from silvr.backtest import costs, trend_engine
from silvr.backtest.models import BacktestConfig, ExitReason
from silvr.backtest.trend_engine import TrendDataError, TrendPortfolioEngine, TrendRunResult
from silvr.data.funding import FundingRate, FundingSchedule
from silvr.models import Candle, SignalDirection
from silvr.risk import RiskConfig
from silvr.strategy.trend import params, sizing
from silvr.strategy.trend.params import ExchangeLimits
from silvr.strategy.trend.signals import DailyBar

D1 = datetime(2024, 3, 1, tzinfo=UTC)  # first run day; history is the 100 days before it
MINUTE = timedelta(minutes=1)
BPS = {"spread_bps": 3.0, "slippage_bps": 5.0}
LONG = SignalDirection.LONG
TAKER = 0.0005

# AAA closes 96 / 96.5 / 98 on run days 1 to 3: day 3 is a breakout for n=2 (stop mid(96.5, 98) = 97.25)
# and n=3 (stop mid(96, 96.5, 98) = 97). BBB stays at 96 and never breaks out.
BASE = [96.0, 96.5, 98.0]

Day = float | Callable[[int], tuple[float, float, float, float]]


def day(i: int) -> datetime:
    """00:00 UTC of run day i (1-based)."""
    return D1 + timedelta(days=i - 1)


def at(i: int, minute: int) -> datetime:
    return day(i) + minute * MINUTE


@pytest.fixture(autouse=True)
def tiny_universe(monkeypatch: pytest.MonkeyPatch) -> None:
    for module in (params, sizing):  # sizing reads its own module globals at call time
        monkeypatch.setattr(module, "SYMBOLS", ("AAA", "BBB"))
        monkeypatch.setattr(module, "LOOKBACKS", (2,))
    monkeypatch.setattr(sizing, "EXCHANGE_LIMITS", {s: ExchangeLimits(5.0, 0.001, 0.001) for s in ("AAA", "BBB")})


def history() -> dict[str, list[DailyBar]]:
    """100 days alternating 96 / 97 (ending on 97), so volatility is warm and nothing breaks out."""
    bars: dict[str, list[DailyBar]] = {}
    for symbol in ("AAA", "BBB"):
        bars[symbol] = []
        for i in range(100):
            close = 96.0 + i % 2
            bars[symbol].append(DailyBar(symbol, (D1 - timedelta(days=100 - i)).date(), close, close, close, close))
    return bars


def candle(symbol: str, t: datetime, o: float, h: float, l: float, c: float) -> Candle:
    return Candle(symbol, "1m", t, o, h, l, c, 1.0, close_time=t + MINUTE - timedelta(milliseconds=1))


def minutes(aaa: list[Day], bbb: float = 96.0) -> Iterator[dict[str, Candle]]:
    """One mapping per minute; each AAA day is a flat price or a function of the minute of the day."""
    for i, spec in enumerate(aaa, start=1):
        for m in range(1440):
            t = at(i, m)
            o, h, l, c = spec(m) if callable(spec) else (spec,) * 4
            yield {"AAA": candle("AAA", t, o, h, l, c), "BBB": candle("BBB", t, bbb, bbb, bbb, bbb)}


def schedule(rates: dict[datetime, float] | None = None) -> FundingSchedule:
    """Every 8 hours from a day before the run to 20 days after, rate 0 unless given."""
    rates = rates or {}
    times = [D1 - timedelta(days=1) + k * timedelta(hours=8) for k in range(3 * 21)]
    return FundingSchedule(FundingRate(t, rates.get(t, 0.0)) for t in times)


def engine(*, k: float = 1.0, rates: dict[datetime, float] | None = None) -> TrendPortfolioEngine:
    config = BacktestConfig(initial_balance=15_000.0, risk=RiskConfig.trend())
    funding = {"AAA": schedule(rates), "BBB": schedule()}
    return TrendPortfolioEngine(config, funding=funding, history=history(), k=k)


def run(aaa: list[Day], **kwargs: object) -> TrendRunResult:
    return engine(**kwargs).run(minutes(aaa))  # type: ignore[arg-type]


def flat_then(changes: dict[int, tuple[float, float, float, float]], before: float, after: float | None = None,
              switch: int = 1440) -> Callable[[int], tuple[float, float, float, float]]:
    """A day at `before` until minute `switch`, then `after`, with single-minute candles in `changes`."""
    def spec(m: int) -> tuple[float, float, float, float]:
        if m in changes:
            return changes[m]
        price = before if m < switch or after is None else after
        return (price,) * 4
    return spec


def test_no_lookahead_entry_and_stop() -> None:
    # Day 4: a spike to 120 at 10:00, close 110; a 20:00 dip to 100 would only hit a stop raised intraday
    # (mid(98, 120) = 109). Day 5 00:00 raises the stop to mid(98, 110) = 104; a 05:00 dip to 103 hits it.
    d4 = flat_then({600: (100.0, 120.0, 100.0, 120.0), 1200: (110.0, 110.0, 100.0, 110.0)}, 100.0, 110.0, 601)
    d5 = flat_then({300: (110.0, 110.0, 103.0, 103.0)}, 110.0, 103.0, 301)

    result = run([*BASE, d4, d5])

    [trade] = result.trades
    assert trade.entry_time == day(4)  # the breakout closed day 3; the fill is day 4's first open
    assert trade.entry_price == pytest.approx(costs.entry_price(100.0, LONG, **BPS))
    assert trade.stop_loss == pytest.approx(97.25)
    assert trade.exit_time == at(5, 300)
    assert trade.exit_price == pytest.approx(costs.market_exit_price(104.0, LONG, **BPS))
    assert trade.exit_reason == ExitReason.STOP_LOSS
    assert trade.notes == "AAA n=2" and trade.session_name == "trend"


def test_gap_fills_at_open() -> None:
    d4 = flat_then({360: (90.0, 90.0, 89.0, 90.0)}, 100.0)

    [trade] = run([*BASE, d4]).trades

    assert trade.exit_time == at(4, 360)
    assert trade.exit_price == pytest.approx(costs.market_exit_price(90.0, LONG, **BPS))
    assert trade.exit_reason == ExitReason.STOP_LOSS


def test_stop_checked_on_entry_minute() -> None:
    d4 = flat_then({0: (100.0, 100.0, 97.0, 98.0)}, 100.0)

    [trade] = run([*BASE, d4]).trades

    assert trade.entry_time == trade.exit_time == day(4)
    assert trade.exit_price == pytest.approx(costs.market_exit_price(97.25, LONG, **BPS))
    assert trade.exit_reason == ExitReason.STOP_LOSS


def test_missing_month_fails_closed() -> None:
    def without_bbb(stream: Iterator[dict[str, Candle]]) -> Iterator[dict[str, Candle]]:
        for minute in stream:
            yield {"AAA": minute["AAA"]} if minute["AAA"].open_time == at(2, 5) else minute

    with pytest.raises(TrendDataError, match="BBB") as error:
        engine().run(without_bbb(minutes(BASE)))
    assert error.value.symbol == "BBB" and error.value.minute == at(2, 5) and "2024-03" in str(error.value)

    def skip_minute(stream: Iterator[dict[str, Candle]]) -> Iterator[dict[str, Candle]]:
        return (minute for minute in stream if minute["AAA"].open_time != at(2, 5))

    with pytest.raises(TrendDataError, match="2024-03-02T00:05"):
        engine().run(skip_minute(minutes(BASE)))


def test_missing_funding_schedule_or_wrong_profile_refused() -> None:
    config = BacktestConfig(initial_balance=15_000.0, risk=RiskConfig.trend())
    with pytest.raises(TrendDataError, match="BBB"):
        TrendPortfolioEngine(config, funding={"AAA": schedule()}, history=history(), k=1.0)
    with pytest.raises(ValueError, match="trend"):
        TrendPortfolioEngine(BacktestConfig(), funding={"AAA": schedule(), "BBB": schedule()}, history=history(), k=1.0)


@pytest.mark.parametrize(
    ("cut", "message"),
    [(slice(None, -1), "warm-up history ends"), ([*range(50), *range(51, 100)], "warm-up history gap")],
    ids=["early_end", "gap"],
)
def test_warm_up_history_gap_or_early_end_fails_closed(cut: slice | list[int], message: str) -> None:
    bars = history()
    bars["BBB"] = bars["BBB"][cut] if isinstance(cut, slice) else [bars["BBB"][i] for i in cut]
    config = BacktestConfig(initial_balance=15_000.0, risk=RiskConfig.trend())
    funding = {"AAA": schedule(), "BBB": schedule()}

    with pytest.raises(TrendDataError, match=message) as error:
        TrendPortfolioEngine(config, funding=funding, history=bars, k=1.0).run(minutes(BASE))
    assert error.value.symbol == "BBB"


def test_kill_switch_flattens_and_halts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(params, "LOOKBACKS", (2, 3))
    monkeypatch.setattr(sizing, "LOOKBACKS", (2, 3))
    # Day 4: both slices enter at 100, AAA jumps to 250 at 01:00, then one 02:00 candle drops to 100 (above
    # both stops). Days 5 and 6 are new breakouts that must not be traded.
    d4 = flat_then({120: (250.0, 250.0, 100.0, 100.0)}, 100.0, 250.0, 60)
    d4_after = flat_then({}, 100.0)

    def day4(m: int) -> tuple[float, float, float, float]:
        return d4(m) if m <= 120 else d4_after(m)

    result = run([*BASE, day4, 300.0, 300.0])

    assert len(result.trades) == 2
    assert {trade.exit_reason for trade in result.trades} == {ExitReason.KILL_SWITCH}
    assert {trade.exit_time for trade in result.trades} == {at(4, 120)}
    exit_price = costs.market_exit_price(100.0, LONG, **BPS)
    assert all(trade.exit_price == pytest.approx(exit_price) for trade in result.trades)
    assert result.kill_switch_tripped_at == at(4, 120)
    assert result.rejections["kill switch"] >= 1


def test_funding_charged_to_open_slices(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trend_engine, "target_notional", lambda **_: 150.0)  # 1.5 units, floored to 1
    monkeypatch.setattr(sizing, "EXCHANGE_LIMITS", {s: ExchangeLimits(5.0, 1.0, 1.0) for s in ("AAA", "BBB")})

    [trade] = run([*BASE, 100.0], rates={at(4, 480): 0.0001}).trades

    assert trade.position_size == 1.0
    assert trade.funding == pytest.approx(0.01)  # 1 x 100 x 0.0001
    assert trade.exit_reason == ExitReason.END_OF_DATA


def test_daily_drawdown_is_intraday_worst() -> None:
    d4 = flat_then({720: (100.0, 100.0, 97.5, 98.0)}, 100.0)  # a 12:00 dip to 98 that recovers to 100

    result = run([*BASE, d4, 100.0])

    [trade] = result.trades
    entry_fee = costs.fee(trade.entry_price, trade.position_size, TAKER)
    dip_equity = 15_000.0 - entry_fee + trade.position_size * (98.0 - trade.entry_price)
    point = next(p for p in result.daily_equity if p.timestamp.date() == day(4).date())
    assert point.drawdown == pytest.approx(15_000.0 - dip_equity)
    assert point.drawdown > 15_000.0 - point.equity  # the day ended above its worst minute


def test_risk_rejection_reason_counted() -> None:
    # Day 3 closes 97.05 over (96, 97): stop mid(97, 97.05) = 97.025, under 0.1% below a 97.11 fill.
    result = run([96.0, 97.0, 97.05, 97.05])

    assert result.trades == []
    assert result.rejections["Stop-loss distance below configured minimum"] == 1


def test_r_t_stat_is_min_of_trade_and_day(monkeypatch: pytest.MonkeyPatch) -> None:
    gap = flat_then({360: (90.0, 90.0, 89.0, 90.0)}, 100.0)

    monkeypatch.setattr(trend_engine, "day_r_t_stat", lambda trades: -5.0)
    low_day = run([*BASE, gap]).metrics
    assert low_day["day_r_t_stat"] == -5.0
    assert low_day["r_t_stat"] == -5.0 < low_day["trade_r_t_stat"]

    monkeypatch.setattr(trend_engine, "day_r_t_stat", lambda trades: 5.0)
    high_day = run([*BASE, gap]).metrics
    assert high_day["r_t_stat"] == high_day["trade_r_t_stat"] < high_day["day_r_t_stat"]


def test_never_uses_the_real_kill_switch(tmp_path) -> None:
    real = tmp_path / "KILL_SWITCH"
    real.write_text('{"reason": "owner"}', encoding="utf-8")
    config = BacktestConfig(initial_balance=15_000.0, risk=RiskConfig.trend(kill_switch_path=real))
    funding = {"AAA": schedule(), "BBB": schedule()}

    result = TrendPortfolioEngine(config, funding=funding, history=history(), k=1.0).run(minutes([*BASE, 100.0]))

    assert len(result.trades) == 1  # the active real file blocks nothing: the run has its own simulated switch
    assert real.read_text(encoding="utf-8") == '{"reason": "owner"}'


def test_backtest_cost_defaults_are_conservative() -> None:
    config = BacktestConfig()

    assert (config.slippage_bps, config.spread_bps) == (5.0, 3.0)


def test_kill_switch_trip_blocks_until_next_utc_day(monkeypatch: pytest.MonkeyPatch) -> None:
    # Days 3 and 4 both close as breakouts (n=2), so an entry is due at day 4 00:00 and again at day 5 00:00.
    # The simulated switch trips at day 4 00:00 (as a risk-limit trip would): day 4's entry is blocked and the
    # reset at the next UTC day lets day 5's entry through.
    switches: list[trend_engine.SimulatedKillSwitch] = []

    class TripsOnDay4(trend_engine.SimulatedKillSwitch):
        def __init__(self) -> None:
            super().__init__()
            switches.append(self)

        @property
        def now(self) -> datetime | None:
            return self._now

        @now.setter
        def now(self, value: datetime | None) -> None:
            self._now = value
            if value == day(4):
                self.trip("Max daily loss limit reached")

    monkeypatch.setattr(trend_engine, "SimulatedKillSwitch", TripsOnDay4)

    result = run([*BASE, 100.0, 100.0])

    assert result.rejections["Kill switch is active"] == 1
    [trade] = result.trades
    assert trade.entry_time == day(5)
    assert switches[0].trips == [{"reason": "Max daily loss limit reached", "tripped_at": day(4), "reset_at": day(5)}]
