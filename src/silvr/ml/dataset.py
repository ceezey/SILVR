"""Dataset creation for the ML probability-filter foundation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from silvr.ml.features import FeatureEngineeringPipeline
from silvr.models import Candle, SignalDirection
from silvr.strategy import SilverBulletSignal, SilverBulletStrategyEngine


@dataclass(frozen=True, slots=True)
class MLSetupRow:
    """One supervised row representing one rule-based setup."""

    signal_time: datetime
    symbol: str
    timeframe: str
    direction: SignalDirection
    session_name: str
    features: dict[str, float]
    label: int
    outcome_time: datetime


@dataclass(frozen=True, slots=True)
class MLDataset:
    """Supervised setup dataset and stable feature ordering."""

    rows: tuple[MLSetupRow, ...]
    feature_names: tuple[str, ...]
    skipped_unresolved: int = 0

    def as_matrices(
        self,
        rows: Sequence[MLSetupRow] | None = None,
    ) -> tuple[list[list[float]], list[int]]:
        """Return X/y arrays in the dataset feature order."""

        selected_rows = self.rows if rows is None else tuple(rows)
        matrix = [
            [float(row.features.get(name, 0.0)) for name in self.feature_names]
            for row in selected_rows
        ]
        labels = [int(row.label) for row in selected_rows]
        return matrix, labels


@dataclass(frozen=True, slots=True)
class MLDatasetSplit:
    """Chronological train/validation/test split."""

    train: tuple[MLSetupRow, ...]
    validation: tuple[MLSetupRow, ...]
    test: tuple[MLSetupRow, ...]


@dataclass(slots=True)
class MLDatasetBuilder:
    """Build supervised ML rows from deterministic Silver Bullet signals."""

    strategy: SilverBulletStrategyEngine
    feature_pipeline: FeatureEngineeringPipeline = field(default_factory=FeatureEngineeringPipeline)
    max_lookahead_candles: int = 100

    def __post_init__(self) -> None:
        if self.max_lookahead_candles < 1:
            raise ValueError("max_lookahead_candles must be positive")

    def build(
        self,
        candles: Sequence[Candle],
        *,
        higher_timeframe_candles: Sequence[Candle] | None = None,
    ) -> MLDataset:
        """Create one labeled row for each resolvable rule-based setup."""

        ordered = tuple(sorted(candles, key=lambda item: item.open_time))
        rows: list[MLSetupRow] = []
        skipped_unresolved = 0
        minimum_history = max(5, self.strategy.config.swing_lookback + 3)

        for index in range(minimum_history - 1, len(ordered) - 1):
            candles_at_signal = ordered[: index + 1]
            signal = self.strategy.evaluate(
                candles_at_signal,
                higher_timeframe_candles=higher_timeframe_candles,
            )
            if signal.direction == SignalDirection.NO_TRADE:
                continue

            future = ordered[index + 1 : index + 1 + self.max_lookahead_candles]
            outcome = label_signal_outcome(signal, future)
            if outcome is None:
                skipped_unresolved += 1
                continue

            features = self.feature_pipeline.build_features(
                signal=signal,
                candles_at_signal=candles_at_signal,
            )
            label, outcome_time = outcome
            rows.append(
                MLSetupRow(
                    signal_time=signal.generated_at,
                    symbol=signal.symbol,
                    timeframe=signal.timeframe,
                    direction=signal.direction,
                    session_name=signal.session_name or "unknown",
                    features=features,
                    label=label,
                    outcome_time=outcome_time,
                )
            )

        return MLDataset(
            rows=tuple(rows),
            feature_names=self.feature_pipeline.feature_names,
            skipped_unresolved=skipped_unresolved,
        )


def label_signal_outcome(
    signal: SilverBulletSignal,
    future_candles: Sequence[Candle],
) -> tuple[int, datetime] | None:
    """Label 1 if TP is reached before SL, else 0 if SL is reached first.

    If both TP and SL are touched in the same candle, the conservative label is
    a loss because intrabar order is unknown from OHLCV candles.
    """

    if signal.entry_price is None or signal.stop_loss is None or signal.take_profit is None:
        return None
    if signal.direction not in {SignalDirection.LONG, SignalDirection.SHORT}:
        return None

    for candle in future_candles:
        timestamp = candle.close_time or candle.open_time
        if signal.direction == SignalDirection.LONG:
            stop_hit = candle.low <= signal.stop_loss
            target_hit = candle.high >= signal.take_profit
        else:
            stop_hit = candle.high >= signal.stop_loss
            target_hit = candle.low <= signal.take_profit

        if stop_hit:
            return 0, timestamp
        if target_hit:
            return 1, timestamp
    return None


def time_based_split(
    dataset: MLDataset,
    *,
    train_fraction: float = 0.6,
    validation_fraction: float = 0.2,
) -> MLDatasetSplit:
    """Split rows chronologically without randomization."""

    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between 0 and 1")
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between 0 and 1")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("train and validation fractions must leave room for test data")

    rows = tuple(sorted(dataset.rows, key=lambda item: item.signal_time))
    count = len(rows)
    if count == 0:
        return MLDatasetSplit(train=(), validation=(), test=())

    train_end = max(1, int(count * train_fraction))
    validation_end = max(train_end + 1, int(count * (train_fraction + validation_fraction)))
    validation_end = min(validation_end, count)
    return MLDatasetSplit(
        train=rows[:train_end],
        validation=rows[train_end:validation_end],
        test=rows[validation_end:],
    )
