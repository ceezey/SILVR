"""Typed configuration loading for safe bot startup."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit


class ConfigError(ValueError):
    """Raised when configuration is missing, invalid, or unsafe."""


class TradingMode(str, Enum):
    """Supported safe runtime modes."""

    BACKTEST = "backtest"
    DEMO = "demo"
    PAPER = "paper"


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Validated application configuration."""

    mode: TradingMode = TradingMode.PAPER
    live_trading: bool = False
    paper_trading: bool = True
    demo_trading: bool = False
    # Kept out of repr: a Postgres URL carries the password.
    database_url: str | None = field(default=None, repr=False)
    exchange_name: str = "binance_futures"
    symbol: str = "BTCUSDT"
    timeframe: str = "1m"
    api_key: str | None = None
    api_secret: str | None = None
    binance_testnet: bool = False
    binance_base_url: str | None = None
    telegram_enabled: bool = False
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    ml_filter_enabled: bool = False
    ml_registry_path: Path = Path("models/model_registry.json")
    ml_min_probability: float = 0.60
    ml_reduce_risk_threshold: float = 0.55
    risk_engine_enabled: bool = True
    kill_switch_enabled: bool = False
    kill_switch_path: Path | None = None
    stop_loss_required: bool = True
    max_risk_per_trade: float = 0.005
    max_daily_loss: float = 0.02
    max_leverage: float = 3.0


def load_config(
    *,
    env_path: str | Path = ".env",
    yaml_path: str | Path = "config.yaml",
    environ: Mapping[str, str] | None = None,
) -> AppConfig:
    """Load config from defaults, optional config.yaml, optional .env, and env.

    Later sources override earlier sources. Live trading is rejected in Phase 1.
    """

    raw: dict[str, str] = {
        "TRADING_MODE": TradingMode.PAPER.value,
        "LIVE_TRADING": "false",
        "PAPER_TRADING": "true",
        "DEMO_TRADING": "false",
        "DATABASE_URL": "",
        "EXCHANGE_NAME": "binance_futures",
        "SYMBOL": "BTCUSDT",
        "TIMEFRAME": "1m",
        "BINANCE_TESTNET": "false",
        "BINANCE_FUTURES_BASE_URL": "",
        "TELEGRAM_ENABLED": "false",
        "ML_FILTER_ENABLED": "false",
        "ML_REGISTRY_PATH": "models/model_registry.json",
        "ML_MIN_PROBABILITY": "0.60",
        "ML_REDUCE_RISK_THRESHOLD": "0.55",
        "RISK_ENGINE_ENABLED": "true",
        "KILL_SWITCH_ENABLED": "false",
        "KILL_SWITCH_PATH": "",
        "STOP_LOSS_REQUIRED": "true",
        "MAX_RISK_PER_TRADE": "0.005",
        "MAX_DAILY_LOSS": "0.02",
        "MAX_LEVERAGE": "3",
    }
    raw.update(_flatten_config_yaml(Path(yaml_path)))
    raw.update(_read_env_file(Path(env_path)))
    raw.update(dict(os.environ if environ is None else environ))
    if raw.get("MODE", "").strip():
        raw["TRADING_MODE"] = raw["MODE"]
    if _parse_bool(raw.get("DEMO_TRADING", "false"), "DEMO_TRADING") and raw.get("TRADING_MODE") == TradingMode.PAPER.value:
        raw["TRADING_MODE"] = TradingMode.DEMO.value

    mode = _parse_mode(raw.get("TRADING_MODE", TradingMode.PAPER.value))
    live_trading = _parse_bool(raw.get("LIVE_TRADING", "false"), "LIVE_TRADING")
    paper_trading = _parse_bool(raw.get("PAPER_TRADING", "true"), "PAPER_TRADING")
    demo_trading = _parse_bool(raw.get("DEMO_TRADING", "false"), "DEMO_TRADING")

    if live_trading:
        raise ConfigError("LIVE_TRADING=true is rejected in Phase 1")
    if raw.get("TRADING_MODE", "").strip().lower() == "live":
        raise ConfigError("TRADING_MODE=live is not supported in Phase 1")
    if mode == TradingMode.PAPER and not paper_trading:
        raise ConfigError("PAPER_TRADING must be true when TRADING_MODE=paper")
    if mode == TradingMode.DEMO and not demo_trading:
        raise ConfigError("DEMO_TRADING must be true when MODE=demo")
    if demo_trading and live_trading:
        raise ConfigError("DEMO_TRADING=true cannot be combined with LIVE_TRADING=true")
    if demo_trading and paper_trading:
        raise ConfigError("PAPER_TRADING must be false when DEMO_TRADING=true")

    database_url = _blank_to_none(raw.get("DATABASE_URL"))
    if database_url is not None and urlsplit(database_url).scheme not in {"postgresql", "postgres"}:
        raise ConfigError("DATABASE_URL must be a postgresql:// URL")
    exchange_name = _required(raw, "EXCHANGE_NAME").strip().lower()
    if not exchange_name.replace("_", "").isalnum():
        raise ConfigError("EXCHANGE_NAME must contain only letters, numbers, or underscores")
    symbol = _required(raw, "SYMBOL").strip().upper()
    if not symbol.isalnum():
        raise ConfigError("SYMBOL must contain only letters and numbers")
    timeframe = _required(raw, "TIMEFRAME").strip().lower()
    if not timeframe[:-1].isdigit() or timeframe[-1:] not in {"m", "h", "d", "w"}:
        raise ConfigError("TIMEFRAME must look like 1m, 5m, 1h, 4h, or 1d")

    api_key = _blank_to_none(raw.get("BINANCE_API_KEY"))
    api_secret = _blank_to_none(raw.get("BINANCE_API_SECRET"))
    if bool(api_key) != bool(api_secret):
        raise ConfigError("BINANCE_API_KEY and BINANCE_API_SECRET must be provided together")
    binance_testnet = _parse_bool(raw.get("BINANCE_TESTNET", "false"), "BINANCE_TESTNET")
    binance_base_url = _blank_to_none(raw.get("BINANCE_FUTURES_BASE_URL"))
    if demo_trading and not api_key:
        raise ConfigError("BINANCE_API_KEY and BINANCE_API_SECRET are required for demo mode")
    if demo_trading and not binance_testnet:
        raise ConfigError("BINANCE_TESTNET must be true when MODE=demo")
    if demo_trading and binance_base_url and not is_binance_futures_testnet_url(binance_base_url):
        raise ConfigError("Demo mode requires a Binance Futures testnet endpoint")
    telegram_enabled = _parse_bool(raw.get("TELEGRAM_ENABLED", "false"), "TELEGRAM_ENABLED")
    telegram_bot_token = _blank_to_none(raw.get("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id = _blank_to_none(raw.get("TELEGRAM_CHAT_ID"))
    if telegram_enabled and (not telegram_bot_token or not telegram_chat_id):
        raise ConfigError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required when TELEGRAM_ENABLED=true")
    ml_filter_enabled = _parse_bool(raw.get("ML_FILTER_ENABLED", "false"), "ML_FILTER_ENABLED")
    ml_registry_path = Path(_required(raw, "ML_REGISTRY_PATH"))
    if ml_registry_path.name in {"", ".", ".."}:
        raise ConfigError("ML_REGISTRY_PATH must point to a model registry file")
    if ".." in ml_registry_path.parts:
        raise ConfigError("ML_REGISTRY_PATH must not traverse parent directories")
    if ml_registry_path.exists() and ml_registry_path.is_dir():
        raise ConfigError("ML_REGISTRY_PATH must point to a file, not a directory")
    ml_min_probability = _parse_float(raw.get("ML_MIN_PROBABILITY", "0.60"), "ML_MIN_PROBABILITY")
    ml_reduce_risk_threshold = _parse_float(
        raw.get("ML_REDUCE_RISK_THRESHOLD", "0.55"),
        "ML_REDUCE_RISK_THRESHOLD",
    )
    if not 0 <= ml_reduce_risk_threshold <= 1:
        raise ConfigError("ML_REDUCE_RISK_THRESHOLD must be between 0 and 1")
    if not 0 <= ml_min_probability <= 1:
        raise ConfigError("ML_MIN_PROBABILITY must be between 0 and 1")
    if ml_reduce_risk_threshold > ml_min_probability:
        raise ConfigError("ML_REDUCE_RISK_THRESHOLD must be less than or equal to ML_MIN_PROBABILITY")
    risk_engine_enabled = _parse_bool(raw.get("RISK_ENGINE_ENABLED", "true"), "RISK_ENGINE_ENABLED")
    kill_switch_enabled = _parse_bool(raw.get("KILL_SWITCH_ENABLED", "false"), "KILL_SWITCH_ENABLED")
    kill_switch_path = Path(raw["KILL_SWITCH_PATH"]) if _blank_to_none(raw.get("KILL_SWITCH_PATH")) else None
    if kill_switch_enabled and kill_switch_path is None:
        raise ConfigError("KILL_SWITCH_PATH is required when KILL_SWITCH_ENABLED=true")
    stop_loss_required = _parse_bool(raw.get("STOP_LOSS_REQUIRED", "true"), "STOP_LOSS_REQUIRED")
    max_risk_per_trade = _parse_float(raw.get("MAX_RISK_PER_TRADE", "0.005"), "MAX_RISK_PER_TRADE")
    max_daily_loss = _parse_float(raw.get("MAX_DAILY_LOSS", "0.02"), "MAX_DAILY_LOSS")
    max_leverage = _parse_float(raw.get("MAX_LEVERAGE", "3"), "MAX_LEVERAGE")
    if not 0 < max_risk_per_trade <= 0.005:
        raise ConfigError("MAX_RISK_PER_TRADE must be greater than 0 and no more than 0.005")
    if demo_trading:
        if not risk_engine_enabled:
            raise ConfigError("RISK_ENGINE_ENABLED must be true in demo mode")
        if not kill_switch_enabled:
            raise ConfigError("KILL_SWITCH_ENABLED must be true in demo mode")
        if kill_switch_path is None:
            raise ConfigError("KILL_SWITCH_PATH is required in demo mode")
        if not stop_loss_required:
            raise ConfigError("STOP_LOSS_REQUIRED must be true in demo mode")
        if not 0 < max_daily_loss <= 0.02:
            raise ConfigError("MAX_DAILY_LOSS must be greater than 0 and no more than 0.02 in demo mode")
        if not 0 < max_leverage <= 3:
            raise ConfigError("MAX_LEVERAGE must be greater than 0 and no more than 3 in demo mode")

    return AppConfig(
        mode=mode,
        live_trading=live_trading,
        paper_trading=paper_trading,
        demo_trading=demo_trading,
        database_url=database_url,
        exchange_name=exchange_name,
        symbol=symbol,
        timeframe=timeframe,
        api_key=api_key,
        api_secret=api_secret,
        binance_testnet=binance_testnet,
        binance_base_url=binance_base_url,
        telegram_enabled=telegram_enabled,
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
        ml_filter_enabled=ml_filter_enabled,
        ml_registry_path=ml_registry_path,
        ml_min_probability=ml_min_probability,
        ml_reduce_risk_threshold=ml_reduce_risk_threshold,
        risk_engine_enabled=risk_engine_enabled,
        kill_switch_enabled=kill_switch_enabled,
        kill_switch_path=kill_switch_path,
        stop_loss_required=stop_loss_required,
        max_risk_per_trade=max_risk_per_trade,
        max_daily_loss=max_daily_loss,
        max_leverage=max_leverage,
    )


def _parse_mode(value: str) -> TradingMode:
    normalized = value.strip().lower()
    try:
        return TradingMode(normalized)
    except ValueError as exc:
        allowed = ", ".join(mode.value for mode in TradingMode)
        raise ConfigError(f"TRADING_MODE must be one of: {allowed}") from exc


def _parse_bool(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ConfigError(f"{name} must be a boolean value")


def _parse_float(value: str, name: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc


def _required(raw: Mapping[str, str], name: str) -> str:
    value = raw.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required")
    return value


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.lstrip("\ufeff").strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise ConfigError(f"Invalid .env line {line_number}: expected KEY=value")
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key:
            raise ConfigError(f"Invalid .env line {line_number}: empty key")
        values[key] = _strip_quotes(value.strip())
    return values


def _flatten_config_yaml(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    section: str | None = None
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith(":") and ":" not in stripped[:-1]:
            section = stripped[:-1].strip().upper()
            continue
        if ":" not in stripped:
            raise ConfigError(f"Invalid config.yaml line {line_number}: expected key: value")
        key, value = stripped.split(":", 1)
        normalized_key = key.strip().upper()
        if not normalized_key:
            raise ConfigError(f"Invalid config.yaml line {line_number}: empty key")
        full_key = f"{section}_{normalized_key}" if section else normalized_key
        values[full_key] = _strip_quotes(value.strip())

    aliases = {
        "MODE": "TRADING_MODE",
        "DATABASE_URL": "DATABASE_URL",
        "EXCHANGE_NAME": "EXCHANGE_NAME",
        "TRADING_LIVE_TRADING": "LIVE_TRADING",
        "TRADING_PAPER_TRADING": "PAPER_TRADING",
        "TRADING_MODE": "TRADING_MODE",
        "EXCHANGE_SYMBOL": "SYMBOL",
        "EXCHANGE_TIMEFRAME": "TIMEFRAME",
        "EXCHANGE_BINANCE_API_KEY": "BINANCE_API_KEY",
        "EXCHANGE_BINANCE_API_SECRET": "BINANCE_API_SECRET",
        "EXCHANGE_BINANCE_TESTNET": "BINANCE_TESTNET",
        "EXCHANGE_BINANCE_FUTURES_BASE_URL": "BINANCE_FUTURES_BASE_URL",
        "TELEGRAM_ENABLED": "TELEGRAM_ENABLED",
        "TELEGRAM_BOT_TOKEN": "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID": "TELEGRAM_CHAT_ID",
        "ALERTS_TELEGRAM_ENABLED": "TELEGRAM_ENABLED",
        "ALERTS_TELEGRAM_BOT_TOKEN": "TELEGRAM_BOT_TOKEN",
        "ALERTS_TELEGRAM_CHAT_ID": "TELEGRAM_CHAT_ID",
        "ML_ENABLED": "ML_FILTER_ENABLED",
        "ML_FILTER_ENABLED": "ML_FILTER_ENABLED",
        "ML_REGISTRY_PATH": "ML_REGISTRY_PATH",
        "ML_MIN_PROBABILITY": "ML_MIN_PROBABILITY",
        "ML_REDUCE_RISK_THRESHOLD": "ML_REDUCE_RISK_THRESHOLD",
        "TRADING_DEMO_TRADING": "DEMO_TRADING",
        "RISK_ENGINE_ENABLED": "RISK_ENGINE_ENABLED",
        "RISK_KILL_SWITCH_ENABLED": "KILL_SWITCH_ENABLED",
        "RISK_KILL_SWITCH_PATH": "KILL_SWITCH_PATH",
        "RISK_STOP_LOSS_REQUIRED": "STOP_LOSS_REQUIRED",
        "RISK_MAX_RISK_PER_TRADE": "MAX_RISK_PER_TRADE",
        "RISK_MAX_DAILY_LOSS": "MAX_DAILY_LOSS",
        "RISK_MAX_LEVERAGE": "MAX_LEVERAGE",
    }
    return {aliases.get(key, key): value for key, value in values.items()}


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


BINANCE_FUTURES_TESTNET_HOST = "testnet.binancefuture.com"


def is_binance_futures_testnet_url(value: str) -> bool:
    """Return whether a URL is exactly the Binance Futures testnet over https."""

    try:
        parts = urlsplit(value.strip())
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme.lower() == "https"
        and parts.hostname == BINANCE_FUTURES_TESTNET_HOST
        and parts.username is None
        and parts.password is None
        and port in (None, 443)
    )
