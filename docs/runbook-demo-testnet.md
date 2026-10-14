# Demo / Testnet Runbook (RUNBOOK)

**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Version:** 0.1
**Owner:** Cian Jake Francisco
**Status:** Draft
**Last updated:** 2026-10-14
**Last reconciled:** 2026-10-08 against code at commit `62037d1`; the URL, risk-limit and kill-switch statements in step 3 re-checked 2026-10-09 against `70ccaec`; steps 5 and 7 and the step 5 Verify rows re-run 2026-10-09 against `099085b`; the step 7 restart statement re-checked 2026-10-09 against `5c781fc`; the opening note and steps 3, 5, 6 and 7 rewritten 2026-10-14 against `40ea0b1` (demo runtime `973cd82`, kill-switch flatten `cf8d41f`, exact-host guard and redirect refusal `40ea0b1`); the step 5 Verify rows were not re-run (no network)

This runbook prepares and checks Binance Futures demo (testnet) mode: creating testnet keys, setting the demo environment, running the demo readiness checker, a dry startup, verification and stopping. It absorbs the demo steps of the old `DEPLOYMENT.md` and the demo example of the old `CONFIGURATION.md`.

**What demo mode does since `973cd82`.** `python -m silver_bot` in demo mode reads closed 1m (or `TIMEFRAME`) candles from the testnet public klines endpoint and runs the paper engine on them: strategy, ML filter, risk engine from settings with persisted state and the kill switch, and simulated fills with the backtest costs (`main.py:114-148`, `execution/runtime.py:42-110`). It places no testnet order: `place_order` and `cancel_order` still raise `OrderPlacementDisabled`, and the klines request is an unsigned GET that carries no API key (`exchange/binance_futures.py:107-148`). The adapter accepts only the exact production or testnet host and refuses redirects (`40ea0b1`). The keys are required by configuration and readiness but are not sent anywhere. A ready report does not prove the keys are valid: the checker only tests that both values are non-blank. No demo run against the real testnet is recorded yet (G-3). Live trading remains blocked at configuration load (`Planned, blocked`).

Related documents: [rfc-silverbot-readiness-gates.md](rfc-silverbot-readiness-gates.md) (the 18 demo checks and the 15 live checks), [sdd-silverbot.md](sdd-silverbot.md) (section 3.4 configuration, section 2.3 modes), [ops-silverbot.md](ops-silverbot.md) (compose `demo` profile, stopping), [prd-silverbot.md](prd-silverbot.md) (PRD-F5), [runbook-local-dev.md](runbook-local-dev.md) (setup), [scrutiny-silverbot.md](scrutiny-silverbot.md) (G-3, G-6, G-10).

## Steps

1. **Create Binance Futures testnet keys.** Sign in to the Binance Futures testnet site (`testnet.binancefuture.com`) with its own testnet account and create an API key there. Testnet keys are separate from production keys and hold play money only. Rules for the key:
   - Enable only the permission needed to read and trade futures on the testnet. Do not enable withdrawals or transfers (trade-only, no withdrawals). Testnet funds are not real, but the habit must match what a future live key will require.
   - Restrict the key to your own IP address if the site offers it.
   - Never reuse a production key here, and never paste a production key into any file.
   - Keep the key and secret only in your private, git-ignored `.env`.

2. **Check `.env` is git-ignored.** Run from the repository root:

   ```bash
   git check-ignore .env
   ```

   It should print `.env`. The demo readiness checker also requires a line that is exactly `.env` in `.gitignore`.

3. **Write the demo environment** in `.env` (or the process environment). Replace the two key values with your testnet key and secret; do not commit them:

   ```dotenv
   MODE=demo
   TRADING_MODE=demo
   DEMO_TRADING=true
   BINANCE_TESTNET=true
   LIVE_TRADING=false
   PAPER_TRADING=false
   BINANCE_API_KEY=<testnet-key>
   BINANCE_API_SECRET=<testnet-secret>
   BINANCE_FUTURES_BASE_URL=https://testnet.binancefuture.com
   DATABASE_PATH=data/silver_bot.sqlite3
   EXCHANGE_NAME=binance_futures
   SYMBOL=BTCUSDT
   TIMEFRAME=1m
   RISK_ENGINE_ENABLED=true
   KILL_SWITCH_ENABLED=true
   KILL_SWITCH_PATH=data/KILL_SWITCH
   STOP_LOSS_REQUIRED=true
   MAX_RISK_PER_TRADE=0.005
   MAX_DAILY_LOSS=0.02
   MAX_LEVERAGE=3
   ```

   What the flags do. `DEMO_TRADING=true` turns on every demo requirement, even if the mode is not `demo`. `PAPER_TRADING` must be `false` when `DEMO_TRADING=true`. `LIVE_TRADING` must stay `false` (true is rejected). `BINANCE_TESTNET=true` is required, and a base URL, if set, must be `https` with host exactly `testnet.binancefuture.com` (no userinfo, port 443 or none); lookalike hosts are rejected since `0a76564` (`config/settings.py:348-365`, G-10 closed). Risk per trade must be at most 0.005 in every mode; daily loss at most 0.02 and leverage at most 3 are checked in demo mode only. `KILL_SWITCH_PATH` must be set; the demo runtime passes it to the risk engine through `build_risk_engine` (`execution/runtime.py:76`, `973cd82`), so a running demo session reads the file on every candle, rejects new entries while it exists and flattens the simulated position (`cf8d41f`).

4. **Run the demo readiness checker.** It writes a JSON report and places no orders. Send the report to a folder of your choice:

   ```bash
   python -m silver_bot.demo_readiness --output out/demo_readiness_report.json
   ```

   The default output path is `reports/demo_readiness_report.json`, the repository evidence folder, which is why these steps write to `out/` instead. Exit code 0 means all 18 checks passed; exit code 2 means at least one failed, and the report lists each failed check with its reason. The checker reads `.env` from the current folder and overlays the process environment. It does not read values that exist only in `config.yaml` (except for the first check), so put demo values in `.env`.

5. **Smoke run.** Confirm the health check accepts the configuration, then run a bounded demo session on testnet market data:

   ```bash
   python -m silver_bot.health
   python -m silver_bot --max-candles 2
   ```

   The first exits 0. The second creates the SQLite file, writes `bot_started` to `logs/audit.jsonl`, fetches up to 500 recent closed candles from `https://testnet.binancefuture.com` to warm up, then polls every 10 s and stops after 2 new closed candles (about 2 to 3 minutes at `1m`) with exit 0 and `bot_stopped` (`"exit_code": 0`). It writes `reports/paper_trading_report.json` (`mode` `demo`, `fills` `simulated`; `--output-dir DIR` puts it elsewhere). Without `--max-candles` it runs until Ctrl+C or SIGTERM, which also exits 0. If the testnet cannot be reached it audits `market_data_unavailable` and exits 1; a rejected configuration or base URL exits 2. To use the container instead, `docker compose --profile demo run --rm demo` runs the same entrypoint with the `demo` profile settings until stopped (append `python -m silver_bot --max-candles 2` for a bounded run; see [ops-silverbot.md](ops-silverbot.md) §0); and `docker compose --profile demo run --rm demo python -m silver_bot.demo_readiness` runs the checker inside it.

6. **Test the kill-switch file the way the checkers see it.** The readiness check `kill_switch_not_active` fails while the file exists, so the file must be absent when you want a ready report:

   ```bash
   touch data/KILL_SWITCH
   python -m silver_bot.demo_readiness --output out/demo_readiness_report.json
   rm data/KILL_SWITCH
   ```

   The first run exits 2 with the switch present; after removing the file the checker passes again. A running demo session also reads the file: while it exists every new entry is rejected with `Kill switch is active`, and on the next candle the session records `kill_switch_active` and closes the simulated position or cancels the pending simulated order (`cf8d41f`). It does not stop the process; stop it as in step 7.

7. **Stop.** A session started with `--max-candles` exits 0 by itself. Otherwise press Ctrl+C, or `docker compose stop` for the container; both exit 0. Exit 78 no longer exists (`973cd82`). Supervisors do not restart on 2 since `5c781fc`, but do restart on 1 (market data unavailable or a crash); stop a restarting unit with `sudo systemctl stop silver-bot` ([ops-silverbot.md](ops-silverbot.md) sections 4.1 and 4.8). Remove testnet keys from `.env` when you finish, or revoke them on the testnet site.

## Verify

Run against a temporary folder holding only a demo `.env` with placeholder key values (`fake-testnet-key`, `fake-testnet-secret`), a `.gitignore` containing `.env`, and the block from step 3.

| Step | Command | Observed |
|------|---------|----------|
| 4 | `python -m silver_bot.demo_readiness --output out/demo_readiness_report.json` | exit 0; `ready` true; 18 checks, all passed (`demo_config_validation` through `no_committed_secrets`) |
| 4 (negative) | same, with `BINANCE_TESTNET=false` and `BINANCE_FUTURES_BASE_URL=https://fapi.binance.com` in the process environment | exit 2; `ready` false; failed: `demo_config_validation` (`BINANCE_TESTNET must be true when MODE=demo`), `binance_testnet_enabled`, `binance_testnet_endpoint` |
| 5 | `python -m silver_bot.health; echo $?` | no output, `0` |
| 5 | `python -m silver_bot; echo $?` | Observed at `099085b` (2026-10-09): `ERROR silver_bot.main demo mode not available yet: needs market data (G-13)`, `78`. Since `973cd82` this starts a demo session instead; the new smoke run needs the network and was not run here. The same path is covered offline by `tests/test_main.py::test_paper_mode_runs_on_market_data_and_writes_report` (paper, mocked klines) and `::test_market_data_failure_exits_1_and_audits` |
| 5 (negative) | `BINANCE_TESTNET=false python -m silver_bot` | `ERROR silver_bot.main configuration rejected: BINANCE_TESTNET must be true when MODE=demo`, exit `2` |
| 6 | `touch data/KILL_SWITCH`, then the checker | exit `2` (file removed afterwards) |

The placeholder keys passed, which confirms that the checker does not validate keys with the exchange. Not run: step 1 (it needs a testnet account and the network), the compose commands (no Docker daemon was used), and the step 5 smoke run, which contacts the testnet.

Done means: the checker exits 0 with 18 passed checks, health exits 0, the smoke run exits 0 (not 1 or 2) and writes `reports/paper_trading_report.json` with `mode` `demo`, the kill-switch file is absent, `LIVE_TRADING` is `false`, and no key value appears in any tracked file, in the readiness report or in the audit log.

## Self-Check

- [x] Every runnable command was executed against the code with a temporary demo `.env` containing placeholder values; no real key was used and the repository `.env` was not read or changed.
- [x] The runbook states that demo reads public testnet klines with simulated fills, places no order and sends no key, and defines the smoke run accordingly.
- [x] Key creation requires trade-only permission with withdrawals disabled, a separate testnet account and a private git-ignored `.env`.
- [x] The exact-host URL check (G-10) and the kill-switch path the demo runtime reads (G-6) are stated next to the settings they affect.
- [x] No em dash and no live-trading step appears; live remains `Planned, blocked`.
- [ ] Step 1 and the Docker commands were not executed, so they are described from the site rules and the compose file only.
