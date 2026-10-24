from datetime import UTC, datetime, timedelta

import pytest

from silver_bot.data.funding import (
    FundingDataError,
    FundingRate,
    FundingSchedule,
    load_funding_csv,
    write_funding_csv,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)
EIGHT_HOURS = timedelta(hours=8)


def rates(count, *, first=T0, offset_ms=7):
    return [
        FundingRate(first + EIGHT_HOURS * i + timedelta(milliseconds=offset_ms), 0.0001 * (i + 1))
        for i in range(count)
    ]


def test_csv_round_trip(tmp_path):
    path = tmp_path / "BTCUSDT-funding.csv"
    original = rates(4) + [FundingRate(T0 + EIGHT_HOURS * 4, -0.00012345678901)]

    write_funding_csv(path, list(reversed(original)) + [original[0]])  # unsorted, one duplicate

    assert path.read_text().startswith("time_ms,rate\n")
    assert load_funding_csv(path) == sorted(original, key=lambda item: item.time)
    assert list(tmp_path.glob("*.part")) == []


def test_load_rejects_bad_header_and_bad_row(tmp_path):
    bad_header = tmp_path / "a.csv"
    bad_header.write_text("time,rate\n1,0.1\n")
    bad_row = tmp_path / "b.csv"
    bad_row.write_text("time_ms,rate\nnot-a-number,0.1\n")

    with pytest.raises(FundingDataError):
        load_funding_csv(bad_header)
    with pytest.raises(FundingDataError, match="line 2"):
        load_funding_csv(bad_row)
    with pytest.raises(FundingDataError):
        load_funding_csv(tmp_path / "missing.csv")


def test_due_returns_rates_in_window():
    schedule = FundingSchedule(rates(5, offset_ms=0))

    def t(n):
        return T0 + EIGHT_HOURS * n

    assert [r.time for r in schedule.due(t(1), t(3))] == [t(2), t(3)]  # start exclusive, end inclusive
    assert schedule.due(t(1), t(1)) == []
    assert schedule.due(t(1) - timedelta(minutes=1), t(1))[0].time == t(1)
    assert schedule.due(t(4), t(9)) == []
    assert len(schedule.due(t(0) - EIGHT_HOURS, t(9))) == 5


def test_coverage_ok_with_millisecond_offsets():
    schedule = FundingSchedule(rates(10))

    schedule.check_coverage(T0 + timedelta(hours=1), T0 + timedelta(hours=60))
    schedule.check_coverage(T0, T0 + EIGHT_HOURS * 9)  # first rate is 7 ms after start


def test_coverage_gap_raises():
    data = rates(10)
    del data[5]
    schedule = FundingSchedule(data)

    with pytest.raises(FundingDataError, match="gap"):
        schedule.check_coverage(T0, T0 + EIGHT_HOURS * 9)
    # The same data is fine for windows that do not touch the hole.
    schedule.check_coverage(T0, T0 + EIGHT_HOURS * 3)
    schedule.check_coverage(T0 + EIGHT_HOURS * 7, T0 + EIGHT_HOURS * 9)


def test_coverage_edge_hole_inside_short_window_raises():
    # Rates at +8h and +19h; the +16h rate is missing, so a position open 14h-20h owes an unknown payment.
    schedule = FundingSchedule([FundingRate(T0 + timedelta(hours=8), 0.0001), FundingRate(T0 + timedelta(hours=19), 0.0001)])

    with pytest.raises(FundingDataError, match="gap"):
        schedule.check_coverage(T0 + timedelta(hours=14), T0 + timedelta(hours=20))


def test_coverage_short_window_with_distant_neighbours_raises():
    schedule = FundingSchedule(rates(2))  # rates at +7ms and +8h, nothing for days after
    start = T0 + timedelta(days=3)

    with pytest.raises(FundingDataError, match="gap"):
        schedule.check_coverage(start, start + timedelta(hours=2))


def test_coverage_hole_spanning_a_boundary_raises():
    data = rates(10)
    del data[4]  # hole of 16h between rate 3 (+24h) and rate 5 (+40h)
    schedule = FundingSchedule(data)

    with pytest.raises(FundingDataError, match="gap"):
        schedule.check_coverage(T0 + timedelta(hours=30), T0 + timedelta(hours=60))  # hole spans start
    with pytest.raises(FundingDataError, match="gap"):
        schedule.check_coverage(T0, T0 + timedelta(hours=30))  # hole spans end


def test_coverage_requires_both_ends_and_some_rates():
    schedule = FundingSchedule(rates(4))

    with pytest.raises(FundingDataError, match="no funding rates"):
        FundingSchedule([]).check_coverage(T0, T0 + EIGHT_HOURS)
    with pytest.raises(FundingDataError, match="gap"):
        schedule.check_coverage(T0 - timedelta(hours=9), T0 + EIGHT_HOURS)  # starts too late
    with pytest.raises(FundingDataError, match="gap"):
        schedule.check_coverage(T0, T0 + EIGHT_HOURS * 3 + timedelta(hours=9))  # ends too early
    schedule.check_coverage(T0 - timedelta(hours=8), T0 + EIGHT_HOURS * 3 + timedelta(hours=8))


def test_coverage_short_window_between_rates_is_fine():
    schedule = FundingSchedule(rates(4))
    inside = T0 + timedelta(hours=1)

    schedule.check_coverage(inside, inside + timedelta(hours=2))  # nothing due, nothing missing


def test_load_rejects_non_finite_rates(tmp_path):
    for value in ("nan", "inf", "-inf"):
        path = tmp_path / f"{value}.csv"
        path.write_text(f"time_ms,rate\n1000,{value}\n")
        with pytest.raises(FundingDataError, match="line 2"):
            load_funding_csv(path)
