from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from silvr.data import CandleDataError, load_binance_kline_csv, timeframe_interval

START_MS = int(datetime(2026, 1, 2, 15, 0, tzinfo=UTC).timestamp() * 1000)
MINUTE_MS = 60_000


def kline(open_ms: int, *, step_ms: int = MINUTE_MS, o=100.0, h=101.0, l=99.0, c=100.5, v=10.0) -> str:
    return f"{open_ms},{o},{h},{l},{c},{v},{open_ms + step_ms - 1},0,0,0,0,0"


def write(path: Path, rows: list[str], *, header: bool = False) -> Path:
    lines = (["open_time,open,high,low,close,volume,close_time,quote_volume,count,"
              "taker_buy_volume,taker_buy_quote_volume,ignore"] if header else []) + rows
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def load(*paths: Path, timeframe: str = "1m"):
    return load_binance_kline_csv(list(paths), symbol="BTCUSDT", timeframe=timeframe)


def test_loads_rows_without_header(tmp_path: Path) -> None:
    file = write(tmp_path / "a.csv", [kline(START_MS + i * MINUTE_MS) for i in range(3)])

    result = load(file)

    assert len(result.candles) == 3
    first = result.candles[0]
    assert first.open_time == datetime(2026, 1, 2, 15, 0, tzinfo=UTC)
    assert first.close_time == datetime(2026, 1, 2, 15, 1, tzinfo=UTC)
    assert first.symbol == "BTCUSDT"
    assert first.timeframe == "1m"
    assert (first.open, first.high, first.low, first.close, first.volume) == (100.0, 101.0, 99.0, 100.5, 10.0)
    assert result.files == [file]
    assert result.gaps == 0


def test_skips_header_row_even_with_bom(tmp_path: Path) -> None:
    file = tmp_path / "a.csv"
    file.write_text(
        "﻿open_time,open,high,low,close,volume,close_time,a,b,c,d,e\n" + kline(START_MS) + "\n",
        encoding="utf-8",
    )

    assert len(load(file).candles) == 1


def test_microsecond_timestamps(tmp_path: Path) -> None:
    open_us = START_MS * 1000
    row = f"{open_us},100,101,99,100.5,10,{open_us + MINUTE_MS * 1000 - 1},0,0,0,0,0"
    file = write(tmp_path / "a.csv", [row])

    candle = load(file).candles[0]

    assert candle.open_time == datetime(2026, 1, 2, 15, 0, tzinfo=UTC)
    assert candle.close_time == datetime(2026, 1, 2, 15, 1, tzinfo=UTC)


def test_directory_input_sorted_and_overlap_deduplicated(tmp_path: Path) -> None:
    folder = tmp_path / "candles"
    folder.mkdir()
    write(folder / "b.csv", [kline(START_MS + 2 * MINUTE_MS), kline(START_MS + 3 * MINUTE_MS)])
    write(folder / "a.csv", [kline(START_MS), kline(START_MS + MINUTE_MS), kline(START_MS + 2 * MINUTE_MS)])
    (folder / "notes.txt").write_text("ignored", encoding="utf-8")

    result = load(folder)

    assert [c.open_time for c in result.candles] == [
        datetime(2026, 1, 2, 15, i, tzinfo=UTC) for i in range(4)
    ]
    assert [p.name for p in result.files] == ["a.csv", "b.csv"]


def test_gap_is_counted(tmp_path: Path) -> None:
    file = write(tmp_path / "a.csv", [kline(START_MS), kline(START_MS + 5 * MINUTE_MS)])

    assert load(file).gaps == 1


def test_candle_duration_must_match_timeframe_both_ways(tmp_path: Path) -> None:
    five = 5 * MINUTE_MS
    coarse = write(tmp_path / "five.csv", [kline(START_MS + i * five, step_ms=five) for i in range(3)])
    fine = write(tmp_path / "one.csv", [kline(START_MS + i * MINUTE_MS) for i in range(3)])

    assert len(load(coarse, timeframe="5m").candles) == 3
    with pytest.raises(CandleDataError, match="duration .* TIMEFRAME=1m") as info:
        load(coarse, timeframe="1m")
    assert f"{coarse}:1" in str(info.value)
    with pytest.raises(CandleDataError, match="TIMEFRAME=5m"):
        load(fine, timeframe="5m")


@pytest.mark.parametrize(
    ("row", "fragment"),
    [
        ("1,2,3", "at least 7 columns"),
        ("abc,100,101,99,100.5,10,1,0,0,0,0,0", "timestamps must be integers"),
        (f"{START_MS},x,101,99,100.5,10,{START_MS + 59_999},0,0,0,0,0", "must be numbers"),
        (f"{START_MS},nan,101,99,100.5,10,{START_MS + 59_999},0,0,0,0,0", "finite and positive"),
        (f"{START_MS},0,101,99,100.5,10,{START_MS + 59_999},0,0,0,0,0", "finite and positive"),
        (f"{START_MS},100,101,99,100.5,-1,{START_MS + 59_999},0,0,0,0,0", "volume"),
        (f"{START_MS},100,99,101,100.5,10,{START_MS + 59_999},0,0,0,0,0", "high/low"),
    ],
)
def test_bad_rows_name_file_and_line(tmp_path: Path, row: str, fragment: str) -> None:
    file = write(tmp_path / "bad.csv", [kline(START_MS - MINUTE_MS), row])

    with pytest.raises(CandleDataError, match=fragment) as info:
        load(file)

    assert f"{file}:2" in str(info.value)


def test_conflicting_duplicate_is_rejected(tmp_path: Path) -> None:
    file = write(tmp_path / "a.csv", [kline(START_MS), kline(START_MS, c=100.7)])

    with pytest.raises(CandleDataError, match="conflicting duplicate"):
        load(file)


def test_missing_path_empty_directory_and_empty_file(tmp_path: Path) -> None:
    with pytest.raises(CandleDataError, match="not found"):
        load(tmp_path / "missing.csv")
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(CandleDataError, match="No .csv files"):
        load(empty_dir)
    with pytest.raises(CandleDataError, match="No candle rows"):
        load(write(tmp_path / "header_only.csv", [], header=True))
    with pytest.raises(CandleDataError, match="No candle paths"):
        load_binance_kline_csv([], symbol="BTCUSDT", timeframe="1m")


@pytest.mark.parametrize(("value", "minutes"), [("1m", 1), ("15m", 15), ("1h", 60), ("4h", 240), ("1d", 1440), ("1w", 10080)])
def test_timeframe_interval(value: str, minutes: int) -> None:
    assert timeframe_interval(value) == timedelta(minutes=minutes)


@pytest.mark.parametrize("value", ["", "m", "0m", "1x", "abc"])
def test_timeframe_interval_rejects_bad_values(value: str) -> None:
    with pytest.raises(CandleDataError, match="Unsupported timeframe"):
        timeframe_interval(value)
