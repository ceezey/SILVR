# G-3 Entrypoint, Batch 2: Design Spec

**Date:** 2026-10-09
**Status:** Approved by the owner, including unattended execution on `dev` with nothing pushed
**Owner:** Cian Jake Francisco (ceezey)
**Branch:** `dev` (base commit `f8a51b4`)
**Baseline:** `python -m pytest -q` passes 170 tests at `f8a51b4`

---

## 1. Intent

### What the owner asked for

- Replace the startup-stub entrypoint (G-3) so the bot can do real work from the command line.
- First goal: run backtests on real market data and produce the evidence reports that readiness looks for (G-1).
- Stop supervisors restart-looping the process (H-4).
- Paper and demo stay unavailable until real market data exists (G-13, G-17). Live stays `Planned, blocked`.

### Decisions made during brainstorming

| # | Question | Decision |
|---|----------|----------|
| ED-1 | First capability | Backtest from Binance public kline CSV files. |
| ED-2 | Out-of-sample report | Yes: chronological 60/20/20 split with the existing helper; each segment backtested separately; no tuning. |
| ED-3 | Paper and demo meanwhile | Exit code 78 with a clear message; supervisors stop restarting on 78. |
| ED-4 | Mode selection | From config (`TRADING_MODE`), as today. Flags supply backtest inputs only. No subcommands. |
| ED-5 | Kill switch in backtests (decided after the permission classifier refused a design that dropped the kill-switch path) | A simulated per-run kill switch in a temp directory, always on, tripping and halting like live; the real file is never used. |

### Invariants

- No change loosens a risk, kill-switch, readiness or live gate. `LIVE_TRADING=true` and `TRADING_MODE=live` stay rejected at load.
- A backtest never reads or writes the real kill-switch file; it runs on its own simulated, always-on kill switch.
- No new dependency. No network I/O. Reports go to `reports/`, which is gitignored and never committed.
- No performance claim is written into any committed doc.

## 2. Behaviour

Paths are relative to `src/silver_bot/` unless they start with a root filename.

### 2.1 Command line (`main.py`)

`python -m silver_bot [--candles PATH ...] [--output-dir DIR]` (also `python main.py` and the `silver-bot` script).

- `--candles PATH` may repeat. Each path is a `.csv` file or a directory (every `*.csv` directly inside it, sorted by name). `--output-dir` defaults to `reports`.
- Flow: parse args (argparse; bad args exit 2), load config (`ConfigError` logs and returns 2, as today), initialize storage, audit `bot_started`, dispatch, audit `bot_stopped` with `exit_code`, return the code.

| Mode | Behaviour | Exit |
|---|---|---|
| `backtest` | No `--candles`: log `backtest mode needs --candles`, return 2. Otherwise load candles (2.2), run (2.3), log the report paths, return 0. `CandleDataError` logs and returns 2. | 0 or 2 |
| `paper`, `demo` | `--candles` given: log `--candles only applies to backtest mode`, return 2. Otherwise log and audit `mode_unavailable` with message `mode not available yet: needs market data (G-13)`, return 78. | 2 or 78 |

`EXIT_MODE_UNAVAILABLE = 78` is a module constant in `main.py`.

### 2.2 Candle loader (new `data/csv_loader.py`)

`load_binance_kline_csv(paths: Sequence[str | Path], *, symbol: str, timeframe: str) -> CandleLoadResult`

- `CandleLoadResult` (frozen dataclass): `candles: list[Candle]` (sorted by `open_time`), `files: list[Path]`, `gaps: int`.
- `CandleDataError(ValueError)` for every failure, with file and 1-based line where one applies.
- Input format: Binance public kline CSV (data.binance.vision), columns `open_time, open, high, low, close, volume, close_time, ...` (12 columns; only the first 7 are read). A first row whose first cell is `open_time` (case-insensitive) is a header and is skipped.
- Timestamps: integer milliseconds; a value `>= 10**15` is microseconds. Converted to UTC. `close_time` is Binance's value plus one unit of its own scale (1 ms, or 1 µs for microsecond files), so it lands on the next interval boundary.
- Rejects: missing path; a directory with no `.csv`; no rows at all; a row with fewer than 7 columns; a non-integer timestamp; a non-finite or non-positive price; negative or non-finite volume; OHLC that `Candle` rejects; the same `open_time` twice with different values (identical duplicates from overlapping files are dropped); consecutive spacing that is not a positive whole multiple of `timeframe`.
- `gaps` counts consecutive pairs spaced more than one interval apart.
- `timeframe` units: `m` minutes, `h` hours, `d` days, `w` weeks (the same set `load_config` accepts).

### 2.3 Runner (new `backtest/runner.py`) and factory refactor

- `risk/factory.py` gains `build_risk_config(config: AppConfig) -> RiskConfig` (settings caps and the real kill-switch path when enabled). `build_risk_engine` uses it.
- `build_backtest_config(config: AppConfig, *, export_dir: Path | None, kill_switch_path: Path) -> BacktestConfig`: `risk=replace(build_risk_config(config), kill_switch_path=kill_switch_path)`, the ML filter config from settings, `export_dir=export_dir`. Costs and balance keep `BacktestConfig` defaults.
- **Simulated kill switch (ED-5).** Every engine run (the full period and each segment) gets its own kill-switch file inside a fresh `tempfile.TemporaryDirectory()`. The engine checks and trips it as live would, so a trip halts the rest of that simulated run. It is on even when `KILL_SWITCH_ENABLED=false`. The real `KILL_SWITCH_PATH` is never given to a backtest engine. The trip record is read before cleanup and reported in `backtest_run.json` (`kill_switch: {mode: simulated_per_run, tripped, reason, tripped_at}`) and in each OOS segment (`kill_switch: {tripped, reason, tripped_at}`).
- `run_backtest(config: AppConfig, candles: Sequence[Candle], output_dir: Path, *, inputs: Mapping[str, Any]) -> BacktestRunSummary`:
  1. Full period: `BacktestEngine(config=build_backtest_config(config, export_dir=output_dir)).run(candles)`. Writes `backtest_report.json`, `trades.csv`, `equity_curve.csv`, `rejected_signals.csv` through the existing export.
  2. Out of sample: `BacktestValidationSuite().chronological_split(list(candles))` with default fractions 0.6 and 0.2. Each non-empty segment runs in a new engine (fresh risk state, `export_dir=None`). Writes `out_of_sample_validation_report.json`:
     `{"method": "chronological_split", "fractions": {"training": 0.6, "validation": 0.2, "final_test": 0.2}, "parameters_tuned": false, "segments": {"training": {...}, "validation": {...}, "final_test": {...}}}` where each segment is `{"candles": int, "start": iso or null, "end": iso or null, "metrics": dict or null}`.
  3. Run record: writes `backtest_run.json` with `inputs` (as given), `symbol`, `timeframe`, `candles`, `first_open_time`, `last_open_time`, `slippage_bps`, `spread_bps`, `maker_fee`, `taker_fee`, `ml_filter_enabled`, `risk_per_trade`, `package_version` (`silver_bot.__version__`).
  - Raises `ValueError` on empty `candles`.
- `BacktestRunSummary` (frozen dataclass): `candles: int`, `report_paths: dict[str, Path]` (keys `backtest_report`, `trades`, `equity_curve`, `rejected_signals`, `out_of_sample_validation_report`, `backtest_run`).
- `main.py` passes `inputs={"files": [str(p) for p in loaded.files], "gaps": loaded.gaps}`.

### 2.4 Restart loop (H-4)

- `deploy/systemd/silver-bot.service`: `ExecStart=/usr/bin/docker compose -f /opt/silver-bot/docker-compose.yaml up bot --exit-code-from bot` and `RestartPreventExitStatus=78`. `docker compose up` exits 0 when a container fails unless `--exit-code-from` is given, so without it systemd would still loop.
- `docker-compose.yaml` `bot` service: `restart: "no"`. systemd is the only supervisor on the host path.
- `docker-compose.yaml` `backtest` and `research` services: `command: ["python", "-m", "silver_bot", "--candles", "/app/data/candles"]`.
- `Dockerfile` `CMD` and `health.py` are unchanged.

## 3. Execution

| Wave | Lane | Scope | Files |
|---|---|---|---|
| 1 | A, loader | 2.2 | `data/csv_loader.py`, `data/__init__.py`, `tests/test_csv_loader.py` |
| 1 | B, runner | 2.3 | `risk/factory.py`, `risk/__init__.py`, `backtest/runner.py`, `backtest/__init__.py`, `tests/test_backtest_runner.py`, `tests/test_risk_engine.py` |
| 1 | C, deploy | 2.4 | `deploy/systemd/silver-bot.service`, `docker-compose.yaml`, `tests/test_deployment_files.py` |
| 2 | M, entrypoint | 2.1 | `main.py`, `tests/test_main.py` |

Wave 1 lanes run in parallel worktrees branched from `dev` and share no files. They merge into `dev` in order A, B, C. Wave 2 runs on `dev` after the merge. Then one docs agent and the four safety reviewers (on the code diff from `f8a51b4`) run in parallel; blocking findings are verified before any fix.

## 4. Testing

- Loader: header and no header; ms and µs timestamps; directory input; overlapping identical rows dropped; each rejection in 2.2 raises `CandleDataError` naming the file and line; a 5m file loaded as `1m` passes spacing (multiple) but a 1m file loaded as `5m` fails; gap count.
- Runner: the six report files exist; `out_of_sample_validation_report.json` and `backtest_report.json` pass `readiness` report checks (non-empty JSON objects); the backtest risk config points at the run's simulated kill switch even when settings enable or disable the real one, and an existing real kill file does not block the backtest and is not modified; trip records appear in the reports; settings caps reach `RiskConfig`; ML settings reach `MLFilterConfig`; empty candles raise.
- Entrypoint: paper and demo return 78 and audit `mode_unavailable`; backtest without `--candles` returns 2; `--candles` in paper returns 2; a bad CSV returns 2; an end-to-end run on a small Binance-format CSV returns 0 and writes reports that pass the readiness report checks; `LIVE_TRADING=true` still returns 2.
- Deploy: systemd has `--exit-code-from bot` and `RestartPreventExitStatus=78`; compose `bot` has `restart: "no"`; backtest and research pass `--candles`; existing safety assertions still hold.

## 5. Documentation Updates

After merge: SDD 2.3, 4.6 and 6; PRD section 3 status of PRD-F2 and PRD-F11 and section 5.1; scrutiny G-3 (backtest runtime closed; paper and demo remain on G-13 and G-17), H-4 closed, G-1 (tooling exists; evidence still empty until the owner runs it), G-5, G-9 and G-12 partial notes; audit D-1, D-46, H-4; OPS (exit 78 and supervisor behaviour); `runbook-backtest.md` (download klines from data.binance.vision into `data/candles/`, run, read the reports); `runbook-local-dev.md`; QAD rows for the new tests; index change log and process records; README quick start. Re-materialize.

## 6. Acceptance

- `python -m pytest -q` passes on `dev` with more than 170 tests.
- `python tools/materialize_docs.py --check` reports no changes.
- `TRADING_MODE=backtest python -m silver_bot --candles <fixture>` exits 0 and writes the six report files; paper exits 78.
- The four safety reviewers report no unresolved blocking finding.
