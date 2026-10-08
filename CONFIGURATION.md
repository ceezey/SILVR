# Configuration Checklist

This bot is configured from safe defaults, optional `config.yaml`, optional
`.env`, and finally process environment variables. Later sources override
earlier sources.

Live trading is not implemented or approved. Default examples must stay:

```text
LIVE_TRADING=false
PAPER_TRADING=true
DEMO_TRADING=false
```

## Configuration Files

Current files:

```text
.env.example
config.example.yaml
Dockerfile
docker-compose.yaml
deploy/systemd/silver-bot.service
deploy/scripts/prepare-host.sh
deploy/logrotate/silver-bot
```

Local files you may create:

```text
.env
config.yaml
```

Never commit `.env`, real API keys, Telegram tokens, private keys, account
screenshots, runtime databases, logs, models, or reports with private data.

## Environment Variables Used By Code

Runtime configuration loaded by `silver_bot.config.load_config`:

| Variable | Required | Safe default | Notes |
| --- | --- | --- | --- |
| `MODE` | Optional | blank | Alias for `TRADING_MODE`; use `demo` for Binance Futures demo/testnet. |
| `TRADING_MODE` | Optional | `paper` | Allowed by app config: `paper`, `backtest`, `demo`. `live` is rejected. |
| `LIVE_TRADING` | Optional | `false` | `true` is rejected by app config. |
| `PAPER_TRADING` | Optional | `true` | Must be `true` when `TRADING_MODE=paper`. |
| `DEMO_TRADING` | Optional | `false` | Must be `true` only for `MODE=demo`; cannot be combined with live or paper mode. |
| `DATABASE_PATH` | Optional | `data/silver_bot.sqlite3` | Must be a file path, not a directory, and must not use `..`. |
| `EXCHANGE_NAME` | Optional | `binance_futures` | Letters, numbers, and underscores only. |
| `SYMBOL` | Optional | `BTCUSDT` | Letters and numbers only, uppercased internally. |
| `TIMEFRAME` | Optional | `1m` | Must look like `1m`, `5m`, `1h`, `4h`, or `1d`. |
| `BINANCE_API_KEY` | Optional | blank | If provided, secret must also be provided. Use placeholders in examples. |
| `BINANCE_API_SECRET` | Optional | blank | If provided, key must also be provided. Use placeholders in examples. |
| `BINANCE_TESTNET` | Optional | `false` | Must be `true` for demo/testnet mode. |
| `BINANCE_FUTURES_BASE_URL` | Optional | blank | Optional override; demo mode only allows Binance Futures testnet. |
| `TELEGRAM_ENABLED` | Optional | `false` | If `true`, token and chat ID are required. |
| `TELEGRAM_BOT_TOKEN` | Optional | blank | Required only when Telegram is enabled. |
| `TELEGRAM_CHAT_ID` | Optional | blank | Required only when Telegram is enabled. |
| `ML_FILTER_ENABLED` | Optional | `false` | Optional probability filter. |
| `ML_REGISTRY_PATH` | Optional | `models/model_registry.json` | Must be a file path and must not use `..`. |
| `ML_MIN_PROBABILITY` | Optional | `0.60` | Must be between 0 and 1. |
| `ML_REDUCE_RISK_THRESHOLD` | Optional | `0.55` | Must be between 0 and `ML_MIN_PROBABILITY`. |
| `STOP_LOSS_REQUIRED` | Optional | `true` | Must be `true` in demo/testnet mode. |

Live-readiness variables used by `silver_bot.readiness`:

| Variable | Required for readiness pass | Safe default | Notes |
| --- | --- | --- | --- |
| `BACKTEST_REPORT_PATH` | Yes | `reports/backtest_report.json` | File must exist. |
| `OOS_VALIDATION_REPORT_PATH` | Yes | `reports/out_of_sample_validation_report.json` | File must exist. |
| `PAPER_TRADING_REPORT_PATH` | Yes | `reports/paper_trading_report.json` | File must exist. |
| `RISK_ENGINE_ENABLED` | Yes | `true` | Must be `true`. |
| `KILL_SWITCH_ENABLED` | Yes | `false` | Must be `true` for readiness pass. |
| `KILL_SWITCH_PATH` | Yes | blank | Required when kill switch is enabled; the file must not already exist for readiness to pass. |
| `TELEGRAM_ALERTS_TESTED` | Conditional | `false` | Required as `true` when `TELEGRAM_ENABLED=true`. |
| `READINESS_CHECK_PASSED` | Yes | `false` | Manual final confirmation. |
| `API_WITHDRAWALS_DISABLED` | Yes | `false` | Manual API-security confirmation. |
| `MAX_RISK_PER_TRADE` | Yes | `0.005` | Must be greater than 0 and no more than `0.005`. |
| `MAX_DAILY_LOSS` | Yes | `0.02` | Must be greater than 0 and no more than `0.02`. |
| `MAX_LEVERAGE` | Yes | `3` | Must be greater than 0 and no more than `3`. |

Deployment-only variables in Docker files:

```text
PYTHONDONTWRITEBYTECODE=1
PYTHONUNBUFFERED=1
```

## config.yaml Fields Used By Code

`config.yaml` is optional. The parser supports simple YAML-like key/value
sections only; it is not a full YAML parser.

Root-level aliases:

```yaml
mode: paper
database_path: data/silver_bot.sqlite3
exchange_name: binance_futures
telegram_enabled: false
telegram_bot_token: ""
telegram_chat_id: ""
ml_enabled: false
ml_filter_enabled: false
ml_registry_path: models/model_registry.json
ml_min_probability: 0.60
ml_reduce_risk_threshold: 0.55
```

Section aliases:

```yaml
trading:
  mode: paper
  live_trading: false
  paper_trading: true
  demo_trading: false

exchange:
  symbol: BTCUSDT
  timeframe: 1m
  binance_api_key: ""
  binance_api_secret: ""
  binance_testnet: false
  binance_futures_base_url: ""

risk:
  engine_enabled: true
  kill_switch_enabled: false
  kill_switch_path: ""
  stop_loss_required: true
  max_risk_per_trade: 0.005
  max_daily_loss: 0.02
  max_leverage: 3

telegram:
  enabled: false
  bot_token: ""
  chat_id: ""

alerts:
  telegram_enabled: false
  telegram_bot_token: ""
  telegram_chat_id: ""

ml:
  enabled: false
  filter_enabled: false
  registry_path: models/model_registry.json
  min_probability: 0.60
  reduce_risk_threshold: 0.55
```

Environment variables override `config.yaml`.

## Backtest Configuration

Minimum safe values:

```text
TRADING_MODE=backtest
LIVE_TRADING=false
PAPER_TRADING=false
DATABASE_PATH=data/silver_bot.sqlite3
SYMBOL=BTCUSDT
TIMEFRAME=1m
ML_FILTER_ENABLED=false
```

Backtest mode does not require Binance API keys or Telegram settings.

## Paper Trading Configuration

Minimum safe values:

```text
TRADING_MODE=paper
LIVE_TRADING=false
PAPER_TRADING=true
DATABASE_PATH=data/silver_bot.sqlite3
SYMBOL=BTCUSDT
TIMEFRAME=1m
TELEGRAM_ENABLED=false
ML_FILTER_ENABLED=false
```

Telegram is optional. If enabled, manually fill:

```text
TELEGRAM_BOT_TOKEN=<your-paper-alert-bot-token>
TELEGRAM_CHAT_ID=<your-chat-id>
```

## Demo/Testnet Configuration

Demo mode uses Binance Futures demo/testnet credentials and endpoints only. It
is not real-money live trading, but it is also not paper simulation. It must
remain isolated from production Binance endpoints:

```text
MODE=demo
TRADING_MODE=demo
DEMO_TRADING=true
BINANCE_TESTNET=true
LIVE_TRADING=false
PAPER_TRADING=false
BINANCE_API_KEY=<demo-testnet-api-key>
BINANCE_API_SECRET=<demo-testnet-api-secret>
BINANCE_FUTURES_BASE_URL=https://testnet.binancefuture.com
RISK_ENGINE_ENABLED=true
KILL_SWITCH_ENABLED=true
KILL_SWITCH_PATH=KILL_SWITCH
STOP_LOSS_REQUIRED=true
MAX_RISK_PER_TRADE=0.005
MAX_DAILY_LOSS=0.02
MAX_LEVERAGE=3
```

Demo mode rejects production Binance URLs, `LIVE_TRADING=true`, disabled
testnet mode, disabled risk engine, disabled kill switch, disabled stop-loss
requirements, and unsafe risk/leverage limits.

Run demo readiness without placing orders:

```bash
python -m silver_bot.demo_readiness
```

It writes:

```text
reports/demo_readiness_report.json
```

## Research Configuration

The Docker Compose `research` service currently uses safe backtest startup:

```text
TRADING_MODE=backtest
LIVE_TRADING=false
PAPER_TRADING=false
ML_FILTER_ENABLED=false
```

Research mode must never place orders.

## ML Configuration

ML is optional and disabled by default:

```text
ML_FILTER_ENABLED=false
ML_REGISTRY_PATH=models/model_registry.json
ML_MIN_PROBABILITY=0.60
ML_REDUCE_RISK_THRESHOLD=0.55
```

If enabled, an active model registry must exist and ML can only approve, reject,
or reduce risk on existing rule-based signals. ML cannot generate trades.

## Telegram Configuration

Disabled default:

```text
TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

Enabled paper alerts:

```text
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=<paper-alert-token>
TELEGRAM_CHAT_ID=<chat-id>
```

Do not commit real Telegram tokens.

## Deployment Configuration

Docker and Compose default to paper mode:

```text
TRADING_MODE=paper
LIVE_TRADING=false
PAPER_TRADING=true
DATABASE_PATH=/app/data/silver_bot.sqlite3
ML_REGISTRY_PATH=/app/models/model_registry.json
```

Runtime directories are mounted:

```text
./data:/app/data
./logs:/app/logs
./models:/app/models
./reports:/app/reports
```

`.env` is excluded from Docker image builds by `.dockerignore`.

The Compose `demo` profile is explicit and still forces `LIVE_TRADING=false`:

```bash
docker compose build
docker compose --profile demo run --rm demo python -m silver_bot.demo_readiness
docker compose --profile demo run --rm demo
```

The demo profile sets the non-secret safety gates itself:

```text
MODE=demo
TRADING_MODE=demo
DEMO_TRADING=true
BINANCE_TESTNET=true
BINANCE_FUTURES_BASE_URL=https://testnet.binancefuture.com
LIVE_TRADING=false
PAPER_TRADING=false
RISK_ENGINE_ENABLED=true
KILL_SWITCH_ENABLED=true
KILL_SWITCH_PATH=/app/data/KILL_SWITCH
STOP_LOSS_REQUIRED=true
MAX_RISK_PER_TRADE=0.005
MAX_DAILY_LOSS=0.02
MAX_LEVERAGE=3
```

You still must supply demo/testnet `BINANCE_API_KEY` and
`BINANCE_API_SECRET` through local runtime configuration only.

## Live Readiness Configuration

This is not live mode. It only generates a readiness report:

```bash
python -m silver_bot.readiness --output reports/live_readiness_report.json
```

For the readiness report to pass, you must manually provide:

```text
BACKTEST_REPORT_PATH=reports/backtest_report.json
OOS_VALIDATION_REPORT_PATH=reports/out_of_sample_validation_report.json
PAPER_TRADING_REPORT_PATH=reports/paper_trading_report.json
RISK_ENGINE_ENABLED=true
KILL_SWITCH_ENABLED=true
KILL_SWITCH_PATH=KILL_SWITCH
TELEGRAM_ENABLED=false
TELEGRAM_ALERTS_TESTED=false
BINANCE_API_KEY=<env-only-api-key>
BINANCE_API_SECRET=<env-only-api-secret>
LIVE_TRADING=true
PAPER_TRADING=false
READINESS_CHECK_PASSED=true
API_WITHDRAWALS_DISABLED=true
MAX_RISK_PER_TRADE=0.005
MAX_DAILY_LOSS=0.02
MAX_LEVERAGE=3
```

If `TELEGRAM_ENABLED=true`, then `TELEGRAM_ALERTS_TESTED=true` is required
after an actual alert test.

The readiness checker also requires the `KILL_SWITCH_PATH` file to be absent.
If that file exists, the kill switch is active and live readiness is blocked.

The current application still rejects live startup. Passing readiness does not
place orders and does not implement live execution.

## Example .env For Paper Mode

```dotenv
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

## Example .env For Readiness Check Mode

This example is for report generation only. Do not use it to start trading.

```dotenv
TRADING_MODE=paper
LIVE_TRADING=false
PAPER_TRADING=true

BACKTEST_REPORT_PATH=reports/backtest_report.json
OOS_VALIDATION_REPORT_PATH=reports/out_of_sample_validation_report.json
PAPER_TRADING_REPORT_PATH=reports/paper_trading_report.json
RISK_ENGINE_ENABLED=true
KILL_SWITCH_ENABLED=true
KILL_SWITCH_PATH=KILL_SWITCH
TELEGRAM_ENABLED=false
TELEGRAM_ALERTS_TESTED=false
BINANCE_API_KEY=<env-only-api-key>
BINANCE_API_SECRET=<env-only-api-secret>
READINESS_CHECK_PASSED=false
API_WITHDRAWALS_DISABLED=false
MAX_RISK_PER_TRADE=0.005
MAX_DAILY_LOSS=0.02
MAX_LEVERAGE=3
```

For a readiness pass, the checker specifically expects `LIVE_TRADING=true` and
`PAPER_TRADING=false`, but the running bot still blocks live mode. Keep normal
runtime examples on `LIVE_TRADING=false`.

## Manual Values You Must Fill In

For ordinary paper mode:

```text
SYMBOL
TIMEFRAME
TELEGRAM_BOT_TOKEN if TELEGRAM_ENABLED=true
TELEGRAM_CHAT_ID if TELEGRAM_ENABLED=true
```

For demo/testnet mode:

```text
MODE=demo
DEMO_TRADING=true
BINANCE_TESTNET=true
LIVE_TRADING=false
PAPER_TRADING=false
BINANCE_API_KEY with a demo/testnet key
BINANCE_API_SECRET with a demo/testnet secret
KILL_SWITCH_PATH
```

For ML:

```text
ML_REGISTRY_PATH to a valid active model registry if ML_FILTER_ENABLED=true
```

For readiness report only:

```text
BACKTEST_REPORT_PATH
OOS_VALIDATION_REPORT_PATH
PAPER_TRADING_REPORT_PATH
KILL_SWITCH_PATH
BINANCE_API_KEY from environment only
BINANCE_API_SECRET from environment only
TELEGRAM_ALERTS_TESTED if Telegram is enabled
READINESS_CHECK_PASSED after manual review
API_WITHDRAWALS_DISABLED after exchange API permission review
MAX_RISK_PER_TRADE
MAX_DAILY_LOSS
MAX_LEVERAGE
```

## Do Not Enable Live Yet

Live trading is not approved. Do not add real keys to committed files, do not
turn on live execution, and do not bypass the readiness checker, risk engine, or
kill switch.
