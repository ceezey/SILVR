"""Pass or fail criteria for backtest evidence.

Only thresholds the BRD fixes are hard checks: profit factor at least 1.2
(BRD-M1), positive expectancy (BRD-M2) and non-zero costs (BRD-M3). Maximum
drawdown (BRD-M4, OI-3) and minimum trade count (BRD-M5, OI-9) are owner
inputs; until a number is given they are reported as not evaluated and the
verdict cannot be a plain pass.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MIN_PROFIT_FACTOR = 1.2

PASS = "pass"
FAIL = "fail"
PASS_PENDING_OWNER_INPUT = "pass_pending_owner_input"


def evaluate_evidence(
    metrics: Mapping[str, Any],
    *,
    slippage_bps: float,
    spread_bps: float,
    max_drawdown_percent: float | None = None,
    min_trades: int | None = None,
) -> dict[str, Any]:
    """Return each criterion with passed true, false or None, and a verdict."""

    profit_factor = float(metrics.get("profit_factor", 0.0))
    expectancy = float(metrics.get("expectancy", 0.0))
    checks = [
        _check(
            "profit_factor",
            profit_factor >= MIN_PROFIT_FACTOR,
            f"profit factor {profit_factor:.4f} vs at least {MIN_PROFIT_FACTOR} (BRD-M1)",
        ),
        _check("expectancy", expectancy > 0, f"expectancy {expectancy:.4f} vs greater than 0 (BRD-M2)"),
        _check(
            "costs_non_zero",
            slippage_bps > 0 and spread_bps > 0,
            f"slippage {slippage_bps} bps and spread {spread_bps} bps must both be above 0 (BRD-M3)",
        ),
    ]
    drawdown = float(metrics.get("max_drawdown_percent", 0.0))
    if max_drawdown_percent is None:
        checks.append(_check("max_drawdown", None, "Owner input required (OI-3)"))
    else:
        checks.append(
            _check(
                "max_drawdown",
                drawdown <= max_drawdown_percent,
                f"max drawdown {drawdown:.4f} vs at most {max_drawdown_percent} (BRD-M4)",
            )
        )
    trades = int(metrics.get("total_trades", 0))
    if min_trades is None:
        checks.append(_check("min_trades", None, "Owner input required (OI-9)"))
    else:
        checks.append(_check("min_trades", trades >= min_trades, f"{trades} trades vs at least {min_trades} (BRD-M5)"))

    if any(check["passed"] is False for check in checks):
        verdict = FAIL
    elif any(check["passed"] is None for check in checks):
        verdict = PASS_PENDING_OWNER_INPUT
    else:
        verdict = PASS
    return {"verdict": verdict, "checks": checks}


def combine_verdicts(*verdicts: str) -> str:
    """Return the weakest verdict: fail, then pending owner input, then pass."""

    if FAIL in verdicts:
        return FAIL
    if PASS_PENDING_OWNER_INPUT in verdicts:
        return PASS_PENDING_OWNER_INPUT
    return PASS


def _check(name: str, passed: bool | None, reason: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "reason": reason}
