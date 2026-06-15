"""Earnings and economic events calendar endpoint."""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Query

router = APIRouter(tags=["calendar"])

# Hardcoded upcoming crypto events (in production, fetch from CoinGecko or CryptoCompare)
CRYPTO_EVENTS: list[dict[str, Any]] = [
    {
        "asset": "ETH",
        "event": "Ethereum Pectra Upgrade",
        "date": "2025-05-07",
        "impact": "HIGH",
        "type": "protocol",
    },
    {
        "asset": "BTC",
        "event": "Bitcoin Halving Anniversary",
        "date": "2025-04-19",
        "impact": "MEDIUM",
        "type": "milestone",
    },
    {
        "asset": "SOL",
        "event": "Solana Breakpoint Conference",
        "date": "2025-09-20",
        "impact": "MEDIUM",
        "type": "conference",
    },
    {
        "asset": "ETH",
        "event": "Ethereum Devcon 2025",
        "date": "2025-11-12",
        "impact": "MEDIUM",
        "type": "conference",
    },
    {
        "asset": "BTC",
        "event": "CME Bitcoin Futures Expiry (monthly)",
        "date": "2025-05-30",
        "impact": "MEDIUM",
        "type": "derivatives",
    },
]


@router.get("/calendar/events")
async def get_upcoming_events(
    days_ahead: int = Query(default=30, ge=1, le=365),
) -> dict[str, Any]:
    """Get upcoming crypto and macro events that may impact trading.

    Returns events within the next N days, sorted ascending by days_until.
    Also attempts to fetch from the macro_calendar fetcher if available.

    Returns:
        {
            "events": [
                {
                    "asset": str | None,
                    "event": str,
                    "date": str,
                    "days_until": int,
                    "impact": "HIGH" | "MEDIUM" | "LOW",
                    "type": "protocol" | "macro" | "conference" | "milestone" | "derivatives",
                    "should_avoid_trading": bool
                }
            ],
            "total": int,
            "days_ahead": int,
            "generated_at": str,
        }
    """
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days_ahead)

    events: list[dict[str, Any]] = []

    # Process hardcoded crypto events
    for e in CRYPTO_EVENTS:
        try:
            event_date = datetime.fromisoformat(e["date"]).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        if event_date > cutoff:
            continue

        days_until = max(0, (event_date - now).days)
        # Avoid trading on HIGH-impact events that are happening today (days_until <= 0)
        should_avoid = e["impact"] == "HIGH" and days_until <= 0

        events.append(
            {
                "asset": e.get("asset"),
                "event": e["event"],
                "date": e["date"],
                "days_until": days_until,
                "impact": e["impact"],
                "type": e["type"],
                "should_avoid_trading": should_avoid,
            }
        )

    # Attempt to enrich with macro calendar if available
    try:
        from app.data.fetchers.macro_calendar import get_macro_calendar

        macro = get_macro_calendar()
        if hasattr(macro, "get_upcoming_events"):
            macro_events = await macro.get_upcoming_events()
            for me in macro_events[:10]:
                event_date_raw = me.get("date")
                if event_date_raw:
                    try:
                        event_dt = datetime.fromisoformat(str(event_date_raw)).replace(
                            tzinfo=timezone.utc
                        )
                        days_until = max(0, (event_dt - now).days)
                    except Exception:
                        days_until = me.get("days_until", 0)
                else:
                    days_until = me.get("days_until", 0)

                if days_until > days_ahead:
                    continue

                events.append(
                    {
                        "asset": None,
                        "event": me.get("event", ""),
                        "date": str(me.get("date", "")),
                        "days_until": days_until,
                        "impact": me.get("impact", "MEDIUM"),
                        "type": "macro",
                        "should_avoid_trading": False,
                    }
                )
    except Exception:
        pass  # Macro calendar is optional

    events.sort(key=lambda x: x.get("days_until", 999))

    return {
        "events": events,
        "total": len(events),
        "days_ahead": days_ahead,
        "generated_at": now.isoformat(),
    }
