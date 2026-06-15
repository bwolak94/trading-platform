"""Email Sender — sends HTML email digests for daily performance summaries.

Configuration via environment variables:
  EMAIL_SMTP_HOST=smtp.gmail.com
  EMAIL_SMTP_PORT=587
  EMAIL_SMTP_USER=your@email.com
  EMAIL_SMTP_PASS=your_app_password
  EMAIL_RECIPIENT=recipient@email.com

Uses only stdlib `smtplib` + `email` — no external dependencies.
"""

from __future__ import annotations

import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

SMTP_HOST = os.environ.get("EMAIL_SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("EMAIL_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("EMAIL_SMTP_USER", "")
SMTP_PASS = os.environ.get("EMAIL_SMTP_PASS", "")
EMAIL_RECIPIENT = os.environ.get("EMAIL_RECIPIENT", "")


def is_configured() -> bool:
    """Return True if email is configured."""
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASS and EMAIL_RECIPIENT)


async def send_daily_digest(performance: dict[str, Any], top_signals: list[dict] | None = None) -> bool:
    """Send a daily HTML performance digest email.

    Args:
        performance: Performance snapshot dict (win_rate, total_pnl_pct, etc.)
        top_signals: Optional list of top signal dicts

    Returns:
        True on success, False on failure
    """
    if not is_configured():
        logger.debug("Email not configured — skipping daily digest")
        return False

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    win_rate = performance.get("win_rate", 0) * 100
    total_pnl = performance.get("total_pnl_pct", 0)
    sharpe = performance.get("sharpe_ratio", 0)
    max_dd = performance.get("max_drawdown_pct", 0)
    total_trades = performance.get("total_trades", 0)

    pnl_color = "#4ade80" if total_pnl >= 0 else "#f87171"
    pnl_prefix = "+" if total_pnl >= 0 else ""

    signals_html = ""
    if top_signals:
        rows = "".join(
            f"<tr><td>{s.get('asset', s.get('symbol','?'))}</td>"
            f"<td style='color:{'#4ade80' if s.get('direction','') == 'LONG' else '#f87171'}'>{s.get('direction', '?')}</td>"
            f"<td>{s.get('confidence', 0)}%</td>"
            f"<td>{s.get('strategy_name', '?')}</td></tr>"
            for s in top_signals[:5]
        )
        signals_html = f"""
        <h2 style='color:#e4e4e7'>Top Signals Today</h2>
        <table border='0' cellpadding='8' cellspacing='0' style='width:100%;border-collapse:collapse;background:#18181b;border-radius:8px'>
        <tr style='color:#71717a;font-size:12px'><th>Asset</th><th>Direction</th><th>Confidence</th><th>Strategy</th></tr>
        {rows}
        </table>"""

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style='background:#09090b;color:#e4e4e7;font-family:system-ui,sans-serif;padding:24px;'>
    <div style='max-width:600px;margin:0 auto'>
        <h1 style='color:#ffffff;border-bottom:1px solid #27272a;padding-bottom:12px'>
            📊 AI Trading Navigator — Daily Report
        </h1>
        <p style='color:#71717a'>{date_str} UTC</p>

        <h2 style='color:#e4e4e7'>Performance Summary</h2>
        <table border='0' cellpadding='12' cellspacing='0' style='width:100%;border-collapse:collapse'>
        <tr>
            <td style='background:#18181b;border-radius:8px;text-align:center;padding:16px'>
                <div style='color:#71717a;font-size:12px'>Total PnL</div>
                <div style='color:{pnl_color};font-size:24px;font-weight:bold'>{pnl_prefix}{total_pnl:.2f}%</div>
            </td>
            <td style='background:#18181b;border-radius:8px;text-align:center;padding:16px;margin-left:8px'>
                <div style='color:#71717a;font-size:12px'>Win Rate</div>
                <div style='color:#e4e4e7;font-size:24px;font-weight:bold'>{win_rate:.1f}%</div>
            </td>
        </tr>
        <tr>
            <td style='background:#18181b;border-radius:8px;text-align:center;padding:16px'>
                <div style='color:#71717a;font-size:12px'>Sharpe Ratio</div>
                <div style='color:#e4e4e7;font-size:24px;font-weight:bold'>{sharpe:.2f}</div>
            </td>
            <td style='background:#18181b;border-radius:8px;text-align:center;padding:16px'>
                <div style='color:#71717a;font-size:12px'>Max Drawdown</div>
                <div style='color:#f87171;font-size:24px;font-weight:bold'>{max_dd:.1f}%</div>
            </td>
        </tr>
        </table>
        <p style='color:#71717a;font-size:12px;text-align:center'>{total_trades} total trades</p>

        {signals_html}

        <p style='color:#52525b;font-size:11px;text-align:center;margin-top:32px'>
            AI Trading Navigator — For educational and research purposes only. Not financial advice.
        </p>
    </div>
    </body>
    </html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"AI Trading Navigator — Daily Report {date_str}"
    msg["From"] = SMTP_USER
    msg["To"] = EMAIL_RECIPIENT
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, EMAIL_RECIPIENT, msg.as_string())
        logger.info("Daily digest email sent to %s", EMAIL_RECIPIENT)
        return True
    except Exception as exc:
        logger.error("Failed to send daily digest email: %s", exc)
        return False
