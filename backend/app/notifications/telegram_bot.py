"""Telegram Bot — signal notifications and user commands."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
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
        self._queued_alerts: dict[str, list[dict]] = {}
        self._alert_windows: dict[str, dict] = {}

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
        self._app.add_handler(CommandHandler("weekly_report", self._cmd_weekly_report))
        self._app.add_handler(CommandHandler("next_session", self._cmd_next_session))
        self._app.add_handler(CommandHandler("setalertwindow", self.handle_alert_window_command))

        # Inline keyboard button handler for signal approval / skip / explain
        self._app.add_handler(
            CallbackQueryHandler(self._handle_signal_callback)
        )

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

    # Confidence threshold above which inline approval buttons are shown
    _APPROVAL_CONFIDENCE_THRESHOLD = 75

    async def send_signal(self, chat_id: str, signal: dict[str, Any]) -> bool:
        """Send a formatted signal notification to a specific chat.

        For high-confidence signals (confidence >= 75) an InlineKeyboardMarkup is
        appended with "Approved / Skip / Explain" buttons.

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
        signal_id = str(signal.get("id", signal.get("signal_id", "")))
        confidence = int(signal.get("confidence", 0))

        # Build optional inline keyboard for high-confidence signals
        reply_markup: InlineKeyboardMarkup | None = None
        if signal_id and confidence >= self._APPROVAL_CONFIDENCE_THRESHOLD:
            reply_markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "\u2705 Note: Approved",
                            callback_data=f"approve_{signal_id}",
                        ),
                        InlineKeyboardButton(
                            "\u274c Skip",
                            callback_data=f"skip_{signal_id}",
                        ),
                        InlineKeyboardButton(
                            "\u2139\ufe0f Explain",
                            callback_data=f"explain_{signal_id}",
                        ),
                    ]
                ]
            )

        try:
            await self._bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="HTML",
                reply_markup=reply_markup,
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
            "/weekly_report — Weekly performance summary\n"
            "/next_session — Upcoming session opens & alerts\n"
            "/pause — Pause notifications\n"
            "/resume — Resume notifications\n"
            "/setalertwindow HH-HH — Set alert delivery window\n\n"
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

    async def _handle_signal_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle inline keyboard button presses for signal approval / skip / explain.

        Supported callback_data patterns:
        - approve_<signal_id>  → marks signal USER_APPROVED
        - skip_<signal_id>     → marks signal USER_SKIPPED
        - explain_<signal_id>  → fetches RAG explanation and sends as follow-up
        """
        query = update.callback_query
        if not query or not query.data:
            return

        await query.answer()  # removes the loading spinner on the button

        data: str = query.data
        if "_" not in data:
            return

        action, signal_id = data.split("_", 1)

        if action == "approve":
            await self._update_signal_status(signal_id, "USER_APPROVED")
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("\u2705 Signal noted!")

        elif action == "skip":
            await self._update_signal_status(signal_id, "USER_SKIPPED")
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("Skipped.")

        elif action == "explain":
            explanation = await self._fetch_signal_explanation(signal_id)
            await query.message.reply_text(explanation, parse_mode="HTML")

        elif data.startswith("approve_signal_"):
            # Semi-auto order placement — route to order preview handler
            await self.handle_order_approve(update, context)

        elif data.startswith("paper_confirm_"):
            parts = data.split("_", 2)
            sid = parts[2] if len(parts) > 2 else "unknown"
            await self._update_signal_status(sid, "PAPER_CONFIRMED")
            await query.edit_message_text(
                text="\u2705 <b>Paper trade noted.</b>\nSimulated position recorded in the system.",
                parse_mode="HTML",
            )

        elif data.startswith("paper_cancel_"):
            await query.edit_message_text(
                text="Order cancelled.",
                parse_mode="HTML",
            )

        else:
            logger.debug("Unknown callback action: %s", action)

    async def _update_signal_status(self, signal_id: str, status: str) -> None:
        """Update a signal's status in the database.

        Args:
            signal_id: UUID string of the signal.
            status: New status string (e.g. "USER_APPROVED", "USER_SKIPPED").
        """
        try:
            import uuid as _uuid

            from sqlalchemy import update

            from app.core.database import async_session
            from app.models.signal import Signal

            parsed_id = _uuid.UUID(signal_id)
            async with async_session() as session:
                await session.execute(
                    update(Signal)
                    .where(Signal.id == parsed_id)
                    .values(status=status)
                )
                await session.commit()
            logger.info("Signal %s → status set to %s", signal_id, status)
        except Exception as exc:
            logger.warning("Failed to update signal %s status: %s", signal_id, exc)

    async def _fetch_signal_explanation(self, signal_id: str) -> str:
        """Fetch a RAG-enhanced explanation for a signal.

        Loads the signal from the DB, fetches live context, and builds
        the explanation prompt. If Claude is configured it will call the
        AI explanation endpoint; otherwise returns the raw prompt.

        Args:
            signal_id: UUID string of the signal.

        Returns:
            Formatted explanation text suitable for sending as a Telegram message.
        """
        try:
            import uuid as _uuid

            from sqlalchemy import select

            from app.core.database import async_session
            from app.models.signal import Signal

            parsed_id = _uuid.UUID(signal_id)
            async with async_session() as session:
                result = await session.execute(
                    select(Signal).where(Signal.id == parsed_id)
                )
                sig = result.scalar_one_or_none()

            if sig is None:
                return f"\u26a0\ufe0f Signal {signal_id} not found."

            signal_dict: dict = {
                "id": str(sig.id),
                "asset": sig.asset,
                "direction": sig.direction,
                "confidence": int(sig.confidence),
                "strategy_name": getattr(sig, "strategy_name", ""),
                "entry_price": float(sig.entry_price) if sig.entry_price else None,
                "stop_loss": float(sig.stop_loss) if sig.stop_loss else None,
                "take_profit_1": float(sig.take_profit_1) if sig.take_profit_1 else None,
                "factors": sig.factors or [],
                "regime": sig.regime,
            }

            from app.ai.rag_context import build_rag_explanation_prompt, fetch_signal_context

            context = await fetch_signal_context(sig.asset, sig.direction)
            prompt = await build_rag_explanation_prompt(signal_dict, context)

            # Try to call Claude via the explain endpoint
            try:
                import httpx

                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        "http://localhost:8000/api/v1/analyze/explain",
                        json={"signal_id": signal_id, "prompt": prompt},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        explanation_text = data.get("explanation", prompt[:1000])
                        return f"\u2139\ufe0f <b>Signal Explanation</b>\n\n{explanation_text}"
            except Exception:
                pass

            # Fallback: return the raw context summary
            context_summary = ""
            if context.get("news"):
                context_summary += "News: " + context["news"][0]["headline"] + "\n"
            if context.get("funding_rate"):
                context_summary += f"Funding: {context['funding_rate']*100:.4f}%\n"
            context_summary += f"Fear & Greed: {context.get('fear_greed_index', 50)}"

            return (
                f"\u2139\ufe0f <b>{sig.asset} {sig.direction} — Context Summary</b>\n\n"
                f"Confidence: {int(sig.confidence)}%\n"
                f"Entry: {sig.entry_price} | SL: {sig.stop_loss}\n"
                f"Regime: {sig.regime}\n\n"
                f"{context_summary}"
            )

        except Exception as exc:
            logger.error("Failed to fetch explanation for signal %s: %s", signal_id, exc)
            return f"\u26a0\ufe0f Could not load explanation for signal {signal_id}."

    async def _cmd_weekly_report(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /weekly_report — generate a weekly performance summary from DB signals.

        Fetches the last 7 days of signals and calculates:
        - Total signals, wins, losses, win rate
        - Average R:R
        - Best/worst strategy by win rate
        - Regime breakdown
        - Top insight
        """
        from datetime import timedelta

        from sqlalchemy import func, select

        from app.core.database import async_session
        from app.models.notification_history import NotificationHistory

        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)

        async with async_session() as session:
            result = await session.execute(
                select(NotificationHistory)
                .where(NotificationHistory.message_type == "SIGNAL")
                .where(NotificationHistory.sent_at >= week_ago)
                .order_by(NotificationHistory.sent_at.asc())
            )
            rows = result.scalars().all()

        if not rows:
            await update.message.reply_text(
                "No signal data found for the past 7 days.", parse_mode="HTML"
            )
            return

        # Compute aggregates
        total = len(rows)
        wins = sum(1 for r in rows if r.outcome == "WIN")
        losses = sum(1 for r in rows if r.outcome == "LOSS")
        win_rate = (wins / total * 100) if total > 0 else 0.0

        # Average R:R from pnl_pct / risk approximation (use pnl as proxy)
        pnl_values = [r.pnl_pct for r in rows if r.pnl_pct is not None]
        avg_rr = sum(abs(p) for p in pnl_values) / len(pnl_values) if pnl_values else 0.0

        # Best / worst strategy by win rate
        strategy_stats: dict[str, dict[str, int]] = {}
        for r in rows:
            strat = r.strategy or "unknown"
            if strat not in strategy_stats:
                strategy_stats[strat] = {"wins": 0, "total": 0}
            strategy_stats[strat]["total"] += 1
            if r.outcome == "WIN":
                strategy_stats[strat]["wins"] += 1

        def _wr(stats: dict[str, int]) -> float:
            return (stats["wins"] / stats["total"] * 100) if stats["total"] > 0 else 0.0

        best_strategy, best_wr, best_symbol = "N/A", 0.0, "N/A"
        worst_strategy, worst_wr = "N/A", 100.0

        if strategy_stats:
            best_entry = max(strategy_stats.items(), key=lambda kv: _wr(kv[1]))
            worst_entry = min(strategy_stats.items(), key=lambda kv: _wr(kv[1]))
            best_strategy = best_entry[0]
            best_wr = _wr(best_entry[1])
            worst_strategy = worst_entry[0]
            worst_wr = _wr(worst_entry[1])
            # Find best symbol for best strategy
            best_rows = [r for r in rows if (r.strategy or "unknown") == best_strategy and r.outcome == "WIN"]
            if best_rows:
                best_symbol = best_rows[0].asset or "N/A"

        # Regime breakdown
        regime_stats_map: dict[str, dict[str, int]] = {}
        for r in rows:
            # regime is not stored on notification_history directly — use strategy as proxy
            regime_key = r.strategy or "unknown"
            if regime_key not in regime_stats_map:
                regime_stats_map[regime_key] = {"wins": 0, "total": 0}
            regime_stats_map[regime_key]["total"] += 1
            if r.outcome == "WIN":
                regime_stats_map[regime_key]["wins"] += 1

        regime_lines = "\n".join(
            f"  • {strat}: {_wr(stats):.0f}% WR ({stats['total']} signals)"
            for strat, stats in sorted(
                regime_stats_map.items(), key=lambda kv: _wr(kv[1]), reverse=True
            )[:5]
        )

        # Top insight: highest pnl trade
        top_insight = "No closed trades with P&L data yet."
        if pnl_values:
            best_pnl = max(pnl_values)
            best_pnl_row = next((r for r in rows if r.pnl_pct == best_pnl), None)
            if best_pnl_row:
                top_insight = (
                    f"{best_pnl_row.asset} {best_pnl_row.direction} "
                    f"({best_pnl_row.strategy}) returned {best_pnl:+.2f}%"
                )

        date_from = week_ago.strftime("%b %d")
        date_to = now.strftime("%b %d")

        message = (
            f"\U0001f4ca <b>Weekly Performance Report</b>\n"
            f"Period: {date_from} – {date_to} UTC\n\n"
            f"\U0001f4c8 Signals: <b>{total}</b> | "
            f"\u2705 <b>{wins}</b> Wins | \u274c <b>{losses}</b> Losses\n"
            f"Win Rate: <b>{win_rate:.1f}%</b>\n"
            f"Avg R:R: <b>{avg_rr:.2f}</b>\n\n"
            f"\U0001f3c6 Best Setup: <b>{best_strategy}</b> on {best_symbol} "
            f"(<b>{best_wr:.0f}%</b> WR)\n"
            f"\u26a0\ufe0f Worst Setup: <b>{worst_strategy}</b> (<b>{worst_wr:.0f}%</b> WR)\n\n"
            f"\U0001f3af Strategy Performance:\n{regime_lines}\n\n"
            f"\U0001f4a1 Top Insight: {top_insight}\n\n"
            f"Next Report: Monday 08:00 UTC"
        )

        await update.message.reply_text(message, parse_mode="HTML")

    async def _cmd_next_session(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /next_session — show upcoming session opens and pre-session alerts.

        Calculates time until the next London and NY session opens based on
        current UTC time. Also notes if we are currently inside a session.
        """
        now = datetime.now(timezone.utc)
        hour = now.hour
        minute = now.minute
        current_minutes = hour * 60 + minute

        # Session opens in UTC minutes from midnight
        LONDON_OPEN = 7 * 60       # 07:00 UTC
        LONDON_CLOSE = 16 * 60     # 16:00 UTC
        NY_OPEN = 13 * 60          # 13:00 UTC
        NY_CLOSE = 21 * 60         # 21:00 UTC
        ASIAN_OPEN = 0             # 00:00 UTC
        ASIAN_CLOSE = 9 * 60       # 09:00 UTC

        def _mins_to_str(minutes: int) -> str:
            h, m = divmod(minutes, 60)
            return f"{h:02d}:{m:02d} UTC"

        def _until(target_mins: int) -> str:
            diff = target_mins - current_minutes
            if diff < 0:
                diff += 24 * 60  # wrap to next day
            h, m = divmod(diff, 60)
            parts = []
            if h > 0:
                parts.append(f"{h}h")
            parts.append(f"{m}m")
            return " ".join(parts)

        # Current session status
        in_london = LONDON_OPEN <= current_minutes <= LONDON_CLOSE
        in_ny = NY_OPEN <= current_minutes <= NY_CLOSE
        in_asian = current_minutes <= ASIAN_CLOSE or current_minutes >= 23 * 60

        session_status_lines = []
        if in_london:
            session_status_lines.append("\U0001f7e2 LONDON — <b>OPEN</b> (closes at 16:00 UTC)")
        else:
            session_status_lines.append(
                f"\u26aa LONDON — closed (opens in {_until(LONDON_OPEN)} at 07:00 UTC)"
            )

        if in_ny:
            session_status_lines.append("\U0001f7e2 NEW YORK — <b>OPEN</b> (closes at 21:00 UTC)")
        else:
            session_status_lines.append(
                f"\u26aa NEW YORK — closed (opens in {_until(NY_OPEN)} at 13:00 UTC)"
            )

        if in_asian:
            session_status_lines.append("\U0001f7e2 ASIAN — <b>OPEN</b> (closes at 09:00 UTC)")
        else:
            session_status_lines.append(
                f"\u26aa ASIAN — closed (opens in {_until(ASIAN_OPEN)} at 00:00 UTC)"
            )

        # Overlap detection
        overlap_note = ""
        if in_london and in_ny:
            overlap_note = "\n\u26a1 London/NY Overlap — <b>Highest liquidity window!</b>"
        elif in_london:
            mins_to_ny = NY_OPEN - current_minutes
            if 0 < mins_to_ny <= 60:
                overlap_note = f"\n\u23f0 NY Open in {_until(NY_OPEN)} — watch for breakout"

        # Pre-session alerts
        pre_session_alerts = []
        mins_to_london = (LONDON_OPEN - current_minutes) % (24 * 60)
        mins_to_ny = (NY_OPEN - current_minutes) % (24 * 60)
        if mins_to_london <= 60:
            pre_session_alerts.append(
                f"\u23f0 London Open in {_until(LONDON_OPEN)} — monitor GBP/EUR pairs and BTC"
            )
        if mins_to_ny <= 60:
            pre_session_alerts.append(
                f"\u23f0 NY Open in {_until(NY_OPEN)} — watch for major moves on USD pairs"
            )

        alerts_text = "\n".join(pre_session_alerts) if pre_session_alerts else "No imminent session opens."

        message = (
            f"\U0001f552 <b>Session Status</b> ({now.strftime('%H:%M UTC')})\n\n"
            + "\n".join(session_status_lines)
            + overlap_note
            + f"\n\n\U0001f514 <b>Pre-Session Alerts:</b>\n{alerts_text}"
        )

        await update.message.reply_text(message, parse_mode="HTML")

    # ── Alert Window & Queue Helpers ────────────────────────────────────

    def _is_in_alert_window(self, settings: dict) -> bool:
        """Check if current UTC time is within user's alert window.

        Reads alert_window_start and alert_window_end from the settings dict
        (integers 0-23 representing UTC hours). Defaults to 0-23 (always on).
        Supports overnight windows, e.g. start=20, end=8.
        """
        hour = datetime.now(timezone.utc).hour
        start = settings.get("alert_window_start", 0)
        end = settings.get("alert_window_end", 23)
        if start <= end:
            return start <= hour <= end
        # Overnight window (e.g. 20:00 – 08:00)
        return hour >= start or hour <= end

    async def _queue_or_send(
        self, chat_id: str, message: str, confidence: float, settings: dict
    ) -> None:
        """Send immediately if in window or high confidence, else queue for digest.

        Signals with confidence >= 80% are always delivered immediately,
        bypassing the alert window restriction.
        """
        if confidence >= 80.0:
            await self._send_to_chat(chat_id, message)
            return
        if self._is_in_alert_window(settings):
            await self._send_to_chat(chat_id, message)
        else:
            self._queued_alerts.setdefault(chat_id, []).append(
                {"message": message, "confidence": confidence}
            )
            logger.info("Signal queued for user %s (outside alert window)", chat_id)

    async def _send_to_chat(self, chat_id: str, message: str) -> None:
        """Internal helper — send HTML message to a specific chat_id."""
        if not self._bot:
            return
        try:
            await self._bot.send_message(
                chat_id=chat_id, text=message, parse_mode="HTML"
            )
        except Exception as exc:
            logger.error("Failed to send message to %s: %s", chat_id, exc)

    async def flush_queued_alerts(self, chat_id: str) -> None:
        """Send all queued alerts for a user as a single digest message.

        Called when the user's alert window opens or when they run /resume.
        Alerts are sorted by confidence descending before sending.
        """
        queued = self._queued_alerts.pop(chat_id, [])
        if not queued:
            return
        digest = f"\U0001f4e5 <b>Queued Signals ({len(queued)} while outside window)</b>\n\n"
        for item in sorted(queued, key=lambda x: x["confidence"], reverse=True):
            digest += item["message"][:200] + "\n---\n"
        await self._send_to_chat(chat_id, digest)

    # ── Semi-Auto Order Placement ────────────────────────────────────────

    async def handle_order_approve(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle [APPROVE] tap on a signal notification.

        Displays a paper-mode order preview. This is DISPLAY ONLY — no real
        order execution occurs unless exchange API keys are configured.
        Callback data format: approve_signal_{signal_id}
        """
        query = update.callback_query
        if not query:
            return
        await query.answer()

        data = query.data or ""
        parts = data.split("_")
        # Format: approve_signal_{signal_id}
        signal_id = parts[2] if len(parts) > 2 else "unknown"

        preview_text = (
            f"\U0001f4cb <b>Order Preview</b>\n\n"
            f"Signal ID: {signal_id}\n"
            f"\u26a0\ufe0f Paper mode — review parameters:\n\n"
            f"To place a real order, configure exchange API keys in Settings.\n"
            f"Current: <i>Simulation mode only</i>"
        )

        await query.edit_message_text(
            text=preview_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "\u2713 Confirm (Paper)",
                            callback_data=f"paper_confirm_{signal_id}",
                        ),
                        InlineKeyboardButton(
                            "\u2717 Cancel",
                            callback_data=f"paper_cancel_{signal_id}",
                        ),
                    ]
                ]
            ),
        )

    async def handle_alert_window_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """/setalertwindow HH-HH — set the user's alert delivery window.

        Example: /setalertwindow 08-22 → only deliver alerts 08:00-22:00 UTC.
        Signals with >80% confidence are always delivered regardless of window.
        Overnight windows are supported, e.g. /setalertwindow 20-08.
        Use /setalertwindow 00-23 to receive all alerts at any time.
        """
        args = context.args
        if not args or "-" not in args[0]:
            await update.message.reply_text(
                "Usage: /setalertwindow HH-HH\n"
                "Example: /setalertwindow 08-22\n"
                "Signals outside your window will be queued and sent as a digest.\n"
                "Use /setalertwindow 00-23 to receive all alerts.",
                parse_mode="HTML",
            )
            return

        try:
            start, end = map(int, args[0].split("-"))
            if not (0 <= start <= 23 and 0 <= end <= 23):
                raise ValueError("Hours must be 0-23")
            chat_id = str(update.effective_chat.id)
            self._alert_windows[chat_id] = {"start": start, "end": end}
            await update.message.reply_text(
                f"\u2705 Alert window set: {start:02d}:00 \u2013 {end:02d}:00 UTC\n"
                f"Signals outside this window will be queued.\n"
                f">80% confidence signals are always delivered immediately.",
                parse_mode="HTML",
            )
        except (ValueError, IndexError):
            await update.message.reply_text(
                "Invalid format. Use: /setalertwindow 08-22",
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
