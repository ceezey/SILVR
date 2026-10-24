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
    assert 'LIVE_TRADING: "true"' not in compose


def test_compose_bot_services_use_the_local_postgres() -> None:
    compose = read("docker-compose.yaml")

    assert "image: postgres:18" in compose
    assert "DATABASE_URL: postgresql://silverbot:${POSTGRES_PASSWORD:-silverbot}@postgres:5432/silverbot" in compose
    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-silverbot}" in compose
    assert '"127.0.0.1:${POSTGRES_PORT:-5432}:5432"' in compose
    assert compose.count("condition: service_healthy") == 4
    assert "DATABASE_PATH" not in compose


def test_compose_dashboard_is_loopback_only_on_the_host_network() -> None:
    compose = read("docker-compose.yaml")
    block = compose.split("\n  dashboard:\n", 1)[1].split("\n  paper:\n", 1)[0]

    assert "network_mode: host" in block
    assert "ports:" not in block
    assert "--host" not in block
    assert 'command: ["python", "-m", "silver_bot.monitoring.dashboard_server", "--port", "8765"]' in block


def test_dockerfile_runs_as_uid_1000_without_a_volume_line() -> None:
    dockerfile = read("Dockerfile")

    assert "useradd --uid 1000" in dockerfile
    assert not any(line.startswith("VOLUME") for line in dockerfile.splitlines())
    assert "DATABASE_PATH" not in dockerfile


def test_systemd_service_runs_compose_paper_bot_and_dashboard() -> None:
    service = read("deploy/systemd/silver-bot.service")

    assert "docker compose" in service
    assert "up bot dashboard" in service
    assert "TRADING_MODE=live" not in service
    assert "User=ubuntu" in service


def test_systemd_propagates_exit_code_and_stops_on_bad_configuration() -> None:
    service = read("deploy/systemd/silver-bot.service")

    assert "up bot dashboard --exit-code-from bot" in service
    assert "RestartPreventExitStatus=2 78" in service


def test_logrotate_covers_the_audit_log() -> None:
    assert "/opt/silver-bot/logs/*.jsonl" in read("deploy/logrotate/silver-bot")


def test_no_railway_files_remain() -> None:
    assert not (ROOT / "railway.toml").exists()
    assert not (ROOT / "deploy" / "railway").exists()


def test_compose_bot_does_not_self_restart() -> None:
    compose = read("docker-compose.yaml")
    bot_block = compose.split("\n  bot:\n", 1)[1].split("\n  paper:\n", 1)[0]

    assert 'restart: "no"' in bot_block
    assert "unless-stopped" not in compose


def test_compose_backtest_services_read_candles_directory() -> None:
    compose = read("docker-compose.yaml")

    assert compose.count('command: ["python", "-m", "silver_bot", "--candles", "/app/data/candles"]') == 2
