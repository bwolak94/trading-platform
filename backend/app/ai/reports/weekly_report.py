"""Weekly performance report generator.

Scheduled every Monday at 08:00 UTC to summarise the prior week's
paper-trading activity and dispatch via Telegram, Discord, and email.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


async def generate_weekly_report() -> None:
    """Generate and send weekly trading report every Monday at 08:00 UTC."""
    try:
        logger.info("Generating weekly trading report...")

        from app.ai.simulation.paper_trading_engine import get_paper_trading_engine

        engine = get_paper_trading_engine()
        perf = engine.get_performance()

        # Performance values
        total_trades: int = perf.get("total_trades", 0)
        win_rate: float = perf.get("win_rate", 0.0)
        total_pnl_pct: float = perf.get("total_pnl_pct", 0.0)
        sharpe_ratio: float = perf.get("sharpe_ratio", 0.0)
        max_drawdown_pct: float = perf.get("max_drawdown_pct", 0.0)
        profit_factor: float = perf.get("profit_factor", 0.0)
        open_positions: int = perf.get("open_positions", 0)
        peak_equity: float = perf.get("peak_equity", 0.0)

        # Date range labels
        now = datetime.now(timezone.utc)
        week_start = (now - timedelta(days=7)).strftime("%b %d")
        week_end = now.strftime("%b %d, %Y")
        pnl_prefix = "+" if total_pnl_pct >= 0 else ""

        report_lines = [
            f"📊 *Weekly Trading Report* — {week_start} to {week_end}",
            "",
            "📈 *Performance Summary*",
            f"• Total Trades: {total_trades}",
            f"• Win Rate: {win_rate * 100:.1f}%",
            f"• Total PnL: {pnl_prefix}{total_pnl_pct:.2f}%",
            f"• Sharpe Ratio: {sharpe_ratio:.2f}",
            f"• Max Drawdown: {max_drawdown_pct:.2f}%",
            f"• Profit Factor: {profit_factor:.2f}",
            "",
            "🤖 *Engine Status*",
            f"• Open Positions: {open_positions}",
            f"• Peak Equity: {peak_equity:.2f}%",
        ]

        # Optional equity-curve context
        try:
            from app.ai.simulation.performance_tracker import get_performance_tracker

            tracker = get_performance_tracker()
            curve = getattr(tracker, "equity_curve", [])
            if curve:
                report_lines.extend([
                    "",
                    "📉 *Recent Activity*",
                    "• Equity progression tracked",
                ])
        except Exception:
            pass

        report_text = "\n".join(report_lines)

        # Send via Telegram
        try:
            from app.notifications.telegram_bot import get_telegram_bot

            bot = get_telegram_bot()
            if bot:
                await bot.send_message(report_text)
        except Exception as exc:
            logger.warning("Telegram weekly report failed: %s", exc)

        # Send via Discord
        try:
            from app.notifications.discord_bot import send_alert_to_discord

            await send_alert_to_discord(
                f"Weekly Report — {week_start} to {week_end}",
                "\n".join(report_lines[3:]),  # Skip the header line
                "info",
            )
        except Exception as exc:
            logger.warning("Discord weekly report failed: %s", exc)

        # Send email digest
        try:
            from app.notifications.email_sender import send_daily_digest

            await send_daily_digest(perf, [])
        except Exception as exc:
            logger.warning("Email weekly report failed: %s", exc)

        logger.info("Weekly report sent successfully")

    except Exception as exc:
        logger.error("Weekly report generation failed: %s", exc, exc_info=True)
