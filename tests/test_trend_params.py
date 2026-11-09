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


def test_every_symbol_has_exchange_limits():
    assert set(params.EXCHANGE_LIMITS) == set(params.SYMBOLS)
    assert all(l.min_notional > 0 and l.qty_step > 0 and l.min_qty > 0 for l in params.EXCHANGE_LIMITS.values())
