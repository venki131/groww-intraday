"""
Telegram Notification Service.

Sends structured trade alerts and daily summaries via Telegram Bot API.
Credentials are loaded exclusively from environment variables.
Notifications are disabled by default (TELEGRAM_ENABLED=false).
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Optional

from config.logging_config import get_logger

logger = get_logger(__name__)


class TelegramNotifier:
    """
    Sends Telegram messages for trade events and system alerts.

    Args:
        bot_token: Telegram bot token (defaults to TELEGRAM_BOT_TOKEN env var).
        chat_id: Telegram chat/channel ID (defaults to TELEGRAM_CHAT_ID env var).
        enabled: If False, all sends are silently skipped.
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        enabled: bool = False,
    ) -> None:
        self._token: str = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._chat_id: str = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self._enabled: bool = enabled or (
            os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
        )

        if self._enabled and (not self._token or not self._chat_id):
            logger.warning(
                "Telegram enabled but credentials missing. "
                "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."
            )
            self._enabled = False

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Send a raw text message to the configured Telegram chat.

        Args:
            text: Message text (supports HTML formatting).
            parse_mode: 'HTML' or 'Markdown'.

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self._enabled:
            logger.debug("Telegram disabled; skipping message", preview=text[:60])
            return False

        try:
            import httpx
            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            payload = {
                "chat_id": self._chat_id,
                "text": text,
                "parse_mode": parse_mode,
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
            logger.debug("Telegram message sent")
            return True
        except Exception as exc:
            logger.error("Telegram send failed", error=str(exc))
            return False

    async def notify_trade_entry(
        self,
        ticker: str,
        side: str,
        quantity: int,
        price: Decimal,
        stop_loss: Optional[Decimal],
        take_profit: Optional[Decimal],
        strategy: str,
        mode: str = "paper",
    ) -> bool:
        """
        Send a trade entry notification.

        Args:
            ticker: NSE symbol.
            side: 'BUY' or 'SELL'.
            quantity: Shares traded.
            price: Entry price.
            stop_loss: Stop-loss level.
            take_profit: Take-profit level.
            strategy: Strategy name.
            mode: 'paper' or 'backtest'.
        """
        emoji = "🟢" if side == "BUY" else "🔴"
        sl_text = f"₹{float(stop_loss):.2f}" if stop_loss else "N/A"
        tp_text = f"₹{float(take_profit):.2f}" if take_profit else "N/A"

        text = (
            f"{emoji} <b>TRADE ENTRY [{mode.upper()}]</b>\n"
            f"Symbol   : <code>{ticker}</code>\n"
            f"Side     : <b>{side}</b>\n"
            f"Qty      : {quantity}\n"
            f"Price    : ₹{float(price):.2f}\n"
            f"SL       : {sl_text}\n"
            f"TP       : {tp_text}\n"
            f"Strategy : {strategy}"
        )
        return await self.send_message(text)

    async def notify_trade_exit(
        self,
        ticker: str,
        quantity: int,
        entry_price: Decimal,
        exit_price: Decimal,
        pnl: Decimal,
        exit_reason: str,
        mode: str = "paper",
    ) -> bool:
        """
        Send a trade exit notification with P&L.

        Args:
            ticker: NSE symbol.
            quantity: Shares traded.
            entry_price: Entry price.
            exit_price: Exit price.
            pnl: Net P&L in INR.
            exit_reason: Reason for exit.
            mode: Trading mode.
        """
        pnl_emoji = "✅" if pnl >= 0 else "❌"
        text = (
            f"{pnl_emoji} <b>TRADE EXIT [{mode.upper()}]</b>\n"
            f"Symbol   : <code>{ticker}</code>\n"
            f"Qty      : {quantity}\n"
            f"Entry    : ₹{float(entry_price):.2f}\n"
            f"Exit     : ₹{float(exit_price):.2f}\n"
            f"PnL      : ₹{float(pnl):+.2f}\n"
            f"Reason   : {exit_reason}"
        )
        return await self.send_message(text)

    async def notify_daily_summary(
        self,
        total_trades: int,
        winning_trades: int,
        total_pnl: Decimal,
        capital: Decimal,
        mode: str = "paper",
    ) -> bool:
        """
        Send end-of-day summary notification.

        Args:
            total_trades: Number of trades taken today.
            winning_trades: Number of profitable trades.
            total_pnl: Net P&L for the day.
            capital: Current portfolio value.
            mode: Trading mode.
        """
        pnl_emoji = "📈" if total_pnl >= 0 else "📉"
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        text = (
            f"{pnl_emoji} <b>DAILY SUMMARY [{mode.upper()}]</b>\n"
            f"Total Trades : {total_trades}\n"
            f"Win Rate     : {win_rate:.1f}%\n"
            f"Net PnL      : ₹{float(total_pnl):+.2f}\n"
            f"Portfolio    : ₹{float(capital):,.2f}"
        )
        return await self.send_message(text)

    async def notify_error(self, error_msg: str, context: str = "") -> bool:
        """
        Send an error/alert notification.

        Args:
            error_msg: Error description.
            context: Additional context (e.g. function name).
        """
        text = (
            f"🚨 <b>ERROR ALERT</b>\n"
            f"Context : {context}\n"
            f"Error   : {error_msg}"
        )
        return await self.send_message(text)