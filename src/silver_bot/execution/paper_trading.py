"""Paper trading orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from silver_bot.backtest.models import TradeRecord
from silver_bot.data import MarketDataStream
from silver_bot.execution.models import PaperEventType, PaperLifecycleEvent
from silver_bot.execution.paper_executor import PaperExecutionEngine
from silver_bot.ml import MLDecision, MLProbabilityFilter
from silver_bot.models import Candle, SignalDirection
from silver_bot.monitoring import StructuredAuditLogger
from silver_bot.monitoring.telegram import TelegramAlerter
from silver_bot.risk import RiskManagementEngine, RiskRequest
from silver_bot.storage import SQLiteStorage
from silver_bot.strategy import SilverBulletStrategyEngine


@dataclass(slots=True)
class PaperTradingResult:
    """Paper trading run summary."""

    candles_processed: int = 0
    events: list[PaperLifecycleEvent] = field(default_factory=list)
    trades: list[TradeRecord] = field(default_factory=list)
    closed_trades: int = 0
    equity: float = 10_000.0


class PaperTradingEngine:
    """Run strategy, risk, and paper execution on live-like candle streams."""

    def __init__(
        self,
        *,
        stream: MarketDataStream,
        strategy: SilverBulletStrategyEngine | None = None,
        risk: RiskManagementEngine | None = None,
        executor: PaperExecutionEngine | None = None,
        storage: SQLiteStorage | None = None,
        alerter: TelegramAlerter | None = None,
        ml_filter: MLProbabilityFilter | None = None,
        audit_logger: StructuredAuditLogger | None = None,
        initial_equity: float = 10_000.0,
    ) -> None:
        self.stream = stream
        self.strategy = strategy or SilverBulletStrategyEngine()
        self.risk = risk or RiskManagementEngine()
        self.executor = executor or PaperExecutionEngine()
        self.storage = storage
        self.alerter = alerter or TelegramAlerter()
        self.ml_filter = ml_filter or MLProbabilityFilter()
        self.audit = audit_logger or StructuredAuditLogger()
        self.equity = initial_equity
        self._candles: list[Candle] = []
        self._kill_alert_sent = False

    async def run(self, *, max_candles: int | None = None) -> PaperTradingResult:
        """Run paper trading over stream candles."""

        if self.storage is not None:
            self.storage.initialize()
        self.audit.log("bot_started", "Paper bot started", context={"mode": "paper"})
        await self.alerter.bot_started()

        result = PaperTradingResult(equity=self.equity)
        async for candle in self.stream.candles():
            self._candles.append(candle)
            result.candles_processed += 1
            if self.storage is not None:
                self.storage.save_candles([candle])

            if self.risk.kill_switch.is_active() and not self._kill_alert_sent:
                event = PaperLifecycleEvent(
                    event_type=PaperEventType.KILL_SWITCH_ACTIVE,
                    symbol=candle.symbol,
                    timestamp=candle.close_time or candle.open_time,
                    message="Kill switch active",
                    context={},
                )
                await self.alerter.kill_switch_active()
                self._record_event(event, result)
                self._kill_alert_sent = True

            for event in self.executor.process_candle(candle):
                self._record_event(event, result)
                if event.event_type == PaperEventType.PAPER_TRADE_OPENED:
                    direction = str((event.context or {}).get("direction", "UNKNOWN"))
                    await self.alerter.paper_trade_opened(event.symbol, direction)
                if event.event_type == PaperEventType.PAPER_TRADE_CLOSED and event.trade is not None:
                    self.equity += event.trade.realized_pnl
                    result.equity = self.equity
                    result.closed_trades += 1
                    self.risk.release_trade(
                        realized_pnl=event.trade.realized_pnl,
                        day=event.trade.exit_time.date(),
                    )
                    if self.storage is not None:
                        self.storage.save_paper_trade(event.trade)
                    await self.alerter.paper_trade_closed(event.symbol, event.trade.realized_pnl)
                    result.trades.append(event.trade)

            if not self.executor.has_active_trade:
                await self._evaluate_signal(candle, result)

            if max_candles is not None and result.candles_processed >= max_candles:
                break

        result.equity = self.equity
        self.audit.log(
            "bot_stopped",
            "Paper bot stopped",
            context={
                "mode": "paper",
                "candles_processed": result.candles_processed,
                "closed_trades": result.closed_trades,
                "ending_equity": result.equity,
            },
        )
        await self.alerter.bot_stopped()
        return result

    async def _evaluate_signal(self, candle: Candle, result: PaperTradingResult) -> None:
        signal = self.strategy.evaluate(self._candles)
        self._log_strategy_decision(signal)
        if signal.direction == SignalDirection.NO_TRADE:
            self.audit.log(
                "signal_rejected",
                "Strategy signal rejected",
                context={
                    "symbol": signal.symbol,
                    "timeframe": signal.timeframe,
                    "reason": signal.reason or "Unknown rejection reason",
                },
            )
            await self.alerter.signal_rejected(signal.symbol, signal.reason or "Unknown rejection reason")
            return

        ml_decision = self.ml_filter.evaluate(
            signal=signal,
            candles_at_signal=self._candles,
        )
        self.audit.log(
            "ml_decision",
            "ML filter evaluated strategy signal",
            context={
                "symbol": signal.symbol,
                "timeframe": signal.timeframe,
                "decision": ml_decision.decision.value,
                "probability": ml_decision.probability,
                "threshold": ml_decision.threshold,
                "reduce_risk_threshold": ml_decision.reduce_risk_threshold,
                "risk_multiplier": ml_decision.risk_multiplier,
                "model_id": ml_decision.model_id,
                "reason": ml_decision.reason,
            },
        )
        if self.storage is not None:
            self.storage.save_ml_prediction(ml_decision)

        signal_event = PaperLifecycleEvent(
            event_type=PaperEventType.SIGNAL_DETECTED,
            symbol=signal.symbol,
            timestamp=signal.generated_at,
            message="Strategy signal detected",
            context={
                "direction": signal.direction.value,
                "score": signal.setup_quality_score,
                "ml_probability": ml_decision.probability,
                "ml_decision": ml_decision.decision.value,
            },
        )
        self._record_event(signal_event, result)
        await self.alerter.signal_detected(signal.symbol, signal.direction.value)
        if ml_decision.decision == MLDecision.REJECT:
            await self.alerter.ml_rejection(signal.symbol, ml_decision.probability, ml_decision.reason)
        else:
            await self.alerter.ml_approval(signal.symbol, ml_decision.probability)

        if ml_decision.decision == MLDecision.REJECT:
            rejected = PaperLifecycleEvent(
                event_type=PaperEventType.RISK_REJECTED,
                symbol=signal.symbol,
                timestamp=signal.generated_at,
                message=f"ML rejected: {ml_decision.reason}",
                context={
                    "reason": ml_decision.reason,
                    "ml_probability": ml_decision.probability,
                    "ml_decision": ml_decision.decision.value,
                },
            )
            self._record_event(rejected, result)
            self.audit.log(
                "signal_rejected",
                "ML rejected strategy signal",
                context={
                    "symbol": signal.symbol,
                    "timeframe": signal.timeframe,
                    "reason": ml_decision.reason,
                    "ml_probability": ml_decision.probability,
                    "ml_decision": ml_decision.decision.value,
                },
            )
            return

        decision = self.risk.evaluate(
            RiskRequest(
                equity=self.equity,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                direction=signal.direction.value,
                signal_day=signal.generated_at.date(),
            )
        )
        if not decision.approved:
            event_type = (
                PaperEventType.KILL_SWITCH_ACTIVE
                if decision.reason == "Kill switch is active"
                else PaperEventType.RISK_REJECTED
            )
            rejected = PaperLifecycleEvent(
                event_type=event_type,
                symbol=signal.symbol,
                timestamp=signal.generated_at,
                message=f"Risk rejected: {decision.reason}",
                context={"reason": decision.reason},
            )
            self._record_event(rejected, result)
            self.audit.log(
                "risk_rejected",
                "Risk rejected strategy signal",
                context={
                    "symbol": signal.symbol,
                    "timeframe": signal.timeframe,
                    "reason": decision.reason,
                    "ml_probability": ml_decision.probability,
                    "ml_decision": ml_decision.decision.value,
                },
            )
            if decision.reason == "Kill switch is active":
                self.audit.log(
                    "kill_switch_active",
                    "Kill switch blocked paper signal",
                    context={"symbol": signal.symbol, "timeframe": signal.timeframe},
                )
                await self.alerter.kill_switch_active()
            else:
                await self.alerter.risk_rejection(signal.symbol, decision.reason)
            return
        if ml_decision.decision == MLDecision.REDUCE_RISK:
            decision = replace(
                decision,
                position_size=decision.position_size * ml_decision.risk_multiplier,
                risk_amount=decision.risk_amount * ml_decision.risk_multiplier,
                leverage=decision.leverage * ml_decision.risk_multiplier,
                reason=f"{decision.reason}; ML reduced risk",
            )

        order_event = self.executor.submit_limit_order(
            signal=signal,
            risk_decision=decision,
            ml_probability=ml_decision.probability,
            ml_decision=ml_decision.decision.value,
        )
        self.risk.reserve_trade(signal.generated_at.date())
        self._record_event(order_event, result)

    def _record_event(self, event: PaperLifecycleEvent, result: PaperTradingResult) -> None:
        result.events.append(event)
        self.audit.log(
            event.event_type.value,
            event.message,
            context={
                "symbol": event.symbol,
                "timestamp": event.timestamp,
                **(event.context or {}),
            },
        )
        if self.storage is not None:
            self.storage.save_paper_event(
                event_type=event.event_type.value,
                symbol=event.symbol,
                timestamp=event.timestamp.isoformat(),
                message=event.message,
                context=event.context or {},
            )

    def _log_strategy_decision(self, signal) -> None:
        self.audit.log(
            "strategy_decision",
            "Strategy evaluated setup",
            context={
                "symbol": signal.symbol,
                "timeframe": signal.timeframe,
                "direction": signal.direction.value,
                "reason": signal.reason,
                "entry_price": signal.entry_price,
                "stop_loss": signal.stop_loss,
                "take_profit": signal.take_profit,
                "risk_reward_ratio": signal.risk_reward_ratio,
                "session_name": signal.session_name,
                "setup_quality_score": signal.setup_quality_score,
            },
        )
