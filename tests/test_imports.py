def test_phase_one_package_boundaries_import() -> None:
    import silvr.backtest
    import silvr.config
    import silvr.data
    import silvr.exchange
    import silvr.execution
    import silvr.ml
    import silvr.monitoring
    import silvr.risk
    import silvr.storage
    import silvr.strategy
    import silvr.utils

    assert silvr.config
    assert silvr.exchange
    assert silvr.risk
