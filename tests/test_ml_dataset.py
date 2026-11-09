from datetime import UTC, datetime, timedelta

import pytest

from silvr.ml import (
    LEAKAGE_COLUMN_KEYWORDS,
    FeatureEngineeringPipeline,
    MLDataset,
    MLDatasetBuilder,
    MLSetupRow,
    time_based_split,
    validate_no_future_leakage_columns,
)
from silvr.models import Candle, SignalDirection
from silvr.strategy import SilverBulletStrategyConfig, SilverBulletStrategyEngine


def candle(index: int, open_: float, high: float, low: float, close: float) -> Candle:
    opened = datetime(2026, 1, 2, 15, 0, tzinfo=UTC) + timedelta(minutes=index)
    return Candle(
        symbol="BTCUSDT",
        timeframe="1m",
        open_time=opened,
        close_time=opened + timedelta(minutes=1),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1000 + index,
    )


def valid_long_setup() -> list[Candle]:
    return [
        candle(0, 110, 115, 109, 112),
        candle(1, 112, 118, 111, 116),
        candle(2, 116, 140, 114, 119),
        candle(3, 119, 120, 105, 107),
        candle(4, 107, 108, 99, 101),
        candle(5, 101, 102, 98, 100),
        candle(6, 100, 115, 99.5, 113),
        candle(7, 113, 145, 110, 142),
        candle(8, 112, 115, 105, 112),
    ]


def strategy() -> SilverBulletStrategyEngine:
    return SilverBulletStrategyEngine(
        SilverBulletStrategyConfig(
            swing_lookback=2,
            atr_period=3,
            minimum_rr=2.0,
            minimum_signal_score=70,
        )
    )


def test_dataset_builder_creates_one_setup_row_with_winning_label() -> None:
    candles = [
        *valid_long_setup(),
        candle(9, 112, 141, 105, 140),
    ]

    dataset = MLDatasetBuilder(strategy=strategy(), max_lookahead_candles=5).build(candles)

    assert len(dataset.rows) == 1
    row = dataset.rows[0]
    assert row.label == 1
    assert row.direction == SignalDirection.LONG
    assert row.session_name == "new_york_am"
    assert row.features["direction_long"] == 1.0
    assert row.features["reward_to_risk"] == 4.25
    assert set(row.features) == set(dataset.feature_names)


def test_dataset_builder_creates_losing_label() -> None:
    candles = [
        *valid_long_setup(),
        candle(9, 112, 113, 97, 99),
    ]

    dataset = MLDatasetBuilder(strategy=strategy(), max_lookahead_candles=5).build(candles)

    assert len(dataset.rows) == 1
    assert dataset.rows[0].label == 0


def test_feature_names_do_not_include_future_leakage_columns() -> None:
    pipeline = FeatureEngineeringPipeline()

    validate_no_future_leakage_columns(pipeline.feature_names)

    for name in pipeline.feature_names:
        assert not any(keyword in name.lower() for keyword in LEAKAGE_COLUMN_KEYWORDS)
    with pytest.raises(ValueError, match="future leakage"):
        validate_no_future_leakage_columns(["future_close"])


def test_time_based_split_preserves_chronological_order() -> None:
    rows = tuple(
        MLSetupRow(
            signal_time=datetime(2026, 1, 1, 12, index, tzinfo=UTC),
            symbol="BTCUSDT",
            timeframe="1m",
            direction=SignalDirection.LONG,
            session_name="new_york_am",
            features={name: float(index) for name in FeatureEngineeringPipeline().feature_names},
            label=index % 2,
            outcome_time=datetime(2026, 1, 1, 13, index, tzinfo=UTC),
        )
        for index in range(10)
    )
    shuffled = (rows[4], rows[0], rows[9], rows[3], rows[1], rows[2], rows[8], rows[6], rows[7], rows[5])
    dataset = MLDataset(rows=shuffled, feature_names=FeatureEngineeringPipeline().feature_names)

    split = time_based_split(dataset, train_fraction=0.6, validation_fraction=0.2)

    assert [row.signal_time.minute for row in split.train] == [0, 1, 2, 3, 4, 5]
    assert [row.signal_time.minute for row in split.validation] == [6, 7]
    assert [row.signal_time.minute for row in split.test] == [8, 9]
