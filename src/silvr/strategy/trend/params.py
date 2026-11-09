"""Frozen trend_ensemble parameters. Nothing here is tuned on results."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

STRATEGY_NAME = "trend_ensemble"

SYMBOLS: tuple[str, ...] = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "LTCUSDT", "TRXUSDT", "ATOMUSDT", "NEARUSDT", "BCHUSDT",
)

# Donchian lookbacks in days, from Zarattini, Pagani and Barbon (SSRN 5209907), section 4.3.
LOOKBACKS: tuple[int, ...] = (5, 10, 20, 30, 60, 90, 150, 250, 360)

VOL_TARGET = 0.25  # annual volatility target
VOL_WINDOW = 90  # daily returns, annualized with sqrt(365)
MAX_GROSS_LEVERAGE = 2.0  # total notional cap, times equity
SCALE_K: float | None = 1.0  # the paper's own per-slice sizing (0.25 / vol / 9 / 15 of equity), chosen by the owner on 2026-11-10 after the k = 4.011 training check tripped the kill switch; not fitted to results; training realized volatility at k = 1.0 was 0.0935 (first calibration run)

INITIAL_BALANCE = 15_000.0
KILL_SWITCH_DRAWDOWN = 4_500.0  # 0.30 x INITIAL_BALANCE, in dollars


@dataclass(frozen=True)
class ExchangeLimits:
    """One symbol's Binance USDT-M minimums."""

    min_notional: float
    qty_step: float
    min_qty: float


# Binance USDT-M futures exchangeInfo (MIN_NOTIONAL notional, LOT_SIZE stepSize and minQty),
# fetched once on 2026-11-09. Never fetched at runtime.
EXCHANGE_LIMITS: Mapping[str, ExchangeLimits] = MappingProxyType(
    {
        "BTCUSDT": ExchangeLimits(50.0, 0.001, 0.001),
        "ETHUSDT": ExchangeLimits(20.0, 0.001, 0.001),
        "SOLUSDT": ExchangeLimits(5.0, 0.01, 0.01),
        "BNBUSDT": ExchangeLimits(5.0, 0.01, 0.01),
        "XRPUSDT": ExchangeLimits(5.0, 0.1, 0.1),
        "ADAUSDT": ExchangeLimits(5.0, 1.0, 1.0),
        "DOGEUSDT": ExchangeLimits(5.0, 1.0, 1.0),
        "AVAXUSDT": ExchangeLimits(5.0, 1.0, 1.0),
        "LINKUSDT": ExchangeLimits(20.0, 0.01, 0.01),
        "DOTUSDT": ExchangeLimits(5.0, 0.1, 0.1),
        "LTCUSDT": ExchangeLimits(20.0, 0.001, 0.001),
        "TRXUSDT": ExchangeLimits(5.0, 1.0, 1.0),
        "ATOMUSDT": ExchangeLimits(5.0, 0.01, 0.01),
        "NEARUSDT": ExchangeLimits(5.0, 1.0, 1.0),
        "BCHUSDT": ExchangeLimits(20.0, 0.001, 0.001),
    }
)
