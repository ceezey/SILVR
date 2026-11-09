import pytest

from silvr.strategy.trend import params
from silvr.strategy.trend.sizing import fit_gross_cap, round_to_exchange, target_notional


def test_target_notional_formula():
    assert target_notional(equity=15_000, vol=0.5, k=1.0) == pytest.approx(1.0 * 0.25 / 0.5 / 15 / 9 * 15_000)


def test_gross_cap_pro_rata():
    out = fit_gross_cap({"a": 10_000, "b": 30_000}, open_notional=0.0, equity=15_000)
    assert out == pytest.approx({"a": 7_500, "b": 22_500})


def test_gross_cap_no_room():
    assert fit_gross_cap({"a": 100}, open_notional=30_000, equity=15_000) == {"a": 0.0}


def test_gross_cap_over_cap_open_notional_scales_to_zero():
    assert fit_gross_cap({"a": 100}, open_notional=40_000, equity=15_000) == {"a": 0.0}


def test_gross_cap_untouched_when_room():
    assert fit_gross_cap({"a": 100}, open_notional=0.0, equity=15_000) == {"a": 100}


def test_gross_cap_empty_or_zero_new_unchanged():
    assert fit_gross_cap({}, open_notional=40_000, equity=15_000) == {}
    assert fit_gross_cap({"a": 0.0}, open_notional=40_000, equity=15_000) == {"a": 0.0}


def test_round_down_and_minimums():
    lim = params.EXCHANGE_LIMITS["BTCUSDT"]
    assert round_to_exchange("BTCUSDT", lim.qty_step * 3.7, 1e9) == pytest.approx(lim.qty_step * 3)
    assert round_to_exchange("BTCUSDT", lim.min_qty, (lim.min_notional / lim.min_qty) * 0.5) == 0.0


def test_round_floors_through_float_error():
    assert 0.3 / 0.1 < 3  # the trap: 2.9999999999999996, so a plain floor gives 2 steps
    assert round_to_exchange("XRPUSDT", 0.3, 1e9) == 0.3
    assert round_to_exchange("XRPUSDT", 0.39, 1e9) == 0.3


def test_round_below_min_qty_is_zero():
    assert round_to_exchange("BTCUSDT", 0.0009, 1e9) == 0.0
