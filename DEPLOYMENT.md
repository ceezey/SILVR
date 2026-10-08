# Deployment Guide

## Purpose

This document explains how to deploy the bot safely for 24/7 operation.

Recommended deployment:

```text
VPS + Docker + systemd + Telegram alerts
```

## Deployment Principle

The bot must be deployed in paper mode first.

Binance Futures demo/testnet mode is a separate non-real-money mode for
exchange-facing validation. It must still keep `LIVE_TRADING=false`.

Live mode should only be enabled after the readiness checklist passes.

## Recommended Hosting

Recommended options:

```text
Oracle Cloud Always Free VPS
Low-cost VPS
Local machine for development only
```

Do not rely on personal laptop uptime for live trading.

## Environment Files

Create:

```text
.env
config.yaml
```

Never commit `.env`.

Use these examples:

```text
.env.example
config.example.yaml
CONFIGURATION.md
```

Required `.gitignore` entries:

```text
.env
logs/
data/raw/
data/processed/
models/
reports/
*.sqlite
*.db
```

## Environment Variables

Current safe paper-mode example:

```text
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
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
ML_FILTER_ENABLED=false
ML_REGISTRY_PATH=models/model_registry.json
ML_MIN_PROBABILITY=0.60
ML_REDUCE_RISK_THRESHOLD=0.55
```

See `CONFIGURATION.md` for all runtime, YAML, ML, Telegram, deployment, and
readiness variables.

## Docker Deployment

Build image:

```bash
docker build -t ict-silver-bullet-bot .
```

Run the image default. This starts the current safe application startup in
paper mode:

```bash
docker run --rm \
  --env-file .env \
  -e LIVE_TRADING=false \
  -e TRADING_MODE=paper \
  -e PAPER_TRADING=true \
  -v "$PWD/data:/app/data" \
  -v "$PWD/logs:/app/logs" \
  -v "$PWD/models:/app/models" \
  -v "$PWD/reports:/app/reports" \
  ict-silver-bullet-bot
```

Run backtest startup:

```bash
docker run --rm \
  --env-file .env \
  -e LIVE_TRADING=false \
  -e TRADING_MODE=backtest \
  -e PAPER_TRADING=false \
  -v "$PWD/data:/app/data" \
  -v "$PWD/logs:/app/logs" \
  -v "$PWD/models:/app/models" \
  -v "$PWD/reports:/app/reports" \
  ict-silver-bullet-bot
```

The Docker image default command is:

```text
python -m silver_bot
```

There is intentionally no default live-trading command.

## Docker Compose

Available services:

```text
bot
paper
demo
backtest
research
```

The first version uses SQLite and host-mounted runtime directories. PostgreSQL
can be added later if needed.

Prepare local runtime directories and a local `.env` file:

```bash
sh deploy/scripts/prepare-host.sh
```

Build the image:

```bash
docker compose build
```

Run the default paper-mode service:

```bash
docker compose up bot
```

Run paper mode as a one-off command:

```bash
docker compose --profile paper run --rm paper
```

Run demo/testnet startup after configuring demo/testnet `.env` values:

```bash
docker compose --profile demo run --rm demo
```

Run backtest startup:

```bash
docker compose --profile backtest run --rm backtest
```

Run research-safe startup:

```bash
docker compose --profile research run --rm research
```

All Compose services force:

```text
LIVE_TRADING=false
```

The `demo` profile also forces:

```text
MODE=demo
TRADING_MODE=demo
DEMO_TRADING=true
BINANCE_TESTNET=true
PAPER_TRADING=false
```

The `data`, `logs`, `models`, and `reports` directories are mounted as volumes:

```text
./data:/app/data
./logs:/app/logs
./models:/app/models
./reports:/app/reports
```

Do not bake `.env` or secrets into the image. The `.dockerignore` file excludes
`.env`, runtime state, database files, logs, reports, model artifacts, and local
development caches.

## systemd Service

Create a service file:

```text
/etc/systemd/system/silver-bot.service
```

An example service file is included at:

```text
deploy/systemd/silver-bot.service
```

Install it:

```bash
sudo cp deploy/systemd/silver-bot.service /etc/systemd/system/silver-bot.service
sudo systemctl daemon-reload
```

Enable service:

```bash
sudo systemctl enable silver-bot
```

Start service:

```bash
sudo systemctl start silver-bot
```

View logs:

```bash
sudo journalctl -u silver-bot -f
```

The service starts the Compose `bot` service, which defaults to paper mode.

## VPS Setup Checklist

1. Create VPS.
2. Add SSH key.
3. Update packages.
4. Install Docker.
5. Install Docker Compose.
6. Clone private repository.
7. Create `.env`.
8. Confirm `.env` is not committed.
9. Run `sh deploy/scripts/prepare-host.sh`.
10. Review `.env` and keep `LIVE_TRADING=false`.
11. Build the image with `docker compose build`.
12. Run tests locally or in CI before deployment.
13. Run backtest startup with `docker compose --profile backtest run --rm backtest`.
14. Run paper mode with `docker compose up bot`.
15. Confirm Telegram alerts if enabled.
16. Install log rotation from `deploy/logrotate/silver-bot`.
17. Enable systemd service.
18. Monitor logs.

## Security Checklist

API key must have:

```text
withdrawals disabled
IP restriction enabled if possible
minimum required permissions
```

Repository must not contain:

```text
API keys
secret tokens
private keys
account screenshots
.env file
```

Container image must not contain:

```text
.env
config.yaml with secrets
runtime SQLite databases
logs
models with private metadata
reports with account information
```

Secrets should be provided at runtime through a local `.env` file or a VPS
secret manager. The Compose file may read `.env`, but Docker build must not copy
it into the image.

## Production Safety Checklist

Before enabling unattended paper deployment:

```text
LIVE_TRADING=false confirmed
TRADING_MODE=paper confirmed
PAPER_TRADING=true confirmed
.env permissions restricted
data/logs/models/reports mounted as volumes
health check passes
kill switch path tested
Telegram alerts tested if enabled
systemd restart behavior tested
log rotation installed
backtest startup command tested
paper startup command tested
```

## Paper Deployment Checklist

Paper mode is ready when:

```text
bot runs continuously
WebSocket reconnect works
data is stored correctly
signals are logged
paper trades are simulated
Telegram alerts work
daily report works
kill switch works
```

## Demo/Testnet Deployment Checklist

Demo/testnet mode is ready when:

```text
python -m silver_bot.demo_readiness passes
MODE=demo
DEMO_TRADING=true
BINANCE_TESTNET=true
LIVE_TRADING=false
PAPER_TRADING=false
Binance Futures testnet endpoint confirmed
demo/testnet API keys are loaded from private environment values
risk engine enabled
kill switch enabled and tested
stop loss required
safe risk and leverage limits confirmed
```

Generate a demo readiness report without placing orders:

```bash
python -m silver_bot.demo_readiness
```

The report is written to:

```text
reports/demo_readiness_report.json
```

## Live Deployment Checklist

Live mode is blocked unless:

```text
profitable or acceptable backtest
out-of-sample validation passed
paper trading stable
risk engine tested
kill switch tested
Telegram alerts tested
API key secured
withdrawals disabled
manual approval given
```

Generate a readiness report without placing orders:

```bash
python -m silver_bot.readiness --output reports/live_readiness_report.json
```

The readiness checker requires explicit evidence paths and confirmations:

```text
BACKTEST_REPORT_PATH=reports/backtest_report.json
OOS_VALIDATION_REPORT_PATH=reports/out_of_sample_validation_report.json
PAPER_TRADING_REPORT_PATH=reports/paper_trading_report.json
RISK_ENGINE_ENABLED=true
KILL_SWITCH_ENABLED=true
KILL_SWITCH_PATH=KILL_SWITCH
TELEGRAM_ENABLED=false
TELEGRAM_ALERTS_TESTED=false
READINESS_CHECK_PASSED=true
API_WITHDRAWALS_DISABLED=true
MAX_RISK_PER_TRADE=0.005
MAX_DAILY_LOSS=0.02
MAX_LEVERAGE=3
```

If Telegram is enabled, `TELEGRAM_ALERTS_TESTED=true` is required. API keys for
readiness must be present in the process environment as `BINANCE_API_KEY` and
`BINANCE_API_SECRET`. The checker does not place orders and does not implement
live execution. The configured `KILL_SWITCH_PATH` file must also be absent; if
it exists, the kill switch is active and readiness remains blocked.

## Emergency Commands

Stop service:

```bash
sudo systemctl stop silver-bot
```

Restart service:

```bash
sudo systemctl restart silver-bot
```

View logs:

```bash
sudo journalctl -u silver-bot -f
```

Docker stop:

```bash
docker compose down
```

Create or activate the kill-switch file configured for the bot before stopping
services if a safety lockout is needed.

## Deployment Rule

Never deploy live trading directly.

Deployment order:

```text
backtest
paper
demo/testnet
small live test
full live only after proven stability
```
