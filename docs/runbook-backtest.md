# Backtest and Evidence Runbook (RUNBOOK)

**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Version:** 0.1
**Owner:** Cian Jake Francisco
**Status:** Draft
**Last updated:** 2026-10-09
**Last reconciled:** 2026-10-09 against code at commit `099085b` (G-3 entrypoint batch 2)

This runbook downloads Binance USD-M futures klines, runs the backtest from the command line, and reads the six reports it writes. It absorbs the "outputs" parts of the old `BACKTESTING.md`. Live trading is `Planned, blocked`; nothing here enables it or places an order.

**Read this first.**

- The command line runs one backtest per call on local CSV files (`main.py:91-109`, `099085b`). The code downloads nothing (G-13): you fetch the files from data.binance.vision by hand (steps 1 to 4).
- Each run backtests the full period, then a chronological 60/20/20 split (training, validation, final test), each segment in a fresh engine with fresh risk state; nothing is tuned (`backtest/runner.py:60-126`). There is no walk-forward, Monte Carlo, sensitivity run or pass or fail verdict (G-12).
- Strategy settings are the code defaults (`SilverBulletStrategyEngine()`, `backtest/engine.py:39`; G-18). Costs and balance are the `BacktestConfig` defaults: maker fee 0.0002, taker fee 0.0005, slippage 5.0 bps, spread 3.0 bps, balance 10000 (`backtest/models.py:30-35`). Risk caps and the `ML_*` settings come from your configuration (`backtest/runner.py:48-55`).
- The reports are not committed. `reports/` and `data/` are git-ignored (`.gitignore:5,7`). No doc in this repository may quote a number from these reports as a performance claim; a report is evidence only for the owner's gate review (QAD §6.1).
- Paper and demo modes exit 78 (`main.py:86-88`); only backtest mode runs.

Related documents: [prd-silverbot.md](prd-silverbot.md) (PRD-F2), [sdd-silverbot.md](sdd-silverbot.md) (sections 3.3 and 4.6), [rfc-silverbot-risk-kill-switch.md](rfc-silverbot-risk-kill-switch.md) (simulated kill switch), [rfc-silverbot-readiness-gates.md](rfc-silverbot-readiness-gates.md) (readiness checkers), [runbook-local-dev.md](runbook-local-dev.md) (setup), [ops-silverbot.md](ops-silverbot.md) §5.5 (the same run in the container), [scrutiny-silverbot.md](scrutiny-silverbot.md) (G-1, G-12, G-13).

## Kill switch in backtests (simulated per run)

A backtest never uses the real kill switch at `KILL_SWITCH_PATH`. Every engine run (the full period and each of the three segments) gets its own `KILL_SWITCH` file inside a fresh temporary directory (`backtest/runner.py:129-143`; decision ED-5 in the [G-3 entrypoint spec](superpowers/specs/2026-10-09-g3-entrypoint-design.md)).

- It is always on, even with `KILL_SWITCH_ENABLED=false` (`backtest/runner.py:49`).
- The risk engine trips it as it would the real one: on the max-daily-loss or max-consecutive-losses limit (`risk/engine.py:83,86,129`). After a trip every later entry in that simulated run is rejected with `Kill switch is active`.
- A real kill file neither blocks a backtest nor is modified by one (`tests/test_backtest_runner.py:109`).
- The trip is reported, then the temporary directory is deleted: `backtest_run.json` has `kill_switch: {mode: simulated_per_run, tripped, reason, tripped_at}` for the full period, and each segment of `out_of_sample_validation_report.json` has `kill_switch: {tripped, reason, tripped_at}` (`backtest/runner.py:118,146-170`).

## Steps

Run every command from the repository root with the virtual environment active ([runbook-local-dev.md](runbook-local-dev.md)). The examples use BTCUSDT 1m; change both everywhere for another market.

1. **Choose the market and the months.** The symbol and timeframe must match `SYMBOL` and `TIMEFRAME` in your configuration (defaults `BTCUSDT`, `1m`). The loader accepts timeframes in `m`, `h`, `d` and `w` (`data/csv_loader.py:19,35-41`); Binance's `1mo` files are rejected. Expected: one symbol, one timeframe, a list of `YYYY-MM` months.

2. **Make an empty download folder** outside the repository: `mkdir -p ~/klines && cd ~/klines`. Expected: an empty folder. Keep downloads apart from `data/candles/` and from any code.

3. **Download each month.** The monthly USD-M futures files are at

   ```text
   https://data.binance.vision/data/futures/um/monthly/klines/<SYMBOL>/<TIMEFRAME>/<SYMBOL>-<TIMEFRAME>-<YYYY>-<MM>.zip
   ```

   `<SYMBOL>` is the contract, for example `BTCUSDT`; `<TIMEFRAME>` the interval, for example `1m`; `<YYYY>-<MM>` the month. Each zip has a checksum file at the same URL plus `.CHECKSUM`. For three months of BTCUSDT 1m:

   ```bash
   for m in 2025-11 2025-12 2026-01; do
     curl -fLO "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-$m.zip"
     curl -fLO "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-$m.zip.CHECKSUM"
   done
   sha256sum -c *.CHECKSUM
   ```

   PowerShell: `Invoke-WebRequest -Uri "<url>" -OutFile "<file>"` per file, then compare `(Get-FileHash <file> -Algorithm SHA256).Hash` with the first field of the `.CHECKSUM` file. Expected: `curl` exits 0 for each file and `sha256sum` prints `OK` for each zip. A month that has not ended yet has no monthly file (HTTP 404).

4. **Unzip the CSVs into `data/candles/`.** From the repository root:

   ```bash
   mkdir -p data/candles
   for z in ~/klines/*.zip; do unzip -o "$z" -d data/candles; done
   ls data/candles
   ```

   PowerShell: `Get-ChildItem ~/klines/*.zip | ForEach-Object { Expand-Archive $_ -DestinationPath data/candles -Force }`. Expected: one `BTCUSDT-1m-YYYY-MM.csv` per month directly in `data/candles/`. The loader reads every `*.csv` directly inside the folder in name order and ignores other files and subfolders (`data/csv_loader.py:82-97`). Keep one symbol and one timeframe per folder: the loader stamps `SYMBOL` on every row and does not read it from the file.

5. **Set backtest mode.** In `.env` at the repository root set:

   ```text
   MODE=
   TRADING_MODE=backtest
   PAPER_TRADING=false
   DEMO_TRADING=false
   LIVE_TRADING=false
   SYMBOL=BTCUSDT
   TIMEFRAME=1m
   ```

   `MODE` must be blank or `backtest`. A non-blank `MODE` overrides `TRADING_MODE` from every source (D-42), and the shipped `.env.example` sets `MODE=paper`, so a copied `.env` loads as paper with `PAPER_TRADING=false` and the run exits 2 with `PAPER_TRADING must be true when TRADING_MODE=paper`. Expected: `python -c "from silver_bot.config import load_config; print(load_config().mode)"` prints `TradingMode.BACKTEST`.

6. **Run the backtest:**

   ```bash
   python -m silver_bot --candles data/candles; echo $?
   ```

   `--candles` may repeat and takes a file or a directory; `--output-dir DIR` writes the reports somewhere other than `reports/`. Expected: one log line `wrote <name>: reports/<file>` for each of six reports, then `backtest complete: N candles, G gaps`, then `0`. Other exit codes:

   | Exit | Log line | Fix |
   |---|---|---|
   | 2 | `backtest mode needs --candles` | Pass `--candles data/candles` |
   | 2 | `candle data rejected: <file>:<line>: <reason>` | Fix or remove the named file; a spacing error naming `TIMEFRAME` means the files do not match `TIMEFRAME` |
   | 2 | `configuration rejected: <reason>` | Fix `.env` (step 5) |
   | 2 | `--candles only applies to backtest mode` | The mode is not backtest; check `MODE` and `TRADING_MODE` |
   | 78 | `paper mode not available yet: needs market data (G-13)` | The mode is paper or demo; set backtest mode (step 5) |

   The run also writes `data/silver_bot.sqlite3` and appends `bot_started` and `bot_stopped` (with `exit_code`) to `logs/audit.jsonl`. Runtime grows faster than the candle count, because the engine re-evaluates the growing candle prefix on every bar (`backtest/engine.py:106`); start with one month. To run the same thing in the container, see [ops-silverbot.md](ops-silverbot.md) §5.5.

7. **Read the six reports** in `reports/` (or `--output-dir`):

   | File | Content |
   |------|---------|
   | `backtest_report.json` | Full-period metrics dictionary only: trade counts, win rate, profit factor, expectancy, average R, drawdown, streaks, fees, net profit, return, per-session performance |
   | `trades.csv` | One row per closed trade: ids, direction, entry and exit times and prices, stop, target, size, `realized_pnl`, `realized_r`, `fees`, `slippage`, excursions, `exit_reason`, `setup_quality_score`, notes, ML fields. A zero-trade run writes a 0-byte file |
   | `equity_curve.csv` | `timestamp,equity,realized_pnl,drawdown` per candle (realized equity only; drawdown in currency) |
   | `rejected_signals.csv` | Every NO_TRADE, ML rejection and risk rejection with its reason, including `Risk rejected: Kill switch is active` after a simulated trip |
   | `out_of_sample_validation_report.json` | `method` `chronological_split`, `fractions` 0.6 / 0.2 / 0.2, `parameters_tuned` false, and `segments.training`, `segments.validation`, `segments.final_test`, each with `candles`, `start`, `end`, `metrics` and `kill_switch`. An empty segment has 0 candles and nulls |
   | `backtest_run.json` | The run record: `inputs.files` and `inputs.gaps` from the loader, `symbol`, `timeframe`, `candles`, `first_open_time`, `last_open_time`, `slippage_bps`, `spread_bps`, `maker_fee`, `taker_fee`, `ml_filter_enabled`, `risk_per_trade`, `kill_switch` and `package_version` |

   Check, in this order: `backtest_run.json` lists the files you meant and `inputs.gaps` is 0 (a gap is a missing interval; the loader counts it and fills nothing); the cost fields are non-zero (BRD-M3); `kill_switch.tripped` in the run record and in each segment (if true, the rest of that run after `tripped_at` took no trade, so read its metrics with that in mind); `trades.csv` has rows. Discipline: if you change strategy code or settings between runs, choose them on the training and validation segments only and look at `final_test` once at the end; no code enforces this (D-33).

8. **Run the live readiness checker on the reports** (it reads only process environment, and its defaults are `reports/backtest_report.json` and `reports/out_of_sample_validation_report.json`):

   ```bash
   python -m silver_bot.readiness --output readiness/live_readiness_report.json; echo $?
   ```

   Expected: `2` and `"ready": false`: live trading is blocked at configuration load regardless, the paper report does not exist, and the manual confirmations are unset. `backtest_report_exists` and `out_of_sample_validation_report_exists` pass once step 6 succeeded, because the checker tests only that each report is a readable, non-empty JSON object (`readiness.py:150-177`). It reads no metric, so passing those two checks is not evidence.

## Verify

Run on 2026-10-09 at `099085b` with `python -m silver_bot` from a scratch folder holding a 120-row synthetic file in Binance format (header row, ms timestamps). No number from these runs is a strategy result, and none is recorded here.

| Check | Command | Observed |
|-------|---------|----------|
| Backtest | `TRADING_MODE=backtest PAPER_TRADING=false python -m silver_bot --candles data/candles` | six `wrote` lines, `backtest complete: 120 candles, 0 gaps`, exit 0; six files in `reports/`; `backtest_run.json` `kill_switch` is `{"mode": "simulated_per_run", "reason": null, "tripped": false, "tripped_at": null}` |
| No `--candles` | same environment, no flag | `backtest mode needs --candles`, exit 2 |
| Paper | default environment | `paper mode not available yet: needs market data (G-13)`, exit 78 |
| Paper with `--candles` | default environment, `--candles data/candles` | `--candles only applies to backtest mode`, exit 2 |
| Live flag | `LIVE_TRADING=true python -m silver_bot` | `configuration rejected: LIVE_TRADING=true is rejected in Phase 1`, exit 2 |
| Copied `.env.example` | `.env` with `MODE=paper`, process `TRADING_MODE=backtest PAPER_TRADING=false` | `configuration rejected: PAPER_TRADING must be true when TRADING_MODE=paper`, exit 2; with `MODE=` the same command exits 0 |
| Download | `curl -fLO` of `BTCUSDT-1m-2026-01.zip` and its `.CHECKSUM` | both HTTP 200; `sha256sum -c` prints `OK`; the CSV starts with the header `open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore` and millisecond timestamps |

Done means: step 6 exits 0, the six files exist, `backtest_run.json` lists the intended files, and nothing from `reports/` is committed or quoted. Live trading stays blocked whatever step 8 prints.

## Self-Check

- [x] Every command except the PowerShell variants was executed against the code at `099085b` in a scratch folder; nothing was written to the repository `reports/` directory.
- [x] The absence of a network download (G-13), walk-forward and pass or fail criteria (G-12) is stated before the steps.
- [x] The simulated per-run kill switch and where its trips are reported are stated (ED-5).
- [x] The reports are git-ignored and no performance number appears in this runbook.
- [x] The readiness checker's report checks (non-empty JSON object only, no metrics) are stated beside the command that uses it.
- [ ] A full real-data run has been reviewed by the owner (not yet; G-1).
