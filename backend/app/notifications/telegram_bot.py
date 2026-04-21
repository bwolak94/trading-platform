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
        self._app.add_handler(CommandHandler("history", self._cmd_history))
        self._app.add_handler(CommandHandler("performance", self._cmd_performance))
        self._app.add_handler(CommandHandler("active", self._cmd_active))

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

        Also persists the notification to the history table.
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
            await self._log_notification(chat_id, "SIGNAL", signal, message)
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
            await self._log_notification(chat_id, "KILL_SWITCH", {}, message)
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
        strategy = signal.get("strategy_name", signal.get("strategy", ""))
        created = signal.get("created_at", "")

        # Format factors
        factors_text = ""
        factors = signal.get("factors", [])
        for f in factors[:3]:
            name = f.get("name", "") if isinstance(f, dict) else str(f)
            weight = f.get("weight", 0) if isinstance(f, dict) else 0
            weight_pct = int(weight * 100)
            label = f.get("label", "") if isinstance(f, dict) else ""
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

        strategy_line = f"\n\U0001f916 Strategy: <b>{strategy}</b>" if strategy else ""

        message = (
            f"{direction_icon} <b>SIGNAL: {asset} {direction}</b>\n"
            f"\U0001f4ca Confidence: <b>{confidence:.0f}%</b>\n"
            f"\U0001f4b0 Entry: <b>${entry:,.4f}</b>\n"
            f"\U0001f6d1 SL: <b>${sl:,.4f}</b>\n"
            f"\U0001f3af TP1: <b>${tp1:,.4f}</b> | TP2: <b>${tp2:,.4f}</b>\n"
            f"\u2696\ufe0f R/R: <b>{rr:.1f}</b>"
            f"{strategy_line}\n"
            f"\n"
            f"<b>Factors:</b>\n"
            f"{factors_text}\n"
            f"\u23f0 {time_str} | Regime: {regime}"
        )
        return message

    async def _log_notification(
        self,
        chat_id: str,
        message_type: str,
        signal: dict[str, Any],
        message_text: str,
    ) -> None:
        """Persist a sent notification to the notification_history table."""
        try:
            from app.core.database import async_session
            from app.models.notification_history import NotificationHistory

            async with async_session() as session:
                row = NotificationHistory(
                    chat_id=chat_id,
                    message_type=message_type,
                    asset=signal.get("asset") or signal.get("symbol"),
                    direction=signal.get("direction") or signal.get("action"),
                    confidence=signal.get("confidence"),
                    strategy=signal.get("strategy_name") or signal.get("strategy"),
                    entry_price=signal.get("entry_price") or signal.get("entry"),
                    stop_loss=signal.get("stop_loss"),
                    take_profit_1=signal.get("take_profit_1"),
                    message_text=message_text,
                    outcome="PENDING",
                )
                session.add(row)
                await session.commit()
        except Exception as exc:
            logger.debug("Failed to log notification: %s", exc)

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
            "/history — Last 20 notifications with outcomes\n"
            "/performance — Bot win rate & PnL stats\n"
            "/active — Active simulated positions\n"
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

    async def _cmd_history(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /history — show last 20 notifications with outcomes."""
        from app.core.database import async_session
        from app.models.notification_history import NotificationHistory
        from sqlalchemy import select, desc

        chat_id = str(update.effective_chat.id)

        async with async_session() as session:
            result = await session.execute(
                select(NotificationHistory)
                .where(NotificationHistory.chat_id == chat_id)
                .where(NotificationHistory.message_type == "SIGNAL")
                .order_by(desc(NotificationHistory.sent_at))
                .limit(20)
            )
            rows = result.scalars().all()

        if not rows:
            await update.message.reply_text(
                "No notification history found.", parse_mode="HTML"
            )
            return

        outcome_icon = {"WIN": "\u2705", "LOSS": "\u274c", "PENDING": "\u23f3", "EXPIRED": "\u23f9"}
        lines = ["<b>Last 20 Signal Notifications:</b>\n"]
        for r in rows:
            icon = "\U0001f7e2" if r.direction == "LONG" else "\U0001f534"
            oc = outcome_icon.get(r.outcome or "PENDING", "\u2022")
            pnl_str = f" {r.pnl_pct:+.1f}%" if r.pnl_pct is not None else ""
            time_str = r.sent_at.strftime("%m/%d %H:%M") if r.sent_at else ""
            lines.append(
                f"{oc} {icon} {r.asset} {r.direction} "
                f"({r.confidence}%){pnl_str} — {time_str}"
            )

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def _cmd_performance(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /performance — show win rate and PnL stats."""
        from app.ai.simulation.paper_trading_engine import get_paper_trading_engine

        engine = get_paper_trading_engine()
        perf = engine.get_performance()

        total = perf.get("total_trades", 0)
        win_rate = perf.get("win_rate", 0) * 100
        total_pnl = perf.get("total_pnl_pct", 0)
        max_dd = perf.get("max_drawdown_pct", 0)
        sharpe = perf.get("sharpe_ratio", 0)
        pf = perf.get("profit_factor", 0)
        best = perf.get("best_trade", 0)
        worst = perf.get("worst_trade", 0)

        status_icon = "\U0001f7e2" if engine.is_running else "\U0001f534"

        await update.message.reply_text(
            f"<b>Bot Performance</b> {status_icon}\n\n"
            f"\U0001f4ca Total trades: <b>{total}</b>\n"
            f"\U0001f3af Win rate: <b>{win_rate:.1f}%</b>\n"
            f"\U0001f4b0 Total PnL: <b>{total_pnl:+.2f}%</b>\n"
            f"\U0001f4c9 Max drawdown: <b>{max_dd:.2f}%</b>\n"
            f"\u26a1 Sharpe: <b>{sharpe:.2f}</b>\n"
            f"\U0001f4c8 Profit factor: <b>{pf:.2f}</b>\n"
            f"\u2705 Best trade: <b>{best:+.2f}%</b>\n"
            f"\u274c Worst trade: <b>{worst:+.2f}%</b>\n"
            f"Open positions: <b>{perf.get('open_positions', 0)}</b>",
            parse_mode="HTML",
        )

    async def _cmd_active(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /active — show currently open simulated positions."""
        from app.ai.simulation.paper_trading_engine import get_paper_trading_engine

        engine = get_paper_trading_engine()
        positions = engine.get_open_positions()

        if not positions:
            await update.message.reply_text(
                "No active simulated positions.", parse_mode="HTML"
            )
            return

        lines = [f"<b>Active Positions ({len(positions)})</b>\n"]
        for p in positions:
            icon = "\U0001f7e2" if p["direction"] == "LONG" else "\U0001f534"
            pnl = p.get("pnl_pct", 0)
            pnl_icon = "\u2197\ufe0f" if pnl >= 0 else "\u2198\ufe0f"
            lines.append(
                f"{icon} {p['symbol']} {p['direction']} | "
                f"Entry: {p['entry_price']:.4f} | "
                f"PnL: {pnl_icon} <b>{pnl:+.2f}%</b> | "
                f"Conf: {p['confidence']}%"
            )

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

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

    async def send_message(self, text: str) -> bool:
        """Send a plain text message to the configured default chat.

        Uses the TELEGRAM_CHAT_ID setting if available.
        Returns True on success, False otherwise.
        """
        if not self._bot:
            logger.warning("Telegram bot not initialized — cannot send message")
            return False

        chat_id = settings.TELEGRAM_CHAT_ID if hasattr(settings, "TELEGRAM_CHAT_ID") else None
        if not chat_id:
            logger.warning("TELEGRAM_CHAT_ID not configured — cannot send message")
            return False

        try:
            await self._bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="Markdown",
            )
            return True
        except Exception as exc:
            logger.error("Failed to send Telegram message: %s", exc)
            return False


# Module-level singleton
_telegram_notifier: TelegramNotifier | None = None


def get_telegram_bot() -> TelegramNotifier | None:
    """Return the module-level TelegramNotifier singleton.

    Returns None if the bot has not been initialized yet.
    """
    return _telegram_notifier


def set_telegram_bot(notifier: TelegramNotifier) -> None:
    """Register the TelegramNotifier singleton (called at startup)."""
    global _telegram_notifier
    _telegram_notifier = notifier
