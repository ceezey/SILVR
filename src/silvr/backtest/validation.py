"""Backtest validation: the chronological train / validation / final-test split."""

from __future__ import annotations

from dataclasses import dataclass

from silvr.models import Candle


@dataclass(frozen=True, slots=True)
class BacktestSplit:
    """Chronological train/validation/final-test split."""

    training: list[Candle]
    validation: list[Candle]
    final_test: list[Candle]


class BacktestValidationSuite:
    """Small validation helper for chronological splits."""

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
