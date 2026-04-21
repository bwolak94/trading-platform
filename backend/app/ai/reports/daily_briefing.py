"""Daily Briefing — scheduled at 00:00 UTC to generate and send a performance summary.

Sends via:
- Telegram (existing bot)
- Discord (via webhook)
- Email (via SMTP if configured)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


async def generate_and_send_daily_briefing() -> dict[str, Any]:
    """Generate and send the daily trading briefing.

    Returns a dict with delivery status for each channel.
    """
    logger.info("Daily briefing: generating...")

    # Get performance data
    from app.ai.simulation.paper_trading_engine import get_paper_trading_engine
    engine = get_paper_trading_engine()
    perf = engine.get_performance()

    # Build briefing message
    win_rate = perf.get("win_rate", 0) * 100
    total_pnl = perf.get("total_pnl_pct", 0)
    total_trades = perf.get("total_trades", 0)
    sharpe = perf.get("sharpe_ratio", 0)
    max_dd = perf.get("max_drawdown_pct", 0)
    pnl_prefix = "+" if total_pnl >= 0 else ""

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    telegram_msg = (
        f"📊 *Daily Briefing — {date_str}*\n\n"
        f"📈 Total PnL: *{pnl_prefix}{total_pnl:.2f}%*\n"
        f"🎯 Win Rate: {win_rate:.1f}%\n"
        f"📉 Max Drawdown: {max_dd:.1f}%\n"
        f"⚡ Sharpe Ratio: {sharpe:.2f}\n"
        f"🔢 Total Trades: {total_trades}"
    )

    results: dict[str, bool] = {}

    # Send Telegram
    try:
        from app.notifications.telegram_bot import get_telegram_bot
        bot = get_telegram_bot()
        await bot.send_message(telegram_msg)
        results["telegram"] = True
    except Exception as exc:
        logger.warning("Daily briefing Telegram failed: %s", exc)
        results["telegram"] = False

    # Send Discord
    try:
        from app.notifications.discord_bot import send_alert_to_discord
        await send_alert_to_discord(
            title=f"📊 Daily Briefing — {date_str}",
            message=(
                f"**PnL:** {pnl_prefix}{total_pnl:.2f}% | "
                f"**Win Rate:** {win_rate:.1f}% | "
                f"**Sharpe:** {sharpe:.2f} | "
                f"**Max DD:** {max_dd:.1f}% | "
                f"**Trades:** {total_trades}"
            ),
        )
        results["discord"] = True
    except Exception as exc:
        logger.warning("Daily briefing Discord failed: %s", exc)
        results["discord"] = False

    # Send Email
    try:
        from app.notifications.email_sender import send_daily_digest
        await send_daily_digest(perf)
        results["email"] = True
    except Exception as exc:
        logger.warning("Daily briefing email failed: %s", exc)
        results["email"] = False

    logger.info("Daily briefing sent: %s", results)
    return {"date": date_str, "performance": perf, "delivery": results}
