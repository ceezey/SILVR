from datetime import UTC, datetime, time

from silver_bot.strategy import SessionWindow, SilverBulletSessionEngine


def test_new_york_session_detection_is_timezone_aware() -> None:
    engine = SilverBulletSessionEngine()

    state = engine.evaluate(datetime(2026, 6, 1, 14, 30, tzinfo=UTC))

    assert state.is_active is True
    assert state.name == "new_york_am"
    assert state.start_at is not None
    assert state.start_at.hour == 10


def test_new_york_session_detection_handles_standard_time() -> None:
    engine = SilverBulletSessionEngine()

    state = engine.evaluate(datetime(2026, 1, 2, 15, 30, tzinfo=UTC))

    assert state.is_active is True
    assert state.name == "new_york_am"
    assert state.start_at is not None
    assert state.start_at.hour == 10


def test_sessions_are_configurable_and_disabled_sessions_do_not_activate() -> None:
    engine = SilverBulletSessionEngine(
        sessions=(SessionWindow("custom", time(9, 0), time(9, 30), False),)
    )

    state = engine.evaluate(datetime(2026, 1, 2, 14, 15, tzinfo=UTC))

    assert state.is_active is False
    assert state.name is None
