import json
import urllib.error
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from silver_bot.exchange import binance_futures
from silver_bot.main import main
from silver_bot.readiness import evaluate_live_readiness

MODE_KEYS = ("MODE", "TRADING_MODE", "PAPER_TRADING", "DEMO_TRADING", "LIVE_TRADING", "KILL_SWITCH_ENABLED")
START_MS = int(datetime(2026, 1, 2, 14, 0, tzinfo=UTC).timestamp() * 1000)


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    for key in MODE_KEYS:
        monkeypatch.delenv(key, raising=False)
    return tmp_path


def backtest_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_MODE", "backtest")
    monkeypatch.setenv("PAPER_TRADING", "false")


def write_klines(path: Path, count: int = 60) -> Path:
    rows = []
    for index in range(count):
        open_ms = START_MS + index * 60_000
        base = 100 + (index % 7)
        rows.append(f"{open_ms},{base},{base + 2},{base - 2},{base + 1},1000,{open_ms + 59_999},0,0,0,0,0")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def audit_events(root: Path) -> list[dict]:
    lines = (root / "logs" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


DEMO_ENV = {
    "MODE": "demo",
    "DEMO_TRADING": "true",
    "PAPER_TRADING": "false",
    "BINANCE_TESTNET": "true",
    "BINANCE_API_KEY": "testnet-key",
    "BINANCE_API_SECRET": "testnet-secret",
    "KILL_SWITCH_ENABLED": "true",
    "KILL_SWITCH_PATH": "KILL_SWITCH",
}


@pytest.fixture
def klines(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Serve flat 1m klines around now; the first (warm-up) call withholds the two newest closed ones.

    The newest kline is still forming, as on Binance. Returns the requested URLs.
    """

    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    forming_ms = now_ms - now_ms % 60_000
    opens = [forming_ms - minutes * 60_000 for minutes in range(10, -1, -1)]
    urls: list[str] = []

    def http_get(url: str) -> bytes:
        urls.append(url)
        query = parse_qs(urlsplit(url).query)
        start, end = int(query["startTime"][0]), int(query["endTime"][0])
        cutoff = forming_ms - 3 * 60_000 if len(urls) == 1 else forming_ms
        rows = [
            [open_ms, "100", "101", "99", "100", "5", open_ms + 59_999, "0", 0, "0", "0", "0"]
            for open_ms in opens
            if start <= open_ms <= min(end, cutoff)
        ]
        return json.dumps(rows).encode()

    monkeypatch.setattr(binance_futures, "_urllib_get", http_get)
    return urls


def test_paper_mode_runs_on_market_data_and_writes_report(workdir: Path, klines: list[str]) -> None:
    assert main(["--max-candles", "2"]) == 0

    assert {urlsplit(url).hostname for url in klines} == {"fapi.binance.com"}
    assert all("signature" not in url and "key" not in url.lower() for url in klines)
    report = json.loads((workdir / "reports" / "paper_trading_report.json").read_text(encoding="utf-8"))
    assert report["mode"] == "paper"
    assert report["fills"] == "simulated"
    assert report["candles_processed"] == 2
    readiness = evaluate_live_readiness(project_root=workdir, environ={})
    assert "paper_trading_report_exists" not in {item.name for item in readiness.failed_checks}
    events = audit_events(workdir)
    assert events[0]["event_type"] == "bot_started"
    assert events[-1]["event_type"] == "bot_stopped"
    assert events[-1]["context"]["exit_code"] == 0


def test_demo_mode_reads_testnet_market_data(
    workdir: Path, monkeypatch: pytest.MonkeyPatch, klines: list[str]
) -> None:
    for key, value in DEMO_ENV.items():
        monkeypatch.setenv(key, value)

    assert main(["--max-candles", "1"]) == 0

    assert {urlsplit(url).hostname for url in klines} == {"testnet.binancefuture.com"}
    assert all("testnet-key" not in url and "testnet-secret" not in url for url in klines)
    report = json.loads((workdir / "reports" / "paper_trading_report.json").read_text(encoding="utf-8"))
    assert report["mode"] == "demo"
    assert report["candles_processed"] == 1


def test_market_data_failure_exits_1_and_audits(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def unreachable(url: str) -> bytes:
        raise urllib.error.URLError("no route")

    monkeypatch.setattr(binance_futures, "_urllib_get", unreachable)

    assert main([]) == 1

    events = audit_events(workdir)
    assert [event["event_type"] for event in events] == ["bot_started", "market_data_unavailable", "bot_stopped"]
    assert events[-1]["context"]["exit_code"] == 1


def test_max_candles_is_rejected_in_backtest_and_when_below_one(
    workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert main(["--max-candles", "0"]) == 2
    backtest_env(monkeypatch)
    assert main(["--max-candles", "5"]) == 2


def test_candles_flag_outside_backtest_is_usage_error(workdir: Path) -> None:
    assert main(["--candles", "x.csv"]) == 2


def test_backtest_without_candles_is_usage_error(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backtest_env(monkeypatch)

    assert main([]) == 2


def test_backtest_with_bad_csv_returns_2(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backtest_env(monkeypatch)
    bad = workdir / "bad.csv"
    bad.write_text("not,a,kline\n", encoding="utf-8")

    assert main(["--candles", str(bad)]) == 2


def test_backtest_end_to_end_writes_readiness_evidence(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backtest_env(monkeypatch)
    folder = workdir / "data" / "candles"
    folder.mkdir(parents=True)
    write_klines(folder / "BTCUSDT-1m-2026-01.csv")

    assert main(["--candles", str(folder)]) == 0

    reports = workdir / "reports"
    for name in (
        "backtest_report.json",
        "out_of_sample_validation_report.json",
        "backtest_run.json",
        "trades.csv",
        "equity_curve.csv",
        "rejected_signals.csv",
    ):
        assert (reports / name).exists(), name
    readiness = evaluate_live_readiness(project_root=workdir, environ={})
    failed = {item.name for item in readiness.failed_checks}
    assert "backtest_report_exists" not in failed
    assert "out_of_sample_validation_report_exists" not in failed
    run = json.loads((reports / "backtest_run.json").read_text(encoding="utf-8"))
    assert run["inputs"]["files"] == [str(folder / "BTCUSDT-1m-2026-01.csv")]
    assert audit_events(workdir)[-1]["context"]["exit_code"] == 0


def test_output_dir_flag(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backtest_env(monkeypatch)
    csv_path = write_klines(workdir / "a.csv")

    assert main(["--candles", str(csv_path), "--output-dir", "out"]) == 0
    assert (workdir / "out" / "backtest_report.json").exists()


def test_live_flag_still_rejected(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVE_TRADING", "true")

    assert main([]) == 2


def test_unknown_flag_exits_2(workdir: Path) -> None:
    with pytest.raises(SystemExit) as info:
        main(["--live"])

    assert info.value.code == 2


def test_crash_during_backtest_still_audits_bot_stopped(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import silver_bot.main as entry

    backtest_env(monkeypatch)
    csv_path = write_klines(workdir / "a.csv")

    def explode(*args, **kwargs):
        raise RuntimeError("engine failure")

    monkeypatch.setattr(entry, "run_backtest", explode)

    with pytest.raises(RuntimeError, match="engine failure"):
        main(["--candles", str(csv_path)])

    last = audit_events(workdir)[-1]
    assert last["event_type"] == "bot_stopped"
    assert last["context"]["exit_code"] == 1
