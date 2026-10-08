def test_phase_one_package_boundaries_import() -> None:
    import silver_bot.backtest
    import silver_bot.config
    import silver_bot.data
    import silver_bot.exchange
    import silver_bot.execution
    import silver_bot.ml
    import silver_bot.monitoring
    import silver_bot.risk
    import silver_bot.storage
    import silver_bot.strategy
    import silver_bot.utils

    assert silver_bot.config
    assert silver_bot.exchange
    assert silver_bot.risk
