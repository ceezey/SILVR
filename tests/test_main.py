import json
from pathlib import Path

import pytest

from silvr.backtest import trend_runner
from silvr.exchange import binance_futures
from silvr.main import main
from silvr.storage import PostgresStorage
from silvr.strategy.trend import params

MODE_KEYS = ("MODE", "TRADING_MODE", "PAPER_TRADING", "DEMO_TRADING", "LIVE_TRADING", "KILL_SWITCH_ENABLED", "DATABASE_URL")
NO_STRATEGY = "no strategy available for paper or demo mode yet: trend_ensemble runs in backtest only"


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    for key in MODE_KEYS:
        monkeypatch.delenv(key, raising=False)
    return tmp_path


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record any exchange adapter, HTTP call or storage the run would construct."""

    touched: list[str] = []

    def record(name: str):
        def fail(*args, **kwargs):
            touched.append(name)
            raise AssertionError(f"{name} must not be used in paper or demo mode")

        return fail

    monkeypatch.setattr(binance_futures.BinanceFuturesAdapter, "from_config", classmethod(record("adapter")))
    monkeypatch.setattr(binance_futures.BinanceFuturesAdapter, "__init__", record("adapter"))
    monkeypatch.setattr(binance_futures, "_urllib_get", record("http"))
    monkeypatch.setattr(PostgresStorage, "__init__", record("storage"))
    return touched


def backtest_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_MODE", "backtest")
    monkeypatch.setenv("PAPER_TRADING", "false")


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
def fake_backtest(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Freeze SCALE_K and replace run_trend_backtest; returns the calls it received."""

    calls: list[dict] = []

    def fake(**kwargs):
        calls.append(kwargs)
        return Path(kwargs["output_dir"]) / trend_runner.REPORT_NAME

    monkeypatch.setattr(params, "SCALE_K", 1.25)
    monkeypatch.setattr(trend_runner, "run_trend_backtest", fake)
    return calls


def test_paper_mode_exits_2_without_network(
    workdir: Path, no_network: list[str], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://bot:s3cret-pw@db/silvr")

    assert main([]) == 2

    assert no_network == []
    assert NO_STRATEGY in caplog.text
    events = audit_events(workdir)
    assert [event["event_type"] for event in events] == ["bot_started", "bot_stopped"]
    assert events[-1]["context"]["exit_code"] == 2
    assert "s3cret-pw" not in (workdir / "logs" / "audit.jsonl").read_text(encoding="utf-8")
    assert "s3cret-pw" not in caplog.text


def test_demo_mode_exits_2_without_network(
    workdir: Path, no_network: list[str], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    for key, value in DEMO_ENV.items():
        monkeypatch.setenv(key, value)

    assert main([]) == 2

    assert no_network == []
    assert NO_STRATEGY in caplog.text
    assert "testnet-secret" not in (workdir / "logs" / "audit.jsonl").read_text(encoding="utf-8")


def test_paper_mode_rejects_a_non_binance_base_url(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINANCE_FUTURES_BASE_URL", "https://evil.example")

    assert main([]) == 2


def test_backtest_mode_runs_trend_runner(workdir: Path, monkeypatch: pytest.MonkeyPatch, fake_backtest: list[dict]) -> None:
    backtest_env(monkeypatch)

    assert main(["--candles", "data/candles", "--funding", "data/funding"]) == 0
    assert main(["--candles", "c", "--funding", "f", "--output-dir", "out", "--segments", "all"]) == 0

    assert fake_backtest == [
        {
            "candles_root": Path("data/candles"),
            "funding_root": Path("data/funding"),
            "output_dir": Path("reports"),
            "segments": ("training",),
            "k": 1.25,
        },
        {
            "candles_root": Path("c"),
            "funding_root": Path("f"),
            "output_dir": Path("out"),
            "segments": trend_runner.SEGMENT_NAMES,
            "k": 1.25,
        },
    ]
    assert audit_events(workdir)[-1]["context"]["exit_code"] == 0


def test_backtest_refuses_while_scale_k_is_not_frozen(
    workdir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    backtest_env(monkeypatch)
    monkeypatch.setattr(params, "SCALE_K", None)
    called: list[object] = []
    monkeypatch.setattr(trend_runner, "run_trend_backtest", lambda **kwargs: called.append(kwargs))

    assert main(["--candles", "data/candles", "--funding", "data/funding"]) == 2

    assert called == []
    assert "SCALE_K is not frozen" in capsys.readouterr().err


def test_backtest_with_missing_data_returns_2(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backtest_env(monkeypatch)
    monkeypatch.setattr(params, "SCALE_K", 1.0)

    assert main(["--candles", str(workdir / "none"), "--funding", str(workdir / "none")]) == 2


def test_strategy_choice_only_trend(workdir: Path, monkeypatch: pytest.MonkeyPatch, fake_backtest: list[dict]) -> None:
    backtest_env(monkeypatch)

    assert main(["--strategy", "trend_ensemble"]) == 0
    with pytest.raises(SystemExit) as info:
        main(["--strategy", "nope"])
    assert info.value.code == 2
    assert len(fake_backtest) == 1


def test_live_flag_still_rejected(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVE_TRADING", "true")

    assert main([]) == 2


def test_unknown_flag_exits_2(workdir: Path) -> None:
    with pytest.raises(SystemExit) as info:
        main(["--live"])

    assert info.value.code == 2


def test_crash_during_backtest_still_audits_bot_stopped(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backtest_env(monkeypatch)
    monkeypatch.setattr(params, "SCALE_K", 1.0)

    def explode(**kwargs):
        raise RuntimeError("engine failure")

    monkeypatch.setattr(trend_runner, "run_trend_backtest", explode)

    with pytest.raises(RuntimeError, match="engine failure"):
        main([])

    last = audit_events(workdir)[-1]
    assert last["event_type"] == "bot_stopped"
    assert last["context"]["exit_code"] == 1
