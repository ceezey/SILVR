import math
import statistics
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from silvr.backtest import ExitReason
from silvr.backtest.metrics import calculate_metrics, day_r_t_stat
from silvr.backtest.models import EquityPoint, TradeRecord

START = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
NEW_KEYS = ("average_win_r", "average_loss_r", "realized_rr", "r_stdev", "r_t_stat", "return_to_drawdown")


def trade(index: int, *, realized_r: float, realized_pnl: float) -> TradeRecord:
    return TradeRecord(
        trade_id=index,
        symbol="BTC/USDT",
        timeframe="5m",
        session_name="london",
        direction="long",
        entry_time=START + timedelta(minutes=index),
        exit_time=START + timedelta(minutes=index + 1),
        entry_price=100.0,
        exit_price=101.0,
        stop_loss=99.0,
        take_profit=102.0,
        position_size=1.0,
        risk_amount=100.0,
        realized_pnl=realized_pnl,
        realized_r=realized_r,
        fees=0.0,
        slippage=0.0,
        max_favorable_excursion=1.0,
        max_adverse_excursion=0.0,
        exit_reason=ExitReason.TAKE_PROFIT,
        setup_quality_score=3,
    )


def trades_with_r(values: list[float]) -> list[TradeRecord]:
    return [trade(i, realized_r=value, realized_pnl=value * 100.0) for i, value in enumerate(values)]


def trades_with_pnl(values: list[float]) -> list[TradeRecord]:
    return [trade(i, realized_r=value / 100.0, realized_pnl=value) for i, value in enumerate(values)]


def curve(*, dd: float) -> list[EquityPoint]:
    return [EquityPoint(timestamp=START, equity=10_000.0, realized_pnl=0.0, drawdown=dd)]


def test_r_statistics_on_mixed_trades() -> None:
    # realized_r: +2.0, -1.0, +2.0, -1.0
    m = calculate_metrics(trades_with_r([2.0, -1.0, 2.0, -1.0]), curve(dd=100.0), initial_balance=10_000.0)
    assert m["average_win_r"] == 2.0
    assert m["average_loss_r"] == 1.0
    assert m["realized_rr"] == 2.0
    assert m["r_stdev"] == pytest.approx(statistics.stdev([2.0, -1.0, 2.0, -1.0]))
    assert m["r_t_stat"] == pytest.approx(0.5 / (m["r_stdev"] / 2.0))


def test_no_trades_gives_zeros() -> None:
    m = calculate_metrics([], [], initial_balance=10_000.0)
    for key in NEW_KEYS:
        assert m[key] == 0.0


def test_single_trade_has_zero_stdev_and_t_stat() -> None:
    m = calculate_metrics(trades_with_r([1.5]), curve(dd=0.0), initial_balance=10_000.0)
    assert m["r_stdev"] == 0.0 and m["r_t_stat"] == 0.0


def test_wins_without_losses_give_infinite_rr() -> None:
    m = calculate_metrics(trades_with_r([2.0, 1.0]), curve(dd=0.0), initial_balance=10_000.0)
    assert m["realized_rr"] == float("inf")


def test_losses_without_wins_give_zero_rr() -> None:
    m = calculate_metrics(trades_with_r([-1.0, -2.0]), curve(dd=0.0), initial_balance=10_000.0)
    assert m["realized_rr"] == 0.0
    assert m["average_win_r"] == 0.0
    assert m["average_loss_r"] == 1.5


def test_zero_stdev_gives_zero_t_stat() -> None:
    m = calculate_metrics(trades_with_r([1.0, 1.0, 1.0]), curve(dd=0.0), initial_balance=10_000.0)
    assert m["r_stdev"] == 0.0
    assert m["r_t_stat"] == 0.0


def test_return_to_drawdown() -> None:
    # net profit 500 on 10_000 = 5%; max drawdown 250 = 2.5% -> 2.0
    m = calculate_metrics(trades_with_pnl([300.0, 200.0]), curve(dd=250.0), initial_balance=10_000.0)
    assert m["return_to_drawdown"] == pytest.approx(2.0)


def test_positive_return_without_drawdown_is_infinite_and_loss_is_zero() -> None:
    profit = calculate_metrics(trades_with_pnl([100.0]), curve(dd=0.0), initial_balance=10_000.0)
    assert profit["return_to_drawdown"] == float("inf")
    loss = calculate_metrics(trades_with_pnl([-100.0]), curve(dd=100.0), initial_balance=10_000.0)
    assert loss["return_to_drawdown"] == 0.0


def test_total_funding_metric() -> None:
    # Funding paid is positive, received is negative; the metric is the net sum (0.5 - 0.2 = 0.3).
    trades = [replace(t, funding=f) for t, f in zip(trades_with_pnl([10.0, -5.0]), [0.5, -0.2])]
    assert calculate_metrics(trades, curve(dd=5.0), initial_balance=10_000.0)["total_funding"] == pytest.approx(0.3)
    assert calculate_metrics([], [], initial_balance=10_000.0)["total_funding"] == 0.0


def test_day_r_t_stat_matches_old_pooled_value() -> None:
    # Same fixture values as the pooled-gate day-t tests (tests/test_pooled_gate.py): R summed per UTC entry day.
    def on(day: int, r: float, hour: int = 0) -> TradeRecord:
        return replace(trade(0, realized_r=r, realized_pnl=50.0 * r), entry_time=datetime(2025, 11, day, hour, tzinfo=UTC))

    def t_stat(values: list[float]) -> float:
        return statistics.fmean(values) / (statistics.stdev(values) / math.sqrt(len(values)))

    rs = [2.0, -1.0, 2.0, -1.0, 2.0]
    same_days = [on(5 + i, r) for i, r in enumerate(rs)] + [on(5 + i, r, hour=3) for i, r in enumerate(rs)]
    assert day_r_t_stat(same_days) == pytest.approx(t_stat([2 * r for r in rs]))

    offsetting = [on(5, 2.0), on(6, 2.0), on(7, -1.0), on(8, 2.0)]
    offsetting += [on(5, -1.0, 3), on(6, -1.0, 3), on(7, 2.0, 3), on(8, -1.5, 3)]
    assert day_r_t_stat(offsetting) == pytest.approx(t_stat([1.0, 1.0, 1.0, 0.5]))

    assert day_r_t_stat([on(5, 2.0), on(5, -1.0, 3)]) == 0.0  # one day
    assert day_r_t_stat([on(5, 1.0), on(6, 1.0)]) == 0.0  # no spread
