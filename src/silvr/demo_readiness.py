"""Binance Futures demo/testnet readiness checks.

This module validates demo/testnet operating mode only. It does not enable live
trading, connect to Binance, or place orders.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path

from silvr.config import ConfigError, load_config
from silvr.exchange import is_binance_futures_testnet_url
from silvr.readiness import (
    DEFAULT_SAFE_MAX_DAILY_LOSS,
    DEFAULT_SAFE_MAX_LEVERAGE,
    DEFAULT_SAFE_MAX_RISK_PER_TRADE,
    ReadinessCheck,
    ReadinessReport,
    export_readiness_report,
)


RUNTIME_PRIVATE_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tmp",
    ".venv",
    "__pycache__",
    "data",
    "logs",
    "models",
    "reports",
}


def evaluate_demo_readiness(
    *,
    project_root: Path | str = ".",
    environ: Mapping[str, str] | None = None,
) -> ReadinessReport:
    """Evaluate Binance Futures demo/testnet readiness gates."""

    root = Path(project_root)
    env = dict(_load_env_file(root / ".env") if environ is None else environ)
    if environ is None:
        env.update(os.environ)

    checks = [
        _config_validation_check(root, env),
        _mode_check(env),
        _bool_check(env, "DEMO_TRADING", True, "demo_trading_enabled"),
        _bool_check(env, "LIVE_TRADING", False, "live_trading_disabled"),
        _bool_check(env, "PAPER_TRADING", False, "paper_trading_disabled"),
        _bool_check(env, "BINANCE_TESTNET", True, "binance_testnet_enabled"),
        _testnet_endpoint_check(env),
        _api_keys_check(env),
        _bool_check(env, "RISK_ENGINE_ENABLED", True, "risk_engine_enabled"),
        _bool_check(env, "KILL_SWITCH_ENABLED", True, "kill_switch_enabled"),
        _kill_switch_path_check(env),
        _kill_switch_inactive_check(root, env),
        _bool_check(env, "STOP_LOSS_REQUIRED", True, "stop_loss_required"),
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
        _env_ignored_check(root),
        _no_committed_secrets_check(root),
    ]
    from datetime import datetime, timezone

    return ReadinessReport(
        ready=all(item.passed for item in checks),
        generated_at=datetime.now(timezone.utc).isoformat(),
        checks=tuple(checks),
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for demo/testnet readiness checks."""

    parser = argparse.ArgumentParser(description="Evaluate Binance Futures demo/testnet readiness without trading.")
    parser.add_argument(
        "--output",
        default="reports/demo_readiness_report.json",
        help="Path for demo readiness report JSON.",
    )
    args = parser.parse_args(argv)
    report = evaluate_demo_readiness()
    export_readiness_report(report, args.output)
    return 0 if report.ready else 2


def _config_validation_check(root: Path, env: Mapping[str, str]) -> ReadinessCheck:
    try:
        load_config(
            env_path=root / ".env",
            yaml_path=root / "config.yaml",
            environ=env,
        )
    except ConfigError as exc:
        return ReadinessCheck("demo_config_validation", False, str(exc))
    return ReadinessCheck("demo_config_validation", True, "Demo configuration values are valid")


def _mode_check(env: Mapping[str, str]) -> ReadinessCheck:
    mode = env.get("MODE", env.get("TRADING_MODE", "")).strip().lower()
    if mode == "demo":
        return ReadinessCheck("demo_mode_selected", True, "MODE is demo")
    return ReadinessCheck("demo_mode_selected", False, "MODE must be demo for Binance Futures testnet operation")


def _testnet_endpoint_check(env: Mapping[str, str]) -> ReadinessCheck:
    base_url = env.get("BINANCE_FUTURES_BASE_URL", "").strip()
    if not base_url:
        return ReadinessCheck(
            "binance_testnet_endpoint",
            True,
            "Using default Binance Futures testnet endpoint",
        )
    if is_binance_futures_testnet_url(base_url):
        return ReadinessCheck("binance_testnet_endpoint", True, "Configured endpoint is Binance Futures testnet")
    return ReadinessCheck(
        "binance_testnet_endpoint",
        False,
        "BINANCE_FUTURES_BASE_URL must point to the Binance Futures testnet endpoint in demo mode",
    )


def _api_keys_check(env: Mapping[str, str]) -> ReadinessCheck:
    if env.get("BINANCE_API_KEY", "").strip() and env.get("BINANCE_API_SECRET", "").strip():
        return ReadinessCheck("demo_api_keys_present", True, "Demo API key and secret are present")
    return ReadinessCheck(
        "demo_api_keys_present",
        False,
        "BINANCE_API_KEY and BINANCE_API_SECRET are required for Binance Futures demo/testnet",
    )


def _kill_switch_path_check(env: Mapping[str, str]) -> ReadinessCheck:
    if env.get("KILL_SWITCH_PATH", "").strip():
        return ReadinessCheck("kill_switch_path_configured", True, "KILL_SWITCH_PATH is configured")
    return ReadinessCheck("kill_switch_path_configured", False, "KILL_SWITCH_PATH is required in demo mode")


def _kill_switch_inactive_check(root: Path, env: Mapping[str, str]) -> ReadinessCheck:
    path_text = env.get("KILL_SWITCH_PATH", "").strip()
    if not path_text:
        return ReadinessCheck("kill_switch_not_active", False, "KILL_SWITCH_PATH is required before active-state check")
    path = Path(path_text)
    resolved = path if path.is_absolute() else root / path
    if resolved.exists():
        return ReadinessCheck(
            "kill_switch_not_active",
            False,
            "Kill switch file is active; demo readiness is blocked until it is intentionally cleared",
        )
    return ReadinessCheck("kill_switch_not_active", True, "Kill switch file is not active")


def _env_ignored_check(root: Path) -> ReadinessCheck:
    path = root / ".gitignore"
    if not path.exists():
        return ReadinessCheck("env_ignored_by_git", False, ".gitignore is missing")
    ignored = any(line.strip() == ".env" for line in path.read_text(encoding="utf-8").splitlines())
    if ignored:
        return ReadinessCheck("env_ignored_by_git", True, ".env is listed in .gitignore")
    return ReadinessCheck("env_ignored_by_git", False, ".env must be listed in .gitignore")


def _no_committed_secrets_check(root: Path) -> ReadinessCheck:
    findings = _secret_shape_findings(root)
    if findings:
        return ReadinessCheck(
            "no_committed_secrets",
            False,
            "Potential secret-looking values found outside private runtime files",
        )
    return ReadinessCheck("no_committed_secrets", True, "No secret-looking values found outside private runtime files")


def _secret_shape_findings(root: Path) -> tuple[Path, ...]:
    tracked = _git_tracked_files(root)
    candidates = [root / item for item in tracked] if tracked is not None else [item for item in root.rglob("*")]
    patterns = (
        re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
        re.compile(r"xox[baprs]-[A-Za-z0-9_-]{20,}"),
        re.compile(r"(?i)(api[_-]?secret|api[_-]?key|bot[_-]?token)\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{24,}"),
    )
    findings: list[Path] = []
    for path in candidates:
        if not path.is_file() or path.name.startswith(".env"):
            continue
        if set(path.relative_to(root).parts) & RUNTIME_PRIVATE_DIRS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(pattern.search(text) for pattern in patterns):
            findings.append(path)
    return tuple(findings)


def _git_tracked_files(root: Path) -> tuple[str, ...] | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or result.stdout.strip() != "true":
            return None
        tracked = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if tracked.returncode != 0:
        return None
    return tuple(line for line in tracked.stdout.splitlines() if line.strip())


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
        return ReadinessCheck(check_name, False, f"{key} must be boolean; got {value}")
    return ReadinessCheck(check_name, False, f"{key} must be {expected_text}; got {value}")


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
        return ReadinessCheck(check_name, True, f"{key} is within safe limit")
    if value <= 0:
        return ReadinessCheck(check_name, False, f"{key} must be greater than 0")
    return ReadinessCheck(check_name, False, f"{key} exceeds safe limit {safe_limit}")


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip("\ufeff").strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


if __name__ == "__main__":
    raise SystemExit(main())
