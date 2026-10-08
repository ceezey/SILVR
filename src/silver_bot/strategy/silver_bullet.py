"""Deterministic ICT Silver Bullet strategy engine."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from silver_bot.models import Candle, SignalDirection
from silver_bot.strategy.bias import determine_higher_timeframe_bias
from silver_bot.strategy.displacement import detect_displacement
from silver_bot.strategy.fvg import latest_unmitigated_fvg
from silver_bot.strategy.liquidity import (
    detect_liquidity_sweep,
    liquidity_levels_from_swings,
    nearest_opposing_liquidity,
)
from silver_bot.strategy.models import (
    BiasDirection,
    FairValueGapDirection,
    LiquiditySweep,
    MarketStructureShift,
    SilverBulletSignal,
    SilverBulletStrategyConfig,
    StructureShiftDirection,
    SweepDirection,
)
from silver_bot.strategy.scoring import score_setup
from silver_bot.strategy.sessions import DEFAULT_SESSIONS, SilverBulletSessionEngine
from silver_bot.strategy.structure import detect_market_structure_shift, detect_swing_points


class SilverBulletStrategyEngine:
    """Generate deterministic ICT Silver Bullet research/backtest signals."""

    def __init__(self, config: SilverBulletStrategyConfig | None = None) -> None:
        if config is None:
            config = SilverBulletStrategyConfig(sessions=DEFAULT_SESSIONS)
        if not config.sessions:
            config = SilverBulletStrategyConfig(
                sessions=DEFAULT_SESSIONS,
                session_timezone=config.session_timezone,
                swing_lookback=config.swing_lookback,
                liquidity_lookback=config.liquidity_lookback,
                minimum_fvg_size=config.minimum_fvg_size,
                atr_period=config.atr_period,
                displacement_body_multiplier=config.displacement_body_multiplier,
                displacement_range_multiplier=config.displacement_range_multiplier,
                stop_buffer=config.stop_buffer,
                minimum_rr=config.minimum_rr,
                minimum_signal_score=config.minimum_signal_score,
                allow_counter_bias=config.allow_counter_bias,
            )
        self.config = config
        self.sessions = SilverBulletSessionEngine(
            timezone_name=config.session_timezone,
            sessions=config.sessions,
        )

    def evaluate(
        self,
        candles: Sequence[Candle],
        *,
        higher_timeframe_candles: Sequence[Candle] | None = None,
    ) -> SilverBulletSignal:
        """Evaluate candles and return LONG, SHORT, or NO_TRADE."""

        if len(candles) < max(5, self.config.swing_lookback + 3):
            return self._reject(candles, "Not enough candles to evaluate Silver Bullet setup")

        latest = candles[-1]
        session = self.sessions.evaluate(latest.open_time)
        if not session.is_active:
            return self._reject(candles, "Outside enabled Silver Bullet session")

        swings = detect_swing_points(candles, lookback=self.config.swing_lookback)
        if not swings:
            return self._reject(candles, "No swing highs or lows detected")

        latest_index = len(candles) - 1
        levels = liquidity_levels_from_swings(
            swings,
            lookback=self.config.liquidity_lookback,
            current_index=latest_index,
        )
        if not levels:
            return self._reject(candles, "No buy-side or sell-side liquidity levels detected")

        sweep_candidates = self._sweep_candidates(candles, levels)
        if not sweep_candidates:
            return self._reject(candles, "No liquidity sweep detected")

        rejection_reasons: list[str] = []
        for sweep in sweep_candidates:
            signal = self._evaluate_sweep_candidate(
                candles,
                higher_timeframe_candles=higher_timeframe_candles,
                session=session,
                sweep=sweep,
                swings=swings,
                levels=levels,
            )
            if signal.direction != SignalDirection.NO_TRADE:
                return signal
            if signal.reason:
                rejection_reasons.append(signal.reason)

        detail = rejection_reasons[-1] if rejection_reasons else "No complete setup after sweep"
        return self._reject(candles, detail)

    def _evaluate_sweep_candidate(
        self,
        candles: Sequence[Candle],
        *,
        higher_timeframe_candles: Sequence[Candle] | None,
        session,
        sweep: LiquiditySweep,
        swings: Sequence,
        levels: Sequence,
    ) -> SilverBulletSignal:
        latest = candles[-1]
        direction = (
            FairValueGapDirection.BULLISH
            if sweep.direction == SweepDirection.BULLISH
            else FairValueGapDirection.BEARISH
        )
        displacement = None
        for index in range(sweep.candle_index + 1, len(candles)):
            displacement = detect_displacement(
                candles[: index + 1],
                direction=direction,
                atr_period=self.config.atr_period,
                body_multiplier=self.config.displacement_body_multiplier,
                range_multiplier=self.config.displacement_range_multiplier,
            )
            if displacement is not None:
                break
        if displacement is None:
            return self._reject(candles, "No directional displacement after liquidity sweep")

        mss = self._first_mss_after_sweep(candles, sweep, swings)
        if mss is None:
            return self._reject(candles, "No market structure shift after liquidity sweep")

        expected_mss = (
            StructureShiftDirection.BULLISH
            if sweep.direction == SweepDirection.BULLISH
            else StructureShiftDirection.BEARISH
        )
        if mss.direction != expected_mss:
            return self._reject(candles, "Market structure shift direction does not match sweep")

        fvg = latest_unmitigated_fvg(
            candles,
            direction=direction,
            minimum_size=self.config.minimum_fvg_size,
        )
        if fvg is None or fvg.candle_index <= sweep.candle_index:
            return self._reject(candles, "No retracement into matching Fair Value Gap")

        entry_price = fvg.midpoint
        stop_loss = (
            sweep.swept_price - self.config.stop_buffer
            if sweep.direction == SweepDirection.BULLISH
            else sweep.swept_price + self.config.stop_buffer
        )
        if stop_loss == entry_price:
            return self._reject(candles, "Stop loss equals entry price")

        target_level = nearest_opposing_liquidity(
            entry_price=entry_price,
            direction=sweep.direction,
            levels=[level for level in levels if level.candle_index < sweep.candle_index],
        )
        fallback_distance = abs(entry_price - stop_loss) * self.config.minimum_rr
        take_profit = (
            target_level.price
            if target_level is not None
            else (
                entry_price + fallback_distance
                if sweep.direction == SweepDirection.BULLISH
                else entry_price - fallback_distance
            )
        )
        risk_reward = self._risk_reward(
            direction=sweep.direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        if risk_reward < self.config.minimum_rr:
            return self._reject(candles, "Reward-to-risk below configured minimum")

        bias = determine_higher_timeframe_bias(higher_timeframe_candles or candles)
        if not self.config.allow_counter_bias and self._is_counter_bias(sweep.direction, bias):
            return self._reject(candles, f"Setup rejected by higher-timeframe {bias.value} bias")

        quality = score_setup(
            session_active=session.is_active,
            sweep_direction=sweep.direction,
            displacement=displacement,
            fvg=fvg,
            bias=bias,
            risk_reward_ratio=risk_reward,
        )
        if quality.total < self.config.minimum_signal_score:
            return self._reject(
                candles,
                f"Setup quality score {quality.total} below minimum {self.config.minimum_signal_score}",
            )

        signal_direction = (
            SignalDirection.LONG
            if sweep.direction == SweepDirection.BULLISH
            else SignalDirection.SHORT
        )
        explanation = (
            f"{signal_direction.value} candidate: {session.name} session, "
            f"{sweep.direction.value} liquidity sweep, displacement, MSS, "
            f"FVG retracement, RR {risk_reward:.2f}, score {quality.total}. "
            "Risk engine approval is still required before any trade."
        )
        return SilverBulletSignal(
            direction=signal_direction,
            symbol=latest.symbol,
            timeframe=latest.timeframe,
            generated_at=self._signal_timestamp(latest),
            reason=None,
            explanation=explanation,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward_ratio=risk_reward,
            session_name=session.name,
            setup_quality_score=quality.total,
        )

    def _sweep_candidates(self, candles: Sequence[Candle], levels: Sequence) -> list[LiquiditySweep]:
        start = max(0, len(candles) - self.config.liquidity_lookback)
        candidates: list[LiquiditySweep] = []
        for index in range(len(candles) - 1, start, -1):
            sweep = detect_liquidity_sweep(candles, levels=levels, candle_index=index)
            if sweep is not None:
                candidates.append(sweep)
        return candidates

    def _first_mss_after_sweep(
        self,
        candles: Sequence[Candle],
        sweep: LiquiditySweep,
        swings: Sequence,
    ) -> MarketStructureShift | None:
        for index in range(sweep.candle_index + 1, len(candles)):
            mss = detect_market_structure_shift(candles[: index + 1], sweep=sweep, swings=swings)
            if mss is not None:
                return mss
        return None

    def _reject(self, candles: Sequence[Candle], reason: str) -> SilverBulletSignal:
        latest = candles[-1] if candles else None
        return SilverBulletSignal(
            direction=SignalDirection.NO_TRADE,
            symbol=latest.symbol if latest else "UNKNOWN",
            timeframe=latest.timeframe if latest else "UNKNOWN",
            generated_at=self._signal_timestamp(latest) if latest else datetime.now(timezone.utc),
            reason=reason,
            explanation=f"NO_TRADE: {reason}",
        )

    @staticmethod
    def _signal_timestamp(candle: Candle) -> datetime:
        """Timestamp signals at confirmed candle close when available."""

        return candle.close_time or candle.open_time

    @staticmethod
    def _risk_reward(
        *,
        direction: SweepDirection,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
    ) -> float:
        if direction == SweepDirection.BULLISH:
            risk = entry_price - stop_loss
            reward = take_profit - entry_price
        else:
            risk = stop_loss - entry_price
            reward = entry_price - take_profit
        if risk <= 0 or reward <= 0:
            return 0.0
        return reward / risk

    @staticmethod
    def _is_counter_bias(direction: SweepDirection, bias: BiasDirection) -> bool:
        return (
            direction == SweepDirection.BULLISH
            and bias == BiasDirection.BEARISH
            or direction == SweepDirection.BEARISH
            and bias == BiasDirection.BULLISH
        )
