# Demo / Testnet Runbook (RUNBOOK)

**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Version:** 0.1
**Owner:** Cian Jake Francisco
**Status:** Draft
**Last updated:** 2026-10-08
**Last reconciled:** 2026-10-08 against code at commit `62037d1`

This runbook prepares and checks Binance Futures demo (testnet) mode: creating testnet keys, setting the demo environment, running the demo readiness checker, a dry startup, verification and stopping. It absorbs the demo steps of the old `DEPLOYMENT.md` and the demo example of the old `CONFIGURATION.md`.

**What is not possible yet.** Demo mode today is configuration plus a readiness report. The Binance adapter performs no network I/O: no HTTP, no request signing, no endpoint paths; `fetch_ohlcv` raises `NotImplementedError`, and `place_order` and `cancel_order` always raise `OrderPlacementDisabled`. The entrypoint ignores the mode and runs a startup stub (G-3). So you cannot connect to the testnet, fetch candles, place a testnet order or run a demo session. A "dry startup" here means: configuration loads, the readiness checker passes, the health check passes, and the startup stub exits 0. A ready report also does not prove the keys are valid: the checker only tests that both values are non-blank. Live trading remains blocked at configuration load (`Planned, blocked`).

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
   BINANCE_API_KEY=REPLACE_WITH_TESTNET_KEY
   BINANCE_API_SECRET=REPLACE_WITH_TESTNET_SECRET
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

   What the flags do. `DEMO_TRADING=true` turns on every demo requirement, even if the mode is not `demo`. `PAPER_TRADING` must be `false` when `DEMO_TRADING=true`. `LIVE_TRADING` must stay `false` (true is rejected). `BINANCE_TESTNET=true` plus a base URL containing `testnet.binancefuture.com` is required; the URL check is a substring match, so a lookalike host would pass (G-10): type the URL exactly as shown. The risk limits are range-checked in demo mode only: risk per trade at most 0.005, daily loss at most 0.02, leverage at most 3. `KILL_SWITCH_PATH` must be set, but the runtime does not pass it to the risk engine (G-6), so it is a readiness gate, not an effective stop.

4. **Run the demo readiness checker.** It writes a JSON report and places no orders. Send the report to a folder of your choice:

   ```bash
   python -m silver_bot.demo_readiness --output out/demo_readiness_report.json
   ```

   The default output path is `reports/demo_readiness_report.json`, the repository evidence folder, which is why these steps write to `out/` instead. Exit code 0 means all 18 checks passed; exit code 2 means at least one failed, and the report lists each failed check with its reason. The checker reads `.env` from the current folder and overlays the process environment. It does not read values that exist only in `config.yaml` (except for the first check), so put demo values in `.env`.

5. **Dry startup.** Confirm the health check and the startup stub accept the configuration:

   ```bash
   python -m silver_bot.health
   python -m silver_bot
   ```

   Both exit 0. The second logs `silver bot initialized`, creates the SQLite file and writes `bot_started` and `bot_stopped` to `logs/audit.jsonl`. It does not connect to Binance. To use the container instead, `docker compose --profile demo run --rm demo` runs the same stub with the `demo` profile settings (see [ops-silverbot.md](ops-silverbot.md)); and `docker compose --profile demo run --rm demo python -m silver_bot.demo_readiness` runs the checker inside it.

6. **Test the kill-switch file the way the checkers see it.** The readiness check `kill_switch_not_active` fails while the file exists, so the file must be absent when you want a ready report:

   ```bash
   touch data/KILL_SWITCH
   python -m silver_bot.demo_readiness --output out/demo_readiness_report.json
   rm data/KILL_SWITCH
   ```

   The first run exits 2 with the switch present; after removing the file the checker passes again. This proves the gate, not an emergency stop: nothing in the running bot consults the file today.

7. **Stop.** The startup stub exits by itself. If you started the compose `bot` service or the systemd unit, stop it with the commands in [ops-silverbot.md](ops-silverbot.md) section 4.1 (use `sudo systemctl stop silver-bot` when the unit is enabled, because it restarts the container otherwise). Remove testnet keys from `.env` when you finish, or revoke them on the testnet site.

## Verify

Run against a temporary folder holding only a demo `.env` with placeholder key values (`fake-testnet-key`, `fake-testnet-secret`), a `.gitignore` containing `.env`, and the block from step 3.

| Step | Command | Observed |
|------|---------|----------|
| 4 | `python -m silver_bot.demo_readiness --output out/demo_readiness_report.json` | exit 0; `ready` true; 18 checks, all passed (`demo_config_validation` through `no_committed_secrets`) |
| 4 (negative) | same, with `BINANCE_TESTNET=false` and `BINANCE_FUTURES_BASE_URL=https://fapi.binance.com` in the process environment | exit 2; `ready` false; failed: `demo_config_validation` (`BINANCE_TESTNET must be true when MODE=demo`), `binance_testnet_enabled`, `binance_testnet_endpoint` |
| 5 | `python -m silver_bot.health; echo $?` | no output, `0` |
| 5 | `python -m silver_bot; echo $?` | `INFO silver_bot.main silver bot initialized`, `0` |
| 5 (negative) | `BINANCE_TESTNET=false python -m silver_bot` | `ERROR silver_bot.main configuration rejected: BINANCE_TESTNET must be true when MODE=demo`, exit `2` |
| 6 | `touch data/KILL_SWITCH`, then the checker | exit `2` (file removed afterwards) |

The placeholder keys passed, which confirms that the checker does not validate keys with the exchange. Not run: step 1 (it needs a testnet account and the network), the compose commands (no Docker daemon was used), and any command that would contact Binance (none exists).

Done means: the checker exits 0 with 18 passed checks, health and startup exit 0, the kill-switch file is absent, `LIVE_TRADING` is `false`, and no key value appears in any tracked file, in the readiness report or in the audit log.

## Self-Check

- [x] Every runnable command was executed against the code with a temporary demo `.env` containing placeholder values; no real key was used and the repository `.env` was not read or changed.
- [x] The runbook states that no network I/O, order placement or demo session exists, and defines "dry startup" accordingly.
- [x] Key creation requires trade-only permission with withdrawals disabled, a separate testnet account and a private git-ignored `.env`.
- [x] The substring URL check (G-10) and the inert kill-switch path (G-6) are stated next to the settings they affect.
- [x] No em dash and no live-trading step appears; live remains `Planned, blocked`.
- [ ] Step 1 and the Docker commands were not executed, so they are described from the site rules and the compose file only.
