"""Run trend_ensemble over the chronological 0.6 / 0.2 / 0.2 split and write the out-of-sample report.

Candles stream one month file at a time (all symbols of one month in memory, never the whole history).
Each requested segment runs on its own engine (fresh risk engine and kill switch) on a fresh
INITIAL_BALANCE account, warmed up with the daily bars of every 1m candle before its first minute.
A segment not requested is not simulated and is written as {"skipped": true}.

    python -m silvr.backtest.trend_runner --candles-root data/candles --funding-root data/funding \\
        --output-dir reports/trend --segments training|all
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from silvr.backtest.models import BacktestConfig, EquityPoint
from silvr.backtest.reporting import json_safe
from silvr.backtest.trend_engine import TrendDataError, TrendPortfolioEngine
from silvr.data.csv_loader import CandleDataError, load_binance_kline_csv
from silvr.data.funding import FundingDataError, FundingSchedule, load_funding_csv
from silvr.models import Candle
from silvr.risk import RiskConfig
from silvr.strategy.trend import params
from silvr.strategy.trend.signals import daily_bars

REPORT_NAME = "out_of_sample_validation_report.json"
TRAINING_FRACTION = 0.6
VALIDATION_FRACTION = 0.2
SEGMENT_NAMES = ("training", "validation", "final_test")
TARGET_WEEKLY_NET = 50.0
_MINUTE = timedelta(minutes=1)
_MONTH = re.compile(r"-1m-(\d{4}-\d{2})\.csv$")


def find_candle_files(root: Path, symbol: str) -> list[Path]:
    """Every `{symbol}-1m-*.csv` under `root`, sorted."""

    files = sorted(Path(root).rglob(f"{symbol}-1m-*.csv"))
    if not files:
        raise FileNotFoundError(f"no {symbol}-1m-*.csv files under {root}")
    return files


def segment_bounds(first: datetime, last: datetime) -> dict[str, tuple[datetime, datetime]]:
    """(first, last) 1m open time of each segment, split by minute count like `chronological_split`."""

    count = int((last - first) / _MINUTE) + 1
    training_end = int(count * TRAINING_FRACTION)
    validation_end = training_end + int(count * VALIDATION_FRACTION)
    edges = (0, training_end, validation_end, count)
    return {
        name: (first + edges[i] * _MINUTE, first + (edges[i + 1] - 1) * _MINUTE)
        for i, name in enumerate(SEGMENT_NAMES)
    }


def success_standard(daily_equity: Sequence[EquityPoint], initial_balance: float) -> dict[str, Any]:
    """Net change of marked equity per ISO week (UTC); the first week is measured from the initial balance."""

    closing: dict[tuple[int, int], float] = {}
    for point in daily_equity:  # in time order: the last point of a week is its closing equity
        year, week, _ = point.timestamp.astimezone(UTC).isocalendar()
        closing[(year, week)] = point.equity
    nets: list[float] = []
    previous = initial_balance
    for week in sorted(closing):
        nets.append(closing[week] - previous)
        previous = closing[week]
    average = sum(nets) / len(nets) if nets else 0.0
    return {
        "weeks": len(nets),
        "average_weekly_net": average,
        "losing_week_share": sum(net < 0 for net in nets) / len(nets) if nets else 0.0,
        "worst_week": min(nets, default=0.0),
        "target_weekly_net": TARGET_WEEKLY_NET,
        "met": average >= TARGET_WEEKLY_NET,
    }


def realized_volatility(daily_equity: Sequence[EquityPoint], initial_balance: float) -> float:
    """Annualized sample stdev of daily marked-equity simple returns (first one from the initial balance)."""

    equities = [initial_balance, *(point.equity for point in daily_equity)]
    returns = [now / before - 1.0 for before, now in zip(equities, equities[1:])]
    return statistics.stdev(returns) * math.sqrt(365) if len(returns) >= 2 else 0.0


def _month_files(root: Path, symbol: str) -> dict[str, Path]:
    by_month: dict[str, Path] = {}
    for path in find_candle_files(root, symbol):
        match = _MONTH.search(path.name)
        if match is None or match.group(1) in by_month:
            raise TrendDataError(symbol, None, f"unexpected or duplicate candle file {path}")
        by_month[match.group(1)] = path
    return by_month


def _check_months(files: Mapping[str, Mapping[str, Path]]) -> list[str]:
    """Every symbol must have the same months; fail closed naming the first symbol and month that is missing."""

    months = sorted({month for by_month in files.values() for month in by_month})
    for symbol in params.SYMBOLS:
        for month in months:
            if month not in files[symbol]:
                raise TrendDataError(symbol, datetime.fromisoformat(f"{month}-01T00:00:00+00:00"), "no candle file")
    return months


def _month_candles(path: Path, symbol: str) -> list[Candle]:
    return load_binance_kline_csv([path], symbol=symbol, timeframe="1m").candles


def _month_span(month: str) -> tuple[datetime, datetime]:
    first = datetime.fromisoformat(f"{month}-01T00:00:00+00:00")
    return first, (first + timedelta(days=32)).replace(day=1)


def _minutes(
    files: Mapping[str, Mapping[str, Path]], start: datetime, end: datetime
) -> Iterator[dict[str, Candle]]:
    """A fresh {symbol: candle} dict per minute in [start, end], one month of all symbols at a time."""

    symbols = params.SYMBOLS
    lead = symbols[0]
    for month in sorted(files[lead]):
        month_start, month_end = _month_span(month)
        if month_end <= start or month_start > end:
            continue
        loaded = {symbol: _month_candles(files[symbol][month], symbol) for symbol in symbols}
        times = [candle.open_time for candle in loaded[lead]]
        for symbol in symbols[1:]:
            if [candle.open_time for candle in loaded[symbol]] != times:
                raise TrendDataError(symbol, month_start, f"1m minutes differ from {lead}")
        for i, time in enumerate(times):
            if time > end:
                return
            if time >= start:
                yield {symbol: loaded[symbol][i] for symbol in symbols}


def _candles_through(path_by_month: Mapping[str, Path], symbol: str, stop: datetime) -> Iterator[Candle]:
    """One symbol's candles from the start of the data up to and including `stop`, a month at a time."""

    for month in sorted(path_by_month):
        month_start, _ = _month_span(month)
        if month_start > stop:
            return
        for candle in _month_candles(path_by_month[month], symbol):
            if candle.open_time > stop:
                return
            yield candle


def _history(files: Mapping[str, Mapping[str, Path]], start: datetime) -> dict[str, list[Any]]:
    """Daily bars of every candle through `start`; the segment's own (open) first day is never emitted."""

    history = {}
    for symbol in params.SYMBOLS:
        try:
            history[symbol] = daily_bars(_candles_through(files[symbol], symbol, start))
        except ValueError as exc:
            raise TrendDataError(symbol, None, str(exc)) from exc
    return history


def _data_bounds(files: Mapping[str, Mapping[str, Path]], months: Sequence[str]) -> tuple[datetime, datetime]:
    lead = params.SYMBOLS[0]
    first = _month_candles(files[lead][months[0]], lead)[0].open_time
    last = _month_candles(files[lead][months[-1]], lead)[-1].open_time
    return first, last


def run_trend_backtest(
    *, candles_root: Path, funding_root: Path, output_dir: Path, segments: tuple[str, ...], k: float
) -> Path:
    """Simulate the requested segments, write the report and return its path."""

    files = {symbol: _month_files(candles_root, symbol) for symbol in params.SYMBOLS}
    months = _check_months(files)
    bounds = segment_bounds(*_data_bounds(files, months))
    funding = {
        symbol: FundingSchedule(load_funding_csv(Path(funding_root) / f"{symbol}-funding.csv"))
        for symbol in params.SYMBOLS
    }
    for name in segments:
        for symbol in params.SYMBOLS:
            try:
                funding[symbol].check_coverage(*bounds[name])
            except FundingDataError as exc:
                raise TrendDataError(symbol, None, f"funding for {name}: {exc}") from exc

    config = BacktestConfig(
        initial_balance=params.INITIAL_BALANCE, risk=RiskConfig.trend(), slippage_bps=5.0, spread_bps=3.0
    )
    report: dict[str, Any] = {
        "strategy": params.STRATEGY_NAME,
        "symbols": list(params.SYMBOLS),
        "k": k,
        "parameters_tuned": False,
        "segments": {},
    }
    for name, (start, end) in bounds.items():
        if name not in segments:
            report["segments"][name] = {"skipped": True}
            continue
        engine = TrendPortfolioEngine(config, funding=funding, history=_history(files, start), k=k)
        result = engine.run(_minutes(files, start, end))
        tripped = result.kill_switch_tripped_at
        report["segments"][name] = {
            "candles": (int((end - start) / _MINUTE) + 1) * len(params.SYMBOLS),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "metrics": result.metrics,
            "kill_switch": {"trips": int(tripped is not None), "tripped_at": tripped},
            "success_standard": success_standard(result.daily_equity, config.initial_balance),
            "realized_volatility": realized_volatility(result.daily_equity, config.initial_balance),
            "rejections": dict(result.rejections),
        }

    path = Path(output_dir) / REPORT_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(report), indent=2, sort_keys=True), encoding="utf-8")
    return path


def calibrate_k(
    *, candles_root: Path, funding_root: Path, max_iterations: int = 6, tolerance: float = 0.005
) -> tuple[float, list[tuple[float, float]]]:
    """Find the scale factor k that gives the target volatility on the training segment only.

    Each run scales k by target / realized. Stops within `tolerance` of the target (returning the k that
    produced it) or after `max_iterations` runs (returning the last k run). Prints only k and volatility.
    """

    target = params.VOL_TARGET
    k = 1.0
    history: list[tuple[float, float]] = []
    for _ in range(max_iterations):
        with tempfile.TemporaryDirectory() as output_dir:
            report_path = run_trend_backtest(
                candles_root=candles_root, funding_root=funding_root, output_dir=Path(output_dir),
                segments=("training",), k=k,
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
        realized = report["segments"]["training"]["realized_volatility"]
        history.append((k, realized))
        print(f"k={k:.4f} realized_volatility={realized:.4f}")
        if realized <= 0:
            raise ValueError("cannot calibrate k: the training segment has no volatility (no trades)")
        if abs(realized - target) <= tolerance:
            break
        k *= target / realized
    return history[-1][0], history


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest trend_ensemble and write the out-of-sample report.")
    parser.add_argument("--candles-root", type=Path, default=Path("data/candles"))
    parser.add_argument("--funding-root", type=Path, default=Path("data/funding"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--segments", choices=("training", "all"), default="training")
    args = parser.parse_args(argv)
    if params.SCALE_K is None:
        print("error: SCALE_K is not frozen; calibrate it on the training segment first", file=sys.stderr)
        return 2
    segments = SEGMENT_NAMES if args.segments == "all" else ("training",)
    try:
        path = run_trend_backtest(
            candles_root=args.candles_root,
            funding_root=args.funding_root,
            output_dir=args.output_dir,
            segments=segments,
            k=params.SCALE_K,
        )
    except (TrendDataError, CandleDataError, FundingDataError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
