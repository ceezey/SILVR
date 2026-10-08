# Backtest and Evidence Runbook (RUNBOOK)

**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Version:** 0.1
**Owner:** Cian Jake Francisco
**Status:** Draft
**Last updated:** 2026-10-09
**Last reconciled:** 2026-10-08 against code at commit `62037d1`

This runbook says how to run the backtest engine, where its outputs land, how to produce a chronological out-of-sample split, how to check that the report files are not empty, and how to run the live readiness checker on them. It absorbs the "outputs" parts of the old `BACKTESTING.md`.

**What does not exist (read this first).**

- There is no backtest command line. `python -m silver_bot`, `python main.py` and the `silver-bot` script all ignore the mode and run a startup stub (D-1, G-3). The Compose `backtest` and `research` profiles run the same stub. The engine is a Python library, so every step below is a short Python script.
- Real historical data fetching is not implemented. `HistoricalOHLCVFetcher` delegates to the exchange adapter, and the only adapter's `fetch_ohlcv` raises `NotImplementedError("Binance Futures OHLCV network fetching is not implemented in Phase 1")` (G-13). You must supply candles yourself, for example from a CSV you downloaded elsewhere.
- No code writes `reports/out_of_sample_validation_report.json`, and nothing evaluates pass or fail criteria. The split helper `BacktestValidationSuite.chronological_split` exists but is not called by the engine, and walk-forward, Monte Carlo and sensitivity runs are absent (G-12).
- The three evidence files in `reports/` are 0 bytes today (G-1). This runbook produces evidence files under a folder you choose; it does not claim any strategy performance.

Related documents: [prd-silverbot.md](prd-silverbot.md) (PRD-F2), [sdd-silverbot.md](sdd-silverbot.md) (backtest design and file artifacts), [rfc-silverbot-readiness-gates.md](rfc-silverbot-readiness-gates.md) (readiness checkers), [runbook-local-dev.md](runbook-local-dev.md) (setup), [scrutiny-silverbot.md](scrutiny-silverbot.md) (G-1, G-2, G-11, G-12, G-13).

## Steps

Run every command from one working folder with the virtual environment active (see [runbook-local-dev.md](runbook-local-dev.md)). The examples use a scratch folder so that nothing is written into the repository `reports/` directory.

1. **Supply candles.** Create a CSV with the header `open_time,open,high,low,close,volume`, one row per candle, `open_time` in ISO 8601 with a UTC offset, for example `2026-01-02T15:00:00+00:00`. Candles need not be in order (the engine sorts them), but each row must have `high >= max(open, close)` and `low <= min(open, close)` or loading raises `ValueError`. The fetcher cannot supply this file; it raises `NotImplementedError` (shown in Verify).

2. **Write the run script** `run_backtest.py`. It uses only the engine's public API (`BacktestEngine`, `BacktestConfig`, `Candle`, the strategy classes):

   ```python
   """Run the Silver Bot backtest engine on locally supplied candles."""
   import csv
   import sys
   from datetime import UTC, datetime, timedelta
   from pathlib import Path

   from silver_bot.backtest import BacktestConfig, BacktestEngine
   from silver_bot.models import Candle
   from silver_bot.strategy import SilverBulletStrategyConfig, SilverBulletStrategyEngine


   def load_candles(path: str) -> list[Candle]:
       """Read candles from a CSV with columns open_time,open,high,low,close,volume."""
       rows = []
       with open(path, newline="") as handle:
           for row in csv.DictReader(handle):
               opened = datetime.fromisoformat(row["open_time"]).astimezone(UTC)
               rows.append(Candle(
                   symbol="BTCUSDT", timeframe="1m",
                   open_time=opened, close_time=opened + timedelta(minutes=1),
                   open=float(row["open"]), high=float(row["high"]),
                   low=float(row["low"]), close=float(row["close"]),
                   volume=float(row["volume"]),
               ))
       return rows


   if __name__ == "__main__":
       candles = load_candles(sys.argv[1])
       config = BacktestConfig(slippage_bps=1.0, spread_bps=1.0, export_dir=Path(sys.argv[2]))
       strategy = SilverBulletStrategyEngine(
           SilverBulletStrategyConfig(swing_lookback=2, atr_period=3, minimum_rr=2.0, minimum_signal_score=70)
       )
       result = BacktestEngine(strategy=strategy, config=config).run(candles)
       print(result.metrics["total_trades"], result.metrics["net_profit"])
       print(result.export_paths)
   ```

   Notes on the settings. `BacktestConfig` defaults are `initial_balance=10000.0`, `maker_fee=0.0002`, `taker_fee=0.0005`, `slippage_bps=5.0` and `spread_bps=3.0` (non-zero since `59ed6d5`, G-11 closed; before that both were zero). The script sets 1 bps each explicitly, which is below the defaults; the Verify numbers below were produced with those 1 bps values. The strategy settings in the script (`swing_lookback=2`, `atr_period=3`, `minimum_signal_score=70`) are the values the unit tests use for a 10-candle sample; they are not tuned for real data. For real data start from `SilverBulletStrategyEngine()` defaults and choose settings on the training and validation slices only (step 5). The engine always runs the risk engine and the kill-switch check; the ML filter is off unless configured.

3. **Run the backtest:**

   ```bash
   python run_backtest.py candles.csv out
   ```

   The script prints the trade count, net profit and the four exported paths. The engine also appends audit lines to `logs/audit.jsonl` in the current folder.

4. **Find the outputs.** With `export_dir` set, the engine writes four files into that folder and returns their paths in `result.export_paths`:

   | File | Content |
   |------|---------|
   | `trades.csv` | One row per closed trade: ids, direction, entry and exit times and prices, stop, target, size, `realized_pnl`, `realized_r`, `fees`, `slippage`, excursions, `exit_reason`, `setup_quality_score`, notes, ML fields |
   | `equity_curve.csv` | `timestamp,equity,realized_pnl,drawdown` per candle (realized equity only; drawdown in currency) |
   | `rejected_signals.csv` | Every NO_TRADE, ML rejection and risk rejection with its reason |
   | `backtest_report.json` | The metrics dictionary only: trade counts, win rate, profit factor, expectancy, average R, drawdown, streaks, fees, net profit, return, per-session performance |

   Without `export_dir` nothing is written; the result stays in memory. A run with zero trades writes `trades.csv` as a zero-byte file with no header, so a 0-byte `trades.csv` can be a valid "no trades" result; the JSON report is the file to check for content.

5. **Produce the out-of-sample split.** Write `run_oos.py`, which splits chronologically (60% training, 20% validation, remaining 20% final test), runs the engine on each slice, and writes one JSON file of per-slice metrics:

   ```python
   """Run the engine on each chronological slice and write one JSON file of metrics."""
   import json
   import sys
   from pathlib import Path

   from silver_bot.backtest import BacktestConfig, BacktestEngine
   from silver_bot.backtest.validation import BacktestValidationSuite
   from run_backtest import load_candles

   candles = load_candles(sys.argv[1])
   out = Path(sys.argv[2])
   out.mkdir(parents=True, exist_ok=True)
   split = BacktestValidationSuite().chronological_split(candles, training_fraction=0.6, validation_fraction=0.2)
   report = {}
   for name in ("training", "validation", "final_test"):  # run final_test once, after settings are frozen
       slice_ = getattr(split, name)
       config = BacktestConfig(slippage_bps=1.0, spread_bps=1.0, export_dir=out / name)
       report[name] = {"candles": len(slice_), "metrics": BacktestEngine(config=config).run(slice_).metrics}
   (out / "out_of_sample_validation_report.json").write_text(
       json.dumps(report, indent=2, sort_keys=True, default=str)
   )
   print({k: v["metrics"]["total_trades"] for k, v in report.items()})
   ```

   ```bash
   python run_oos.py candles.csv oos
   ```

   Discipline: tune strategy and cost settings on `training` and `validation` only. Run `final_test` once, after the settings are frozen; no code enforces this (F03.61), so it is a manual rule (never optimize on the final test set). The JSON file is a plain per-slice metrics dump with no pass or fail verdict; deciding what counts as a pass is an open owner input (see [brd-silverbot.md](brd-silverbot.md) section 8).

6. **Check the report files are non-empty.** Since `88220e6` the readiness checker fails an empty or non-JSON-object report, but it does not look at `trades.csv` or at any metric, so check yourself:

   ```bash
   find out oos -type f -size 0
   ```

   Every path printed is an empty file. Expect only `trades.csv` files from slices that had no trades. On Windows PowerShell: `Get-ChildItem out,oos -Recurse -File | Where-Object Length -eq 0`. Also open `out/backtest_report.json` and confirm `total_trades` is greater than zero and that you understand the cost settings used.

7. **Run the live readiness checker on your reports.** It reads only process environment variables (not `.env`), so point the three report paths at your files with inline variables and send its own report to a safe folder:

   ```bash
   BACKTEST_REPORT_PATH=out/backtest_report.json OOS_VALIDATION_REPORT_PATH=oos/out_of_sample_validation_report.json python -m silver_bot.readiness --output readiness/live_readiness_report.json
   ```

   PowerShell:

   ```powershell
   $env:BACKTEST_REPORT_PATH="out/backtest_report.json"; $env:OOS_VALIDATION_REPORT_PATH="oos/out_of_sample_validation_report.json"; python -m silver_bot.readiness --output readiness/live_readiness_report.json
   ```

   Exit code 2 and `"ready": false` are the expected result: live trading is blocked at configuration load regardless, the paper report is missing, and the manual confirmations are unset. The checker only tests that each report is a readable, non-empty JSON object (since `88220e6`; before it, a 0-byte file passed). It reads no metric, so a pass on those three checks is not evidence.

## Verify

Run against the 10-candle synthetic sample (the unit-test setup, written to a scratch folder). These numbers come from synthetic data used to prove the commands work; they are not a strategy result and must not be quoted as one.

| Step | Command | Observed |
|------|---------|----------|
| 3 | `python run_backtest.py candles.csv out` | `1 211.69942074999986` then the four paths under `out`; exit 0 |
| 3 | default strategy settings on the same 10 candles | `0 0`; `trades.csv` is 0 bytes; the JSON report is 374 bytes |
| 4 | `ls -l out` | `backtest_report.json` 651 bytes, `equity_curve.csv` 492, `rejected_signals.csv` 756, `trades.csv` 730 |
| 5 | `python run_oos.py candles.csv oos` | `{'training': 0, 'validation': 0, 'final_test': 0}` (slices of 6, 2 and 2 candles are too short to trade); `out_of_sample_validation_report.json` 1498 bytes |
| 6 | `find out oos -type f -size 0` | `oos/training/trades.csv`, `oos/validation/trades.csv`, `oos/final_test/trades.csv` (all zero-trade runs); nothing from `out` |
| 7 | `python -m silver_bot.readiness` with the two paths set | exit 2, `ready` false; `backtest_report_exists` True, `out_of_sample_validation_report_exists` True, `paper_trading_report_exists` False |
| Fetcher | `HistoricalOHLCVFetcher(BinanceFuturesAdapter(testnet=True)).fetch(symbol="btcusdt", timeframe="1m", start=..., end=...)` | `NotImplementedError: Binance Futures OHLCV network fetching is not implemented in Phase 1` |

Done means: step 3 exits 0, `out/backtest_report.json` has `total_trades` above zero, step 6 lists no empty `*_report.json` or `out_of_sample_validation_report.json`, and you have not copied anything into `reports/` until you intend it to be evidence. Live trading stays blocked whatever step 7 prints.

## Self-Check

- [x] Every command and script was executed against the code on a synthetic candle file under a scratch folder; no file was written to the repository `reports/` directory.
- [x] The absence of a backtest CLI, of real historical fetching (G-13) and of an out-of-sample report writer is stated before the steps.
- [x] Costs are set non-zero in the scripts, and the defaults (5.0 and 3.0 bps since `59ed6d5`, zero before) are stated (G-11).
- [x] No strategy performance number is presented as a result; the sample figures are labelled synthetic.
- [x] The readiness checker's report checks (non-empty JSON object only, no metrics; G-2) are stated beside the command that uses it.
- [ ] The scripts were not run on real market data, because no code in the repository can fetch it.
