import random
from datetime import UTC, datetime, timedelta

import pytest

from silver_bot.data.csv_loader import timeframe_interval
from silver_bot.data.resample import HtfCandle, Resampler
from silver_bot.models import Candle

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
DAY = datetime(2026, 1, 5, tzinfo=UTC)
MINUTE = timedelta(minutes=1)


def minute(open_time: datetime, o=100.0, h=101.0, l=99.0, c=100.5, v=10.0) -> Candle:
    return Candle("BTCUSDT", "1m", open_time, o, h, l, c, v, open_time + MINUTE)


def run(timeframe: str, candles: list[Candle]) -> list[HtfCandle]:
    resampler = Resampler(timeframe)
    out: list[HtfCandle] = []
    for candle in candles:
        out.extend(resampler.push(candle))
    return out


def test_15m_candle_emitted_only_after_period_ends() -> None:
    resampler = Resampler("15m")
    candles = [minute(DAY + i * MINUTE, o=100 + i, h=110 + i, l=90 + i, c=101 + i, v=1 + i) for i in range(16)]

    for candle in candles[:15]:
        assert resampler.push(candle) == []
    emitted = resampler.push(candles[15])

    assert len(emitted) == 1
    htf = emitted[0]
    assert htf.complete is True
    assert htf.candle == Candle(
        "BTCUSDT", "15m", DAY, open=100, high=124, low=90, close=115, volume=sum(1 + i for i in range(15)),
        close_time=DAY + timedelta(minutes=15) - timedelta(milliseconds=1),
    )


def test_4h_and_1d_boundaries_are_utc_epoch_aligned() -> None:
    candles = [minute(DAY + i * MINUTE) for i in range(2 * 1440 + 1)]

    four_hour = run("4h", candles)
    daily = run("1d", candles)

    assert four_hour[1].candle.open_time == DAY + timedelta(hours=4)
    assert four_hour[1].candle.close_time == DAY + timedelta(hours=8) - timedelta(milliseconds=1)  # 04:00-07:59
    assert [h.candle.open_time for h in daily] == [DAY, DAY + timedelta(days=1)]
    assert daily[0].candle.close_time == DAY + timedelta(days=1) - timedelta(milliseconds=1)  # 00:00-23:59
    assert all(h.candle.timeframe == "4h" for h in four_hour)
    assert all(h.candle.timeframe == "1d" for h in daily)
    assert all(h.complete for h in four_hour + daily)
    assert all((h.candle.open_time - EPOCH) % timeframe_interval(h.candle.timeframe) == timedelta(0) for h in daily)


def test_gap_inside_period_emits_incomplete_candle() -> None:
    candles = [minute(DAY + i * MINUTE, v=2.0) for i in range(15) if i != 7]
    candles.append(minute(DAY + 15 * MINUTE))

    emitted = run("15m", candles)

    assert len(emitted) == 1
    assert emitted[0].complete is False
    assert emitted[0].candle.volume == pytest.approx(14 * 2.0)


def test_gap_spanning_whole_periods_emits_only_present_periods() -> None:
    first = [minute(DAY + i * MINUTE) for i in range(15)]
    after_gap = [minute(DAY + timedelta(hours=2) + i * MINUTE) for i in range(2)]
    resampler = Resampler("15m")

    for candle in first:
        assert resampler.push(candle) == []
    emitted = resampler.push(after_gap[0])
    assert [h.candle.open_time for h in emitted] == [DAY]
    assert resampler.push(after_gap[1]) == []
    flushed = resampler.flush()

    assert [h.candle.open_time for h in flushed] == [DAY + timedelta(hours=2)]
    assert flushed[0].complete is False
    assert resampler.flush() == []


def test_push_rejects_out_of_order_or_duplicate_minutes() -> None:
    resampler = Resampler("15m")
    resampler.push(minute(DAY + MINUTE))

    with pytest.raises(ValueError):
        resampler.push(minute(DAY + MINUTE))
    with pytest.raises(ValueError):
        resampler.push(minute(DAY))


def test_unsupported_timeframe_rejected() -> None:
    with pytest.raises(ValueError):
        Resampler("1h")


def batch_rebuild(timeframe: str, candles: list[Candle], cutoff: datetime) -> list[HtfCandle]:
    """Independent batch aggregation: group by period, keep periods ending at or before cutoff."""

    period = timeframe_interval(timeframe)
    groups: dict[datetime, list[Candle]] = {}
    for candle in candles:
        groups.setdefault(EPOCH + (candle.open_time - EPOCH) // period * period, []).append(candle)
    out = []
    for start in sorted(groups):
        if start + period > cutoff:
            continue
        group = groups[start]
        out.append(HtfCandle(
            Candle(
                "BTCUSDT", timeframe, start, group[0].open, max(c.high for c in group), min(c.low for c in group),
                group[-1].close, sum(c.volume for c in group), start + period - timedelta(milliseconds=1),
            ),
            complete=len(group) == period // MINUTE,
        ))
    return out


def test_no_lookahead_against_batch_rebuild() -> None:
    rng = random.Random(7)
    candles: list[Candle] = []
    price = 100.0
    t = DAY + timedelta(hours=3, minutes=7)  # deliberately misaligned start
    for _ in range(3 * 1440):
        if rng.random() < 0.01:
            t += timedelta(minutes=rng.randint(2, 90))  # outage
        o = price
        c = o * (1 + rng.uniform(-0.002, 0.002))
        h = max(o, c) * (1 + rng.uniform(0, 0.001))
        l = min(o, c) * (1 - rng.uniform(0, 0.001))
        candles.append(minute(t, o, h, l, c, rng.uniform(1, 50)))
        price = c
        t += MINUTE

    for timeframe in ("15m", "4h", "1d"):
        resampler = Resampler(timeframe)
        emitted: list[HtfCandle] = []
        full = batch_rebuild(timeframe, candles, candles[-1].open_time + timedelta(days=2))
        for i, candle in enumerate(candles):
            emitted.extend(resampler.push(candle))
            # Every step: emitted == the full batch rebuild limited to periods ended by now.
            assert emitted == [h for h in full if h.candle.close_time < candle.open_time]
            # Truncated rebuild is O(n), so it runs on a stride plus the last step.
            if i % 101 == 0 or i == len(candles) - 1:
                assert emitted == batch_rebuild(timeframe, candles[: i + 1], candle.open_time)
        assert len(emitted) > 0
