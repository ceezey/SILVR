from pathlib import Path

import pytest

from silvr.config import ConfigError, TradingMode, load_config


def test_default_config_is_safe(tmp_path: Path) -> None:
    config = load_config(
        env_path=tmp_path / ".env",
        yaml_path=tmp_path / "config.yaml",
        environ={},
    )

    assert config.mode == TradingMode.PAPER
    assert config.live_trading is False
    assert config.paper_trading is True
    assert config.ml_filter_enabled is False
    assert config.ml_min_probability == 0.60
    assert config.ml_reduce_risk_threshold == 0.55


def test_env_file_overrides_defaults_without_enabling_live(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "TRADING_MODE=backtest",
                "PAPER_TRADING=false",
                "DATABASE_URL=postgresql://bot:pw@db.internal:5432/silvr",
                "SYMBOL=ethusdt",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})

    assert config.mode == TradingMode.BACKTEST
    assert config.paper_trading is False
    assert config.database_url == "postgresql://bot:pw@db.internal:5432/silvr"
    assert config.symbol == "ETHUSDT"


def test_env_file_allows_utf8_bom(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("\ufeffTRADING_MODE=backtest\nPAPER_TRADING=false\n", encoding="utf-8")

    config = load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})

    assert config.mode == TradingMode.BACKTEST


def test_live_trading_flag_is_rejected(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("LIVE_TRADING=true\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="LIVE_TRADING=true"):
        load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})


def test_live_mode_is_rejected(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("TRADING_MODE=live\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="TRADING_MODE"):
        load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})


def test_partial_binance_credentials_are_rejected(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("BINANCE_API_KEY=key-only\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="provided together"):
        load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})


@pytest.mark.parametrize("url", ["sqlite:///silvr.sqlite3", "data/silvr.sqlite3", "mysql://db/silvr"])
def test_database_url_must_be_postgres(tmp_path: Path, url: str) -> None:
    with pytest.raises(ConfigError, match="postgresql://"):
        load_config(env_path=tmp_path / ".env", yaml_path=tmp_path / "missing.yaml", environ={"DATABASE_URL": url})


def test_malformed_database_url_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not a valid URL"):
        load_config(
            env_path=tmp_path / ".env",
            yaml_path=tmp_path / "missing.yaml",
            environ={"DATABASE_URL": "postgresql://[bad/silvr"},
        )


def test_database_url_accepts_postgres_scheme_and_defaults_to_none(tmp_path: Path) -> None:
    def load(environ: dict[str, str]):
        return load_config(env_path=tmp_path / ".env", yaml_path=tmp_path / "missing.yaml", environ=environ)

    assert load({}).database_url is None
    assert load({"DATABASE_URL": "postgres://bot:pw@db/silvr"}).database_url == "postgres://bot:pw@db/silvr"


def test_database_url_is_not_in_config_repr(tmp_path: Path) -> None:
    config = load_config(
        env_path=tmp_path / ".env",
        yaml_path=tmp_path / "missing.yaml",
        environ={"DATABASE_URL": "postgresql://bot:secret-password@db/silvr"},
    )

    assert "secret-password" not in repr(config)


def test_ml_thresholds_must_be_valid(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "ML_FILTER_ENABLED=true",
                "ML_MIN_PROBABILITY=0.50",
                "ML_REDUCE_RISK_THRESHOLD=0.60",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="less than or equal"):
        load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})


def test_config_yaml_aliases_are_loaded(tmp_path: Path) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                "trading:",
                "  mode: backtest",
                "  paper_trading: false",
                "exchange:",
                "  symbol: ethusdt",
                "  timeframe: 5m",
                "ml:",
                "  filter_enabled: true",
                "  registry_path: models/example_registry.json",
                "  min_probability: 0.70",
                "  reduce_risk_threshold: 0.60",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(env_path=tmp_path / "missing.env", yaml_path=yaml_path, environ={})

    assert config.mode == TradingMode.BACKTEST
    assert config.paper_trading is False
    assert config.symbol == "ETHUSDT"
    assert config.timeframe == "5m"
    assert config.ml_filter_enabled is True
    assert config.ml_registry_path == Path("models/example_registry.json")


def test_symbol_timeframe_and_exchange_are_validated(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("SYMBOL=BTC/USDT\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="SYMBOL"):
        load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})

    env_path.write_text("TIMEFRAME=minute\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="TIMEFRAME"):
        load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})

    env_path.write_text("EXCHANGE_NAME=binance-futures\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="EXCHANGE_NAME"):
        load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})


def test_ml_registry_path_cannot_escape_workspace(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("ML_REGISTRY_PATH=../model_registry.json\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="ML_REGISTRY_PATH"):
        load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})


def demo_env() -> str:
    return "\n".join(
        [
            "MODE=demo",
            "DEMO_TRADING=true",
            "BINANCE_TESTNET=true",
            "LIVE_TRADING=false",
            "PAPER_TRADING=false",
            "BINANCE_API_KEY=testnet-key",
            "BINANCE_API_SECRET=testnet-secret",
            "RISK_ENGINE_ENABLED=true",
            "KILL_SWITCH_ENABLED=true",
            "KILL_SWITCH_PATH=KILL_SWITCH",
            "STOP_LOSS_REQUIRED=true",
            "MAX_RISK_PER_TRADE=0.005",
            "MAX_DAILY_LOSS=0.02",
            "MAX_LEVERAGE=3",
        ]
    )


def test_demo_config_passes_with_safe_values(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(demo_env(), encoding="utf-8")

    config = load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})

    assert config.mode == TradingMode.DEMO
    assert config.demo_trading is True
    assert config.live_trading is False
    assert config.paper_trading is False
    assert config.binance_testnet is True


def test_demo_config_rejects_production_binance_url(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        demo_env() + "\nBINANCE_FUTURES_BASE_URL=https://fapi.binance.com\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="testnet endpoint"):
        load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})


def test_demo_config_rejects_live_trading_flag(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(demo_env().replace("LIVE_TRADING=false", "LIVE_TRADING=true"), encoding="utf-8")

    with pytest.raises(ConfigError, match="LIVE_TRADING=true"):
        load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})


def test_demo_config_rejects_disabled_testnet_flag(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(demo_env().replace("BINANCE_TESTNET=true", "BINANCE_TESTNET=false"), encoding="utf-8")

    with pytest.raises(ConfigError, match="BINANCE_TESTNET"):
        load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})


def test_max_risk_per_trade_above_cap_is_rejected_in_paper_mode(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("MAX_RISK_PER_TRADE=0.01\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="MAX_RISK_PER_TRADE"):
        load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})


def test_kill_switch_enabled_without_path_is_rejected_in_paper_mode(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("KILL_SWITCH_ENABLED=true\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="KILL_SWITCH_PATH"):
        load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})


def test_demo_config_rejects_lookalike_testnet_url(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        demo_env() + "\nBINANCE_FUTURES_BASE_URL=https://testnet.binancefuture.com.evil.com\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="testnet endpoint"):
        load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_shipped_env_example_loads_as_paper(tmp_path: Path) -> None:
    config = load_config(
        env_path=REPO_ROOT / ".env.example",
        yaml_path=tmp_path / "missing.yaml",
        environ={},
    )

    assert config.mode == TradingMode.PAPER
    assert config.paper_trading is True
    assert config.demo_trading is False
    assert config.live_trading is False


def test_shipped_env_example_lets_trading_mode_select_backtest(tmp_path: Path) -> None:
    config = load_config(
        env_path=REPO_ROOT / ".env.example",
        yaml_path=tmp_path / "missing.yaml",
        environ={"TRADING_MODE": "backtest", "PAPER_TRADING": "false"},
    )

    assert config.mode == TradingMode.BACKTEST
