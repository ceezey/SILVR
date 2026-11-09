"""Frozen trend_ensemble parameters stay as written in the design."""

from silvr.strategy.trend import params


def test_frozen_values():
    assert params.STRATEGY_NAME == "trend_ensemble"
    assert len(params.SYMBOLS) == 15 and len(set(params.SYMBOLS)) == 15
    assert len(params.LOOKBACKS) == 9 and min(params.LOOKBACKS) == 5 and max(params.LOOKBACKS) == 360
    assert list(params.LOOKBACKS) == sorted(set(params.LOOKBACKS))
    assert (params.VOL_TARGET, params.VOL_WINDOW, params.MAX_GROSS_LEVERAGE) == (0.25, 90, 2.0)
    assert params.KILL_SWITCH_DRAWDOWN == 0.30 * params.INITIAL_BALANCE
    assert params.SCALE_K is not None and params.SCALE_K > 0


def test_exact_frozen_values():
    """Any edit to a frozen value fails here, so a change after a counted run cannot slip in unnoticed."""
    assert params.SYMBOLS == (
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
        "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
        "LTCUSDT", "TRXUSDT", "ATOMUSDT", "NEARUSDT", "BCHUSDT",
    )
    assert params.LOOKBACKS == (5, 10, 20, 30, 60, 90, 150, 250, 360)
    assert params.SCALE_K == 4.011
    assert params.KILL_SWITCH_DRAWDOWN == 4500.0
    assert params.INITIAL_BALANCE == 15000.0
    assert {s: (l.min_notional, l.qty_step, l.min_qty) for s, l in params.EXCHANGE_LIMITS.items()} == {
        "BTCUSDT": (50.0, 0.001, 0.001),
        "ETHUSDT": (20.0, 0.001, 0.001),
        "SOLUSDT": (5.0, 0.01, 0.01),
        "BNBUSDT": (5.0, 0.01, 0.01),
        "XRPUSDT": (5.0, 0.1, 0.1),
        "ADAUSDT": (5.0, 1.0, 1.0),
        "DOGEUSDT": (5.0, 1.0, 1.0),
        "AVAXUSDT": (5.0, 1.0, 1.0),
        "LINKUSDT": (20.0, 0.01, 0.01),
        "DOTUSDT": (5.0, 0.1, 0.1),
        "LTCUSDT": (20.0, 0.001, 0.001),
        "TRXUSDT": (5.0, 1.0, 1.0),
        "ATOMUSDT": (5.0, 0.01, 0.01),
        "NEARUSDT": (5.0, 1.0, 1.0),
        "BCHUSDT": (20.0, 0.001, 0.001),
    }


def test_every_symbol_has_exchange_limits():
    assert set(params.EXCHANGE_LIMITS) == set(params.SYMBOLS)
    assert all(l.min_notional > 0 and l.qty_step > 0 and l.min_qty > 0 for l in params.EXCHANGE_LIMITS.values())
