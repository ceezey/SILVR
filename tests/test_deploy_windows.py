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


def test_forward_task_has_a_12_hour_limit_and_dashboard_none() -> None:
    script = read("install-forward-tasks.ps1")

    forward = script.split("$forwardXml = ", 1)[1].split("Register-ScheduledTask", 1)[0]
    dashboard = script.split("$dashboardSettings = ", 1)[1].split("\n$", 1)[0]
    assert "<ExecutionTimeLimit>PT12H</ExecutionTimeLimit>" in forward
    assert "-ExecutionTimeLimit ([TimeSpan]::Zero)" in dashboard
    assert "-Xml $forwardXml" in script and "-Settings $dashboardSettings" in script


def test_installer_pins_trigger_and_task_settings() -> None:
    script = read("install-forward-tasks.ps1")
    forward = script.split("$forwardXml = ", 1)[1].split("Register-ScheduledTask", 1)[0]

    # Windows rejects a CIM MSFT_TaskMonthlyTrigger ("The parameter is incorrect"), so the monthly task is XML.
    assert "MSFT_TaskMonthlyTrigger" not in script
    assert "<ScheduleByMonth><DaysOfMonth><Day>1</Day></DaysOfMonth>" in forward
    assert "<StartWhenAvailable>true</StartWhenAvailable>" in forward
    assert "<LogonType>InteractiveToken</LogonType>" in forward
    assert "<WorkingDirectory>$rootXml</WorkingDirectory>" in forward
    assert "-StartWhenAvailable" in script and "-LogonType Interactive" in script  # the dashboard task
    assert script.count("-WorkingDirectory $Root") == 1


def test_forward_test_toasts_instead_of_throwing_when_python_is_missing() -> None:
    script = read("forward-test.ps1")

    missing = script.split("if (-not (Test-Path $python)) {", 1)[1].split("}", 1)[0]
    assert "throw" not in script
    assert "Add-Content $log" in missing and "Show-Toast $crash" in missing and "exit 1" in missing
    assert "$null -eq $LASTEXITCODE" in script
    assert "$_ -and $_.StartsWith('TOAST: ')" in script


def test_forward_test_asks_for_an_editable_install_when_the_venv_is_missing() -> None:
    """The run checks that silvr imports from this checkout, which only an editable install gives."""
    script = read("forward-test.ps1")

    missing = script.split("if (-not (Test-Path $python)) {", 1)[1].split("}", 1)[0]
    assert "pip install -e ." in missing
