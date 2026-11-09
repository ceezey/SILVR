"""Deterministic signal quality scoring."""

from __future__ import annotations

from silvr.strategy.models import (
    BiasDirection,
    DisplacementEvent,
    FairValueGap,
    SignalQualityBreakdown,
    SweepDirection,
)


def score_setup(
    *,
    session_active: bool,
    sweep_direction: SweepDirection,
    displacement: DisplacementEvent,
    fvg: FairValueGap,
    bias: BiasDirection,
    risk_reward_ratio: float,
) -> SignalQualityBreakdown:
    """Score a deterministic setup from 0 to 100."""

    session_score = 15 if session_active else 0
    liquidity_score = 20
    displacement_score = min(20, int(displacement.strength_score // 5))
    fvg_score = 15 if fvg.size > 0 else 0

    aligns_long = sweep_direction == SweepDirection.BULLISH and bias in {
        BiasDirection.BULLISH,
        BiasDirection.NEUTRAL,
    }
    aligns_short = sweep_direction == SweepDirection.BEARISH and bias in {
        BiasDirection.BEARISH,
        BiasDirection.NEUTRAL,
    }
    htf_score = 15 if aligns_long or aligns_short else 0
    rr_score = 10 if risk_reward_ratio >= 2 else max(0, int(risk_reward_ratio / 2 * 10))
    volatility_score = 5 if displacement.atr > 0 else 0
    total = min(
        100,
        session_score
        + liquidity_score
        + displacement_score
        + fvg_score
        + htf_score
        + rr_score
        + volatility_score,
    )
    return SignalQualityBreakdown(
        total=total,
        session=session_score,
        liquidity=liquidity_score,
        displacement=displacement_score,
        fvg=fvg_score,
        htf_alignment=htf_score,
        risk_reward=rr_score,
        volatility=volatility_score,
    )
