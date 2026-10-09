# G-3 Entrypoint, Batch 2: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the startup-stub entrypoint with config-driven dispatch that runs settings-driven backtests on Binance public kline CSVs and writes the readiness evidence reports, exits 78 for paper and demo, and stops supervisors restart-looping.

**Architecture:** Wave 1 runs three lanes in parallel worktrees off `dev` with no shared files: A (CSV loader), B (risk-config factory refactor and backtest runner), C (systemd and compose). Wave 2 wires `main()` to A and B on `dev`. Then a docs pass and four safety reviewers.

**Tech Stack:** Python 3.11+ (tests on 3.14), standard library only (`csv`, `argparse`, `json`, `math`, `datetime`), pytest 8+.

**Spec:** [docs/superpowers/specs/2026-10-09-g3-entrypoint-design.md](../specs/2026-10-09-g3-entrypoint-design.md)

## Global Constraints

- Run tests with `python -m pytest -q` from the repo root. Baseline at `f8a51b4`: 170 passed.
- No new dependencies; `pyproject.toml` `dependencies = []` stays empty. No network I/O.
- Never loosen a risk, kill-switch, readiness or live gate. `LIVE_TRADING=true` stays rejected at load.
- A backtest never reads or writes the real kill-switch file.
- Exit codes: 0 success, 2 usage, config or data error, 78 mode unavailable.
- Commit only the files a task names. Never `git add -A` or `git add .`; the shared tree holds another session's untracked files (for example `docs/cr-silverbot-operator-dashboard.md`).
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Do not push. Do not edit docs, `AGENTS.md`, `MODEL_CARD.md`, `BRAND.md`, `DESIGN.md` or `.claude/agents/*.md` in code tasks.

## Review Focus

- A CSV file saved with a UTF-8 BOM before the header: must still detect the header (Task A1, `utf-8-sig`).
- Two monthly files that overlap by one identical row: the duplicate is dropped, not an error (Task A1).
- A microsecond-timestamp file (Binance spot since 2025): `close_time` must be open plus one interval, not plus 1 ms (Task A1).
- A backtest run while a real `KILL_SWITCH` file exists and settings enable the kill switch: the backtest runs and the file is byte-identical afterwards (Task B2).
- `main()` called with an unknown flag: argparse exits 2 (Task M1).

---

## Wave 1, Lane A: loader (branch `feat/csv-loader`)

### Task A1: Binance kline CSV loader

**Files:**
- Create: `src/silver_bot/data/csv_loader.py`
- Modify: `src/silver_bot/data/__init__.py` (export `CandleDataError`, `CandleLoadResult`, `load_binance_kline_csv`, `timeframe_interval`; keep `__all__` sorted)
- Test: `tests/test_csv_loader.py`

**Interfaces:**
- Produces: `load_binance_kline_csv(paths: Sequence[str | Path], *, symbol: str, timeframe: str) -> CandleLoadResult`; `CandleLoadResult(candles: list[Candle], files: list[Path], gaps: int)`; `CandleDataError(ValueError)`; `timeframe_interval(timeframe: str) -> timedelta`.

- [ ] **Step 1: Write the failing tests.** Create `tests/test_csv_loader.py`:

```python
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from silver_bot.data import CandleDataError, load_binance_kline_csv, timeframe_interval

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


def test_coarser_file_passes_finer_timeframe_but_not_reverse(tmp_path: Path) -> None:
    five = 5 * MINUTE_MS
    coarse = write(tmp_path / "five.csv", [kline(START_MS + i * five, step_ms=five) for i in range(3)])
    fine = write(tmp_path / "one.csv", [kline(START_MS + i * MINUTE_MS) for i in range(3)])

    assert len(load(coarse, timeframe="1m").candles) == 3
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
```

- [ ] **Step 2: Run to verify failure.** `python -m pytest -q tests/test_csv_loader.py`. Expected: ImportError for `CandleDataError`.

- [ ] **Step 3: Implement.** Create `src/silver_bot/data/csv_loader.py`:

```python
"""Load Binance public kline CSV files (data.binance.vision) into candles.

Offline only: the owner downloads the files; nothing here touches the network.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from silver_bot.models import Candle

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MICROSECOND_THRESHOLD = 10**15
_UNIT_MINUTES = {"m": 1, "h": 60, "d": 1440, "w": 10080}


class CandleDataError(ValueError):
    """Raised when candle input files are missing or malformed."""


@dataclass(frozen=True, slots=True)
class CandleLoadResult:
    """Validated candles plus where they came from."""

    candles: list[Candle]
    files: list[Path]
    gaps: int


def timeframe_interval(timeframe: str) -> timedelta:
    """Return the candle interval for a timeframe such as 1m, 4h or 1d."""

    value = timeframe.strip().lower()
    if len(value) < 2 or not value[:-1].isdigit() or value[-1] not in _UNIT_MINUTES or int(value[:-1]) <= 0:
        raise CandleDataError(f"Unsupported timeframe: {timeframe!r}")
    return timedelta(minutes=int(value[:-1]) * _UNIT_MINUTES[value[-1]])


def load_binance_kline_csv(
    paths: Sequence[str | Path],
    *,
    symbol: str,
    timeframe: str,
) -> CandleLoadResult:
    """Load, validate, de-duplicate and sort Binance kline CSV rows."""

    interval = timeframe_interval(timeframe)
    files = _expand(paths)
    by_open_time: dict[datetime, Candle] = {}
    for file in files:
        for line_number, row in _rows(file):
            candle = _parse_row(row, where=f"{file}:{line_number}", symbol=symbol, timeframe=timeframe)
            existing = by_open_time.get(candle.open_time)
            if existing is None:
                by_open_time[candle.open_time] = candle
            elif existing != candle:
                raise CandleDataError(
                    f"{file}:{line_number}: conflicting duplicate candle at {candle.open_time.isoformat()}"
                )
    if not by_open_time:
        raise CandleDataError("No candle rows found in: " + ", ".join(str(file) for file in files))

    candles = [by_open_time[key] for key in sorted(by_open_time)]
    gaps = 0
    for previous, current in zip(candles, candles[1:]):
        step = current.open_time - previous.open_time
        if step % interval != timedelta(0):
            raise CandleDataError(
                f"Candle spacing {step} before {current.open_time.isoformat()} "
                f"is not a multiple of TIMEFRAME={timeframe}"
            )
        if step > interval:
            gaps += 1
    return CandleLoadResult(candles=candles, files=files, gaps=gaps)


def _expand(paths: Sequence[str | Path]) -> list[Path]:
    if not paths:
        raise CandleDataError("No candle paths given")
    files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            found = sorted(item for item in path.iterdir() if item.is_file() and item.suffix.lower() == ".csv")
            if not found:
                raise CandleDataError(f"No .csv files in {path}")
            files.extend(found)
        elif path.is_file():
            files.append(path)
        else:
            raise CandleDataError(f"Candle path not found: {path}")
    return files


def _rows(file: Path) -> Iterator[tuple[int, list[str]]]:
    with file.open(newline="", encoding="utf-8-sig") as handle:
        for line_number, row in enumerate(csv.reader(handle), start=1):
            if not row or all(not cell.strip() for cell in row):
                continue
            if line_number == 1 and row[0].strip().lower() == "open_time":
                continue
            yield line_number, row


def _parse_row(row: list[str], *, where: str, symbol: str, timeframe: str) -> Candle:
    if len(row) < 7:
        raise CandleDataError(f"{where}: expected at least 7 columns, got {len(row)}")
    try:
        open_raw = int(row[0])
        close_raw = int(row[6])
    except ValueError as exc:
        raise CandleDataError(f"{where}: timestamps must be integers") from exc
    try:
        open_, high, low, close, volume = (float(cell) for cell in row[1:6])
    except ValueError as exc:
        raise CandleDataError(f"{where}: OHLCV values must be numbers") from exc
    if not all(math.isfinite(price) and price > 0 for price in (open_, high, low, close)):
        raise CandleDataError(f"{where}: prices must be finite and positive")
    if not math.isfinite(volume) or volume < 0:
        raise CandleDataError(f"{where}: volume must be finite and non-negative")
    try:
        return Candle(
            symbol=symbol,
            timeframe=timeframe,
            open_time=_to_utc(open_raw),
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume,
            close_time=_to_utc(close_raw + 1),
        )
    except (ValueError, OverflowError) as exc:
        raise CandleDataError(f"{where}: {exc}") from exc


def _to_utc(raw: int) -> datetime:
    """Convert a Binance ms (or, from 10**15 up, µs) timestamp to UTC."""

    if raw < 0:
        raise ValueError("timestamp must be non-negative")
    micros = raw if raw >= _MICROSECOND_THRESHOLD else raw * 1000
    return _EPOCH + timedelta(microseconds=micros)
```

`close_time` is Binance's close plus one unit of its own scale (1 ms, or 1 µs for microsecond files), so it lands on the next interval boundary.

- [ ] **Step 4: Export.** In `src/silver_bot/data/__init__.py` add `from silver_bot.data.csv_loader import CandleDataError, CandleLoadResult, load_binance_kline_csv, timeframe_interval` and the four names to `__all__`, sorted.

- [ ] **Step 5: Run the full suite.** `python -m pytest -q`. Expected: all pass.

- [ ] **Step 6: Commit.** `git add src/silver_bot/data/csv_loader.py src/silver_bot/data/__init__.py tests/test_csv_loader.py` then `git commit -m "feat(data): load Binance public kline CSV files offline (G-3)"`.

---

## Wave 1, Lane B: runner (branch `feat/backtest-runner`)

### Task B1: `build_risk_config` with optional kill switch

**Files:**
- Modify: `src/silver_bot/risk/factory.py`, `src/silver_bot/risk/__init__.py`
- Test: `tests/test_risk_engine.py` (append)

**Interfaces:**
- Produces: `build_risk_config(config: AppConfig, *, kill_switch: bool = True) -> RiskConfig`. `build_risk_engine(config, storage=None)` is unchanged in behaviour.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_risk_engine.py`:

```python
from silver_bot.config import AppConfig, TradingMode
from silver_bot.risk import build_risk_config


def test_build_risk_config_can_drop_kill_switch(tmp_path) -> None:
    config = AppConfig(
        mode=TradingMode.BACKTEST,
        paper_trading=False,
        kill_switch_enabled=True,
        kill_switch_path=tmp_path / "KILL_SWITCH",
        max_risk_per_trade=0.004,
    )

    assert build_risk_config(config).kill_switch_path == tmp_path / "KILL_SWITCH"
    without = build_risk_config(config, kill_switch=False)
    assert without.kill_switch_path is None
    assert without.risk_per_trade == 0.004
```

- [ ] **Step 2: Run to verify failure.** `python -m pytest -q tests/test_risk_engine.py`. Expected: ImportError for `build_risk_config`.

- [ ] **Step 3: Implement.** In `src/silver_bot/risk/factory.py` add, above `build_risk_engine`:

```python
def build_risk_config(config: AppConfig, *, kill_switch: bool = True) -> RiskConfig:
    """Return risk limits from settings.

    `kill_switch=False` drops the kill-switch path. Backtests use it so a
    simulated loss streak can never write the real kill-switch file.
    """

    return RiskConfig(
        risk_per_trade=config.max_risk_per_trade,
        max_daily_loss=config.max_daily_loss,
        max_leverage=config.max_leverage,
        kill_switch_path=config.kill_switch_path if kill_switch and config.kill_switch_enabled else None,
    )
```

and make `build_risk_engine` body `return RiskManagementEngine(build_risk_config(config), state_store=storage)` (keep its docstring). Export `build_risk_config` from `risk/__init__.py` (sorted `__all__`).

- [ ] **Step 4: Run the full suite.** `python -m pytest -q`. Expected: all pass.

- [ ] **Step 5: Commit.** `git add src/silver_bot/risk/factory.py src/silver_bot/risk/__init__.py tests/test_risk_engine.py` then `git commit -m "refactor(risk): add build_risk_config with optional kill switch"`.

### Task B2: settings-driven backtest runner with out-of-sample report

**Files:**
- Create: `src/silver_bot/backtest/runner.py`
- Modify: `src/silver_bot/backtest/__init__.py` (export `BacktestRunSummary`, `build_backtest_config`, `run_backtest`; sorted)
- Test: `tests/test_backtest_runner.py`

**Interfaces:**
- Consumes: `build_risk_config` (B1).
- Produces: `build_backtest_config(config: AppConfig, *, export_dir: Path | None) -> BacktestConfig`; `run_backtest(config: AppConfig, candles: Sequence[Candle], output_dir: str | Path, *, inputs: Mapping[str, Any]) -> BacktestRunSummary`; `BacktestRunSummary(candles: int, report_paths: dict[str, Path])` with keys `backtest_report`, `trades`, `equity_curve`, `rejected_signals`, `out_of_sample_validation_report`, `backtest_run`.

- [ ] **Step 1: Write the failing tests.** Create `tests/test_backtest_runner.py`:

```python
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import silver_bot
from silver_bot.backtest import build_backtest_config, run_backtest
from silver_bot.config import AppConfig, TradingMode
from silver_bot.models import Candle
from silver_bot.readiness import evaluate_live_readiness


def candles(count: int = 50) -> list[Candle]:
    start = datetime(2026, 1, 2, 14, 0, tzinfo=UTC)
    result = []
    for index in range(count):
        opened = start + timedelta(minutes=index)
        base = 100 + (index % 7)
        result.append(
            Candle(
                symbol="BTCUSDT",
                timeframe="1m",
                open_time=opened,
                close_time=opened + timedelta(minutes=1),
                open=base,
                high=base + 2,
                low=base - 2,
                close=base + 1,
                volume=1000,
            )
        )
    return result


def backtest_settings(tmp_path: Path, **overrides) -> AppConfig:
    values = dict(mode=TradingMode.BACKTEST, paper_trading=False)
    values.update(overrides)
    return AppConfig(**values)


def test_run_writes_all_reports(tmp_path: Path) -> None:
    summary = run_backtest(backtest_settings(tmp_path), candles(), tmp_path / "reports", inputs={"files": ["x.csv"], "gaps": 0})

    assert summary.candles == 50
    assert set(summary.report_paths) == {
        "backtest_report",
        "trades",
        "equity_curve",
        "rejected_signals",
        "out_of_sample_validation_report",
        "backtest_run",
    }
    for path in summary.report_paths.values():
        assert path.exists()


def test_reports_pass_readiness_report_checks(tmp_path: Path) -> None:
    summary = run_backtest(backtest_settings(tmp_path), candles(), tmp_path / "reports", inputs={})

    report = evaluate_live_readiness(
        project_root=tmp_path,
        environ={
            "BACKTEST_REPORT_PATH": str(summary.report_paths["backtest_report"]),
            "OOS_VALIDATION_REPORT_PATH": str(summary.report_paths["out_of_sample_validation_report"]),
        },
    )
    failed = {item.name for item in report.failed_checks}

    assert "backtest_report_exists" not in failed
    assert "out_of_sample_validation_report_exists" not in failed


def test_out_of_sample_report_structure(tmp_path: Path) -> None:
    summary = run_backtest(backtest_settings(tmp_path), candles(), tmp_path / "reports", inputs={})

    oos = json.loads(summary.report_paths["out_of_sample_validation_report"].read_text(encoding="utf-8"))

    assert oos["method"] == "chronological_split"
    assert oos["parameters_tuned"] is False
    assert oos["fractions"] == {"training": 0.6, "validation": 0.2, "final_test": 0.2}
    assert [oos["segments"][name]["candles"] for name in ("training", "validation", "final_test")] == [30, 10, 10]
    assert oos["segments"]["training"]["end"] < oos["segments"]["validation"]["start"]
    assert oos["segments"]["validation"]["end"] < oos["segments"]["final_test"]["start"]
    assert isinstance(oos["segments"]["final_test"]["metrics"], dict)


def test_run_record_lists_inputs_and_costs(tmp_path: Path) -> None:
    summary = run_backtest(backtest_settings(tmp_path), candles(), tmp_path / "reports", inputs={"files": ["a.csv"], "gaps": 2})

    run = json.loads(summary.report_paths["backtest_run"].read_text(encoding="utf-8"))

    assert run["inputs"] == {"files": ["a.csv"], "gaps": 2}
    assert run["candles"] == 50
    assert run["symbol"] == "BTCUSDT"
    assert run["timeframe"] == "1m"
    assert run["slippage_bps"] == 5.0
    assert run["spread_bps"] == 3.0
    assert run["risk_per_trade"] == 0.005
    assert run["ml_filter_enabled"] is False
    assert run["package_version"] == silver_bot.__version__
    assert run["first_open_time"] == "2026-01-02T14:00:00+00:00"


def test_backtest_ignores_and_preserves_real_kill_switch(tmp_path: Path) -> None:
    kill_file = tmp_path / "KILL_SWITCH"
    kill_file.write_text('{"reason": "owner"}', encoding="utf-8")
    settings = backtest_settings(tmp_path, kill_switch_enabled=True, kill_switch_path=kill_file)

    assert build_backtest_config(settings, export_dir=None).risk.kill_switch_path is None
    summary = run_backtest(settings, candles(), tmp_path / "reports", inputs={})

    assert kill_file.read_text(encoding="utf-8") == '{"reason": "owner"}'
    assert "Kill switch is active" not in summary.report_paths["rejected_signals"].read_text(encoding="utf-8")


def test_settings_reach_backtest_config(tmp_path: Path) -> None:
    settings = backtest_settings(
        tmp_path,
        max_risk_per_trade=0.004,
        max_daily_loss=0.01,
        max_leverage=2.0,
        ml_filter_enabled=True,
        ml_registry_path=tmp_path / "registry.json",
        ml_min_probability=0.7,
        ml_reduce_risk_threshold=0.6,
    )

    config = build_backtest_config(settings, export_dir=tmp_path)

    assert (config.risk.risk_per_trade, config.risk.max_daily_loss, config.risk.max_leverage) == (0.004, 0.01, 2.0)
    assert config.ml_filter.enabled is True
    assert config.ml_filter.registry_path == tmp_path / "registry.json"
    assert (config.ml_filter.min_probability, config.ml_filter.reduce_risk_threshold) == (0.7, 0.6)
    assert config.export_dir == tmp_path
    assert (config.slippage_bps, config.spread_bps) == (5.0, 3.0)


def test_empty_candles_raise(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one candle"):
        run_backtest(backtest_settings(tmp_path), [], tmp_path / "reports", inputs={})
```

- [ ] **Step 2: Run to verify failure.** `python -m pytest -q tests/test_backtest_runner.py`. Expected: ImportError for `build_backtest_config`.

- [ ] **Step 3: Implement.** Create `src/silver_bot/backtest/runner.py`:

```python
"""Settings-driven backtest run that writes the readiness evidence reports."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import silver_bot
from silver_bot.backtest.engine import BacktestEngine
from silver_bot.backtest.models import BacktestConfig
from silver_bot.backtest.reporting import _json_safe
from silver_bot.backtest.validation import BacktestValidationSuite
from silver_bot.config import AppConfig
from silver_bot.ml import MLFilterConfig
from silver_bot.models import Candle
from silver_bot.risk import build_risk_config

TRAINING_FRACTION = 0.6
VALIDATION_FRACTION = 0.2


@dataclass(frozen=True, slots=True)
class BacktestRunSummary:
    """Where a backtest run wrote its reports."""

    candles: int
    report_paths: dict[str, Path]


def build_backtest_config(config: AppConfig, *, export_dir: Path | None) -> BacktestConfig:
    """Return a backtest config whose risk and ML settings come from AppConfig.

    The kill switch is always dropped: a backtest must never read or write the
    real kill-switch file.
    """

    return BacktestConfig(
        risk=build_risk_config(config, kill_switch=False),
        ml_filter=MLFilterConfig(
            enabled=config.ml_filter_enabled,
            registry_path=config.ml_registry_path,
            min_probability=config.ml_min_probability,
            reduce_risk_threshold=config.ml_reduce_risk_threshold,
        ),
        export_dir=export_dir,
    )


def run_backtest(
    config: AppConfig,
    candles: Sequence[Candle],
    output_dir: str | Path,
    *,
    inputs: Mapping[str, Any],
) -> BacktestRunSummary:
    """Run the full-period backtest and a chronological out-of-sample split."""

    if not candles:
        raise ValueError("run_backtest needs at least one candle")
    directory = Path(output_dir)
    ordered = sorted(candles, key=lambda candle: candle.open_time)

    full = BacktestEngine(config=build_backtest_config(config, export_dir=directory)).run(ordered)

    split = BacktestValidationSuite().chronological_split(
        ordered,
        training_fraction=TRAINING_FRACTION,
        validation_fraction=VALIDATION_FRACTION,
    )
    oos_path = directory / "out_of_sample_validation_report.json"
    _write_json(
        oos_path,
        {
            "method": "chronological_split",
            "fractions": {
                "training": TRAINING_FRACTION,
                "validation": VALIDATION_FRACTION,
                "final_test": round(1 - TRAINING_FRACTION - VALIDATION_FRACTION, 10),
            },
            "parameters_tuned": False,
            "segments": {
                "training": _segment(config, split.training),
                "validation": _segment(config, split.validation),
                "final_test": _segment(config, split.final_test),
            },
        },
    )

    settings = build_backtest_config(config, export_dir=None)
    run_path = directory / "backtest_run.json"
    _write_json(
        run_path,
        {
            "inputs": dict(inputs),
            "symbol": config.symbol,
            "timeframe": config.timeframe,
            "candles": len(ordered),
            "first_open_time": ordered[0].open_time.isoformat(),
            "last_open_time": ordered[-1].open_time.isoformat(),
            "slippage_bps": settings.slippage_bps,
            "spread_bps": settings.spread_bps,
            "maker_fee": settings.maker_fee,
            "taker_fee": settings.taker_fee,
            "ml_filter_enabled": settings.ml_filter.enabled,
            "risk_per_trade": settings.risk.risk_per_trade,
            "package_version": silver_bot.__version__,
        },
    )

    paths = dict(full.export_paths)
    paths["out_of_sample_validation_report"] = oos_path
    paths["backtest_run"] = run_path
    return BacktestRunSummary(candles=len(ordered), report_paths=paths)


def _segment(config: AppConfig, candles: list[Candle]) -> dict[str, Any]:
    if not candles:
        return {"candles": 0, "start": None, "end": None, "metrics": None}
    result = BacktestEngine(config=build_backtest_config(config, export_dir=None)).run(candles)
    return {
        "candles": len(candles),
        "start": candles[0].open_time.isoformat(),
        "end": candles[-1].open_time.isoformat(),
        "metrics": result.metrics,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(dict(payload)), indent=2, sort_keys=True), encoding="utf-8")
```

Each segment gets a new engine, so risk state starts fresh per segment. No parameter is chosen from any segment.

- [ ] **Step 4: Export.** In `src/silver_bot/backtest/__init__.py` add `from silver_bot.backtest.runner import BacktestRunSummary, build_backtest_config, run_backtest` and the names to `__all__`, sorted. Then confirm no import cycle: `PYTHONPATH=src python -c "import silver_bot.backtest, silver_bot.risk, silver_bot.ml"` and `PYTHONPATH=src python -c "import silver_bot.ml, silver_bot.backtest"`.

- [ ] **Step 5: Run the full suite.** `python -m pytest -q`. Expected: all pass. If `test_out_of_sample_report_structure` shows split sizes other than 30/10/10 for 50 candles, read `chronological_split` and fix the test expectation only if the helper's arithmetic (`int(len * fraction)`) gives different numbers; record that in the report.

- [ ] **Step 6: Commit.** `git add src/silver_bot/backtest/runner.py src/silver_bot/backtest/__init__.py tests/test_backtest_runner.py` then `git commit -m "feat(backtest): settings-driven runner with out-of-sample report (G-3, G-1)"`.

---

## Wave 1, Lane C: deploy (branch `feat/deploy-no-restart-loop`)

### Task C1: stop supervisors looping on exit 78 (H-4)

**Files:**
- Modify: `deploy/systemd/silver-bot.service` (lines 11-14)
- Modify: `docker-compose.yaml` (`bot` service `restart`; `backtest` and `research` `command`)
- Test: `tests/test_deployment_files.py` (append)

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_deployment_files.py`:

```python
def test_systemd_propagates_exit_code_and_stops_on_mode_unavailable() -> None:
    service = read("deploy/systemd/silver-bot.service")

    assert "up bot --exit-code-from bot" in service
    assert "RestartPreventExitStatus=78" in service


def test_compose_bot_does_not_self_restart() -> None:
    compose = read("docker-compose.yaml")
    bot_block = compose.split("\n  bot:\n", 1)[1].split("\n  paper:\n", 1)[0]

    assert 'restart: "no"' in bot_block
    assert "unless-stopped" not in compose


def test_compose_backtest_services_read_candles_directory() -> None:
    compose = read("docker-compose.yaml")

    assert compose.count('command: ["python", "-m", "silver_bot", "--candles", "/app/data/candles"]') == 2
```

- [ ] **Step 2: Run to verify failure.** `python -m pytest -q tests/test_deployment_files.py`. Expected: the three new tests fail.

- [ ] **Step 3: Implement.**
  - `deploy/systemd/silver-bot.service`: change `ExecStart=/usr/bin/docker compose -f /opt/silver-bot/docker-compose.yaml up bot` to `ExecStart=/usr/bin/docker compose -f /opt/silver-bot/docker-compose.yaml up bot --exit-code-from bot`, and add the line `RestartPreventExitStatus=78` directly after `RestartSec=10`. Leave `Restart=always`, `User`, `Group` and `ExecStop` unchanged.
  - `docker-compose.yaml`: in the `bot` service change `restart: unless-stopped` to `restart: "no"`. In the `backtest` and `research` services change `command: ["python", "-m", "silver_bot"]` to `command: ["python", "-m", "silver_bot", "--candles", "/app/data/candles"]`. Leave the `paper` and `demo` commands and every environment value unchanged.

- [ ] **Step 4: Run the full suite.** `python -m pytest -q`. Expected: all pass, including the existing deploy safety assertions.

- [ ] **Step 5: Commit.** `git add deploy/systemd/silver-bot.service docker-compose.yaml tests/test_deployment_files.py` then `git commit -m "fix(deploy): propagate exit code and stop restarting on exit 78 (H-4)"`.

---

## Wave 2 (on `dev`, after merging A, B, C)

### Task M1: config-driven dispatch in `main()`

**Files:**
- Modify: `src/silver_bot/main.py` (replace body)
- Test: `tests/test_main.py` (create)

**Interfaces:**
- Consumes: `load_binance_kline_csv`, `CandleDataError` (A1); `run_backtest` (B2).
- Produces: `main(argv: list[str] | None = None) -> int`; constants `EXIT_MODE_UNAVAILABLE = 78`, `MODE_UNAVAILABLE_MESSAGE`.

- [ ] **Step 1: Write the failing tests.** Create `tests/test_main.py`:

```python
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from silver_bot.main import EXIT_MODE_UNAVAILABLE, main
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


def test_paper_mode_exits_78_and_audits(workdir: Path) -> None:
    assert main([]) == EXIT_MODE_UNAVAILABLE == 78

    events = audit_events(workdir)
    assert [event["event_type"] for event in events] == ["bot_started", "mode_unavailable", "bot_stopped"]
    assert "G-13" in events[1]["message"]
    assert events[2]["context"]["exit_code"] == 78


def test_demo_mode_exits_78(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in {
        "MODE": "demo",
        "DEMO_TRADING": "true",
        "PAPER_TRADING": "false",
        "BINANCE_TESTNET": "true",
        "BINANCE_API_KEY": "testnet-key",
        "BINANCE_API_SECRET": "testnet-secret",
        "KILL_SWITCH_ENABLED": "true",
        "KILL_SWITCH_PATH": "KILL_SWITCH",
    }.items():
        monkeypatch.setenv(key, value)

    assert main([]) == 78


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
```

- [ ] **Step 2: Run to verify failure.** `python -m pytest -q tests/test_main.py`. Expected: ImportError for `EXIT_MODE_UNAVAILABLE`.

- [ ] **Step 3: Implement.** Replace `src/silver_bot/main.py`:

```python
"""Application entrypoint: run the configured mode.

Backtest mode runs on local Binance kline CSV files. Paper and demo modes are
not available until real market data exists (G-13) and exit 78 so that
supervisors stop restarting. Live trading cannot be configured at all.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from silver_bot.backtest.runner import run_backtest
from silver_bot.config import AppConfig, ConfigError, TradingMode, load_config
from silver_bot.data.csv_loader import CandleDataError, load_binance_kline_csv
from silver_bot.monitoring import StructuredAuditLogger
from silver_bot.storage import SQLiteStorage
from silver_bot.utils.logging import get_logger


logger = get_logger(__name__)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_MODE_UNAVAILABLE = 78
MODE_UNAVAILABLE_MESSAGE = "mode not available yet: needs market data (G-13)"


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""

    parser = argparse.ArgumentParser(
        prog="silver-bot",
        description="Run the configured Silver Bot mode. Live trading is not available.",
    )
    parser.add_argument(
        "--candles",
        action="append",
        default=[],
        metavar="PATH",
        help="Binance kline CSV file or directory of them (backtest mode only; repeatable).",
    )
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="Directory for backtest reports (default: reports).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Load configuration, run the configured mode and return an exit code."""

    args = build_parser().parse_args(argv)
    try:
        config = load_config()
    except ConfigError as exc:
        logger.error("configuration rejected: %s", exc)
        return EXIT_USAGE

    storage = SQLiteStorage(config.database_path)
    storage.initialize()
    audit = StructuredAuditLogger("logs/audit.jsonl")
    audit.log(
        "bot_started",
        "Silver bot started",
        context={
            "mode": config.mode.value,
            "paper_trading": config.paper_trading,
            "database_path": str(config.database_path),
            "ml_filter_enabled": config.ml_filter_enabled,
            "telegram_enabled": config.telegram_enabled,
        },
    )
    exit_code = _dispatch(config, args, audit)
    audit.log("bot_stopped", "Silver bot stopped", context={"mode": config.mode.value, "exit_code": exit_code})
    return exit_code


def _dispatch(config: AppConfig, args: argparse.Namespace, audit: StructuredAuditLogger) -> int:
    if config.mode == TradingMode.BACKTEST:
        return _run_backtest(config, args)
    if args.candles:
        logger.error("--candles only applies to backtest mode")
        return EXIT_USAGE
    logger.error("%s %s", config.mode.value, MODE_UNAVAILABLE_MESSAGE)
    audit.log("mode_unavailable", MODE_UNAVAILABLE_MESSAGE, context={"mode": config.mode.value}, level="WARNING")
    return EXIT_MODE_UNAVAILABLE


def _run_backtest(config: AppConfig, args: argparse.Namespace) -> int:
    if not args.candles:
        logger.error("backtest mode needs --candles")
        return EXIT_USAGE
    try:
        loaded = load_binance_kline_csv(args.candles, symbol=config.symbol, timeframe=config.timeframe)
    except CandleDataError as exc:
        logger.error("candle data rejected: %s", exc)
        return EXIT_USAGE
    summary = run_backtest(
        config,
        loaded.candles,
        Path(args.output_dir),
        inputs={"files": [str(path) for path in loaded.files], "gaps": loaded.gaps},
    )
    for name, path in sorted(summary.report_paths.items()):
        logger.info("wrote %s: %s", name, path)
    logger.info("backtest complete: %d candles, %d gaps", summary.candles, loaded.gaps)
    return EXIT_OK
```

Check `StructuredAuditLogger.log` accepts `level=` as a keyword (`monitoring/audit.py:53-60`); if it does not, drop the `level=` argument and note it.

- [ ] **Step 4: Run the full suite.** `python -m pytest -q`. Expected: all pass. Also run `TRADING_MODE=paper PYTHONPATH=src python -m silver_bot; echo $?` from a scratch directory and expect `78`.

- [ ] **Step 5: Commit.** `git add src/silver_bot/main.py tests/test_main.py` then `git commit -m "feat: config-driven entrypoint with backtest runs and exit 78 (G-3, H-4)"`.

---

## Integration

### Task I1: Merge wave 1
- [ ] `git merge --no-ff` `feat/csv-loader`, `feat/backtest-runner`, `feat/deploy-no-restart-loop` into `dev` in that order; `python -m pytest -q` after each.

### Task I2: Docs pass (after M1)
Per spec section 5. Cite `file:line` on `dev`. Commit only the edited docs and materialized files: `docs: reconcile suite with G-3 entrypoint batch 2`.

### Task I3: Safety review
- [ ] Run the four reviewers on `git diff f8a51b4..dev -- src tests deploy docker-compose.yaml Dockerfile`. Verify blocking findings before acting.

### Task I4: Final verification
- [ ] `python -m pytest -q` passes; `python tools/materialize_docs.py --check` reports no changes; `git status --short` shows only other sessions' untracked files.
