"""Feature engineering for rule-based Silver Bullet setups.

Features in this module are built only from the confirmed signal and candles
available at signal time. Future outcome data belongs in labels, never here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from silvr.models import Candle, SignalDirection
from silvr.strategy import (
    DEFAULT_SESSIONS,
    SilverBulletSessionEngine,
    SilverBulletSignal,
    average_true_range,
)


LEAKAGE_COLUMN_KEYWORDS: tuple[str, ...] = (
    "future",
    "label",
    "outcome",
    "tp_hit",
    "sl_hit",
    "exit",
    "pnl",
    "realized",
    "mfe",
    "mae",
)


FEATURE_NAMES: tuple[str, ...] = (
    "direction_long",
    "direction_short",
    "entry_price",
    "stop_distance",
    "target_distance",
    "reward_to_risk",
    "setup_quality_score",
    "session_london",
    "session_new_york_am",
    "session_new_york_pm",
    "session_unknown",
    "minutes_from_session_open",
    "minutes_until_session_close",
    "day_of_week",
    "hour_new_york",
    "atr",
    "atr_percent",
    "recent_range",
    "recent_body",
    "recent_volume",
    "recent_return_1",
    "recent_return_3",
    "close_position_in_candle",
)


@dataclass(frozen=True, slots=True)
class FeatureEngineeringPipeline:
    """Build numeric ML features for one rule-based setup."""

    atr_period: int = 5
    recent_window: int = 5
    session_timezone: str = "America/New_York"

    @property
    def feature_names(self) -> tuple[str, ...]:
        """Return the stable feature order used by training and inference."""

        return FEATURE_NAMES

    def build_features(
        self,
        *,
        signal: SilverBulletSignal,
        candles_at_signal: Sequence[Candle],
    ) -> dict[str, float]:
        """Return a numeric feature vector using only signal-time data."""

        if not candles_at_signal:
            raise ValueError("candles_at_signal cannot be empty")
        if signal.direction == SignalDirection.NO_TRADE:
            raise ValueError("ML features require a rule-based trade setup signal")
        if signal.entry_price is None or signal.stop_loss is None or signal.take_profit is None:
            raise ValueError("Signal must include entry, stop loss, and take profit")

        latest = candles_at_signal[-1]
        recent = candles_at_signal[-self.recent_window :]
        atr = average_true_range(candles_at_signal, period=self.atr_period)
        stop_distance = abs(signal.entry_price - signal.stop_loss)
        target_distance = abs(signal.take_profit - signal.entry_price)
        candle_range = latest.high - latest.low
        session_features = self._session_features(signal)

        features = {
            "direction_long": 1.0 if signal.direction == SignalDirection.LONG else 0.0,
            "direction_short": 1.0 if signal.direction == SignalDirection.SHORT else 0.0,
            "entry_price": float(signal.entry_price),
            "stop_distance": float(stop_distance),
            "target_distance": float(target_distance),
            "reward_to_risk": float(signal.risk_reward_ratio or 0.0),
            "setup_quality_score": float(signal.setup_quality_score),
            "atr": float(atr),
            "atr_percent": float(atr / latest.close) if latest.close else 0.0,
            "recent_range": _average(item.high - item.low for item in recent),
            "recent_body": _average(abs(item.close - item.open) for item in recent),
            "recent_volume": _average(item.volume for item in recent),
            "recent_return_1": _return_over(candles_at_signal, periods=1),
            "recent_return_3": _return_over(candles_at_signal, periods=3),
            "close_position_in_candle": (
                float((latest.close - latest.low) / candle_range) if candle_range > 0 else 0.0
            ),
        }
        features.update(session_features)
        ordered = {name: float(features.get(name, 0.0)) for name in self.feature_names}
        validate_no_future_leakage_columns(ordered.keys())
        return ordered

    def _session_features(self, signal: SilverBulletSignal) -> dict[str, float]:
        engine = SilverBulletSessionEngine(
            timezone_name=self.session_timezone,
            sessions=DEFAULT_SESSIONS,
        )
        state = engine.evaluate(signal.generated_at)
        local_time = engine._to_local(signal.generated_at)
        session_name = signal.session_name or state.name or "unknown"
        minutes_from_open = 0.0
        minutes_until_close = 0.0
        if state.start_at is not None and state.end_at is not None:
            minutes_from_open = max(0.0, (local_time - state.start_at).total_seconds() / 60.0)
            minutes_until_close = max(0.0, (state.end_at - local_time).total_seconds() / 60.0)
        return {
            "session_london": 1.0 if session_name == "london" else 0.0,
            "session_new_york_am": 1.0 if session_name == "new_york_am" else 0.0,
            "session_new_york_pm": 1.0 if session_name == "new_york_pm" else 0.0,
            "session_unknown": 1.0 if session_name not in {"london", "new_york_am", "new_york_pm"} else 0.0,
            "minutes_from_session_open": minutes_from_open,
            "minutes_until_session_close": minutes_until_close,
            "day_of_week": float(local_time.weekday()),
            "hour_new_york": float(local_time.hour),
        }


def validate_no_future_leakage_columns(feature_names: Sequence[str]) -> None:
    """Raise if feature names include known future/outcome leakage fields."""

    forbidden = [
        name
        for name in feature_names
        if any(keyword in name.lower() for keyword in LEAKAGE_COLUMN_KEYWORDS)
    ]
    if forbidden:
        raise ValueError(f"Feature names contain future leakage columns: {', '.join(forbidden)}")


def _average(values) -> float:
    values_list = [float(value) for value in values]
    return sum(values_list) / len(values_list) if values_list else 0.0


def _return_over(candles: Sequence[Candle], *, periods: int) -> float:
    if len(candles) <= periods:
        return 0.0
    previous = candles[-1 - periods].close
    if previous == 0:
        return 0.0
    return float((candles[-1].close / previous) - 1.0)
