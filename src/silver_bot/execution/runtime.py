"""Paper and demo runtime: real market data in, simulated fills only.

Both modes read closed candles from the Binance Futures public klines endpoint
(production market data in paper mode, the testnet in demo mode) and fill
trades in the local paper executor. No order is sent to any exchange.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from silver_bot.backtest.metrics import calculate_metrics
from silver_bot.backtest.models import BacktestConfig, EquityPoint
from silver_bot.backtest.runner import build_ml_filter_config
from silver_bot.backtest.reporting import json_safe
from silver_bot.config import AppConfig
from silver_bot.data import (
    BinancePollingMarketDataStream,
    ReconnectingMarketDataStream,
    ReconnectPolicy,
    timeframe_interval,
)
from silver_bot.exchange import ExchangeAdapter
from silver_bot.execution.models import PaperExecutionConfig
from silver_bot.execution.paper_executor import PaperExecutionEngine
from silver_bot.execution.paper_trading import PaperTradingEngine, PaperTradingResult
from silver_bot.ml import MLProbabilityFilter
from silver_bot.models import Candle
from silver_bot.monitoring import StructuredAuditLogger
from silver_bot.risk import build_risk_engine
from silver_bot.storage import PostgresStorage

WARMUP_CANDLES = 500
RECONNECT_POLICY = ReconnectPolicy(max_reconnects=5, reconnect_delay_seconds=10.0)
PAPER_REPORT_FILENAME = "paper_trading_report.json"


async def run_paper_session(
    config: AppConfig,
    *,
    adapter: ExchangeAdapter,
    storage: PostgresStorage,
    audit: StructuredAuditLogger,
    output_dir: Path,
    max_candles: int | None = None,
) -> PaperTradingResult | None:
    """Run the paper engine on live closed candles until stopped.

    The risk engine comes from settings with persisted state and the real kill
    switch. The report at `output_dir/paper_trading_report.json` is rewritten
    after every closed trade and when the session ends, however it ends.
    """

    started_at = datetime.now(timezone.utc)
    history = await _warmup(config, adapter, now=started_at)
    polling = BinancePollingMarketDataStream(
        adapter,
        symbol=config.symbol,
        timeframe=config.timeframe,
        after=history[-1].open_time if history else None,
    )
    defaults = BacktestConfig()
    report_path = output_dir / PAPER_REPORT_FILENAME

    def write_report(result: PaperTradingResult) -> None:
        write_paper_report(
            report_path, result, config=config, started_at=started_at, initial_equity=defaults.initial_balance
        )

    engine = PaperTradingEngine(
        stream=ReconnectingMarketDataStream(lambda: polling, policy=RECONNECT_POLICY),
        risk=build_risk_engine(config, storage),
        # Same costs as the backtest, so paper and backtest results compare (BRD-M8).
        executor=PaperExecutionEngine(
            config=PaperExecutionConfig(
                maker_fee=defaults.maker_fee,
                taker_fee=defaults.taker_fee,
                slippage_bps=defaults.slippage_bps,
                spread_bps=defaults.spread_bps,
            )
        ),
        storage=storage,
        ml_filter=MLProbabilityFilter(build_ml_filter_config(config)),
        audit_logger=audit,
        initial_equity=defaults.initial_balance,
        history=history,
        on_trade_closed=write_report,
    )
    try:
        return await engine.run(max_candles=max_candles)
    finally:
        if engine.result is not None:
            write_report(engine.result)


async def _warmup(config: AppConfig, adapter: ExchangeAdapter, *, now: datetime) -> list[Candle]:
    """Return up to WARMUP_CANDLES recent closed candles to seed the strategy."""

    fetched = await adapter.fetch_ohlcv(
        symbol=config.symbol,
        timeframe=config.timeframe,
        start=now - timeframe_interval(config.timeframe) * WARMUP_CANDLES,
        end=now,
        limit=WARMUP_CANDLES,
    )
    return [candle for candle in fetched if candle.close_time is not None and candle.close_time <= now]


def write_paper_report(
    path: Path,
    result: PaperTradingResult,
    *,
    config: AppConfig,
    started_at: datetime,
    initial_equity: float,
) -> None:
    """Write the paper evidence report atomically (a reader never sees half a file)."""

    equity = peak = initial_equity
    curve: list[EquityPoint] = []
    for trade in result.trades:
        equity += trade.realized_pnl
        peak = max(peak, equity)
        curve.append(
            EquityPoint(
                timestamp=trade.exit_time,
                equity=equity,
                realized_pnl=equity - initial_equity,
                drawdown=peak - equity,
            )
        )
    payload: dict[str, Any] = {
        "mode": config.mode.value,
        "symbol": config.symbol,
        "timeframe": config.timeframe,
        "fills": "simulated",
        "started_at": started_at,
        "updated_at": datetime.now(timezone.utc),
        "candles_processed": result.candles_processed,
        "closed_trades": result.closed_trades,
        "initial_equity": initial_equity,
        "ending_equity": result.equity,
        "metrics": calculate_metrics(result.trades, curve, initial_balance=initial_equity),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(json_safe(payload), indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)
