"""Event-driven historical backtest engine."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from silver_bot.backtest import costs
from silver_bot.backtest.metrics import calculate_metrics
from silver_bot.backtest.models import (
    BacktestConfig,
    BacktestResult,
    EquityPoint,
    ExitReason,
    OpenPosition,
    PendingOrder,
    RejectedSignalRecord,
    TradeRecord,
)
from silver_bot.backtest.reporting import export_backtest_result
from silver_bot.backtest.sim_kill_switch import SimulatedKillSwitch
from silver_bot.ml import MLDecision, MLFilterResult, MLProbabilityFilter
from silver_bot.models import Candle, SignalDirection
from silver_bot.monitoring import StructuredAuditLogger
from silver_bot.risk import RiskManagementEngine, RiskRequest
from silver_bot.strategy import SilverBulletStrategyEngine


class BacktestEngine:
    """Replay historical candles through the strategy and simulated execution."""

    def __init__(
        self,
        *,
        strategy: SilverBulletStrategyEngine | None = None,
        config: BacktestConfig | None = None,
        risk_engine: RiskManagementEngine | None = None,
        ml_filter: MLProbabilityFilter | None = None,
        audit_logger: StructuredAuditLogger | None = None,
    ) -> None:
        self.strategy = strategy or SilverBulletStrategyEngine()
        self.config = config or BacktestConfig()
        self.risk = risk_engine or RiskManagementEngine(self.config.risk)
        self.ml_filter = ml_filter or MLProbabilityFilter(self.config.ml_filter)
        self.audit = audit_logger or StructuredAuditLogger()

    def run(self, candles: Sequence[Candle]) -> BacktestResult:
        """Run a backtest over chronological candles."""

        ordered = sorted(candles, key=lambda candle: candle.open_time)
        equity = self.config.initial_balance
        peak_equity = equity
        pending: PendingOrder | None = None
        open_position: OpenPosition | None = None
        trades: list[TradeRecord] = []
        equity_curve: list[EquityPoint] = []
        rejected: list[RejectedSignalRecord] = []
        trade_id = 1
        self.audit.log(
            "bot_started",
            "Backtest started",
            context={"mode": "backtest", "candles": len(ordered)},
        )

        for index, candle in enumerate(ordered):
            kill_switch = self.risk.kill_switch
            if isinstance(kill_switch, SimulatedKillSwitch):
                # Backtest-only: a simulated trip clears at the first candle of a new UTC day.
                kill_switch.now = candle.open_time
                if kill_switch.reset_if_new_day(candle.open_time):
                    self.risk.state.consecutive_losses = 0
            activity_this_candle = False

            if open_position is not None:
                closed = self._update_open_position(open_position, candle, trade_id=trade_id)
                if closed is not None:
                    trades.append(closed)
                    equity += closed.realized_pnl
                    self.risk.release_trade(realized_pnl=closed.realized_pnl, day=closed.exit_time.date())
                    self._log_closed_trade(closed, "Backtest simulated trade closed")
                    trade_id += 1
                    open_position = None
                    pending = None
                    activity_this_candle = True

            if open_position is None and pending is not None:
                filled = self._try_fill(pending, candle)
                if filled is not None:
                    open_position = filled
                    pending = None
                    activity_this_candle = True
                    closed = self._update_open_position(open_position, candle, trade_id=trade_id)
                    if closed is not None:
                        trades.append(closed)
                        equity += closed.realized_pnl
                        self.risk.release_trade(realized_pnl=closed.realized_pnl, day=closed.exit_time.date())
                        self._log_closed_trade(closed, "Backtest simulated trade closed")
                        trade_id += 1
                        open_position = None

            peak_equity = max(peak_equity, equity)
            equity_curve.append(
                EquityPoint(
                    timestamp=candle.close_time or candle.open_time,
                    equity=equity,
                    realized_pnl=equity - self.config.initial_balance,
                    drawdown=peak_equity - equity,
                )
            )

            if activity_this_candle or pending is not None or open_position is not None:
                continue

            visible = ordered[self._window_start(index) : index + 1]
            signal = self.strategy.evaluate(visible)
            self._log_strategy_decision(signal)
            if signal.direction == SignalDirection.NO_TRADE:
                rejected.append(
                    RejectedSignalRecord(
                        timestamp=signal.generated_at,
                        symbol=signal.symbol,
                        timeframe=signal.timeframe,
                        reason=signal.reason or "Unknown rejection reason",
                    )
                )
                self.audit.log(
                    "signal_rejected",
                    "Strategy signal rejected",
                    context={
                        "symbol": signal.symbol,
                        "timeframe": signal.timeframe,
                        "reason": signal.reason or "Unknown rejection reason",
                    },
                )
                continue

            ml_decision = self.ml_filter.evaluate(
                signal=signal,
                candles_at_signal=visible,
            )
            self._log_ml_decision(signal, ml_decision)
            if ml_decision.decision == MLDecision.REJECT:
                rejected.append(
                    RejectedSignalRecord(
                        timestamp=signal.generated_at,
                        symbol=signal.symbol,
                        timeframe=signal.timeframe,
                        reason=f"ML rejected: {ml_decision.reason}",
                        ml_probability=ml_decision.probability,
                        ml_decision=ml_decision.decision.value,
                    )
                )
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
                continue

            risk_decision = self.risk.evaluate(
                RiskRequest(
                    equity=equity,
                    entry_price=signal.entry_price,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                    direction=signal.direction.value,
                    signal_day=signal.generated_at.date(),
                )
            )
            if not risk_decision.approved:
                rejected.append(
                    RejectedSignalRecord(
                        timestamp=signal.generated_at,
                        symbol=signal.symbol,
                        timeframe=signal.timeframe,
                        reason=f"Risk rejected: {risk_decision.reason}",
                        ml_probability=ml_decision.probability,
                        ml_decision=ml_decision.decision.value,
                    )
                )
                self.audit.log(
                    "risk_rejected",
                    "Risk rejected strategy signal",
                    context={
                        "symbol": signal.symbol,
                        "timeframe": signal.timeframe,
                        "reason": risk_decision.reason,
                        "ml_probability": ml_decision.probability,
                        "ml_decision": ml_decision.decision.value,
                    },
                )
                if risk_decision.reason == "Kill switch is active":
                    self.audit.log(
                        "kill_switch_active",
                        "Kill switch blocked backtest signal",
                        context={"symbol": signal.symbol, "timeframe": signal.timeframe},
                    )
                continue
            risk_decision = self._apply_ml_risk_multiplier(risk_decision, ml_decision)

            pending = PendingOrder(
                signal=signal,
                created_at=signal.generated_at,
                risk_decision=risk_decision,
                ml_probability=ml_decision.probability,
                ml_decision=ml_decision.decision.value,
            )
            self.risk.reserve_trade(signal.generated_at.date())
            self.audit.log(
                "paper_trade_opened",
                "Backtest simulated pending order created",
                context={
                    "symbol": signal.symbol,
                    "timeframe": signal.timeframe,
                    "direction": signal.direction.value,
                    "position_size": risk_decision.position_size,
                    "risk_amount": risk_decision.risk_amount,
                    "ml_probability": ml_decision.probability,
                    "ml_decision": ml_decision.decision.value,
                },
            )

        if open_position is not None and ordered:
            final_trade = self._close_at_end(open_position, ordered[-1], trade_id=trade_id)
            trades.append(final_trade)
            equity += final_trade.realized_pnl
            self.risk.release_trade(realized_pnl=final_trade.realized_pnl, day=final_trade.exit_time.date())
            self._log_closed_trade(final_trade, "Backtest simulated trade closed at end of data")
            peak_equity = max(peak_equity, equity)
            equity_curve.append(
                EquityPoint(
                    timestamp=ordered[-1].close_time or ordered[-1].open_time,
                    equity=equity,
                    realized_pnl=equity - self.config.initial_balance,
                    drawdown=peak_equity - equity,
                )
            )

        metrics = calculate_metrics(trades, equity_curve, initial_balance=self.config.initial_balance)
        result = BacktestResult(
            trades=trades,
            equity_curve=equity_curve,
            rejected_signals=rejected,
            metrics=metrics,
        )
        if self.config.export_dir is not None:
            paths = export_backtest_result(result, self.config.export_dir)
            result = BacktestResult(
                trades=result.trades,
                equity_curve=result.equity_curve,
                rejected_signals=result.rejected_signals,
                metrics=result.metrics,
                export_paths=paths,
            )
        self.audit.log(
            "bot_stopped",
            "Backtest stopped",
            context={
                "mode": "backtest",
                "total_trades": len(result.trades),
                "rejected_signals": len(result.rejected_signals),
                "net_profit": result.metrics.get("net_profit", 0.0),
            },
        )
        return result

    def _window_start(self, index: int) -> int:
        window = self.config.strategy_window
        return 0 if window is None else max(0, index + 1 - window)

    def _try_fill(self, pending: PendingOrder, candle: Candle) -> OpenPosition | None:
        signal = pending.signal
        if signal.entry_price is None or signal.stop_loss is None or signal.take_profit is None:
            return None
        if candle.low > signal.entry_price or candle.high < signal.entry_price:
            return None

        direction = signal.direction
        entry_price = costs.entry_price(signal.entry_price, direction, **self._cost_bps())
        position_size = pending.risk_decision.position_size
        entry_fee = costs.fee(entry_price, position_size, self.config.maker_fee)
        risk_amount = abs(entry_price - signal.stop_loss) * position_size
        return OpenPosition(
            signal=signal,
            direction=direction,
            entry_time=candle.open_time,
            entry_price=entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            quantity=position_size,
            entry_fee=entry_fee,
            remaining_quantity=position_size,
            risk_amount=risk_amount,
            ml_probability=pending.ml_probability,
            ml_decision=pending.ml_decision,
        )

    def _update_open_position(
        self,
        position: OpenPosition,
        candle: Candle,
        *,
        trade_id: int,
    ) -> TradeRecord | None:
        self._update_excursions(position, candle)
        if self.config.enable_partial_tp and not position.partial_taken:
            self._maybe_take_partial(position, candle)

        if position.direction == SignalDirection.LONG:
            stop_hit = candle.low <= position.stop_loss
            target_hit = candle.high >= position.take_profit
        else:
            stop_hit = candle.high >= position.stop_loss
            target_hit = candle.low <= position.take_profit

        if stop_hit:
            return self._close_position(
                position,
                candle,
                trade_id=trade_id,
                exit_price=position.stop_loss,
                exit_reason=(
                    ExitReason.BREAKEVEN_STOP
                    if position.stop_loss == position.entry_price and position.partial_taken
                    else ExitReason.STOP_LOSS
                ),
            )
        if target_hit:
            return self._close_position(
                position,
                candle,
                trade_id=trade_id,
                exit_price=position.take_profit,
                exit_reason=ExitReason.TAKE_PROFIT,
            )
        return None

    def _maybe_take_partial(self, position: OpenPosition, candle: Candle) -> None:
        risk_per_unit = abs(position.entry_price - position.signal.stop_loss)
        if risk_per_unit <= 0:
            return
        if position.direction == SignalDirection.LONG:
            partial_price = position.entry_price + risk_per_unit * self.config.partial_tp_r
            reached = candle.high >= partial_price
        else:
            partial_price = position.entry_price - risk_per_unit * self.config.partial_tp_r
            reached = candle.low <= partial_price
        if not reached:
            return

        partial_quantity = position.quantity * self.config.partial_tp_fraction
        exit_price = costs.market_exit_price(partial_price, position.direction, **self._cost_bps())
        gross = self._gross_pnl(
            direction=position.direction,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=partial_quantity,
        )
        fee = costs.fee(exit_price, partial_quantity, self.config.taker_fee)
        position.partial_realized_pnl += gross - fee
        position.partial_fees += fee
        position.remaining_quantity -= partial_quantity
        position.partial_taken = True
        if self.config.move_stop_to_breakeven_after_partial:
            position.stop_loss = position.entry_price

    def _close_position(
        self,
        position: OpenPosition,
        candle: Candle,
        *,
        trade_id: int,
        exit_price: float,
        exit_reason: ExitReason,
    ) -> TradeRecord:
        adjusted_exit = costs.market_exit_price(exit_price, position.direction, **self._cost_bps())
        gross = self._gross_pnl(
            direction=position.direction,
            entry_price=position.entry_price,
            exit_price=adjusted_exit,
            quantity=position.remaining_quantity,
        )
        exit_fee = costs.fee(adjusted_exit, position.remaining_quantity, self.config.taker_fee)
        total_fees = position.entry_fee + position.partial_fees + exit_fee
        realized_pnl = position.partial_realized_pnl + gross - position.entry_fee - exit_fee
        realized_r = realized_pnl / position.risk_amount if position.risk_amount else 0.0
        return TradeRecord(
            trade_id=trade_id,
            symbol=position.signal.symbol,
            timeframe=position.signal.timeframe,
            session_name=position.signal.session_name or "unknown",
            direction=position.direction.value,
            entry_time=position.entry_time,
            exit_time=candle.open_time,
            entry_price=position.entry_price,
            exit_price=adjusted_exit,
            stop_loss=position.signal.stop_loss or position.stop_loss,
            take_profit=position.take_profit,
            position_size=position.quantity,
            risk_amount=position.risk_amount,
            realized_pnl=realized_pnl,
            realized_r=realized_r,
            fees=total_fees,
            slippage=costs.slippage_value(position.entry_price, self.config.slippage_bps)
            + costs.slippage_value(exit_price, self.config.slippage_bps),
            max_favorable_excursion=position.max_favorable_excursion,
            max_adverse_excursion=position.max_adverse_excursion,
            exit_reason=exit_reason,
            setup_quality_score=position.signal.setup_quality_score,
            notes=position.signal.explanation,
            ml_probability=position.ml_probability,
            ml_decision=position.ml_decision,
        )

    def _close_at_end(self, position: OpenPosition, candle: Candle, *, trade_id: int) -> TradeRecord:
        return self._close_position(
            position,
            candle,
            trade_id=trade_id,
            exit_price=candle.close,
            exit_reason=ExitReason.END_OF_DATA,
        )

    def _update_excursions(self, position: OpenPosition, candle: Candle) -> None:
        if position.direction == SignalDirection.LONG:
            favorable = candle.high - position.entry_price
            adverse = position.entry_price - candle.low
        else:
            favorable = position.entry_price - candle.low
            adverse = candle.high - position.entry_price
        position.max_favorable_excursion = max(position.max_favorable_excursion, favorable)
        position.max_adverse_excursion = max(position.max_adverse_excursion, adverse)

    def _cost_bps(self) -> dict[str, float]:
        return {"spread_bps": self.config.spread_bps, "slippage_bps": self.config.slippage_bps}

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

    def _log_ml_decision(self, signal, ml_decision: MLFilterResult) -> None:
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

    def _log_closed_trade(self, trade: TradeRecord, message: str) -> None:
        self.audit.log(
            "paper_trade_closed",
            message,
            context={
                "trade_id": trade.trade_id,
                "symbol": trade.symbol,
                "exit_reason": trade.exit_reason.value,
                "realized_pnl": trade.realized_pnl,
                "realized_r": trade.realized_r,
                "ml_probability": trade.ml_probability,
                "ml_decision": trade.ml_decision,
            },
        )

    @staticmethod
    def _apply_ml_risk_multiplier(
        risk_decision,
        ml_decision: MLFilterResult,
    ):
        if ml_decision.decision != MLDecision.REDUCE_RISK:
            return risk_decision
        multiplier = min(1.0, max(0.0, ml_decision.risk_multiplier))
        return replace(
            risk_decision,
            position_size=risk_decision.position_size * multiplier,
            risk_amount=risk_decision.risk_amount * multiplier,
            leverage=risk_decision.leverage * multiplier,
            reason=f"{risk_decision.reason}; ML reduced risk",
        )

    @staticmethod
    def _gross_pnl(
        *,
        direction: SignalDirection,
        entry_price: float,
        exit_price: float,
        quantity: float,
    ) -> float:
        if direction == SignalDirection.LONG:
            return (exit_price - entry_price) * quantity
        return (entry_price - exit_price) * quantity
