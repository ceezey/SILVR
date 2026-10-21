"""TopDownBacktestEngine: TDOB entries, staged exits, breakeven and funding (spec 3.4-3.6).

A scripted fake strategy returns prepared StepResults, so every number is a hand calculation.
Default costs: taker 0.0005, maker 0.0002, slippage 5 bps, spread 3 bps (half spread 1.5 bps), so a
market fill moves the price by 6.5 bps against the trade. Risk: 0.5% of 10_000 = 50 per trade.

The base long: raw entry 1000 -> 1000 + 0.15 + 0.5 = 1000.65; stop 990.65 (distance 10, qty 50 / 10 = 5);
final target 1040, stage 2 at 1020. Entry fee (taker) = 1000.65 * 5 * 0.0005 = 2.501625.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from silver_bot.backtest import BacktestConfig, ExitReason
from silver_bot.backtest.models import TradeRecord
from silver_bot.backtest.sim_kill_switch import SimulatedKillSwitch
from silver_bot.backtest.top_down_engine import TopDownBacktestEngine
from silver_bot.data.funding import FundingDataError, FundingRate, FundingSchedule
from silver_bot.models import Candle
from silver_bot.risk import RiskConfig, RiskManagementEngine
from silver_bot.strategy.top_down import EntryPlan, StepResult, StructureEvent

START = datetime(2024, 1, 2, 10, 0, tzinfo=UTC)
MS = timedelta(milliseconds=1)
ENTRY = 1000.65
ENTRY_FEE = 2.501625
# Stage 1 from a 15m close of 1010: 1010 - 1010 * 0.00065 = 1009.3435; 1 unit (20% of 5).
S1_GROSS = 1009.3435 - ENTRY  # 8.6935
S1_FEE = 1009.3435 * 1 * 0.0005  # 0.50467175


def bar(minute: int, o: float, h: float, low: float, c: float) -> Candle:
    opened = START + timedelta(minutes=minute)
    return Candle("BTCUSDT", "1m", opened, o, h, low, c, 1.0, close_time=opened + timedelta(minutes=1))


def plan(minute: int, *, side: str = "long", raw: float = 1000.0, stop: float = 990.65, final: float = 1040.0,
         stage2: float | None = 1020.0) -> EntryPlan:
    signal_time = START + timedelta(minutes=minute + 1)
    return EntryPlan(side, signal_time, raw, stop, final, stage2, "new_york_am", None, "test plan")


def bullish_15m_close(minute: int) -> StructureEvent:
    """The 15m candle ending at START + minute closes above its swing (time = period end - 1 ms)."""
    return StructureEvent("bos", "bullish", 1005.0, START + timedelta(minutes=minute) - MS)


def every_8h(first: datetime, count: int, rate: float = 0.0) -> list[FundingRate]:
    return [FundingRate(first + timedelta(hours=8 * k), rate) for k in range(count)]


ZERO_FUNDING = FundingSchedule(every_8h(datetime(2024, 1, 2, 8, 0, tzinfo=UTC), 3))


class FakeStrategy:
    def __init__(self, script: dict[int, StepResult]) -> None:
        self.script = script  # minute offset from START -> result
        self.calls: list[tuple[datetime, bool]] = []

    def step(self, candle: Candle, *, trading: bool = True) -> StepResult:
        self.calls.append((candle.open_time, trading))
        minute = int((candle.open_time - START) / timedelta(minutes=1))
        return self.script.get(minute, StepResult(None, None, ())) if trading else StepResult(None, None, ())


def engine(script: dict[int, StepResult], *, funding: FundingSchedule = ZERO_FUNDING,
           risk_engine: RiskManagementEngine | None = None) -> TopDownBacktestEngine:
    config = BacktestConfig()
    return TopDownBacktestEngine(
        config=config,
        risk_engine=risk_engine or RiskManagementEngine(config.risk),
        funding=funding,
        strategy=FakeStrategy(script),
    )


def enter(minute: int = 0, **kwargs) -> StepResult:
    return StepResult(plan(minute, **kwargs), None, ())


def drift(first: int, last: int) -> list[Candle]:
    """Quiet candles inside (stop, stage 2): low 995 > 990.65, high 1005 < 1020."""
    return [bar(m, 1000, 1005, 995, 1003) for m in range(first, last + 1)]


def path_to_stage1() -> list[Candle]:
    # 10:00 entry candle, quiet to 10:13, 10:14 closes at 1010 = the 15m candle's close.
    return [bar(0, 1000, 1001, 999, 1000), *drift(1, 13), bar(14, 1003, 1011, 1002, 1010)]


def only_trade(result) -> TradeRecord:
    assert len(result.trades) == 1
    return result.trades[0]


def test_entry_uses_taker_fee_and_entry_costs() -> None:
    warm = Candle("BTCUSDT", "1m", START - timedelta(minutes=1), 1000, 1000, 1000, 1000, 1.0, close_time=START)
    tdob = engine({0: enter()})
    result = tdob.run([bar(0, 1000, 1001, 999, 1000)], warmup=[warm])

    trade = only_trade(result)
    assert tdob.strategy.calls == [(warm.open_time, False), (START, True)]
    # Entry 1000.65, qty 5, risk 50; closed END_OF_DATA at the same close 1000 -> 1000 - 0.65 = 999.35.
    assert trade.entry_price == pytest.approx(ENTRY)
    assert trade.position_size == pytest.approx(5.0)
    assert trade.risk_amount == pytest.approx(50.0)
    assert trade.exit_price == pytest.approx(999.35)
    assert trade.exit_reason == ExitReason.END_OF_DATA
    # Taker on both sides: 2.501625 + 999.35 * 5 * 0.0005 (2.498375) = 5.0 (a maker entry would be 1.00065).
    assert trade.fees == pytest.approx(5.0)
    # Gross (999.35 - 1000.65) * 5 = -6.5; minus fees 5.0 -> -11.5; R = -0.23.
    assert trade.realized_pnl == pytest.approx(-11.5)
    assert trade.realized_r == pytest.approx(-0.23)
    assert (trade.entry_time, trade.stop_loss, trade.take_profit) == (START + timedelta(minutes=1), 990.65, 1040.0)
    assert (trade.timeframe, trade.session_name, trade.direction, trade.funding) == ("1m", "new_york_am", "LONG", 0.0)
    assert tdob.risk.state.open_positions == 0 and tdob.risk.state.trades_today == 1


def test_full_path_stage1_stage2_stage3() -> None:
    script = {
        0: enter(),
        # A 15m event closing 1 ms before the entry time is not "after entry": no stage 1 here.
        1: StepResult(None, None, (StructureEvent("bos", "bullish", 990.0, START + timedelta(minutes=1) - MS),)),
        15: StepResult(None, None, (bullish_15m_close(15),)),
    }
    candles = [
        *path_to_stage1(),
        bar(15, 1010, 1021, 1005, 1018),  # stage 1 at its open (from 1010), then stage 2 at 1020, low stays above BE
        bar(16, 1020, 1041, 1015, 1035),  # stage 3 at 1040
    ]
    result = engine(script).run(candles)

    trade = only_trade(result)
    # Stage 2: 1.5 units (30%) at 1020, maker: gross 19.35 * 1.5 = 29.025, fee 1020 * 1.5 * 0.0002 = 0.306.
    # Stage 3: the remaining 2.5 at 1040, maker: gross 39.35 * 2.5 = 98.375, fee 1040 * 2.5 * 0.0002 = 0.52.
    gross = S1_GROSS + 29.025 + 98.375  # 136.0935
    fees = ENTRY_FEE + S1_FEE + 0.306 + 0.52  # 3.83229675
    assert trade.exit_reason == ExitReason.TAKE_PROFIT
    assert trade.exit_price == 1040.0
    assert trade.fees == pytest.approx(fees)
    assert trade.realized_pnl == pytest.approx(gross - fees)  # 132.26120325
    assert trade.realized_r == pytest.approx(132.26120325 / 50)  # 2.645224065
    assert trade.notes.startswith("s1 2024-01-02T10:15Z@1009.343")
    assert "s2 2024-01-02T10:15Z@1020.0" in trade.notes and "s3 2024-01-02T10:16Z@1040.0" in trade.notes
    assert result.equity_curve[-1].equity == pytest.approx(10_000 + 132.26120325)


def test_stage2_missing_rolls_into_final() -> None:
    script = {0: enter(stage2=None), 15: StepResult(None, None, (bullish_15m_close(15),))}
    candles = [*path_to_stage1(), bar(15, 1010, 1021, 1005, 1018), bar(16, 1020, 1041, 1015, 1035)]
    trade = only_trade(engine(script).run(candles))

    # Stage 3 closes all 4 remaining units (50% + the skipped 30%) at 1040: gross 39.35 * 4 = 157.4,
    # fee 1040 * 4 * 0.0002 = 0.832.
    assert trade.exit_reason == ExitReason.TAKE_PROFIT
    assert trade.fees == pytest.approx(ENTRY_FEE + S1_FEE + 0.832)
    assert trade.realized_pnl == pytest.approx(S1_GROSS + 157.4 - (ENTRY_FEE + S1_FEE + 0.832))  # 162.25520325
    assert "s2" not in trade.notes


# Stop before stage 1: 5 units at 990.65 - 990.65 * 0.00065 = 990.0060775 (taker).
# Gross (990.0060775 - 1000.65) * 5 = -53.2196125; exit fee 990.0060775 * 5 * 0.0005 = 2.47501519375.
STOP_FEES = ENTRY_FEE + 2.47501519375  # 4.97664019375
STOP_PNL = -53.2196125 - STOP_FEES  # -58.19625269375


def test_stop_before_stage1_is_full_loss_with_taker_exit() -> None:
    tdob = engine({0: enter()})
    trade = only_trade(tdob.run([bar(0, 1000, 1001, 999, 1000), bar(1, 1000, 1001, 990, 992)]))

    assert trade.exit_reason == ExitReason.STOP_LOSS
    assert trade.exit_price == pytest.approx(990.0060775)
    assert trade.fees == pytest.approx(STOP_FEES)
    assert trade.realized_pnl == pytest.approx(STOP_PNL)
    assert trade.realized_r == pytest.approx(STOP_PNL / 50)  # -1.163925053875
    assert tdob.risk.state.consecutive_losses == 1 and tdob.risk.state.open_positions == 0


def test_breakeven_after_stage1() -> None:
    script = {0: enter(), 15: StepResult(None, None, (bullish_15m_close(15),))}
    candles = [*path_to_stage1(), bar(15, 1010, 1012, 1000, 1001)]  # back to entry after stage 1
    trade = only_trade(engine(script).run(candles))

    # The remaining 4 units exit at the entry 1000.65 as a market fill: 1000.65 - 0.6504225 = 999.9995775,
    # gross -0.6504225 * 4 = -2.60169, fee 999.9995775 * 4 * 0.0005 = 1.999999155.
    fees = ENTRY_FEE + S1_FEE + 1.999999155
    assert trade.exit_reason == ExitReason.BREAKEVEN_STOP
    assert trade.exit_price == pytest.approx(999.9995775)
    assert trade.realized_pnl == pytest.approx(S1_GROSS - 2.60169 - fees)  # 1.085514095


def test_stop_and_target_same_candle_takes_stop() -> None:
    # One candle reaches the stop 990.65, stage 2 (1020) and the final target (1040): the stop wins.
    trade = only_trade(engine({0: enter()}).run([bar(0, 1000, 1001, 999, 1000), bar(1, 1000, 1045, 985, 1030)]))

    assert trade.exit_reason == ExitReason.STOP_LOSS
    assert trade.realized_pnl == pytest.approx(STOP_PNL)
    assert "s2" not in trade.notes and "s3" not in trade.notes


def test_funding_long_pays_short_receives() -> None:
    # Funding at 16:00 with rate 0.0001; the position is open across it, priced at the 16:00 candle's open.
    funding = FundingSchedule([FundingRate(datetime(2024, 1, 2, 8, tzinfo=UTC), 0.0),
                               FundingRate(datetime(2024, 1, 2, 16, tzinfo=UTC), 0.0001),
                               FundingRate(datetime(2024, 1, 3, 0, tzinfo=UTC), 0.0)])
    long_run = engine({0: enter()}, funding=funding).run(
        [bar(0, 1000, 1001, 999, 1000), bar(360, 1010, 1012, 1005, 1010), bar(361, 1010, 1012, 1005, 1010)]
    )
    trade = only_trade(long_run)
    # Long pays 5 * 1010 * 0.0001 = 0.505. END_OF_DATA at 1010 -> 1009.3435: gross 8.6935 * 5 = 43.4675,
    # fees 2.501625 + 1009.3435 * 5 * 0.0005 (2.52335875) = 5.02498375.
    assert trade.funding == pytest.approx(0.505)
    assert trade.realized_pnl == pytest.approx(43.4675 - 5.02498375 - 0.505)  # 37.93751625
    assert long_run.metrics["total_funding"] == pytest.approx(0.505)

    # Short: raw 1000 -> 999.35, stop 1009.35 (qty 5), entry fee 999.35 * 5 * 0.0005 = 2.498375.
    short_plan = enter(side="short", stop=1009.35, final=960.0, stage2=None)
    short_run = engine({0: short_plan}, funding=funding).run(
        [bar(0, 1000, 1001, 999, 1000), bar(360, 990, 995, 989, 990), bar(361, 990, 995, 989, 990)]
    )
    trade = only_trade(short_run)
    # Short receives 5 * 990 * 0.0001 = 0.495. END_OF_DATA at 990 -> 990.6435: gross 8.7065 * 5 = 43.5325,
    # exit fee 990.6435 * 5 * 0.0005 = 2.47660875.
    assert trade.funding == pytest.approx(-0.495)
    assert trade.realized_pnl == pytest.approx(43.5325 - (2.498375 + 2.47660875) + 0.495)  # 39.05251625


def test_missing_funding_row_while_open_raises() -> None:
    # The 16:00 row is missing while the long is open from 10:01 to 16:01: never assume zero.
    funding = FundingSchedule([FundingRate(datetime(2024, 1, 2, 8, tzinfo=UTC), 0.0),
                               FundingRate(datetime(2024, 1, 3, 0, tzinfo=UTC), 0.0)])
    tdob = engine({0: enter()}, funding=funding)
    with pytest.raises(FundingDataError, match="funding gap"):
        tdob.run([bar(0, 1000, 1001, 999, 1000), bar(360, 1010, 1012, 1005, 1010), bar(361, 1010, 1012, 1005, 1010)])


def test_risk_rejection_recorded_and_no_trade() -> None:
    # Final 1010 is (1010 - 1000.65) / 10 = 0.935R, below the risk engine's 2R minimum.
    tdob = engine({0: enter(final=1010.0, stage2=None)})
    result = tdob.run([bar(0, 1000, 1001, 999, 1000), bar(1, 1000, 1001, 999, 1000)])

    assert result.trades == []
    assert [r.reason for r in result.rejected_signals] == ["Risk rejected: Reward-to-risk below configured minimum"]
    assert result.rejected_signals[0].timestamp == START + timedelta(minutes=1)
    assert tdob.risk.state.open_positions == 0 and tdob.risk.state.trades_today == 0


def test_plan_while_position_open_is_rejected() -> None:
    skipped = "reward 2.10R is below the 3R minimum"
    script = {0: enter(), 2: enter(2), 3: StepResult(None, skipped, ())}
    result = engine(script).run([bar(0, 1000, 1001, 999, 1000), *drift(1, 3)])

    assert len(result.trades) == 1  # the first plan only, closed END_OF_DATA
    assert [r.reason for r in result.rejected_signals] == ["position already open", skipped]
    assert [r.timestamp for r in result.rejected_signals] == [START + timedelta(minutes=m) for m in (3, 4)]


def test_kill_switch_trip_blocks_until_next_utc_day() -> None:
    day = timedelta(days=1)
    funding = FundingSchedule(every_8h(datetime(2024, 1, 2, 8, tzinfo=UTC), 6))
    with SimulatedKillSwitch() as kill_switch:
        config = BacktestConfig(risk=RiskConfig(max_consecutive_losses=1, kill_switch_path=kill_switch.path))
        risk = RiskManagementEngine(config.risk, kill_switch=kill_switch)
        next_day = int(day / timedelta(minutes=1))
        script = {0: enter(), 2: enter(2), next_day: enter(next_day)}
        tdob = TopDownBacktestEngine(config=config, risk_engine=risk, funding=funding, strategy=FakeStrategy(script))
        result = tdob.run([
            bar(0, 1000, 1001, 999, 1000),
            bar(1, 1000, 1001, 990, 992),  # stop: one loss trips the switch
            bar(2, 1000, 1001, 999, 1000),  # same UTC day: blocked
            bar(next_day, 1000, 1001, 999, 1000),  # next UTC day: the trip clears and the plan opens
        ])
        report = kill_switch.report()

    assert [t.exit_reason for t in result.trades] == [ExitReason.STOP_LOSS, ExitReason.END_OF_DATA]
    assert [r.reason for r in result.rejected_signals] == ["Risk rejected: Kill switch is active"]
    assert report["trips"] == 2  # the day-2 trade closes END_OF_DATA at a small loss (costs) and trips again
    assert report["trip_log"][0]["reset_at"] == (START + day).isoformat()


def test_phase1_costs_unchanged() -> None:
    # Phase 1 numbers captured before costs.py existed (default costs, so every cost formula is exercised).
    from test_backtest_engine import candle, engine as phase1_engine, valid_long_setup

    win = phase1_engine(BacktestConfig()).run([*valid_long_setup(), candle(9, 112, 141, 105, 140)]).trades[0]
    assert (win.entry_price, win.exit_price, win.realized_pnl, win.fees, win.slippage) == (
        106.0689, 139.90900000000002, 210.93082325000015, 0.5698017500000001, 0.12303445000000002)
    loss = phase1_engine(BacktestConfig()).run([*valid_long_setup(), candle(9, 112, 113, 97, 99)]).trades[0]
    assert (loss.exit_price, loss.realized_pnl, loss.fees, loss.slippage) == (
        97.93629999999999, -51.26738706250007, 0.4386370625, 0.10203445)
    partial = phase1_engine(BacktestConfig(enable_partial_tp=True)).run(
        [*valid_long_setup(), candle(9, 112, 141, 105, 140)]).trades[0]
    assert (partial.exit_reason, partial.exit_price, partial.realized_pnl, partial.fees) == (
        ExitReason.BREAKEVEN_STOP, 105.999955215, 24.29158219430468, 0.47643544632031243)
