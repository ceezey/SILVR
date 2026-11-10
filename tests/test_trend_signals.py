import math
import statistics
from datetime import UTC, date, datetime, timedelta

import pytest

from silvr.models import Candle
from silvr.strategy.trend.signals import (
    DailyBar,
    annualized_vol,
    channel_mid,
    daily_bars,
    is_breakout,
    raise_stop,
    simple_returns,
)

MINUTE = timedelta(minutes=1)


def minutes(start: str, count: int, symbol: str = "BTCUSDT") -> list[Candle]:
    """`count` consecutive 1m candles from `start` (UTC); close at minute i is 100 + i."""
    t0 = datetime.fromisoformat(start).replace(tzinfo=UTC)
    out = []
    for i in range(count):
        c = 100.0 + i
        out.append(Candle(symbol, "1m", t0 + i * MINUTE, c, c + 0.5, c - 0.5, c, 1.0, t0 + (i + 1) * MINUTE))
    return out


def last_minute_close_of(day: date) -> float:
    """Close of the 23:59 minute of `day` in a series that starts at 2024-01-01T00:00."""
    return 100.0 + (day - date(2024, 1, 1)).days * 1440 + 1439


def test_breakout_needs_strictly_higher_close():
    assert is_breakout([1, 2, 3, 4], 3) and not is_breakout([1, 4, 3, 4], 3)


def test_breakout_warmup():
    assert not is_breakout([1, 2, 3], 3)


def test_channel_mid():
    assert channel_mid([10, 20, 15, 30], 3) == 22.5


def test_channel_mid_warmup_raises():
    with pytest.raises(ValueError):
        channel_mid([1, 2], 3)


def test_stop_only_rises():
    assert raise_stop(50.0, 45.0) == 50.0 and raise_stop(50.0, 55.0) == 55.0


def test_vol_warmup_and_value():
    assert annualized_vol([100.0] * 90) is None
    closes = [100.0]
    for i in range(90):  # alternating +2% / -1% returns
        closes.append(closes[-1] * (1.02 if i % 2 else 0.99))
    expected = statistics.stdev(simple_returns(closes)[-90:]) * math.sqrt(365)
    assert expected > 0
    assert annualized_vol(closes) == pytest.approx(expected)


def test_vol_uses_only_the_last_window():
    closes = [1.0, 50.0, 3.0] + [100.0 + (i % 2) for i in range(31)]
    window = simple_returns(closes)[-30:]
    assert annualized_vol(closes, 30) == pytest.approx(statistics.stdev(window) * math.sqrt(365))


def test_default_vol_window_is_the_last_90_returns_not_all():
    closes = [100.0, 200.0, 50.0]  # two wild early returns (+100%, -75%) outside the 90-return window
    for i in range(90):
        closes.append(closes[-1] * (1.02 if i % 2 else 0.99))
    last_90 = statistics.stdev(simple_returns(closes)[-90:]) * math.sqrt(365)
    every = statistics.stdev(simple_returns(closes)) * math.sqrt(365)
    assert every > 2 * last_90  # the two windows give clearly different answers
    assert annualized_vol(closes) == pytest.approx(last_90)


def test_daily_bars_drop_incomplete_last_day():
    bars = daily_bars(minutes(start="2024-01-01T00:00", count=1440 + 60))
    assert [b.day for b in bars] == [date(2024, 1, 1)]
    assert bars[0] == DailyBar("BTCUSDT", date(2024, 1, 1), 100.0, 100.0 + 1439 + 0.5, 99.5, last_minute_close_of(date(2024, 1, 1)))


def test_daily_bars_two_days():
    bars = daily_bars(minutes(start="2024-01-01T00:00", count=2 * 1440 + 1))
    assert [b.day for b in bars] == [date(2024, 1, 1), date(2024, 1, 2)]
    assert bars[1].close == last_minute_close_of(date(2024, 1, 2))


def test_daily_bars_raise_on_incomplete_mid_series_day():
    candles = minutes(start="2024-01-01T00:00", count=2 * 1440)
    del candles[500]  # one minute missing on 2024-01-01
    with pytest.raises(ValueError, match=r"BTCUSDT.*2024-01-01"):
        daily_bars(candles)
