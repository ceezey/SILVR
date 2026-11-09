"""Fair Value Gap detection."""

from __future__ import annotations

from collections.abc import Sequence

from silvr.models import Candle
from silvr.strategy.models import FairValueGap, FairValueGapDirection


def detect_fair_value_gaps(
    candles: Sequence[Candle],
    *,
    minimum_size: float = 0.0,
) -> list[FairValueGap]:
    """Detect bullish and bearish three-candle FVGs."""

    if minimum_size < 0:
        raise ValueError("minimum_size cannot be negative")

    gaps: list[FairValueGap] = []
    for index in range(2, len(candles)):
        first = candles[index - 2]
        third = candles[index]
        if first.high < third.low:
            lower = first.high
            upper = third.low
            size = upper - lower
            if size >= minimum_size:
                gaps.append(
                    FairValueGap(
                        direction=FairValueGapDirection.BULLISH,
                        candle_index=index,
                        lower_bound=lower,
                        upper_bound=upper,
                        midpoint=(lower + upper) / 2,
                        size=size,
                        timestamp=third.open_time,
                    )
                )
        if first.low > third.high:
            lower = third.high
            upper = first.low
            size = upper - lower
            if size >= minimum_size:
                gaps.append(
                    FairValueGap(
                        direction=FairValueGapDirection.BEARISH,
                        candle_index=index,
                        lower_bound=lower,
                        upper_bound=upper,
                        midpoint=(lower + upper) / 2,
                        size=size,
                        timestamp=third.open_time,
                    )
                )
    return gaps


def latest_unmitigated_fvg(
    candles: Sequence[Candle],
    *,
    direction: FairValueGapDirection,
    minimum_size: float = 0.0,
) -> FairValueGap | None:
    """Return the latest FVG receiving its first retracement on the latest candle."""

    if len(candles) < 3:
        return None
    latest_index = len(candles) - 1
    latest = candles[-1]
    gaps = [
        gap
        for gap in detect_fair_value_gaps(candles, minimum_size=minimum_size)
        if gap.direction == direction and gap.candle_index < latest_index
    ]
    for gap in reversed(gaps):
        prior_retraced = any(
            _candle_overlaps_gap(candle, gap)
            for candle in candles[gap.candle_index + 1 : latest_index]
        )
        if prior_retraced:
            continue
        if latest.low <= gap.upper_bound and latest.high >= gap.lower_bound:
            return gap
    return None


def _candle_overlaps_gap(candle: Candle, gap: FairValueGap) -> bool:
    return candle.low <= gap.upper_bound and candle.high >= gap.lower_bound
