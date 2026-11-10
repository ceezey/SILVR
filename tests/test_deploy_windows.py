"""Static checks on the forward-test Windows scripts (nothing here runs PowerShell)."""
import re
from pathlib import Path

WINDOWS = Path(__file__).resolve().parents[1] / "deploy" / "windows"
SCRIPTS = ("forward-test.ps1", "toast.ps1", "install-forward-tasks.ps1")


def read(name: str) -> str:
    return (WINDOWS / name).read_text(encoding="utf-8")


def test_each_script_exists() -> None:
    for name in SCRIPTS:
        assert (WINDOWS / name).is_file(), name


def test_forward_test_runs_the_forward_cli_and_nothing_else_python() -> None:
    script = read("forward-test.ps1")

    assert "silvr.backtest.trend_forward --download" in script
    assert r"logs\forward-test.log" in script
    assert "TOAST: " in script
    assert "toast.ps1" in script


def test_no_script_can_reach_the_trading_entry_point_or_secrets() -> None:
    for name in SCRIPTS:
        script = read(name)
        assert "--live" not in script, name
        assert "LIVE_TRADING" not in script and "TRADING_MODE" not in script, name
        assert "silvr.main" not in script, name
        assert not re.search(r"-m\s+silvr(\s|$)", script), name
        assert ".env" not in script and "config" not in script.lower(), name


def test_toast_has_no_action_or_button() -> None:
    script = read("toast.ps1")

    assert "<action" not in script.lower()
    assert "ToastText02" in script
    assert "ToastNotificationManager" in script


def test_installer_names_only_the_two_silvr_tasks() -> None:
    script = read("install-forward-tasks.ps1")

    names = set(re.findall(r"'(SILVR[^']*)'", script)) | set(re.findall(r'"(SILVR [^"]*)"', script))
    assert {"SILVR Forward Test", "SILVR Dashboard"} <= names
    assert names <= {"SILVR Forward Test", "SILVR Dashboard"}
    assert "SilverBot" not in script
    assert (
        "Unregister-ScheduledTask -TaskName 'SILVR Forward Test','SILVR Dashboard' -Confirm:$false"
        in script
    )
    assert "dashboard_server --port 8765" in script
    assert r"logs\dashboard-console.log" in script
