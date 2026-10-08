"""Mandatory risk-management engine."""

from __future__ import annotations

from datetime import date

from silver_bot.risk.kill_switch import KillSwitch
from silver_bot.risk.models import RiskConfig, RiskDecision, RiskRequest, RiskState, RiskStateStore
from silver_bot.utils.logging import get_logger


logger = get_logger(__name__)


class RiskManagementEngine:
    """Validate strategy candidates before any simulated or future real trade."""

    def __init__(
        self,
        config: RiskConfig | None = None,
        *,
        state: RiskState | None = None,
        kill_switch: KillSwitch | None = None,
        state_store: RiskStateStore | None = None,
    ) -> None:
        self.config = config or RiskConfig()
        self.kill_switch = kill_switch or KillSwitch(self.config.kill_switch_path)
        self.state_store = state_store
        self.state_load_error: str | None = None
        if state is None and state_store is not None:
            try:
                state = state_store.load_risk_state()
            except Exception as exc:  # fail closed on any unreadable state
                self.state_load_error = str(exc)
                logger.error("risk state could not be loaded; trading halted: %s", exc)
        self.state = state or RiskState()

    def evaluate(self, request: RiskRequest) -> RiskDecision:
        """Return a risk decision with an explicit approval or rejection reason."""

        if self.state_load_error is not None:
            return self._reject("Risk state could not be loaded; trading halted")
        previous_day = self.state.current_day
        self.state.roll_day(request.signal_day)
        if self.state.current_day != previous_day:
            self._save_state()

        if self.kill_switch.is_active():
            return self._reject("Kill switch is active")
        if request.equity <= 0:
            return self._reject("Account equity must be positive")
        if request.entry_price is None:
            return self._reject("Entry price is required")
        if request.stop_loss is None:
            return self._reject("Stop loss is required")
        if request.take_profit is None:
            return self._reject("Take profit is required")

        direction = request.direction.upper()
        stop_distance = self._stop_distance(
            direction=direction,
            entry_price=request.entry_price,
            stop_loss=request.stop_loss,
        )
        if stop_distance <= 0:
            return self._reject("Invalid stop loss for trade direction")
        if stop_distance < self.config.minimum_stop_distance:
            return self._reject("Stop-loss distance below configured minimum")

        reward_distance = self._reward_distance(
            direction=direction,
            entry_price=request.entry_price,
            take_profit=request.take_profit,
        )
        if reward_distance <= 0:
            return self._reject("Invalid take profit for trade direction")
        reward_to_risk = reward_distance / stop_distance
        if reward_to_risk < self.config.minimum_reward_to_risk:
            return self._reject("Reward-to-risk below configured minimum", reward_to_risk=reward_to_risk)

        max_daily_loss_amount = request.equity * self.config.max_daily_loss
        if self.state.daily_realized_pnl <= -max_daily_loss_amount:
            self.kill_switch.trip("Max daily loss limit reached")
            return self._reject("Max daily loss limit reached", reward_to_risk=reward_to_risk)
        if self.state.consecutive_losses >= self.config.max_consecutive_losses:
            self.kill_switch.trip("Max consecutive losses limit reached")
            return self._reject("Max consecutive losses limit reached", reward_to_risk=reward_to_risk)
        if self.state.trades_today >= self.config.max_trades_per_day:
            return self._reject("Max trades per day limit reached", reward_to_risk=reward_to_risk)
        if self.state.open_positions >= self.config.max_open_positions:
            return self._reject("Max open positions limit reached", reward_to_risk=reward_to_risk)

        risk_amount = request.equity * self.config.risk_per_trade
        position_size = risk_amount / stop_distance
        notional = position_size * request.entry_price
        leverage = notional / request.equity
        if leverage > self.config.max_leverage:
            return self._reject("Maximum leverage exceeded", reward_to_risk=reward_to_risk, leverage=leverage)

        return RiskDecision(
            approved=True,
            reason="Risk approved",
            position_size=position_size,
            risk_amount=risk_amount,
            reward_to_risk=reward_to_risk,
            leverage=leverage,
        )

    def reserve_trade(self, day: date) -> None:
        """Reserve risk capacity for an opened/pending trade."""

        self.state.roll_day(day)
        self.state.trades_today += 1
        self.state.open_positions += 1
        self._save_state()

    def release_trade(self, *, realized_pnl: float, day: date) -> None:
        """Release open-position capacity and update realized risk state."""

        self.state.roll_day(day)
        self.state.open_positions = max(0, self.state.open_positions - 1)
        self.state.daily_realized_pnl += realized_pnl
        if realized_pnl < 0:
            self.state.consecutive_losses += 1
        elif realized_pnl > 0:
            self.state.consecutive_losses = 0
        self._save_state()
        if self.state.consecutive_losses >= self.config.max_consecutive_losses:
            self.kill_switch.trip("Max consecutive losses limit reached")

    def _save_state(self) -> None:
        if self.state_store is not None and self.state_load_error is None:
            self.state_store.save_risk_state(self.state)

    @staticmethod
    def _stop_distance(*, direction: str, entry_price: float, stop_loss: float) -> float:
        if direction == "LONG":
            return entry_price - stop_loss
        if direction == "SHORT":
            return stop_loss - entry_price
        return 0.0

    @staticmethod
    def _reward_distance(*, direction: str, entry_price: float, take_profit: float) -> float:
        if direction == "LONG":
            return take_profit - entry_price
        if direction == "SHORT":
            return entry_price - take_profit
        return 0.0

    @staticmethod
    def _reject(
        reason: str,
        *,
        reward_to_risk: float = 0.0,
        leverage: float = 0.0,
    ) -> RiskDecision:
        return RiskDecision(
            approved=False,
            reason=reason,
            reward_to_risk=reward_to_risk,
            leverage=leverage,
        )
