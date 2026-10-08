from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_dockerfile_defaults_to_safe_paper_mode() -> None:
    dockerfile = read("Dockerfile")

    assert "TRADING_MODE=paper" in dockerfile
    assert "LIVE_TRADING=false" in dockerfile
    assert "PAPER_TRADING=true" in dockerfile
    assert 'CMD ["python", "-m", "silver_bot"]' in dockerfile
    assert "live" not in dockerfile.lower().split("cmd", maxsplit=1)[-1]


def test_dockerignore_excludes_secrets_and_runtime_state() -> None:
    dockerignore = read(".dockerignore").splitlines()

    assert ".env" in dockerignore
    assert ".env.*" in dockerignore
    assert "logs/" in dockerignore
    assert "data/" in dockerignore
    assert "models/" in dockerignore
    assert "reports/" in dockerignore
    assert "*.sqlite3" in dockerignore


def test_compose_mounts_runtime_volumes_and_has_no_live_default() -> None:
    compose = read("docker-compose.yaml")

    assert "LIVE_TRADING: \"false\"" in compose
    assert "TRADING_MODE: paper" in compose
    assert "TRADING_MODE: demo" in compose
    assert "DEMO_TRADING: \"true\"" in compose
    assert "BINANCE_TESTNET: \"true\"" in compose
    assert "BINANCE_FUTURES_BASE_URL: https://testnet.binancefuture.com" in compose
    assert "KILL_SWITCH_ENABLED: \"true\"" in compose
    assert "KILL_SWITCH_PATH: /app/data/KILL_SWITCH" in compose
    assert "STOP_LOSS_REQUIRED: \"true\"" in compose
    assert "TRADING_MODE: backtest" in compose
    assert "./data:/app/data" in compose
    assert "./logs:/app/logs" in compose
    assert "./models:/app/models" in compose
    assert "./reports:/app/reports" in compose
    assert "TRADING_MODE: live" not in compose


def test_systemd_service_runs_compose_paper_bot() -> None:
    service = read("deploy/systemd/silver-bot.service")

    assert "docker compose" in service
    assert "up bot" in service
    assert "TRADING_MODE=live" not in service
