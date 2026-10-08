"""Optional Telegram alerts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class TelegramClient(Protocol):
    """Minimal Telegram client protocol."""

    async def send_message(self, chat_id: str, text: str) -> None:
        """Send a message."""


@dataclass(frozen=True, slots=True)
class TelegramAlertConfig:
    """Telegram alert settings."""

    enabled: bool = False
    bot_token: str | None = None
    chat_id: str | None = None


@dataclass(slots=True)
class InMemoryTelegramClient:
    """Test client that records messages instead of sending network requests."""

    messages: list[tuple[str, str]] = field(default_factory=list)

    async def send_message(self, chat_id: str, text: str) -> None:
        self.messages.append((chat_id, text))


class TelegramAlerter:
    """Optional Telegram alert facade.

    No network client is created by default. Production wiring can provide a
    client later without making Telegram required for tests or local runs.
    """

    def __init__(
        self,
        config: TelegramAlertConfig | None = None,
        *,
        client: TelegramClient | None = None,
    ) -> None:
        self.config = config or TelegramAlertConfig()
        self.client = client

    async def bot_started(self) -> None:
        await self._send("bot started", "Paper bot started")

    async def bot_stopped(self) -> None:
        await self._send("bot stopped", "Paper bot stopped")

    async def signal_detected(self, symbol: str, direction: str) -> None:
        await self._send("signal detected", f"Signal detected: {symbol} {direction}")

    async def signal_rejected(self, symbol: str, reason: str) -> None:
        await self._send("signal rejected", f"Signal rejected: {symbol} {reason}")

    async def risk_rejection(self, symbol: str, reason: str) -> None:
        await self._send("risk rejection", f"Risk rejected: {symbol} {reason}")

    async def ml_approval(self, symbol: str, probability: float | None) -> None:
        probability_text = "unknown" if probability is None else f"{probability:.2f}"
        await self._send("ml approved", f"ML approved: {symbol} probability={probability_text}")

    async def ml_rejection(self, symbol: str, probability: float | None, reason: str) -> None:
        probability_text = "unknown" if probability is None else f"{probability:.2f}"
        await self._send("ml rejected", f"ML rejected: {symbol} probability={probability_text} {reason}")

    async def paper_trade_opened(self, symbol: str, direction: str) -> None:
        await self._send("paper trade opened", f"Paper trade opened: {symbol} {direction}")

    async def paper_trade_closed(self, symbol: str, realized_pnl: float) -> None:
        await self._send("paper trade closed", f"Paper trade closed: {symbol} PnL={realized_pnl:.2f}")

    async def daily_report(self, report: dict[str, Any]) -> None:
        await self._send(
            "daily report",
            (
                f"Daily report: trades={report.get('trades_taken', 0)} "
                f"PnL={float(report.get('pnl', 0.0)):.2f} "
                f"win_rate={float(report.get('win_rate', 0.0)):.2f}"
            ),
        )

    async def error(self, message: str) -> None:
        await self._send("error", f"Error: {message}")

    async def kill_switch_active(self) -> None:
        await self._send("kill switch active", "Kill switch active")

    async def _send(self, title: str, message: str) -> None:
        if not self.config.enabled:
            return
        if self.client is None:
            return
        if not self.config.chat_id:
            return
        await self.client.send_message(self.config.chat_id, f"[{title}] {message}")
