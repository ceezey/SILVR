"""Live-readiness gate and report generation.

This module only evaluates readiness. It does not enable live trading, connect
to an exchange, or place orders.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SAFE_MAX_RISK_PER_TRADE = 0.005
DEFAULT_SAFE_MAX_DAILY_LOSS = 0.02
DEFAULT_SAFE_MAX_LEVERAGE = 3.0


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    """One live-readiness check result."""

    name: str
    passed: bool
    reason: str

    def to_dict(self) -> dict[str, str | bool]:
        """Serialize the check for JSON output."""

        return {
            "name": self.name,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    """Aggregated readiness decision."""

    ready: bool
    generated_at: str
    checks: tuple[ReadinessCheck, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the readiness report for JSON output."""

        return {
            "ready": self.ready,
            "generated_at": self.generated_at,
            "checks": [item.to_dict() for item in self.checks],
        }

    @property
    def failed_checks(self) -> tuple[ReadinessCheck, ...]:
        """Return failed checks."""

        return tuple(item for item in self.checks if not item.passed)


def evaluate_live_readiness(
    *,
    project_root: Path | str = ".",
    environ: Mapping[str, str] | None = None,
) -> ReadinessReport:
    """Evaluate all required live-readiness gates."""

    root = Path(project_root)
    env = dict(os.environ if environ is None else environ)
    checks = [
        _file_exists("backtest_report_exists", root, env, "BACKTEST_REPORT_PATH", "reports/backtest_report.json"),
        _file_exists(
            "out_of_sample_validation_report_exists",
            root,
            env,
            "OOS_VALIDATION_REPORT_PATH",
            "reports/out_of_sample_validation_report.json",
        ),
        _file_exists(
            "paper_trading_report_exists",
            root,
            env,
            "PAPER_TRADING_REPORT_PATH",
            "reports/paper_trading_report.json",
        ),
        _bool_check(env, "RISK_ENGINE_ENABLED", True, "risk_engine_enabled"),
        _kill_switch_check(env),
        _kill_switch_inactive_check(root, env),
        _telegram_check(env),
        _api_keys_from_environment_check(env),
        _bool_check(env, "LIVE_TRADING", True, "live_trading_enabled_intent"),
        _bool_check(env, "PAPER_TRADING", False, "paper_trading_disabled_for_live"),
        _bool_check(env, "READINESS_CHECK_PASSED", True, "manual_readiness_confirmation"),
        _bool_check(env, "API_WITHDRAWALS_DISABLED", True, "withdrawals_disabled_confirmation"),
        _maximum_float_check(
            env,
            "MAX_RISK_PER_TRADE",
            DEFAULT_SAFE_MAX_RISK_PER_TRADE,
            "max_risk_per_trade_safe",
        ),
        _maximum_float_check(
            env,
            "MAX_DAILY_LOSS",
            DEFAULT_SAFE_MAX_DAILY_LOSS,
            "max_daily_loss_safe",
        ),
        _maximum_float_check(
            env,
            "MAX_LEVERAGE",
            DEFAULT_SAFE_MAX_LEVERAGE,
            "max_leverage_safe",
        ),
    ]
    return ReadinessReport(
        ready=all(item.passed for item in checks),
        generated_at=datetime.now(timezone.utc).isoformat(),
        checks=tuple(checks),
    )


def export_readiness_report(report: ReadinessReport, output_path: Path | str) -> Path:
    """Write readiness report JSON."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for live-readiness checks."""

    parser = argparse.ArgumentParser(description="Evaluate live-readiness gates without trading.")
    parser.add_argument(
        "--output",
        default="reports/live_readiness_report.json",
        help="Path for readiness report JSON.",
    )
    args = parser.parse_args(argv)
    report = evaluate_live_readiness()
    export_readiness_report(report, args.output)
    return 0 if report.ready else 2


def _file_exists(
    check_name: str,
    root: Path,
    env: Mapping[str, str],
    env_key: str,
    default_path: str,
) -> ReadinessCheck:
    path = Path(env.get(env_key, default_path))
    resolved = path if path.is_absolute() else root / path
    if resolved.exists() and resolved.is_file():
        return ReadinessCheck(check_name, True, f"Found {resolved}")
    return ReadinessCheck(
        check_name,
        False,
        f"Missing required report: {resolved}. Set {env_key} to the completed report path.",
    )


def _bool_check(
    env: Mapping[str, str],
    key: str,
    expected: bool,
    check_name: str,
) -> ReadinessCheck:
    value = env.get(key)
    parsed = _parse_bool(value)
    if parsed is expected:
        return ReadinessCheck(check_name, True, f"{key} is {str(expected).lower()}")
    expected_text = str(expected).lower()
    if value is None:
        return ReadinessCheck(check_name, False, f"{key} must be {expected_text}; value is missing")
    if parsed is None:
        return ReadinessCheck(
            check_name,
            False,
            f"{key} must be a boolean value ({expected_text} required); got {value}",
        )
    return ReadinessCheck(check_name, False, f"{key} must be {expected_text}; got {value}")


def _kill_switch_check(env: Mapping[str, str]) -> ReadinessCheck:
    enabled = _parse_bool(env.get("KILL_SWITCH_ENABLED"))
    path = env.get("KILL_SWITCH_PATH", "").strip()
    if enabled is True and path:
        return ReadinessCheck("kill_switch_enabled", True, "Kill switch is configured")
    if enabled is None:
        return ReadinessCheck(
            "kill_switch_enabled",
            False,
            "KILL_SWITCH_ENABLED must be true and KILL_SWITCH_PATH must point to the kill-switch file",
        )
    if enabled is not True:
        return ReadinessCheck("kill_switch_enabled", False, "KILL_SWITCH_ENABLED must be true")
    return ReadinessCheck(
        "kill_switch_enabled",
        False,
        "KILL_SWITCH_PATH is required when KILL_SWITCH_ENABLED=true",
    )


def _kill_switch_inactive_check(root: Path, env: Mapping[str, str]) -> ReadinessCheck:
    path_text = env.get("KILL_SWITCH_PATH", "").strip()
    if not path_text:
        return ReadinessCheck(
            "kill_switch_not_active",
            False,
            "KILL_SWITCH_PATH is required before checking whether the kill switch is active",
        )

    path = Path(path_text)
    resolved = path if path.is_absolute() else root / path
    if resolved.exists():
        return ReadinessCheck(
            "kill_switch_not_active",
            False,
            f"Kill switch file is active at {resolved}; live readiness is blocked until this file is intentionally cleared",
        )
    return ReadinessCheck("kill_switch_not_active", True, "Kill switch file is not active")


def _telegram_check(env: Mapping[str, str]) -> ReadinessCheck:
    telegram_enabled = _parse_bool(env.get("TELEGRAM_ENABLED"))
    if telegram_enabled is False:
        return ReadinessCheck(
            "telegram_alerts_tested_or_disabled",
            True,
            "Telegram is explicitly disabled",
        )
    if telegram_enabled is True and _parse_bool(env.get("TELEGRAM_ALERTS_TESTED")) is True:
        return ReadinessCheck(
            "telegram_alerts_tested_or_disabled",
            True,
            "Telegram alerts tested",
        )
    if telegram_enabled is None:
        return ReadinessCheck(
            "telegram_alerts_tested_or_disabled",
            False,
            "TELEGRAM_ENABLED must be explicitly true or false for readiness",
        )
    return ReadinessCheck(
        "telegram_alerts_tested_or_disabled",
        False,
        "Telegram is enabled, so set TELEGRAM_ALERTS_TESTED=true after a real alert test or set TELEGRAM_ENABLED=false",
    )


def _api_keys_from_environment_check(env: Mapping[str, str]) -> ReadinessCheck:
    api_key = env.get("BINANCE_API_KEY", "").strip()
    api_secret = env.get("BINANCE_API_SECRET", "").strip()
    if api_key and api_secret:
        return ReadinessCheck(
            "api_keys_loaded_from_env_only",
            True,
            "API key and secret are present in the readiness environment",
        )
    return ReadinessCheck(
        "api_keys_loaded_from_env_only",
        False,
        "BINANCE_API_KEY and BINANCE_API_SECRET must both be present in the process environment; use placeholders only in examples",
    )


def _maximum_float_check(
    env: Mapping[str, str],
    key: str,
    safe_limit: float,
    check_name: str,
) -> ReadinessCheck:
    raw = env.get(key)
    try:
        value = float(raw) if raw is not None else safe_limit
    except ValueError:
        return ReadinessCheck(check_name, False, f"{key} must be numeric")
    if 0 < value <= safe_limit:
        return ReadinessCheck(check_name, True, f"{key}={value} within safe limit {safe_limit}")
    if value <= 0:
        return ReadinessCheck(check_name, False, f"{key} must be greater than 0; got {value}")
    return ReadinessCheck(check_name, False, f"{key}={value} exceeds safe limit {safe_limit}")


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return None


if __name__ == "__main__":
    raise SystemExit(main())
