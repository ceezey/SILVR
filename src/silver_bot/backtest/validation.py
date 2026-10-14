"""Backtest validation: chronological splits, walk-forward windows and Monte Carlo."""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from silver_bot.models import Candle


@dataclass(frozen=True, slots=True)
class BacktestSplit:
    """Chronological train/validation/final-test split."""

    training: list[Candle]
    validation: list[Candle]
    final_test: list[Candle]


class BacktestValidationSuite:
    """Small validation helper for chronological splits and sanity warnings."""

    def chronological_split(
        self,
        candles: list[Candle],
        *,
        training_fraction: float = 0.6,
        validation_fraction: float = 0.2,
    ) -> BacktestSplit:
        """Split candles by time order only."""

        if not 0 < training_fraction < 1:
            raise ValueError("training_fraction must be between 0 and 1")
        if not 0 < validation_fraction < 1:
            raise ValueError("validation_fraction must be between 0 and 1")
        if training_fraction + validation_fraction >= 1:
            raise ValueError("training and validation fractions must leave final-test data")

        ordered = sorted(candles, key=lambda candle: candle.open_time)
        training_end = int(len(ordered) * training_fraction)
        validation_end = training_end + int(len(ordered) * validation_fraction)
        return BacktestSplit(
            training=ordered[:training_end],
            validation=ordered[training_end:validation_end],
            final_test=ordered[validation_end:],
        )

    def walk_forward_windows(self, candles: list[Candle], *, windows: int) -> list[list[Candle]]:
        """Split candles into consecutive, non-overlapping windows in time order.

        Each window is evaluated on its own; nothing is fitted on one window and
        applied to the next, so no window sees data from a later one.
        """

        if windows < 1:
            raise ValueError("windows must be at least 1")
        ordered = sorted(candles, key=lambda candle: candle.open_time)
        size = len(ordered) // windows
        if size == 0:
            return []
        result = [ordered[index * size : (index + 1) * size] for index in range(windows - 1)]
        result.append(ordered[(windows - 1) * size :])
        return result

    def validate_chronological_order(self, candles: list[Candle]) -> list[str]:
        """Return warnings for non-chronological input."""

        warnings: list[str] = []
        previous: datetime | None = None
        for candle in candles:
            if previous is not None and candle.open_time < previous:
                warnings.append("Candles are not sorted chronologically")
                break
            previous = candle.open_time
        return warnings


def monte_carlo_r(
    r_multiples: Sequence[float],
    *,
    runs: int = 1000,
    seed: int = 7,
) -> dict[str, Any]:
    """Resample trade R multiples with replacement and summarise the outcomes.

    The seed is fixed, so the same trades always give the same summary. The
    result describes how much the trade sequence alone could vary the final R
    and the worst peak-to-trough drawdown in R; it predicts nothing.
    """

    if runs < 1:
        raise ValueError("runs must be at least 1")
    trades = list(r_multiples)
    if not trades:
        return {
            "runs": runs,
            "seed": seed,
            "trades": 0,
            "final_r": None,
            "max_drawdown_r": None,
            "probability_final_r_not_positive": None,
        }

    rng = random.Random(seed)
    finals: list[float] = []
    drawdowns: list[float] = []
    for _ in range(runs):
        equity = peak = worst = 0.0
        for value in rng.choices(trades, k=len(trades)):
            equity += value
            peak = max(peak, equity)
            worst = max(worst, peak - equity)
        finals.append(equity)
        drawdowns.append(worst)
    return {
        "runs": runs,
        "seed": seed,
        "trades": len(trades),
        "final_r": _percentiles(finals),
        "max_drawdown_r": _percentiles(drawdowns),
        "probability_final_r_not_positive": sum(1 for value in finals if value <= 0) / runs,
    }


def _percentiles(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)

    def pick(fraction: float) -> float:
        return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]

    return {"p5": pick(0.05), "p50": pick(0.5), "p95": pick(0.95)}
