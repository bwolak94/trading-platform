"""Telegram Bot — signal notifications and user commands."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from telegram import Bot, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

# Anti-spam: minimum seconds between signals per chat
MIN_SIGNAL_INTERVAL = 300  # 5 minutes


class TelegramNotifier:
    """Sends trading signals and handles commands via Telegram bot."""

    def __init__(self) -> None:
        self._bot: Bot | None = None
        self._app: Application | None = None
        self._last_signal_time: dict[str, datetime] = {}

    async def initialize(self) -> None:
        """Initialize the bot and register command handlers."""
        if not settings.TELEGRAM_BOT_TOKEN:
            logger.warning("TELEGRAM_BOT_TOKEN not set, Telegram bot disabled")
            return

        self._app = (
            Application.builder()
            .token(settings.TELEGRAM_BOT_TOKEN)
            .build()
        )
        self._bot = self._app.bot

        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("signals", self._cmd_signals))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("pause", self._cmd_pause))
        self._app.add_handler(CommandHandler("resume", self._cmd_resume))

        logger.info("Telegram bot initialized")

    async def start_polling(self) -> None:
        """Start the bot polling loop."""
        if not self._app:
            return
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()
        logger.info("Telegram bot polling started")

    async def stop(self) -> None:
        """Stop the bot gracefully."""
        if not self._app:
            return
        await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()
        logger.info("Telegram bot stopped")

    async def send_signal(self, chat_id: str, signal: dict[str, Any]) -> bool:
        """Send a formatted signal notification to a specific chat.

        Returns False if rate-limited or bot not initialized.
        """
        if not self._bot:
            return False

        # Anti-spam check
        if not self._check_rate_limit(chat_id):
            logger.debug("Rate limited signal for chat %s", chat_id)
            return False

        message = self._format_signal(signal)

        try:
            await self._bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="HTML",
            )
            self._last_signal_time[chat_id] = datetime.now(timezone.utc)
            return True
        except Exception as exc:
            logger.error("Failed to send Telegram message to %s: %s", chat_id, exc)
            return False

    async def send_kill_switch_alert(
        self, chat_id: str, drawdown_pct: float
    ) -> bool:
        """Send a kill switch activation alert."""
        if not self._bot:
            return False

        message = (
            "<b>SYSTEM PAUSED</b>\n\n"
            f"Drawdown limit reached: <b>{drawdown_pct:.1f}%</b>\n"
            "Signal generation has been paused.\n\n"
            "Use /resume to reactivate (manual confirmation required)."
        )

        try:
            await self._bot.send_message(
                chat_id=chat_id, text=message, parse_mode="HTML"
            )
            return True
        except Exception as exc:
            logger.error("Failed to send kill switch alert to %s: %s", chat_id, exc)
            return False

    def _check_rate_limit(self, chat_id: str) -> bool:
        """Check if enough time has passed since last signal for this chat."""
        last = self._last_signal_time.get(chat_id)
        if not last:
            return True
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        return elapsed >= MIN_SIGNAL_INTERVAL

    def _format_signal(self, signal: dict[str, Any]) -> str:
        """Format a signal dict into a Telegram message (HTML)."""
        direction = signal.get("direction", "NEUTRAL")
        direction_icon = {
            "LONG": "\U0001f7e2",   # green circle
            "SHORT": "\U0001f534",  # red circle
            "NEUTRAL": "\u26aa",    # white circle
        }.get(direction, "\u26aa")

        asset = signal.get("asset", "???")
        confidence = signal.get("confidence", 0)
        entry = signal.get("entry_price", 0)
        sl = signal.get("stop_loss", 0)
        tp1 = signal.get("take_profit_1", 0)
        tp2 = signal.get("take_profit_2", 0)
        rr = signal.get("risk_reward", 0)
        regime = signal.get("regime", "UNKNOWN")
        created = signal.get("created_at", "")

        # Format factors
        factors_text = ""
        factors = signal.get("factors", [])
        for f in factors[:3]:
            name = f.get("name", "")
            weight = f.get("weight", 0)
            weight_pct = int(weight * 100)
            label = f.get("label", "")
            label_icon = {
                "BULLISH": "\U0001f4c8",   # chart up
                "BEARISH": "\U0001f4c9",   # chart down
                "POSITIVE": "\U0001f4e3",  # megaphone
                "NEGATIVE": "\U0001f4e3",
            }.get(label, "\u2022")
            factors_text += f"{label_icon} {name} ({weight_pct}%)\n"

        # Format timestamp
        if isinstance(created, str) and created:
            time_str = created
        elif isinstance(created, datetime):
            time_str = created.strftime("%H:%M UTC")
        else:
            time_str = datetime.now(timezone.utc).strftime("%H:%M UTC")

        message = (
            f"{direction_icon} <b>SIGNAL: {asset} {direction}</b>\n"
            f"\U0001f4ca Confidence: <b>{confidence:.0f}%</b>\n"
            f"\U0001f4b0 Entry: <b>${entry:,.2f}</b>\n"
            f"\U0001f6d1 SL: <b>${sl:,.2f}</b>\n"
            f"\U0001f3af TP1: <b>${tp1:,.2f}</b> | TP2: <b>${tp2:,.2f}</b>\n"
            f"\u2696\ufe0f R/R: <b>{rr:.1f}</b>\n"
            f"\n"
            f"<b>Factors:</b>\n"
            f"{factors_text}\n"
            f"\u23f0 {time_str} | Regime: {regime}"
        )
        return message

    # --- Command Handlers ---

    async def _cmd_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /start command."""
        chat_id = str(update.effective_chat.id)
        await update.message.reply_text(
            "<b>AI Trading Navigator</b>\n\n"
            "Welcome! You will receive trading signals here.\n\n"
            "<b>Commands:</b>\n"
            "/signals — Last 5 signals\n"
            "/status — System status & drawdown\n"
            "/pause — Pause notifications\n"
            "/resume — Resume notifications\n\n"
            f"Your chat ID: <code>{chat_id}</code>\n"
            "Add this to your settings to receive alerts.",
            parse_mode="HTML",
        )

    async def _cmd_signals(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /signals command — show last 5 signals."""
        from app.core.database import async_session
        from app.models.signal import Signal
        from sqlalchemy import select

        async with async_session() as session:
            result = await session.execute(
                select(Signal).order_by(Signal.created_at.desc()).limit(5)
            )
            signals = result.scalars().all()

        if not signals:
            await update.message.reply_text(
                "No recent signals available.", parse_mode="HTML"
            )
            return

        lines = ["<b>Last 5 Signals:</b>\n"]
        for s in signals:
            icon = "\U0001f7e2" if s.direction == "LONG" else "\U0001f534"
            lines.append(
                f"{icon} {s.asset} {s.direction} | "
                f"Conf: {s.confidence}% | Status: {s.status}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def _cmd_status(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /status command — show system status."""
        from app.ai.risk.engine import RiskEngine
        from app.core.database import async_session

        risk = RiskEngine()
        async with async_session() as session:
            summary = await risk.get_risk_summary("default", session)

        await update.message.reply_text(
            f"<b>System Status</b>\n\n"
            f"Status: <b>{summary['system_status']}</b>\n"
            f"Drawdown: <b>{summary['drawdown_pct']:.1f}%</b> "
            f"(max {summary['max_drawdown_pct']:.1f}%)\n"
            f"Capital: <b>${summary['capital']:,.0f}</b>\n"
            f"Win streak: {summary['streak']['wins']} | "
            f"Loss streak: {summary['streak']['losses']}",
            parse_mode="HTML",
        )

    async def _cmd_pause(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /pause command — pause notifications."""
        from app.core.database import async_session
        from app.models.user_settings import UserSettings
        from sqlalchemy import select

        chat_id = str(update.effective_chat.id)

        async with async_session() as session:
            result = await session.execute(
                select(UserSettings).where(UserSettings.telegram_chat_id == chat_id)
            )
            user_settings = result.scalar_one_or_none()
            if user_settings:
                user_settings.notifications_enabled = False
                await session.commit()

        await update.message.reply_text(
            "Notifications paused. Use /resume to reactivate.",
            parse_mode="HTML",
        )

    async def _cmd_resume(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /resume command — resume notifications."""
        from app.core.database import async_session
        from app.models.user_settings import UserSettings
        from sqlalchemy import select

        chat_id = str(update.effective_chat.id)

        async with async_session() as session:
            result = await session.execute(
                select(UserSettings).where(UserSettings.telegram_chat_id == chat_id)
            )
            user_settings = result.scalar_one_or_none()
            if user_settings:
                user_settings.notifications_enabled = True
                await session.commit()

        await update.message.reply_text(
            "Notifications resumed. You will receive signals again.",
            parse_mode="HTML",
        )
