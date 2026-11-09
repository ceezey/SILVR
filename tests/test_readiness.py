import json
from pathlib import Path

import pytest

from silvr.readiness import evaluate_live_readiness, export_readiness_report


def required_env() -> dict[str, str]:
    return {
        "RISK_ENGINE_ENABLED": "true",
        "KILL_SWITCH_ENABLED": "true",
        "KILL_SWITCH_PATH": "KILL_SWITCH",
        "TELEGRAM_ENABLED": "false",
        "BINANCE_API_KEY": "env-key",
        "BINANCE_API_SECRET": "env-secret",
        "LIVE_TRADING": "true",
        "PAPER_TRADING": "false",
        "READINESS_CHECK_PASSED": "true",
        "API_WITHDRAWALS_DISABLED": "true",
        "MAX_RISK_PER_TRADE": "0.005",
        "MAX_DAILY_LOSS": "0.02",
        "MAX_LEVERAGE": "3",
    }


def create_required_reports(root: Path) -> None:
    reports = root / "reports"
    reports.mkdir()
    for name in (
        "backtest_report.json",
        "out_of_sample_validation_report.json",
        "paper_trading_report.json",
    ):
        (reports / name).write_text("{}", encoding="utf-8")


def test_live_readiness_passes_when_all_required_conditions_are_met(tmp_path: Path) -> None:
    create_required_reports(tmp_path)

    report = evaluate_live_readiness(project_root=tmp_path, environ=required_env())

    assert report.ready is True
    assert not report.failed_checks


def test_live_readiness_blocks_when_required_reports_are_missing(tmp_path: Path) -> None:
    report = evaluate_live_readiness(project_root=tmp_path, environ=required_env())

    assert report.ready is False
    failed_names = {item.name for item in report.failed_checks}
    assert "backtest_report_exists" in failed_names
    assert "out_of_sample_validation_report_exists" in failed_names
    assert "paper_trading_report_exists" in failed_names


def test_live_readiness_blocks_unsafe_live_flags(tmp_path: Path) -> None:
    create_required_reports(tmp_path)
    env = required_env()
    env["LIVE_TRADING"] = "false"
    env["PAPER_TRADING"] = "true"
    env["READINESS_CHECK_PASSED"] = "false"

    report = evaluate_live_readiness(project_root=tmp_path, environ=env)

    assert report.ready is False
    failed_names = {item.name for item in report.failed_checks}
    assert "live_trading_enabled_intent" in failed_names
    assert "paper_trading_disabled_for_live" in failed_names
    assert "manual_readiness_confirmation" in failed_names


def test_live_readiness_blocks_missing_api_keys_and_withdrawal_confirmation(tmp_path: Path) -> None:
    create_required_reports(tmp_path)
    env = required_env()
    env.pop("BINANCE_API_KEY")
    env["API_WITHDRAWALS_DISABLED"] = "false"

    report = evaluate_live_readiness(project_root=tmp_path, environ=env)

    assert report.ready is False
    failed_names = {item.name for item in report.failed_checks}
    assert "api_keys_loaded_from_env_only" in failed_names
    assert "withdrawals_disabled_confirmation" in failed_names


def test_live_readiness_blocks_unsafe_risk_limits(tmp_path: Path) -> None:
    create_required_reports(tmp_path)
    env = required_env()
    env["MAX_RISK_PER_TRADE"] = "0.02"
    env["MAX_DAILY_LOSS"] = "0.05"
    env["MAX_LEVERAGE"] = "10"

    report = evaluate_live_readiness(project_root=tmp_path, environ=env)

    assert report.ready is False
    failed_names = {item.name for item in report.failed_checks}
    assert "max_risk_per_trade_safe" in failed_names
    assert "max_daily_loss_safe" in failed_names
    assert "max_leverage_safe" in failed_names


def test_live_readiness_requires_telegram_test_when_enabled(tmp_path: Path) -> None:
    create_required_reports(tmp_path)
    env = required_env()
    env["TELEGRAM_ENABLED"] = "true"

    failed = evaluate_live_readiness(project_root=tmp_path, environ=env)
    env["TELEGRAM_ALERTS_TESTED"] = "true"
    passed = evaluate_live_readiness(project_root=tmp_path, environ=env)

    assert failed.ready is False
    assert "telegram_alerts_tested_or_disabled" in {item.name for item in failed.failed_checks}
    assert passed.ready is True


def test_live_readiness_blocks_when_kill_switch_file_is_active(tmp_path: Path) -> None:
    create_required_reports(tmp_path)
    (tmp_path / "KILL_SWITCH").write_text("stop", encoding="utf-8")

    report = evaluate_live_readiness(project_root=tmp_path, environ=required_env())

    assert report.ready is False
    failed = {item.name: item.reason for item in report.failed_checks}
    assert "kill_switch_not_active" in failed
    assert "active" in failed["kill_switch_not_active"]


def test_readiness_report_export(tmp_path: Path) -> None:
    create_required_reports(tmp_path)
    report = evaluate_live_readiness(project_root=tmp_path, environ=required_env())

    path = export_readiness_report(report, tmp_path / "reports" / "live_readiness_report.json")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["ready"] is True
    assert payload["checks"]


def test_readiness_messages_explain_missing_report_and_invalid_boolean(tmp_path: Path) -> None:
    env = required_env()
    env["RISK_ENGINE_ENABLED"] = "maybe"

    report = evaluate_live_readiness(project_root=tmp_path, environ=env)
    reasons = {item.name: item.reason for item in report.failed_checks}

    assert "Set BACKTEST_REPORT_PATH" in reasons["backtest_report_exists"]
    assert "boolean value" in reasons["risk_engine_enabled"]


@pytest.mark.parametrize(
    ("content", "fragment"),
    [
        ("", "is empty"),
        ("   \n", "is empty"),
        ("not json", "not valid JSON"),
        ("[]", "JSON object"),
    ],
)
def test_live_readiness_rejects_unusable_report(tmp_path: Path, content: str, fragment: str) -> None:
    create_required_reports(tmp_path)
    (tmp_path / "reports" / "backtest_report.json").write_text(content, encoding="utf-8")

    report = evaluate_live_readiness(project_root=tmp_path, environ=required_env())
    reasons = {item.name: item.reason for item in report.failed_checks}

    assert report.ready is False
    assert fragment in reasons["backtest_report_exists"]


def test_live_readiness_accepts_report_with_utf8_bom(tmp_path: Path) -> None:
    create_required_reports(tmp_path)
    (tmp_path / "reports" / "backtest_report.json").write_text("\ufeff{}", encoding="utf-8")

    report = evaluate_live_readiness(project_root=tmp_path, environ=required_env())

    assert "backtest_report_exists" not in {item.name for item in report.failed_checks}
