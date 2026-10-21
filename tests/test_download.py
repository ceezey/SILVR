import asyncio
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from silver_bot.data import download as download_module
from silver_bot.data.csv_loader import load_binance_kline_csv
from silver_bot.data.download import DownloadSummary, download, main, month_file_name
from silver_bot.exchange.base import ExchangeAdapter
from silver_bot.models import Candle

MINUTE = timedelta(minutes=1)


class FakeAdapter(ExchangeAdapter):
    """Returns synthetic 1m candles for any [start, end) range; never touches the network."""

    def __init__(self, omit=(), fail_from: datetime | None = None):
        self.calls: list[tuple[datetime, datetime, int]] = []
        self.omit = set(omit)
        self.fail_from = fail_from

    async def fetch_ohlcv(self, *, symbol, timeframe, start, end, limit=1000):
        self.calls.append((start, end, limit))
        if self.fail_from is not None and start >= self.fail_from:
            raise RuntimeError("boom")
        candles = []
        moment = start
        while moment < end:
            if moment not in self.omit:
                candles.append(
                    Candle(
                        symbol=symbol,
                        timeframe=timeframe,
                        open_time=moment,
                        open=100.0,
                        high=101.0,
                        low=99.0,
                        close=100.5,
                        volume=1.5,
                        close_time=moment + MINUTE - timedelta(milliseconds=1),
                    )
                )
            moment += MINUTE
        return candles

    def asked_for(self, year: int, month: int) -> bool:
        return any(s.year == year and s.month == month for s, _, _ in self.calls)


def run(adapter, tmp_path, *, start=date(2024, 1, 1), end=datetime(2024, 3, 1, tzinfo=UTC)):
    return asyncio.run(
        download(symbol="BTCUSDT", timeframe="1m", start=start, end=end, out_dir=tmp_path, adapter=adapter)
    )


def test_month_file_name():
    assert month_file_name("BTCUSDT", "1m", 2024, 1) == "BTCUSDT-1m-2024-01.csv"


def test_writes_monthly_files_that_round_trip_through_loader(tmp_path):
    adapter = FakeAdapter()
    summary = run(adapter, tmp_path)

    assert isinstance(summary, DownloadSummary)
    assert [p.name for p in summary.files] == ["BTCUSDT-1m-2024-01.csv", "BTCUSDT-1m-2024-02.csv"]
    assert summary.candles == 44_640 + 41_760
    assert summary.gaps == 0
    assert summary.skipped == []
    assert all(limit == 1500 for _, _, limit in adapter.calls)
    assert (tmp_path / "BTCUSDT-1m-2024-01.csv").read_text().startswith("open_time,open,high,low,close,volume,close_time\n")
    jan = load_binance_kline_csv([summary.files[0]], symbol="BTCUSDT", timeframe="1m")
    feb = load_binance_kline_csv([summary.files[1]], symbol="BTCUSDT", timeframe="1m")
    both = load_binance_kline_csv(summary.files, symbol="BTCUSDT", timeframe="1m")
    assert (len(jan.candles), len(feb.candles)) == (44_640, 41_760)
    assert len(both.candles) == 86_400 and both.gaps == 0


def test_complete_month_skipped_on_rerun(tmp_path):
    run(FakeAdapter(), tmp_path)
    second = FakeAdapter()
    summary = run(second, tmp_path)

    assert [p.name for p in summary.skipped] == ["BTCUSDT-1m-2024-01.csv", "BTCUSDT-1m-2024-02.csv"]
    assert summary.files == [] and summary.candles == 0
    assert not second.asked_for(2024, 1)


def test_incomplete_month_file_is_refetched(tmp_path):
    run(FakeAdapter(), tmp_path)
    jan = tmp_path / "BTCUSDT-1m-2024-01.csv"
    lines = jan.read_text().splitlines()
    jan.write_text("\n".join(lines[:-1]) + "\n")

    second = FakeAdapter()
    summary = run(second, tmp_path)

    assert second.asked_for(2024, 1)
    assert not second.asked_for(2024, 2)
    assert jan in summary.files
    assert len(load_binance_kline_csv([jan], symbol="BTCUSDT", timeframe="1m").candles) == 44_640


def test_current_month_always_refetched(tmp_path):
    now = datetime.now(UTC)
    start = date(now.year, now.month, 1)
    end = now.replace(microsecond=0)
    if end.date() == start and end.hour == 0 and end.minute < 5:
        pytest.skip("too close to the start of the UTC month")
    run(FakeAdapter(), tmp_path, start=start, end=end)
    second = FakeAdapter()
    summary = run(second, tmp_path, start=start, end=end)

    assert second.asked_for(now.year, now.month)
    assert summary.skipped == []


def test_part_file_never_left_on_error(tmp_path):
    adapter = FakeAdapter(fail_from=datetime(2024, 2, 1, tzinfo=UTC))
    with pytest.raises(RuntimeError):
        run(adapter, tmp_path)

    assert list(tmp_path.glob("*.part")) == []
    jan = tmp_path / "BTCUSDT-1m-2024-01.csv"
    assert len(load_binance_kline_csv([jan], symbol="BTCUSDT", timeframe="1m").candles) == 44_640
    assert not (tmp_path / "BTCUSDT-1m-2024-02.csv").exists()


def test_failed_write_leaves_no_part_and_no_final_file(tmp_path, monkeypatch):
    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(download_module.os, "replace", broken_replace)
    with pytest.raises(OSError):
        run(FakeAdapter(), tmp_path, end=datetime(2024, 2, 1, tzinfo=UTC))

    assert list(tmp_path.iterdir()) == []


def test_gaps_are_reported_and_files_still_load(tmp_path):
    base = datetime(2024, 1, 1, tzinfo=UTC)
    omit = {base + MINUTE * n for n in (10, 100, 1000, 5000, 20000)}
    summary = run(FakeAdapter(omit=omit), tmp_path, end=datetime(2024, 2, 1, tzinfo=UTC))

    assert summary.gaps == 5
    assert summary.candles == 44_640 - 5
    loaded = load_binance_kline_csv(summary.files, symbol="BTCUSDT", timeframe="1m")
    assert len(loaded.candles) == 44_635


def test_download_never_passes_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BINANCE_API_KEY", "secret-key-value")
    monkeypatch.setenv("BINANCE_API_SECRET", "secret-secret-value")
    built = []

    def spy(*args, **kwargs):
        built.append((args, kwargs))
        return FakeAdapter()

    monkeypatch.setattr(download_module, "BinanceFuturesAdapter", spy)
    code = main(
        ["--start", "2024-01-01", "--end", "2024-01-02", "--symbol", "BTCUSDT", "--timeframe", "1m", "--out", str(tmp_path)]
    )

    assert code == 0
    assert built == [((), {})]
    out = capsys.readouterr().out
    assert "1440 candles" in out and "0 gaps" in out and "secret" not in out


def test_main_returns_1_with_reason_on_error(tmp_path, monkeypatch, capsys):
    class Failing(FakeAdapter):
        async def fetch_ohlcv(self, **kwargs):
            raise RuntimeError("exchange unreachable")

    monkeypatch.setattr(download_module, "BinanceFuturesAdapter", lambda: Failing())
    code = main(["--start", "2024-01-01", "--end", "2024-01-02", "--symbol", "BTCUSDT", "--timeframe", "1m", "--out", str(tmp_path)])

    err = capsys.readouterr().err
    assert code == 1
    assert "exchange unreachable" in err and len(err.strip().splitlines()) == 1


def test_main_returns_1_on_bad_arguments(capsys):
    assert main([]) == 1
    assert main(["--start", "not-a-date"]) == 1
    assert "error" in capsys.readouterr().err
