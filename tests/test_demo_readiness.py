import json
from pathlib import Path

from silvr.demo_readiness import evaluate_demo_readiness
from silvr.readiness import export_readiness_report


def demo_env() -> dict[str, str]:
    return {
        "MODE": "demo",
        "DEMO_TRADING": "true",
        "BINANCE_TESTNET": "true",
        "LIVE_TRADING": "false",
        "PAPER_TRADING": "false",
        "BINANCE_API_KEY": "testnet-key",
        "BINANCE_API_SECRET": "testnet-secret",
        "RISK_ENGINE_ENABLED": "true",
        "KILL_SWITCH_ENABLED": "true",
        "KILL_SWITCH_PATH": "KILL_SWITCH",
        "STOP_LOSS_REQUIRED": "true",
        "MAX_RISK_PER_TRADE": "0.005",
        "MAX_DAILY_LOSS": "0.02",
        "MAX_LEVERAGE": "3",
    }


def write_gitignore(root: Path) -> None:
    (root / ".gitignore").write_text(".env\nlogs/\ndata/\nmodels/\nreports/\n", encoding="utf-8")


def test_demo_readiness_passes_with_safe_values(tmp_path: Path) -> None:
    write_gitignore(tmp_path)

    report = evaluate_demo_readiness(project_root=tmp_path, environ=demo_env())

    assert report.ready is True
    assert not report.failed_checks


def test_demo_readiness_rejects_production_endpoint(tmp_path: Path) -> None:
    write_gitignore(tmp_path)
    env = demo_env()
    env["BINANCE_FUTURES_BASE_URL"] = "https://fapi.binance.com"

    report = evaluate_demo_readiness(project_root=tmp_path, environ=env)

    assert report.ready is False
    failed_names = {item.name for item in report.failed_checks}
    assert "demo_config_validation" in failed_names
    assert "binance_testnet_endpoint" in failed_names


def test_demo_readiness_fails_if_risk_kill_switch_or_stop_loss_disabled(tmp_path: Path) -> None:
    write_gitignore(tmp_path)
    env = demo_env()
    env["RISK_ENGINE_ENABLED"] = "false"
    env["KILL_SWITCH_ENABLED"] = "false"
    env["STOP_LOSS_REQUIRED"] = "false"

    report = evaluate_demo_readiness(project_root=tmp_path, environ=env)

    failed_names = {item.name for item in report.failed_checks}
    assert "demo_config_validation" in failed_names
    assert "risk_engine_enabled" in failed_names
    assert "kill_switch_enabled" in failed_names
    assert "stop_loss_required" in failed_names


def test_demo_readiness_fails_if_kill_switch_file_is_active(tmp_path: Path) -> None:
    write_gitignore(tmp_path)
    (tmp_path / "KILL_SWITCH").write_text("stop", encoding="utf-8")

    report = evaluate_demo_readiness(project_root=tmp_path, environ=demo_env())

    assert report.ready is False
    assert "kill_switch_not_active" in {item.name for item in report.failed_checks}


def test_demo_readiness_fails_unsafe_risk_limits(tmp_path: Path) -> None:
    write_gitignore(tmp_path)
    env = demo_env()
    env["MAX_RISK_PER_TRADE"] = "0.02"
    env["MAX_DAILY_LOSS"] = "0.05"
    env["MAX_LEVERAGE"] = "25"

    report = evaluate_demo_readiness(project_root=tmp_path, environ=env)

    failed_names = {item.name for item in report.failed_checks}
    assert "demo_config_validation" in failed_names
    assert "max_risk_per_trade_safe" in failed_names
    assert "max_daily_loss_safe" in failed_names
    assert "max_leverage_safe" in failed_names


def test_demo_readiness_report_does_not_print_secrets(tmp_path: Path) -> None:
    write_gitignore(tmp_path)
    env = demo_env()
    env["BINANCE_API_KEY"] = "super-secret-demo-key"
    env["BINANCE_API_SECRET"] = "super-secret-demo-secret"

    report = evaluate_demo_readiness(project_root=tmp_path, environ=env)
    path = export_readiness_report(report, tmp_path / "reports" / "demo_readiness_report.json")

    payload = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(payload)
    assert "super-secret-demo-key" not in serialized
    assert "super-secret-demo-secret" not in serialized
