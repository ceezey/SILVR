from datetime import UTC, datetime, timedelta

import pytest

from silvr.backtest import BacktestValidationSuite
from silvr.models import Candle


def candles(count: int) -> list[Candle]:
    start = datetime(2026, 1, 2, 14, 0, tzinfo=UTC)
    return [
        Candle(
            symbol="BTCUSDT",
            timeframe="1m",
            open_time=start + timedelta(minutes=index),
            close_time=start + timedelta(minutes=index + 1),
            open=100,
            high=102,
            low=98,
            close=101,
            volume=1000,
        )
        for index in range(count)
    ]


def test_chronological_split_is_time_ordered_and_never_overlaps() -> None:
    data = candles(10)

    split = BacktestValidationSuite().chronological_split(list(reversed(data)))

    assert (split.training, split.validation, split.final_test) == (data[:6], data[6:8], data[8:])


@pytest.mark.parametrize(("training", "validation"), [(0.0, 0.2), (0.6, 1.0), (0.8, 0.2)])
def test_chronological_split_rejects_fractions_without_final_test(training: float, validation: float) -> None:
    with pytest.raises(ValueError):
        BacktestValidationSuite().chronological_split(candles(10), training_fraction=training, validation_fraction=validation)
