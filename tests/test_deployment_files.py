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
    assert "DATABASE_URL: postgresql://silverbot:silverbot@postgres:5432/silverbot" in compose
    assert compose.count("condition: service_healthy") == 3
    assert "DATABASE_PATH" not in compose


def test_dockerfile_has_no_volume_line_and_ships_the_railway_start_script() -> None:
    dockerfile = read("Dockerfile")

    assert not any(line.startswith("VOLUME") for line in dockerfile.splitlines())
    assert "COPY deploy/railway/start.sh ./deploy/railway/start.sh" in dockerfile
    assert "DATABASE_PATH" not in dockerfile


def test_railway_builds_the_dockerfile_and_restarts_only_on_failure() -> None:
    railway = read("railway.toml")

    assert 'builder = "DOCKERFILE"' in railway
    assert 'startCommand = "sh /app/deploy/railway/start.sh"' in railway
    assert 'restartPolicyType = "ON_FAILURE"' in railway
    assert "restartPolicyMaxRetries = 10" in railway
    assert "LIVE" not in railway.upper().replace("DELIVER", "")


def test_railway_start_script_runs_from_the_volume_and_execs_the_bot() -> None:
    script = read("deploy/railway/start.sh")
    lines = [line for line in script.splitlines() if line and not line.startswith("#")]

    assert b"\r" not in (ROOT / "deploy/railway/start.sh").read_bytes()
    assert "cd /app/var" in lines
    assert lines[-1] == "exec python -m silver_bot"
    assert "LIVE_TRADING" not in script and "TRADING_MODE" not in script


def test_compose_bot_does_not_self_restart() -> None:
    compose = read("docker-compose.yaml")
    bot_block = compose.split("\n  bot:\n", 1)[1].split("\n  paper:\n", 1)[0]

    assert 'restart: "no"' in bot_block
    assert "unless-stopped" not in compose


def test_compose_backtest_services_read_candles_directory() -> None:
    compose = read("docker-compose.yaml")

    assert compose.count('command: ["python", "-m", "silver_bot", "--candles", "/app/data/candles"]') == 2
