"""Volatility-target sizing, gross-notional cap and exchange rounding for trend_ensemble."""

from collections.abc import Mapping
from decimal import Decimal

from silvr.strategy.trend.params import (
    EXCHANGE_LIMITS,
    LOOKBACKS,
    MAX_GROSS_LEVERAGE,
    SYMBOLS,
    VOL_TARGET,
)


def target_notional(*, equity: float, vol: float, k: float) -> float:
    """Notional of one slice (one symbol and one lookback) when it is long."""

    return k * VOL_TARGET / vol / len(SYMBOLS) / len(LOOKBACKS) * equity


def fit_gross_cap(new: Mapping[str, float], *, open_notional: float, equity: float) -> dict[str, float]:
    """Scale new slice notionals pro rata so total notional stays within the gross cap."""

    total = sum(new.values())
    room = MAX_GROSS_LEVERAGE * equity - open_notional
    if total == 0 or total <= room:
        return dict(new)
    scale = max(0.0, room) / total
    return {slice_id: notional * scale for slice_id, notional in new.items()}


def round_to_exchange(symbol: str, qty: float, price: float) -> float:
    """Floor qty to the symbol's step; 0.0 when below min_qty or min_notional."""

    limits = EXCHANGE_LIMITS[symbol]
    step = Decimal(str(limits.qty_step))
    rounded = float(Decimal(str(qty)) // step * step)  # Decimal avoids 0.003 / 0.001 == 2.999...
    if rounded < limits.min_qty or rounded * price < limits.min_notional:
        return 0.0
    return rounded
