"""Portfolio backtest for trend_ensemble: every symbol x lookback slice on one marked-to-market account
(spec sections 4 to 7).

Per 1m minute, in this fixed order:
1. New UTC day: close each symbol's daily bar from the minutes seen, record the closed day's EquityPoint,
   raise every open slice's stop to its channel midpoint, queue entries for flat slices that broke out.
2. Fill the queued entries at this minute's open: target notional, risk engine, gross cap, exchange rounding.
3. Funding due in (funded_until, this open] on open slices, priced at this open.
4. Stops on every open slice, including those opened this minute; a minute opening below a stop fills at
   its open.
5. Mark to market at this close; a fall of KILL_SWITCH_DRAWDOWN from peak flattens every slice and halts
   entries for the rest of the run.
6. Once, after the last minute: every open slice closes at that minute's close with costs.

Per-minute work is O(symbols): each symbol keeps its open slices' total quantity, cost, funding and highest
stop, refreshed only when a slice opens, closes, is funded or has its stop raised.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from silvr.backtest import costs
from silvr.backtest.metrics import calculate_metrics, day_r_t_stat
from silvr.backtest.models import BacktestConfig, EquityPoint, ExitReason, TradeRecord
from silvr.backtest.sim_kill_switch import SimulatedKillSwitch
from silvr.data.funding import FundingSchedule
from silvr.models import Candle, SignalDirection
from silvr.risk import RiskManagementEngine, RiskRequest
from silvr.strategy.trend import params
from silvr.strategy.trend.signals import DailyBar, annualized_vol, channel_mid, is_breakout, raise_stop
from silvr.strategy.trend.sizing import fit_gross_cap, round_to_exchange, target_notional

MinuteSource = Callable[[], Iterator[dict[str, Candle]]]

LONG = SignalDirection.LONG
_MINUTE = timedelta(minutes=1)
_MS = timedelta(milliseconds=1)
_FUNDING_LOOKAHEAD = timedelta(hours=9)  # beyond the 8h funding interval, so the next stamp falls inside


class TrendDataError(ValueError):
    """A symbol's 1m candles, funding schedule or warm-up history is missing; the run fails closed."""

    def __init__(self, symbol: str, minute: datetime | None, problem: str = "no 1m candle") -> None:
        where = f" at {minute.isoformat()} (month {minute:%Y-%m})" if minute is not None else ""
        super().__init__(f"{symbol}: {problem}{where}; the trend backtest does not run on partial data")
        self.symbol = symbol
        self.minute = minute


@dataclass(frozen=True)
class TrendRunResult:
    trades: list[TradeRecord]
    daily_equity: list[EquityPoint]
    metrics: dict[str, Any]
    kill_switch_tripped_at: datetime | None  # the drawdown kill switch
    rejections: Counter[str]
    simulated_kill_switch: dict[str, Any]  # SimulatedKillSwitch.report(): risk-limit trips and resets


@dataclass(slots=True)
class _Slice:
    symbol: str
    n: int
    qty: float
    entry_price: float  # cost-adjusted fill
    entry_time: datetime
    initial_stop: float
    stop: float
    risk_amount: float
    entry_fee: float
    entry_slippage: float
    funded_until: datetime
    funding: float = 0.0  # net paid; negative when received


class TrendPortfolioEngine:
    """Replay every symbol's 1m minutes through the trend slices, the risk engine and the kill switch."""

    def __init__(
        self,
        config: BacktestConfig,
        *,
        funding: Mapping[str, FundingSchedule],
        history: Mapping[str, Sequence[DailyBar]],
        k: float,
    ) -> None:
        if config.risk.profile != "trend":
            raise ValueError(f"the trend engine needs the 'trend' risk profile, got {config.risk.profile!r}")
        if not k > 0:
            raise ValueError("k must be positive")
        for symbol in params.SYMBOLS:
            if symbol not in funding:
                raise TrendDataError(symbol, None, "no funding schedule")
            if symbol not in history:
                raise TrendDataError(symbol, None, "no warm-up history")
        self.config = config
        self.funding = funding
        self.history = history
        self.k = k

    def run(self, minutes: Iterable[Mapping[str, Candle]]) -> TrendRunResult:
        with SimulatedKillSwitch() as kill_switch:
            risk = RiskManagementEngine(self.config.risk, kill_switch=kill_switch)
            return _Run(self, risk, kill_switch).run(minutes)


class _Run:
    """The state of one run: the book, the account and the outputs."""

    def __init__(
        self, engine: TrendPortfolioEngine, risk: RiskManagementEngine, kill_switch: SimulatedKillSwitch
    ) -> None:
        self.engine = engine
        self.config = engine.config
        self.risk = risk
        self.kill_switch = kill_switch
        self.bps = {"spread_bps": self.config.spread_bps, "slippage_bps": self.config.slippage_bps}
        self.symbols = params.SYMBOLS
        self.lookbacks = params.LOOKBACKS
        self.closes = {s: [bar.close for bar in engine.history[s]] for s in self.symbols}
        self.book: dict[str, dict[int, _Slice]] = {s: {} for s in self.symbols}
        self.qty = dict.fromkeys(self.symbols, 0.0)
        self.cost = dict.fromkeys(self.symbols, 0.0)  # sum of qty x entry price
        self.fund = dict.fromkeys(self.symbols, 0.0)  # funding paid by open slices
        self.top_stop = dict.fromkeys(self.symbols, -math.inf)
        self.next_funding: dict[str, datetime] = {}
        # cash = initial + realized PnL of closed slices - entry fees of open slices
        self.cash = self.equity = self.peak = self.config.initial_balance
        self.trades: list[TradeRecord] = []
        self.curve: list[EquityPoint] = []
        self.rejections: Counter[str] = Counter()
        self.tripped_at: datetime | None = None

    def run(self, minutes: Iterable[Mapping[str, Candle]]) -> TrendRunResult:
        last: datetime | None = None
        previous: Mapping[str, Candle] = {}
        funding_from = datetime.min
        day_drawdown = 0.0
        for minute in minutes:
            now = self._check_minute(minute, last)
            self.kill_switch.now = now
            queued: list[tuple[str, int, float, float]] = []
            if last is None:
                self._check_history(now)
                funding_from = now
                self.next_funding = dict.fromkeys(self.symbols, now)
            elif now.date() != last.date():
                # 1. Day boundary. A run starting mid-day closes a partial first bar; only its close feeds
                # signals, and that is the true close of the day, so nothing after this minute is used.
                self.kill_switch.reset_if_new_day(now)
                self._check_funding(funding_from, now)
                funding_from = now
                for symbol in self.symbols:
                    self.closes[symbol].append(previous[symbol].close)
                self._point(last, day_drawdown)
                day_drawdown = 0.0
                queued = self._signals()
            if queued:
                self._enter(queued, minute, now)  # 2.
            for symbol in self.symbols:
                candle = minute[symbol]
                if now >= self.next_funding[symbol]:
                    self._fund(symbol, candle, now)  # 3.
                if candle.low <= self.top_stop[symbol]:
                    self._stops(symbol, candle, now)  # 4.
            # 5.
            marks = (self.qty[s] * minute[s].close - self.cost[s] - self.fund[s] for s in self.symbols)
            self.equity = self.cash + sum(marks)
            self.peak = max(self.peak, self.equity)
            if self.tripped_at is None and self.peak - self.equity >= params.KILL_SWITCH_DRAWDOWN:
                self._close_all(minute, now, ExitReason.KILL_SWITCH)
                self.tripped_at = now
            day_drawdown = max(day_drawdown, self.peak - self.equity)
            previous, last = minute, now
        if last is None:
            raise ValueError("no 1m minutes to simulate")
        self._check_funding(funding_from, last)
        self._close_all(previous, last, ExitReason.END_OF_DATA)  # 6.
        self.peak = max(self.peak, self.equity)
        self._point(last, max(day_drawdown, self.peak - self.equity))

        metrics = calculate_metrics(self.trades, self.curve, initial_balance=self.config.initial_balance)
        metrics["trade_r_t_stat"] = metrics["r_t_stat"]
        metrics["day_r_t_stat"] = day_r_t_stat(self.trades)
        metrics["r_t_stat"] = min(metrics["trade_r_t_stat"], metrics["day_r_t_stat"])
        # Called inside TrendPortfolioEngine.run's with-block, so the switch is still open to report.
        report = self.kill_switch.report()
        return TrendRunResult(self.trades, self.curve, metrics, self.tripped_at, self.rejections, report)

    def _check_minute(self, minute: Mapping[str, Candle], last: datetime | None) -> datetime:
        """The minute's open time; every symbol must have a candle at it, one minute after the last."""

        first = minute.get(self.symbols[0])
        now = last + _MINUTE if last is not None else (first.open_time if first is not None else None)
        for symbol in self.symbols:
            candle = minute.get(symbol)
            if candle is None or candle.open_time != now:
                raise TrendDataError(symbol, now)
        assert now is not None
        return now

    def _check_history(self, first: datetime) -> None:
        """Non-empty warm-up must be consecutive days ending the day before the run; a gap shifts every window."""

        day_before = first.date() - timedelta(days=1)
        for symbol in self.symbols:
            days = [bar.day for bar in self.engine.history[symbol]]
            if days and days[-1] != day_before:
                raise TrendDataError(symbol, None, f"warm-up history ends {days[-1]}, not {day_before}")
            for earlier, later in zip(days, days[1:]):
                if later - earlier != timedelta(days=1):
                    raise TrendDataError(symbol, None, f"warm-up history gap between {earlier} and {later}")

    def _check_funding(self, start: datetime, end: datetime) -> None:
        """Fail closed on a funding gap; checked day by day, which covers the same chain as the whole span."""

        for symbol in self.symbols:
            self.engine.funding[symbol].check_coverage(start, end)

    def _signals(self) -> list[tuple[str, int, float, float]]:
        """Raise open stops and return (symbol, n, vol, stop) for each flat slice to enter."""

        queued = []
        for symbol in self.symbols:
            closes = self.closes[symbol]
            vol = annualized_vol(closes)
            slices = self.book[symbol]
            for n in self.lookbacks:
                if n in slices:
                    slices[n].stop = raise_stop(slices[n].stop, channel_mid(closes, n))
                elif len(closes) < n + 1:
                    self.rejections["lookback warm-up"] += 1
                elif not is_breakout(closes, n):
                    self.rejections["no breakout"] += 1
                elif self.tripped_at is not None:
                    self.rejections["kill switch"] += 1
                elif vol is None or vol <= 0:
                    self.rejections["volatility warm-up"] += 1
                else:
                    queued.append((symbol, n, vol, channel_mid(closes, n)))
            self._refresh(symbol)
        return queued

    def _enter(self, queued: list[tuple[str, int, float, float]], minute: Mapping[str, Candle], now: datetime) -> None:
        day = now.date()
        equity = self.equity  # marked at the previous minute's close, the latest known
        approved: dict[str, tuple[str, int, float, float]] = {}
        notional: dict[str, float] = {}
        for symbol, n, vol, stop in queued:
            fill = costs.entry_price(minute[symbol].open, LONG, **self.bps)
            target = target_notional(equity=equity, vol=vol, k=self.engine.k)
            decision = self.risk.evaluate(
                RiskRequest(
                    equity=equity,
                    entry_price=fill,
                    stop_loss=stop,
                    take_profit=None,
                    direction=LONG.value,
                    signal_day=day,
                    requested_size=target / fill,
                )
            )
            if not decision.approved:
                self.rejections[decision.reason] += 1
                continue
            slice_id = f"{symbol}:{n}"
            approved[slice_id] = (symbol, n, stop, fill)
            notional[slice_id] = decision.position_size * fill
        open_notional = sum(self.qty[s] * minute[s].open for s in self.symbols)
        for slice_id, capped in fit_gross_cap(notional, open_notional=open_notional, equity=equity).items():
            symbol, n, stop, fill = approved[slice_id]
            if capped <= 0:  # no room left under the gross cap
                self.rejections["gross cap"] += 1
                continue
            qty = round_to_exchange(symbol, capped / fill, fill)
            if qty == 0:
                self.rejections["below exchange minimum"] += 1
                continue
            fee = costs.fee(fill, qty, self.config.taker_fee)
            self.cash -= fee
            self.book[symbol][n] = _Slice(
                symbol=symbol,
                n=n,
                qty=qty,
                entry_price=fill,
                entry_time=now,
                initial_stop=stop,
                stop=stop,
                risk_amount=qty * (fill - stop),
                entry_fee=fee,
                entry_slippage=costs.slippage_value(minute[symbol].open, self.config.slippage_bps),
                funded_until=now - _MS,  # a funding stamp falling exactly at the fill instant is charged
            )
            # The trend profile's 135 trades/positions per day cannot bind: at most 15 x 9 slices exist.
            self.risk.reserve_trade(day)
        for symbol in {item[0] for item in approved.values()}:
            self._refresh(symbol)

    def _fund(self, symbol: str, candle: Candle, now: datetime) -> None:
        schedule = self.engine.funding[symbol]
        for position in self.book[symbol].values():
            for rate in schedule.due(position.funded_until, now):
                position.funding += position.qty * candle.open * rate.rate  # a long pays a positive rate
            position.funded_until = now
        upcoming = schedule.due(now, now + _FUNDING_LOOKAHEAD)
        self.next_funding[symbol] = upcoming[0].time if upcoming else now + _FUNDING_LOOKAHEAD
        self._refresh(symbol)

    def _stops(self, symbol: str, candle: Candle, now: datetime) -> None:
        for position in list(self.book[symbol].values()):
            if candle.low <= position.stop:
                # A minute opening below the stop fills at its open, never at a price that did not trade.
                self._close(position, min(position.stop, candle.open), now, ExitReason.STOP_LOSS)
        self._refresh(symbol)

    def _close_all(self, minute: Mapping[str, Candle], now: datetime, reason: ExitReason) -> None:
        for symbol in self.symbols:
            for position in list(self.book[symbol].values()):
                self._close(position, minute[symbol].close, now, reason)
            self._refresh(symbol)
        self.equity = self.cash  # nothing is open

    def _close(self, position: _Slice, raw: float, now: datetime, reason: ExitReason) -> None:
        price = costs.market_exit_price(raw, LONG, **self.bps)
        exit_fee = costs.fee(price, position.qty, self.config.taker_fee)
        gross = position.qty * (price - position.entry_price)
        pnl = gross - position.entry_fee - exit_fee - position.funding
        self.cash += gross - exit_fee - position.funding  # the entry fee left cash at entry
        del self.book[position.symbol][position.n]
        self.trades.append(
            TradeRecord(
                trade_id=len(self.trades) + 1,
                symbol=position.symbol,
                timeframe="1d",
                session_name="trend",
                direction=LONG.value,
                entry_time=position.entry_time,
                exit_time=now,
                entry_price=position.entry_price,
                exit_price=price,
                stop_loss=position.initial_stop,
                take_profit=0.0,
                position_size=position.qty,
                risk_amount=position.risk_amount,
                realized_pnl=pnl,
                realized_r=pnl / position.risk_amount,
                fees=position.entry_fee + exit_fee,
                slippage=position.entry_slippage + costs.slippage_value(raw, self.config.slippage_bps),
                # shortcut: excursions are not tracked (per-slice per-minute work); add if a report needs them.
                max_favorable_excursion=0.0,
                max_adverse_excursion=0.0,
                exit_reason=reason,
                setup_quality_score=0,
                notes=f"{position.symbol} n={position.n}",
                funding=position.funding,
            )
        )
        self.risk.release_trade(realized_pnl=pnl, day=now.date())

    def _refresh(self, symbol: str) -> None:
        slices = self.book[symbol].values()
        self.qty[symbol] = sum(s.qty for s in slices)
        self.cost[symbol] = sum(s.qty * s.entry_price for s in slices)
        self.fund[symbol] = sum(s.funding for s in slices)
        self.top_stop[symbol] = max((s.stop for s in slices), default=-math.inf)

    def _point(self, last: datetime, drawdown: float) -> None:
        """The daily EquityPoint, stamped at the close of the day's last minute."""

        initial = self.config.initial_balance
        self.curve.append(EquityPoint(last + _MINUTE - _MS, self.equity, self.cash - initial, drawdown))
