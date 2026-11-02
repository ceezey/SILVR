"""Backtest engine for the top-down OB strategy: staged exits, breakeven and funding on 1m candles
(spec 3.4.3, 3.4.7, 3.4.8, 3.5, 3.6; TD-9, TD-19, TD-23, TD-24).

Per 1m candle, in time order: the simulated kill-switch daily reset; funding due in (previous open,
this open], priced at this open, while a position is open (the run fails closed at start if the
funding history has a gap anywhere in the candle span); strategy.step(); stage 1 on a 15m close in the
trade's direction after entry; the stop, then stage 2 and stage 3 on this candle's range; a new plan
at this candle's close; one realized-only equity point.

Stage 1 price: the 15m candle behind an event is emitted by the resampler when the first 1m candle
of a later period arrives, and its close is the close of the last 1m candle of its period, which is
the previous 1m candle the engine saw. So the previous 1m close is the 15m close, gaps included.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from silver_bot.backtest import costs
from silver_bot.backtest.metrics import calculate_metrics
from silver_bot.backtest.models import (
    BacktestConfig,
    BacktestResult,
    EquityPoint,
    ExitReason,
    RejectedSignalRecord,
    TradeRecord,
)
from silver_bot.backtest.reporting import export_backtest_result
from silver_bot.backtest.sim_kill_switch import SimulatedKillSwitch
from silver_bot.data.funding import FundingSchedule
from silver_bot.models import Candle, SignalDirection
from silver_bot.monitoring import StructuredAuditLogger
from silver_bot.risk import RiskManagementEngine, RiskRequest
from silver_bot.strategy.top_down import EntryPlan, TopDownOBStrategy

STAGE1_FRACTION = 0.2
STAGE2_FRACTION = 0.3  # stage 3 closes whatever remains (TD-9)
MIN_REWARD_R = 3.0  # spec 3.4.6, held on the cost-adjusted entry (3.4.3)
_MS = timedelta(milliseconds=1)


@dataclass(slots=True)
class _Position:
    plan: EntryPlan
    symbol: str
    direction: SignalDirection
    entry_price: float  # cost-adjusted
    quantity: float
    risk_amount: float
    stop: float
    remaining: float
    fees: float
    slippage: float
    funded_until: datetime
    gross: float = 0.0
    funding: float = 0.0
    stage1: bool = False
    stage2: bool = False
    fills: list[str] = field(default_factory=list)
    mfe: float = 0.0
    mae: float = 0.0

    @property
    def long(self) -> bool:
        return self.direction == SignalDirection.LONG


class TopDownBacktestEngine:
    """Replay 1m candles through TopDownOBStrategy with the risk engine on every entry."""

    def __init__(
        self,
        *,
        config: BacktestConfig,
        risk_engine: RiskManagementEngine,
        funding: FundingSchedule,
        strategy: TopDownOBStrategy | None = None,
    ) -> None:
        self.config = config
        self.risk = risk_engine
        self.funding = funding
        self.strategy = strategy or TopDownOBStrategy()
        self.audit = StructuredAuditLogger(retain_events=False)
        self._bps = {"spread_bps": config.spread_bps, "slippage_bps": config.slippage_bps}

    def run(self, candles: Sequence[Candle], *, warmup: Sequence[Candle] = ()) -> BacktestResult:
        ordered = sorted(candles, key=lambda candle: candle.open_time)
        if ordered and warmup and max(candle.open_time for candle in warmup) >= ordered[0].open_time:
            raise ValueError("warm-up candles must all open before the first trading candle")
        if ordered:
            self.funding.check_coverage(ordered[0].open_time, ordered[-1].open_time)  # fail closed (spec 3.6)
        for candle in sorted(warmup, key=lambda candle: candle.open_time):
            self.strategy.step(candle, trading=False)

        equity = peak = self.config.initial_balance
        trades: list[TradeRecord] = []
        curve: list[EquityPoint] = []
        rejected: list[RejectedSignalRecord] = []
        position: _Position | None = None
        previous_close = 0.0  # set by the first candle, before any position can be open
        self.audit.log("bot_started", "Top-down backtest started", context={"candles": len(ordered)})

        for candle in ordered:
            kill_switch = self.risk.kill_switch
            if isinstance(kill_switch, SimulatedKillSwitch):
                # Backtest-only: a simulated trip clears at the first candle of a new UTC day.
                kill_switch.now = candle.open_time
                if kill_switch.reset_if_new_day(candle.open_time):
                    self.risk.state.consecutive_losses = 0

            if position is not None:
                sign = 1.0 if position.long else -1.0  # a long pays a positive rate, a short receives it
                for rate in self.funding.due(position.funded_until, candle.open_time):
                    position.funding += sign * position.remaining * candle.open * rate.rate
                position.funded_until = candle.open_time

            step = self.strategy.step(candle)

            if position is not None and not position.stage1:
                wanted = "bullish" if position.long else "bearish"
                event = next(
                    (e for e in step.events_15m if e.direction == wanted and e.time > position.plan.signal_time),
                    None,
                )
                if event is not None:
                    price = costs.market_exit_price(previous_close, position.direction, **self._bps)
                    qty = position.quantity * STAGE1_FRACTION
                    self._fill(position, qty, price, self.config.taker_fee, "s1", event.time + _MS)
                    position.slippage += costs.slippage_value(previous_close, self.config.slippage_bps)
                    position.stage1 = True
                    position.stop = position.entry_price  # breakeven (TD-19)

            if position is not None and (close := self._manage(position, candle)) is not None:
                trades.append(self._close(position, len(trades) + 1, candle, *close))
                equity += trades[-1].realized_pnl
                position = None

            if step.skipped is not None:
                self._reject(rejected, candle.close_time or candle.open_time, candle.symbol, step.skipped)
            if step.entry is not None:
                if position is not None:
                    self._reject(rejected, step.entry.signal_time, candle.symbol, "position already open")
                else:
                    position = self._open(step.entry, candle, equity, rejected)
                    # TD-39: a limit fills during this candle, whose range may already reach the stop. No target credit.
                    if position is not None and step.entry.limit:
                        position.mae = position.entry_price - candle.low if position.long else candle.high - position.entry_price
                        if (close := self._stop_hit(position, candle)) is not None:
                            trades.append(self._close(position, len(trades) + 1, candle, *close))
                            equity += trades[-1].realized_pnl
                            position = None

            previous_close = candle.close
            peak = max(peak, equity)
            curve.append(self._point(candle, equity, peak))

        if position is not None:
            last = ordered[-1]
            exit_price = costs.market_exit_price(last.close, position.direction, **self._bps)
            position.slippage += costs.slippage_value(last.close, self.config.slippage_bps)
            eod = (exit_price, ExitReason.END_OF_DATA, self.config.taker_fee, "eod")
            trades.append(self._close(position, len(trades) + 1, last, *eod))
            equity += trades[-1].realized_pnl
            peak = max(peak, equity)
            curve.append(self._point(last, equity, peak))

        result = BacktestResult(
            trades=trades,
            equity_curve=curve,
            rejected_signals=rejected,
            metrics=calculate_metrics(trades, curve, initial_balance=self.config.initial_balance),
        )
        if self.config.export_dir is not None:
            paths = export_backtest_result(result, self.config.export_dir)
            result = BacktestResult(trades, curve, rejected, result.metrics, export_paths=paths)
        self.audit.log(
            "bot_stopped",
            "Top-down backtest stopped",
            context={"mode": "backtest", "total_trades": len(trades), "rejected_signals": len(rejected)},
        )
        return result

    def _manage(self, position: _Position, candle: Candle) -> tuple[float, ExitReason, float, str] | None:
        """Stop first (market, at the worse of the stop and the open), then stage 2 and stage 3 as maker
        limit fills at their level.

        Returns the final fill (price, reason, fee rate, label) when the position closes on this candle.
        """
        long, entry = position.long, position.entry_price
        position.mfe = max(position.mfe, candle.high - entry if long else entry - candle.low)
        position.mae = max(position.mae, entry - candle.low if long else candle.high - entry)

        if (stopped := self._stop_hit(position, candle)) is not None:
            return stopped

        def reached(level: float) -> bool:
            return candle.high >= level if long else candle.low <= level

        stage2 = position.plan.stage2
        if stage2 is not None and not position.stage2 and reached(stage2):
            qty = position.quantity * STAGE2_FRACTION
            self._fill(position, qty, stage2, self.config.maker_fee, "s2", candle.open_time)
            position.stage2 = True
        if reached(position.plan.final_target):
            return position.plan.final_target, ExitReason.TAKE_PROFIT, self.config.maker_fee, "s3"
        return None

    def _stop_hit(self, position: _Position, candle: Candle) -> tuple[float, ExitReason, float, str] | None:
        if (candle.low <= position.stop) if position.long else (candle.high >= position.stop):
            # A candle opening beyond the stop fills at its open, never at a price that did not trade.
            raw = min(position.stop, candle.open) if position.long else max(position.stop, candle.open)
            price = costs.market_exit_price(raw, position.direction, **self._bps)
            position.slippage += costs.slippage_value(raw, self.config.slippage_bps)
            reason = ExitReason.BREAKEVEN_STOP if position.stage1 else ExitReason.STOP_LOSS
            return price, reason, self.config.taker_fee, "stop"
        return None

    def _open(self, plan: EntryPlan, candle: Candle, equity: float, rejected: list) -> _Position | None:
        if plan.side not in ("long", "short"):
            raise ValueError(f"unknown plan side {plan.side!r}")
        direction = SignalDirection.LONG if plan.side == "long" else SignalDirection.SHORT
        entry = plan.raw_entry if plan.limit else costs.entry_price(plan.raw_entry, direction, **self._bps)
        long = direction == SignalDirection.LONG
        reward = plan.final_target - entry if long else entry - plan.final_target
        risk = entry - plan.stop if long else plan.stop - entry
        if reward < MIN_REWARD_R * risk:  # the strategy's 3R filter used the raw close
            self._reject(rejected, plan.signal_time, candle.symbol, "reward below 3R after entry costs")
            return None
        decision = self.risk.evaluate(
            RiskRequest(
                equity=equity,
                entry_price=entry,
                stop_loss=plan.stop,
                take_profit=plan.final_target,
                direction=direction.value,
                signal_day=plan.signal_time.date(),
            )
        )
        if not decision.approved:
            self._reject(rejected, plan.signal_time, candle.symbol, f"Risk rejected: {decision.reason}")
            if decision.reason == "Kill switch is active":
                self.audit.log("kill_switch_active", "Kill switch blocked backtest signal", context={})
            return None
        self.risk.reserve_trade(plan.signal_time.date())
        qty = decision.position_size
        self.audit.log(
            "paper_trade_opened",
            "Top-down backtest position opened",
            context={"direction": direction.value, "position_size": qty, "risk_amount": decision.risk_amount,
                     "reason": plan.reason},
        )
        return _Position(
            plan=plan,
            symbol=candle.symbol,
            direction=direction,
            entry_price=entry,
            quantity=qty,
            risk_amount=decision.risk_amount,
            stop=plan.stop,
            remaining=qty,
            # TD-24: market entries pay taker; TD-39: a limit entry is priced like the stage 2 and 3 limit fills
            fees=costs.fee(entry, qty, self.config.maker_fee if plan.limit else self.config.taker_fee),
            slippage=0.0 if plan.limit else costs.slippage_value(plan.raw_entry, self.config.slippage_bps),
            # 1m candles are minute-aligned and stamps have ms offsets, so this charges every stamp at or after
            # the entry instant (the signal candle's close) and none before it.
            funded_until=plan.signal_time - _MS,
        )

    @staticmethod
    def _fill(position: _Position, qty: float, price: float, fee_rate: float, label: str, at: datetime) -> None:
        move = price - position.entry_price if position.long else position.entry_price - price
        position.gross += move * qty
        position.fees += costs.fee(price, qty, fee_rate)
        position.remaining -= qty
        position.fills.append(f"{label} {at:%Y-%m-%dT%H:%MZ}@{price}")

    def _close(self, position: _Position, trade_id: int, candle: Candle, exit_price: float, reason: ExitReason,
               fee_rate: float, label: str) -> TradeRecord:
        """Fill the remaining quantity, release the risk reservation with the whole trade's PnL."""
        self._fill(position, position.remaining, exit_price, fee_rate, label, candle.open_time)
        pnl = position.gross - position.fees - position.funding
        plan = position.plan
        trade = TradeRecord(
            trade_id=trade_id,
            symbol=position.symbol,
            timeframe="1m",
            session_name=plan.session_name,
            direction=position.direction.value,
            entry_time=plan.signal_time,
            exit_time=max(candle.open_time, plan.signal_time),  # a limit can stop out on its own fill candle
            entry_price=position.entry_price,
            exit_price=exit_price,
            stop_loss=plan.stop,
            take_profit=plan.final_target,
            position_size=position.quantity,
            risk_amount=position.risk_amount,
            realized_pnl=pnl,
            realized_r=pnl / position.risk_amount if position.risk_amount else 0.0,
            fees=position.fees,
            slippage=position.slippage,
            max_favorable_excursion=position.mfe,
            max_adverse_excursion=position.mae,
            exit_reason=reason,
            setup_quality_score=0,
            notes="; ".join(position.fills),
            funding=position.funding,
        )
        self.risk.release_trade(realized_pnl=pnl, day=candle.open_time.date())
        self.audit.log(
            "paper_trade_closed",
            "Top-down backtest trade closed",
            context={"trade_id": trade_id, "exit_reason": reason.value, "realized_pnl": pnl,
                     "realized_r": trade.realized_r, "funding": position.funding},
        )
        return trade

    def _reject(self, rejected: list[RejectedSignalRecord], at: datetime, symbol: str, reason: str) -> None:
        rejected.append(RejectedSignalRecord(timestamp=at, symbol=symbol, timeframe="1m", reason=reason))
        self.audit.log("signal_rejected", "Top-down signal rejected", context={"symbol": symbol, "reason": reason})

    def _point(self, candle: Candle, equity: float, peak: float) -> EquityPoint:
        initial = self.config.initial_balance
        return EquityPoint(candle.close_time or candle.open_time, equity, equity - initial, peak - equity)
