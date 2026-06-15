"""Morning AI Briefing — comprehensive daily market briefing at 07:00 UTC."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.core.logging import get_logger

logger = get_logger(__name__)


class MorningBriefingGenerator:
    """Generate a comprehensive daily briefing sent at 07:00 UTC via Telegram.

    Sections:
    1. Header with date and overall market sentiment
    2. Overnight movers (>3% moves in last 24h ticker)
    3. Current regime status for BTC, ETH, SOL, BNB
    4. Risk events next 24h (macro calendar placeholder)
    5. Seasonality note (today's historical performance by weekday)
    """

    async def generate(self, user_id: str = "default") -> str:
        """Generate the morning briefing text for Telegram (HTML formatted).

        All sub-sections are fetched concurrently; individual failures are
        caught and replaced with a graceful fallback string so the overall
        briefing is always delivered.

        Args:
            user_id: Identifier of the user receiving the briefing (reserved
                     for future per-user personalisation).

        Returns:
            HTML-formatted briefing string ready for bot.send_message().
        """
        try:
            sections = await asyncio.gather(
                self._overnight_movers(),
                self._regime_status(),
                self._upcoming_events(),
                self._seasonality_note(),
                return_exceptions=True,
            )

            movers = sections[0] if not isinstance(sections[0], Exception) else "Unavailable"
            regime = sections[1] if not isinstance(sections[1], Exception) else "Unavailable"
            events = sections[2] if not isinstance(sections[2], Exception) else "No data"
            seasonal = sections[3] if not isinstance(sections[3], Exception) else ""

            now = datetime.now(timezone.utc)

            briefing = (
                f"\U0001f305 <b>Morning Briefing \u2014 {now.strftime('%A, %B %d')}</b>\n\n"
                f"\U0001f4ca <b>Overnight Movers</b>\n{movers}\n\n"
                f"\U0001f3af <b>Regime Status</b>\n{regime}\n\n"
                f"\U0001f4c5 <b>Risk Events (Next 24h)</b>\n{events}\n\n"
                f"\U0001f4c8 <b>Seasonality</b>\n{seasonal}\n\n"
                f"\u23f0 Next briefing tomorrow 07:00 UTC"
            )
            return briefing

        except Exception as exc:
            logger.error("Morning briefing generation failed: %s", exc)
            now = datetime.now(timezone.utc)
            return (
                f"\U0001f305 Morning Briefing \u2014 {now.strftime('%A, %B %d')}\n\n"
                f"Briefing generation failed: {exc}"
            )

    async def _overnight_movers(self) -> str:
        """Fetch symbols with >3% moves from Binance 24h futures ticker.

        Returns the top 5 absolute movers formatted with direction emoji.
        Falls back to a human-readable error string on any network failure.
        """
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get("https://fapi.binance.com/fapi/v1/ticker/24hr")
                if r.status_code != 200:
                    return "Data unavailable"
                tickers = r.json()

            movers: list[tuple[str, float]] = []
            for t in tickers:
                pct = float(t.get("priceChangePercent", 0))
                symbol: str = t.get("symbol", "")
                if abs(pct) >= 3.0 and symbol.endswith("USDT"):
                    movers.append((symbol.replace("USDT", ""), pct))

            movers.sort(key=lambda x: abs(x[1]), reverse=True)
            top = movers[:5]

            if not top:
                return "No major movers (all changes <3%)"

            lines = []
            for sym, pct in top:
                arrow = "\U0001f7e2" if pct > 0 else "\U0001f534"
                lines.append(f"{arrow} {sym}: {pct:+.1f}%")
            return "\n".join(lines)

        except Exception as exc:
            return f"Movers unavailable: {exc}"

    async def _regime_status(self) -> str:
        """Get current regime classification for key crypto assets.

        Attempts to query the internal regime endpoint. Falls back to a
        placeholder string if the service is not reachable.
        """
        key_assets = ["BTC", "ETH", "SOL", "BNB"]
        lines: list[str] = []

        try:
            import httpx

            async with httpx.AsyncClient(timeout=8) as client:
                for sym in key_assets:
                    try:
                        r = await client.get(
                            f"http://localhost:8000/api/v1/market/regime?symbol={sym}USDT"
                        )
                        if r.status_code == 200:
                            data = r.json()
                            regime_raw: str = data.get("regime", "UNKNOWN")
                            regime_map = {
                                "TREND_BULL": "\U0001f4c8 Bull Trend",
                                "TREND_BEAR": "\U0001f4c9 Bear Trend",
                                "CONSOLIDATION": "\u2194\ufe0f Range",
                                "HIGH_VOL_CHOPPY": "\u26a1 Volatile/Choppy",
                                "UNKNOWN": "\u2753 Unknown",
                            }
                            label = regime_map.get(regime_raw, regime_raw)
                            lines.append(f"{sym}: {label}")
                        else:
                            lines.append(f"{sym}: Detecting\u2026")
                    except Exception:
                        lines.append(f"{sym}: Unavailable")
        except Exception:
            lines = [f"{sym}: Unavailable" for sym in key_assets]

        return "\n".join(lines)

    async def _upcoming_events(self) -> str:
        """Return high-impact macro events in the next 24h.

        Currently returns a static prompt directing the user to the events
        endpoint. Future versions will integrate a live economic calendar API.
        """
        return "Check /events for full calendar\nNo automated calendar feed configured"

    async def _seasonality_note(self) -> str:
        """Return a day-of-week seasonality note based on historical patterns.

        Uses a static lookup table of weekday tendencies for crypto markets.
        """
        day = datetime.now(timezone.utc).strftime("%A")
        day_notes: dict[str, str] = {
            "Monday": "Mondays historically show mixed opens after weekend low-liquidity.",
            "Tuesday": "Tuesdays tend to be strong continuation days in trending markets.",
            "Wednesday": "Mid-week — volatility often increases around NY session open.",
            "Thursday": "Pre-Friday repositioning; watch for stop hunts near key levels.",
            "Friday": "Fridays: position reduction before weekend \u2014 consider reducing exposure.",
            "Saturday": "Low liquidity; avoid large entries; spreads widen on altcoins.",
            "Sunday": "Pre-week accumulation patterns sometimes visible in late Asian session.",
        }
        return day_notes.get(day, "")


# Module-level singleton

_briefing_generator: MorningBriefingGenerator | None = None


def get_morning_briefing_generator() -> MorningBriefingGenerator:
    """Return the module-level MorningBriefingGenerator singleton.

    Creates the instance on first call (lazy initialisation).
    """
    global _briefing_generator
    if _briefing_generator is None:
        _briefing_generator = MorningBriefingGenerator()
    return _briefing_generator
