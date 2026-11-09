import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from silvr.backtest import EquityPoint, ExitReason, TradeRecord
from silvr.monitoring import (
    InMemoryTelegramClient,
    StructuredAuditLogger,
    TelegramAlertConfig,
    TelegramAlerter,
    build_dashboard_data,
    export_dashboard_data,
    redact_secrets,
)
from silvr.monitoring.reports import (
    build_daily_performance_report,
    build_trade_journal,
    build_weekly_performance_report,
    export_report_json,
    export_trade_journal,
)


def trade(
    trade_id: int,
    *,
    pnl: float,
    realized_r: float,
    session: str = "new_york_am",
    day_offset: int = 0,
) -> TradeRecord:
    opened = datetime(2026, 1, 5, 15, 0, tzinfo=UTC) + timedelta(days=day_offset)
    return TradeRecord(
        trade_id=trade_id,
        symbol="BTCUSDT",
        timeframe="1m",
        session_name=session,
        direction="LONG",
        entry_time=opened,
        exit_time=opened + timedelta(minutes=10),
        entry_price=100,
        exit_price=110,
        stop_loss=95,
        take_profit=110,
        position_size=1,
        risk_amount=5,
        realized_pnl=pnl,
        realized_r=realized_r,
        fees=1,
        slippage=0,
        max_favorable_excursion=12,
        max_adverse_excursion=2,
        exit_reason=ExitReason.TAKE_PROFIT if pnl > 0 else ExitReason.STOP_LOSS,
        setup_quality_score=80,
        notes="rule-based setup",
        ml_probability=0.7,
        ml_decision="approve",
    )


def rejection(reason: str, *, day_offset: int = 0, ml_decision: str | None = None) -> dict[str, Any]:
    """A rejected-setup record as it appears in a report's JSON."""

    timestamp = datetime(2026, 1, 5, 15, 5, tzinfo=UTC) + timedelta(days=day_offset)
    return {
        "timestamp": timestamp,
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "reason": reason,
        "ml_probability": 0.4 if ml_decision else None,
        "ml_decision": ml_decision,
    }


def test_structured_log_generation_and_secret_redaction(tmp_path: Path) -> None:
    log_path = tmp_path / "audit.jsonl"
    logger = StructuredAuditLogger(log_path)

    logger.log(
        "strategy_decision",
        "test event",
        context={
            "symbol": "BTCUSDT",
            "BINANCE_API_KEY": "super-secret-key",
            "nested": {"api_secret": "hidden"},
        },
    )

    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert payload["event_type"] == "strategy_decision"
    assert payload["context"]["BINANCE_API_KEY"] == "[REDACTED]"
    assert payload["context"]["nested"]["api_secret"] == "[REDACTED]"
    assert "super-secret-key" not in log_path.read_text(encoding="utf-8")
    assert redact_secrets({"telegram_bot_token": "token"})["telegram_bot_token"] == "[REDACTED]"


def test_audit_logger_retains_events_by_default() -> None:
    logger = StructuredAuditLogger()

    logger.log("bot_started", "Backtest started")

    assert len(logger.events) == 1


def test_demo_credentials_are_redacted_from_logs(tmp_path: Path) -> None:
    log_path = tmp_path / "audit.jsonl"
    logger = StructuredAuditLogger(log_path)

    logger.log(
        "demo_readiness",
        "Demo readiness checked",
        context={
            "BINANCE_API_KEY": "demo-secret-key",
            "BINANCE_API_SECRET": "demo-secret-value",
            "mode": "demo",
        },
    )

    contents = log_path.read_text(encoding="utf-8")
    payload = json.loads(contents.strip())
    assert payload["context"]["BINANCE_API_KEY"] == "[REDACTED]"
    assert payload["context"]["BINANCE_API_SECRET"] == "[REDACTED]"
    assert "demo-secret-key" not in contents
    assert "demo-secret-value" not in contents


def test_daily_report_generation_and_exports(tmp_path: Path) -> None:
    trades = [trade(1, pnl=100, realized_r=2), trade(2, pnl=-50, realized_r=-1)]
    rejected = [
        rejection("No breakout"),
        rejection("ML rejected setup below probability threshold", ml_decision="reject"),
    ]
    equity = [
        EquityPoint(timestamp=datetime(2026, 1, 5, 15, 0, tzinfo=UTC), equity=10_000, realized_pnl=0, drawdown=0),
        EquityPoint(timestamp=datetime(2026, 1, 5, 16, 0, tzinfo=UTC), equity=9_950, realized_pnl=-50, drawdown=50),
    ]

    report = build_daily_performance_report(
        trades=trades,
        rejected_signals=rejected,
        equity_curve=equity,
        report_date=datetime(2026, 1, 5, tzinfo=UTC).date(),
    )
    export_path = export_report_json(report, tmp_path / "daily.json")

    assert report["trades_taken"] == 2
    assert report["rejected_setups"] == 2
    assert report["pnl"] == 50
    assert report["drawdown"] == 50
    assert report["win_rate"] == 0.5
    assert report["average_r"] == 0.5
    assert report["best_trade"]["trade_id"] == 1
    assert report["worst_trade"]["trade_id"] == 2
    assert report["rule_failures"]["No breakout"] == 1
    assert report["ml_decisions"]["approve"] == 2
    assert report["ml_decisions"]["reject"] == 1
    assert export_path.exists()


def test_weekly_report_generation_journal_and_dashboard_export(tmp_path: Path) -> None:
    trades = [
        trade(1, pnl=100, realized_r=2, session="new_york_am"),
        trade(2, pnl=-25, realized_r=-0.5, session="london", day_offset=1),
    ]
    rejected = [
        rejection("Volatility warm-up"),
        rejection("Volatility warm-up", day_offset=1),
    ]
    equity = [
        EquityPoint(timestamp=datetime(2026, 1, 5, 15, 0, tzinfo=UTC), equity=10_000, realized_pnl=0, drawdown=0),
        EquityPoint(timestamp=datetime(2026, 1, 6, 15, 0, tzinfo=UTC), equity=10_075, realized_pnl=75, drawdown=25),
    ]

    weekly = build_weekly_performance_report(
        trades=trades,
        rejected_signals=rejected,
        equity_curve=equity,
        week_start=datetime(2026, 1, 5, tzinfo=UTC).date(),
    )
    journal = build_trade_journal(trades)
    journal_path = export_trade_journal(trades, tmp_path / "journal.csv")
    dashboard = build_dashboard_data(
        daily_report={"trades_taken": 2},
        weekly_report=weekly,
        recent_trades=journal,
        recent_rejections=[{"reason": "Volatility warm-up"}],
    )
    dashboard_path = export_dashboard_data(dashboard, tmp_path / "dashboard.json")

    assert weekly["total_trades"] == 2
    assert weekly["net_pnl"] == 75
    assert weekly["win_rate"] == 0.5
    assert weekly["profit_factor"] == 4
    assert weekly["average_r"] == 0.75
    assert weekly["max_drawdown"] == 25
    assert weekly["best_session"]["session_name"] == "new_york_am"
    assert weekly["worst_session"]["session_name"] == "london"
    assert weekly["repeated_rejection_reasons"]["Volatility warm-up"] == 2
    assert journal[0]["trade_id"] == 1
    assert journal_path.exists()
    assert dashboard_path.exists()


def test_telegram_disabled_behavior() -> None:
    client = InMemoryTelegramClient()
    alerter = TelegramAlerter(client=client)

    asyncio.run(alerter.bot_started())
    asyncio.run(alerter.signal_rejected("BTCUSDT", "No setup"))
    asyncio.run(alerter.daily_report({"trades_taken": 1, "pnl": 10, "win_rate": 1.0}))

    assert client.messages == []


def test_telegram_mocked_send_behavior() -> None:
    client = InMemoryTelegramClient()
    alerter = TelegramAlerter(
        TelegramAlertConfig(enabled=True, chat_id="chat"),
        client=client,
    )

    asyncio.run(alerter.bot_started())
    asyncio.run(alerter.bot_stopped())
    asyncio.run(alerter.signal_detected("BTCUSDT", "LONG"))
    asyncio.run(alerter.signal_rejected("BTCUSDT", "No breakout"))
    asyncio.run(alerter.risk_rejection("BTCUSDT", "Max trades per day limit reached"))
    asyncio.run(alerter.ml_approval("BTCUSDT", 0.75))
    asyncio.run(alerter.ml_rejection("BTCUSDT", 0.42, "Below threshold"))
    asyncio.run(alerter.paper_trade_opened("BTCUSDT", "LONG"))
    asyncio.run(alerter.paper_trade_closed("BTCUSDT", 12.5))
    asyncio.run(alerter.daily_report({"trades_taken": 1, "pnl": 12.5, "win_rate": 1.0}))
    asyncio.run(alerter.error("mock error"))
    asyncio.run(alerter.kill_switch_active())

    messages = [message for _, message in client.messages]
    assert len(messages) == 12
    assert any("bot stopped" in message for message in messages)
    assert any("Signal rejected" in message for message in messages)
    assert any("Risk rejected" in message for message in messages)
    assert any("ML approved" in message for message in messages)
    assert any("Daily report" in message for message in messages)
