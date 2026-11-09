"""Fill-price and fee formulas shared by the phase 1 and top-down backtest engines.

A market fill moves the price against the trade by half the spread plus the slippage.
"""

from __future__ import annotations

from silvr.models import SignalDirection


def half_spread_value(price: float, spread_bps: float) -> float:
    return price * (spread_bps / 10_000) / 2


def slippage_value(price: float, slippage_bps: float) -> float:
    return price * slippage_bps / 10_000


def entry_price(price: float, side: SignalDirection, *, spread_bps: float, slippage_bps: float) -> float:
    spread = half_spread_value(price, spread_bps)
    slippage = slippage_value(price, slippage_bps)
    return price + spread + slippage if side == SignalDirection.LONG else price - spread - slippage


def market_exit_price(price: float, side: SignalDirection, *, spread_bps: float, slippage_bps: float) -> float:
    spread = half_spread_value(price, spread_bps)
    slippage = slippage_value(price, slippage_bps)
    return price - spread - slippage if side == SignalDirection.LONG else price + spread + slippage


def fee(price: float, qty: float, rate: float) -> float:
    return abs(price * qty * rate)
