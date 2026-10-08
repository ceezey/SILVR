"""Paper-only execution engine."""

from __future__ import annotations

from silver_bot.backtest.models import ExitReason, TradeRecord
from silver_bot.execution.models import (
    PaperEventType,
    PaperExecutionConfig,
    PaperLifecycleEvent,
    PaperOrder,
    PaperPosition,
)
from silver_bot.execution.trade_management import BasicTradeManager
from silver_bot.models import Candle, SignalDirection
from silver_bot.risk import RiskDecision
from silver_bot.strategy import SilverBulletSignal


class PaperExecutionEngine:
    """Simulate order lifecycle without placing real exchange orders."""

    def __init__(
        self,
        *,
        config: PaperExecutionConfig | None = None,
        trade_manager: BasicTradeManager | None = None,
    ) -> None:
        self.config = config or PaperExecutionConfig()
        self.trade_manager = trade_manager or BasicTradeManager()
        self.pending_order: PaperOrder | None = None
        self.open_position: PaperPosition | None = None
        self._next_trade_id = 1

    @property
    def has_active_trade(self) -> bool:
        """Return whether a pending order or open paper position exists."""

        return self.pending_order is not None or self.open_position is not None

    def submit_limit_order(
        self,
        *,
        signal: SilverBulletSignal,
        risk_decision: RiskDecision,
        ml_probability: float | None = None,
        ml_decision: str | None = None,
    ) -> PaperLifecycleEvent:
        """Create a simulated pending limit order."""

        if not risk_decision.approved:
            raise ValueError("risk_decision must be approved before paper order submission")
        if signal.entry_price is None or signal.stop_loss is None or signal.take_profit is None:
            raise ValueError("paper order requires entry, stop loss, and take profit")
        self.pending_order = PaperOrder(
            signal=signal,
            risk_decision=risk_decision,
            created_at=signal.generated_at,
            ml_probability=ml_probability,
            ml_decision=ml_decision,
        )
        return PaperLifecycleEvent(
            event_type=PaperEventType.PAPER_ORDER_CREATED,
            symbol=signal.symbol,
            timestamp=signal.generated_at,
            message="Paper limit order created",
            context={
                "direction": signal.direction.value,
                "entry_price": signal.entry_price,
                "ml_probability": ml_probability,
                "ml_decision": ml_decision,
            },
        )

    def process_candle(self, candle: Candle) -> list[PaperLifecycleEvent]:
        """Advance simulated execution with one candle."""

        events: list[PaperLifecycleEvent] = []
        if self.open_position is not None:
            closed = self._maybe_close_position(candle)
            if closed is not None:
                self.open_position = None
                events.append(closed)
                return events

        if self.pending_order is not None and self.open_position is None:
            opened = self._try_open_position(candle)
            if opened is not None:
                self.open_position = opened
                self.pending_order = None
                signal = opened.order.signal
                events.append(
                    PaperLifecycleEvent(
                        event_type=PaperEventType.PAPER_TRADE_OPENED,
                        symbol=signal.symbol,
                        timestamp=candle.open_time,
                        message="Paper trade opened",
                        context={
                            "direction": signal.direction.value,
                            "entry_price": opened.entry_price,
                            "quantity": opened.quantity,
                        },
                    )
                )
                closed = self._maybe_close_position(candle)
                if closed is not None:
                    self.open_position = None
                    events.append(closed)
        return events

    def _try_open_position(self, candle: Candle) -> PaperPosition | None:
        assert self.pending_order is not None
        signal = self.pending_order.signal
        assert signal.entry_price is not None
        assert signal.stop_loss is not None
        assert signal.take_profit is not None
        if candle.low > signal.entry_price or candle.high < signal.entry_price:
            return None

        entry_price = self._apply_entry_cost(signal.entry_price, signal.direction)
        quantity = self.pending_order.risk_decision.position_size
        entry_fee = abs(entry_price * quantity * self.config.maker_fee)
        risk_amount = abs(entry_price - signal.stop_loss) * quantity
        return PaperPosition(
            order=self.pending_order,
            entry_time=candle.open_time,
            entry_price=entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            quantity=quantity,
            entry_fee=entry_fee,
            risk_amount=risk_amount,
        )

    def _maybe_close_position(self, candle: Candle) -> PaperLifecycleEvent | None:
        assert self.open_position is not None
        position = self.open_position
        signal = position.order.signal
        self._update_excursions(position, candle)
        reason = self.trade_manager.exit_reason(
            direction=signal.direction,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            candle=candle,
        )
        if reason is None:
            return None
        raw_exit = position.stop_loss if reason == ExitReason.STOP_LOSS else position.take_profit
        trade = self._close_position(position, candle, raw_exit=raw_exit, reason=reason)
        return PaperLifecycleEvent(
            event_type=PaperEventType.PAPER_TRADE_CLOSED,
            symbol=trade.symbol,
            timestamp=trade.exit_time,
            message="Paper trade closed",
            trade=trade,
            context={"exit_reason": reason.value, "realized_pnl": trade.realized_pnl},
        )

    def _close_position(
        self,
        position: PaperPosition,
        candle: Candle,
        *,
        raw_exit: float,
        reason: ExitReason,
    ) -> TradeRecord:
        signal = position.order.signal
        adjusted_exit = self._apply_exit_cost(raw_exit, signal.direction)
        gross = self._gross_pnl(
            direction=signal.direction,
            entry_price=position.entry_price,
            exit_price=adjusted_exit,
            quantity=position.quantity,
        )
        exit_fee = abs(adjusted_exit * position.quantity * self.config.taker_fee)
        fees = position.entry_fee + exit_fee
        realized_pnl = gross - fees
        realized_r = realized_pnl / position.risk_amount if position.risk_amount else 0.0
        trade = TradeRecord(
            trade_id=self._next_trade_id,
            symbol=signal.symbol,
            timeframe=signal.timeframe,
            session_name=signal.session_name or "unknown",
            direction=signal.direction.value,
            entry_time=position.entry_time,
            exit_time=candle.open_time,
            entry_price=position.entry_price,
            exit_price=adjusted_exit,
            stop_loss=signal.stop_loss or position.stop_loss,
            take_profit=signal.take_profit or position.take_profit,
            position_size=position.quantity,
            risk_amount=position.risk_amount,
            realized_pnl=realized_pnl,
            realized_r=realized_r,
            fees=fees,
            slippage=self._slippage_value(position.entry_price) + self._slippage_value(raw_exit),
            max_favorable_excursion=position.max_favorable_excursion,
            max_adverse_excursion=position.max_adverse_excursion,
            exit_reason=reason,
            setup_quality_score=signal.setup_quality_score,
            notes=signal.explanation,
            ml_probability=position.order.ml_probability,
            ml_decision=position.order.ml_decision,
        )
        self._next_trade_id += 1
        return trade

    def _update_excursions(self, position: PaperPosition, candle: Candle) -> None:
        direction = position.order.signal.direction
        if direction == SignalDirection.LONG:
            favorable = candle.high - position.entry_price
            adverse = position.entry_price - candle.low
        else:
            favorable = position.entry_price - candle.low
            adverse = candle.high - position.entry_price
        position.max_favorable_excursion = max(position.max_favorable_excursion, favorable)
        position.max_adverse_excursion = max(position.max_adverse_excursion, adverse)

    def _apply_entry_cost(self, price: float, direction: SignalDirection) -> float:
        spread = self._half_spread_value(price)
        slippage = self._slippage_value(price)
        return price + spread + slippage if direction == SignalDirection.LONG else price - spread - slippage

    def _apply_exit_cost(self, price: float, direction: SignalDirection) -> float:
        spread = self._half_spread_value(price)
        slippage = self._slippage_value(price)
        return price - spread - slippage if direction == SignalDirection.LONG else price + spread + slippage

    def _half_spread_value(self, price: float) -> float:
        return price * (self.config.spread_bps / 10_000) / 2

    def _slippage_value(self, price: float) -> float:
        return price * self.config.slippage_bps / 10_000

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
