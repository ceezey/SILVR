# Local Development Runbook (RUNBOOK)

**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Version:** 0.1
**Owner:** Cian Jake Francisco
**Status:** Draft
**Last updated:** 2026-10-09
**Last reconciled:** 2026-10-08 against code at commit `62037d1`; step 3, step 4 and the Tests and Example rows of Verify re-run 2026-10-09 against `70ccaec`; steps 4, 6 and 7 and the Tests, Entrypoint and Files written rows re-run 2026-10-09 against `099085b`; the step 3 block and `.env.example` history, step 4 and the Tests and Config loads rows re-run 2026-10-09 against `5c781fc`

This runbook takes a fresh checkout to a working local environment: virtual environment, install, a safe paper-mode `.env`, the test suite, and the entrypoints that exist. It absorbs the old README "Basic Setup" and the example blocks of the old `CONFIGURATION.md`. Every command below was run against the code as built, except `pip install` (it needs the network; see step 2). Nothing here enables live trading or places an order; the adapter performs no network I/O.

Related documents: [sdd-silverbot.md](sdd-silverbot.md) (section 3.4 configuration reference, section 2.3 modes), [prd-silverbot.md](prd-silverbot.md) (section 5.1 operator surface), [ops-silverbot.md](ops-silverbot.md) (Docker and VPS), [qad-silverbot.md](qad-silverbot.md) (tests), [scrutiny-silverbot.md](scrutiny-silverbot.md) (G-3, G-4), [audit-docs-drift.md](audit-docs-drift.md) (D-1, D-2). The other runbooks are [runbook-backtest.md](runbook-backtest.md) and [runbook-demo-testnet.md](runbook-demo-testnet.md).

## Prerequisites

- Python 3.11 or newer (the project declares `requires-python = ">=3.11"`; the reference environment used 3.14.3).
- Git. No exchange account and no API keys are needed for anything in this runbook.
- The project has no runtime dependencies (`dependencies = []`); the only optional extra is `dev`, which installs `pytest>=8.0`.

## Steps

1. **Open a terminal in the repository root** (the folder that contains `pyproject.toml`).

2. **Create and activate a virtual environment, then install the package with the dev extra.**

   Windows (PowerShell):

   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -e ".[dev]"
   ```

   Linux or macOS:

   ```bash
   python3 -m venv .venv
   . .venv/bin/activate
   python -m pip install -e ".[dev]"
   ```

   There is no `requirements.txt`; the old README step `pip install -r requirements.txt` fails (D-40, G-25). The `pip install` line needs network access to fetch the build backend and `pytest`, so it was not re-run in the offline verification; the existing reference environment already shows `silver-bot 0.1.0` installed editable. Venv creation was run and works. If you cannot install, `pytest` still works from the repository root because `pyproject.toml` sets `pythonpath = ["src"]`.

3. **Create a private `.env` with a paper-mode block.** Since `c6d909d` the shipped `.env.example` loads as paper mode (see "`.env.example` history" below), so `cp .env.example .env` also works; it leaves the kill switch disabled. The block below additionally sets a kill-switch path. Create `.env` in the repository root with exactly this content:

   ```dotenv
   # Leave MODE blank: when set it overrides TRADING_MODE (and would block backtests).
   MODE=
   TRADING_MODE=paper
   LIVE_TRADING=false
   PAPER_TRADING=true
   DEMO_TRADING=false
   DATABASE_PATH=data/silver_bot.sqlite3
   EXCHANGE_NAME=binance_futures
   SYMBOL=BTCUSDT
   TIMEFRAME=1m
   BINANCE_API_KEY=
   BINANCE_API_SECRET=
   BINANCE_TESTNET=false
   BINANCE_FUTURES_BASE_URL=
   TELEGRAM_ENABLED=false
   ML_FILTER_ENABLED=false
   RISK_ENGINE_ENABLED=true
   KILL_SWITCH_ENABLED=true
   KILL_SWITCH_PATH=data/KILL_SWITCH
   STOP_LOSS_REQUIRED=true
   MAX_RISK_PER_TRADE=0.005
   MAX_DAILY_LOSS=0.02
   MAX_LEVERAGE=3
   ```

   `.env` is git-ignored; never commit it and never paste real keys into any file that is tracked. Values are read as written: no `export` prefix, no inline comments (put comments on their own line).

   What each safe default means:

   | Variable | Value | Meaning |
   |----------|-------|---------|
   | `MODE`, `TRADING_MODE` | blank, `paper` | Simulated trading. A non-blank `MODE` overrides `TRADING_MODE`, so `MODE` stays blank, as in the shipped `.env.example` since `5c781fc`, and `TRADING_MODE` alone picks the mode. The allowed modes are `backtest`, `demo`, `paper`; `live` is rejected. |
   | `LIVE_TRADING` | `false` | `true` makes `load_config` raise `ConfigError`; there is no override. |
   | `PAPER_TRADING` | `true` | Must be `true` in paper mode and `false` whenever `DEMO_TRADING=true`. |
   | `DEMO_TRADING` | `false` | `true` switches on every demo-mode requirement (testnet keys and more). Keep `false` for local work. |
   | `DATABASE_PATH` | `data/silver_bot.sqlite3` | SQLite file, relative to the folder you run from; must not contain `..` and must not be a directory. |
   | `EXCHANGE_NAME`, `SYMBOL`, `TIMEFRAME` | `binance_futures`, `BTCUSDT`, `1m` | Target market; timeframe is digits plus one of `m h d w`. |
   | `BINANCE_API_KEY`, `BINANCE_API_SECRET` | blank | Keys must be both set or both blank. Blank is correct outside demo. |
   | `BINANCE_TESTNET`, `BINANCE_FUTURES_BASE_URL` | `false`, blank | Endpoint selection; only used in demo (see [runbook-demo-testnet.md](runbook-demo-testnet.md)). |
   | `TELEGRAM_ENABLED` | `false` | `true` requires a token and chat id, and there is no real transport yet (G-15). |
   | `ML_FILTER_ENABLED` | `false` | The ML filter keys reach the filter in backtests only; the paper loop ignores them (G-9). |
   | `RISK_ENGINE_ENABLED`, `STOP_LOSS_REQUIRED` | `true` | Required `true` for demo; kept `true` everywhere. |
   | `KILL_SWITCH_ENABLED`, `KILL_SWITCH_PATH` | `true`, `data/KILL_SWITCH` | Kill-switch file location. `load_config` rejects `KILL_SWITCH_ENABLED=true` with a blank path in every mode. Only `build_risk_config` and `build_risk_engine` pass the path to the risk engine, and no paper runtime calls them yet; a backtest uses its own simulated switch and never this file. It is not an effective emergency stop today (G-6). |
   | `MAX_RISK_PER_TRADE`, `MAX_DAILY_LOSS`, `MAX_LEVERAGE` | `0.005`, `0.02`, `3` | The documented caps (0.5%, 2%, 3x). `MAX_RISK_PER_TRADE` must be in (0, 0.005] in every mode; the other two are range-checked only in demo mode and by the readiness checkers (G-5). |

   **`.env.example` history.** Until `c6d909d` it set `MODE=paper` and `PAPER_TRADING=false` but also `DEMO_TRADING=true`. When `DEMO_TRADING` is true and the mode is `paper`, the loader promotes the mode to `demo`, and demo mode then requires API keys, so loading stopped with `ConfigError: BINANCE_API_KEY and BINANCE_API_SECRET are required for demo mode` (D-2, G-4). It now sets `PAPER_TRADING=true` and `DEMO_TRADING=false`, like the block above (`.env.example:6-7`; `tests/test_config.py::test_shipped_env_example_loads_as_paper`). Until `5c781fc` it also set `MODE=paper`, which overrides `TRADING_MODE`, so a copied `.env` made every backtest exit 2; it now leaves `MODE` blank (`.env.example:2-3`; `tests/test_config.py::test_shipped_env_example_lets_trading_mode_select_backtest`).

4. **Run the test suite** from the repository root:

   ```bash
   python -m pytest -q
   ```

   Expected: `220 passed`. The tests use mocks and in-memory clients; they need no API keys and no network.

5. **Check the configuration loads and live is off** (this is also what the container health check runs):

   ```bash
   python -m silver_bot.health
   ```

   It prints nothing. Exit code 0 means the configuration loaded; 2 means it was rejected. It does not test the database, the exchange or the kill switch (G-27).

6. **Run the bot entrypoint.** Any of these three is equivalent:

   ```bash
   python -m silver_bot
   python main.py
   silver-bot
   ```

   The last needs the editable install from step 2. The entrypoint loads the configuration, creates the SQLite file, appends `bot_started` to `logs/audit.jsonl`, runs the configured mode and appends `bot_stopped` with `exit_code` (`main.py:51-80`). With the step 3 `.env` (paper mode) it logs `paper mode not available yet: needs market data (G-13)`, appends `mode_unavailable` and exits 78; demo does the same. There is no paper or demo runtime yet (G-3, G-13). If the configuration is rejected it logs `configuration rejected: <reason>` and exits 2. Flags: `--candles PATH` and `--output-dir DIR`, for backtest mode only; `--candles` in paper or demo mode, or an unknown flag, exits 2.

   To run a backtest instead, set `MODE=` (blank), `TRADING_MODE=backtest` and `PAPER_TRADING=false` and pass `--candles`; the full steps, including downloading candle files, are in [runbook-backtest.md](runbook-backtest.md). A non-blank `MODE` overrides `TRADING_MODE` (D-42).

7. **Inspect what it wrote:**

   ```bash
   ls data logs
   ```

   Expected: `data/silver_bot.sqlite3` and `logs/audit.jsonl` with three lines per run: `bot_started`, `mode_unavailable`, `bot_stopped` (`"exit_code": 78`). These paths are relative to the folder you ran from, so run every command from the same place.

## Verify

Each check below was run against a temporary working folder containing only the `.env` from step 3.

| Check | Command | Observed result |
|-------|---------|-----------------|
| Tests | `python -m pytest -q` (repository root) | `220 passed` (2026-10-09, `dev` at `5c781fc`) |
| Config loads | `python -c "from silver_bot.config import load_config; c=load_config(); print(c.mode, c.live_trading, c.paper_trading, c.demo_trading)"` | `TradingMode.PAPER False True False` |
| Example loads | load `.env.example` with `load_config(env_path=".env.example", yaml_path="none.yaml", environ={})` | `TradingMode.PAPER False True False` (mode, live, paper, demo; 2026-10-09) |
| Health | `python -m silver_bot.health; echo $?` | no output, `0` |
| Entrypoint | `python -m silver_bot; echo $?` | `ERROR silver_bot.main paper mode not available yet: needs market data (G-13)`, `78`; `python main.py` gave the same (2026-10-09, `099085b`) |
| Files written | `ls data logs` | `silver_bot.sqlite3`, `audit.jsonl` (three JSON lines per run: `bot_started`, `mode_unavailable`, `bot_stopped` with `"exit_code": 78`, all `"mode": "paper"`) |

Safety posture to confirm: `live_trading` prints `False`, and `LIVE_TRADING=true` in the environment makes both `python -m silver_bot` and `python -m silver_bot.health` exit 2.

## Troubleshooting

- `ConfigError ... required for demo mode`: `DEMO_TRADING=true` is set (perhaps from the commented demo block or an old copy of `.env.example`); set it to `false` for local work.
- `ConfigError: KILL_SWITCH_PATH is required when KILL_SWITCH_ENABLED=true`: set `KILL_SWITCH_PATH` or set `KILL_SWITCH_ENABLED=false`.
- `ConfigError: MAX_RISK_PER_TRADE must be greater than 0 and no more than 0.005`: the per-trade cap applies in every mode.
- `ConfigError: PAPER_TRADING must be true when TRADING_MODE=paper`: `MODE` or `TRADING_MODE` is `paper` while `PAPER_TRADING=false`.
- A `data/` or `logs/` folder appears somewhere unexpected: relative paths follow the current working directory, not the repository root.
- A `config.yaml` is read if present. Its parser is not real YAML (no nesting, indentation ignored), and root keys written after a section header are silently prefixed and ignored (see [sdd-silverbot.md](sdd-silverbot.md) section 3.4).

## Self-Check

- [x] Every command was executed against the code, except `pip install -e ".[dev]"`, which needs the network and is flagged as such in step 2.
- [x] The `.env` block in step 3 was loaded with `load_config` from a temporary folder and returned mode paper, live false.
- [x] The former `.env.example` failure and its fix are stated with the exact error message and cross-referenced to D-2 and G-4.
- [x] The entrypoint is described as built at `099085b`: paper and demo exit 78; backtest needs `--candles` and is covered by [runbook-backtest.md](runbook-backtest.md); no step claims it runs a paper or demo session.
- [x] No real key, secret or personal path appears in the runbook.
- [ ] The Linux and macOS venv commands were not executed (the verification host is Windows).
