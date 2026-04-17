"""Macro Economic Calendar Fetcher — retrieves upcoming economic events from public APIs."""

import logging
from datetime import datetime, timedelta, timezone
from enum import Enum

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ImpactLevel(str, Enum):
    """Economic event impact classification."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EconomicEvent(BaseModel):
    """Single economic calendar event."""

    date: str
    time: str
    currency: str
    impact: ImpactLevel
    event_name: str
    actual: str | None = None
    forecast: str | None = None
    previous: str | None = None


class MacroCalendarResponse(BaseModel):
    """Response wrapper for calendar events."""

    events: list[EconomicEvent]
    fetched_at: str
    source: str
    hours_ahead: int


# Mapping of tradingeconomics importance to our impact levels
_IMPORTANCE_MAP = {
    1: ImpactLevel.LOW,
    2: ImpactLevel.MEDIUM,
    3: ImpactLevel.HIGH,
}

# Nager.Date public holidays don't cover economic events,
# so we use multiple free sources with fallback.

# Primary: Financial Modeling Prep (free tier, no key needed for calendar)
_FMP_CALENDAR_URL = "https://financialmodelingprep.com/api/v3/economic_calendar"

# Fallback: DailyFX-style scraping or static high-impact events
_HIGH_IMPACT_RECURRING = [
    {"event_name": "US Non-Farm Payrolls", "currency": "USD", "impact": "HIGH", "day_of_week": 4, "week_of_month": 0},
    {"event_name": "FOMC Interest Rate Decision", "currency": "USD", "impact": "HIGH"},
    {"event_name": "US CPI (YoY)", "currency": "USD", "impact": "HIGH"},
    {"event_name": "US PPI (MoM)", "currency": "USD", "impact": "MEDIUM"},
    {"event_name": "ECB Interest Rate Decision", "currency": "EUR", "impact": "HIGH"},
    {"event_name": "UK CPI (YoY)", "currency": "GBP", "impact": "HIGH"},
    {"event_name": "BoE Interest Rate Decision", "currency": "GBP", "impact": "HIGH"},
    {"event_name": "US Retail Sales (MoM)", "currency": "USD", "impact": "HIGH"},
    {"event_name": "US GDP (QoQ)", "currency": "USD", "impact": "HIGH"},
    {"event_name": "US Initial Jobless Claims", "currency": "USD", "impact": "MEDIUM"},
    {"event_name": "US ISM Manufacturing PMI", "currency": "USD", "impact": "HIGH"},
    {"event_name": "BoJ Interest Rate Decision", "currency": "JPY", "impact": "HIGH"},
]


class MacroCalendarFetcher:
    """Fetches upcoming macro economic events from public calendar APIs.

    Uses Financial Modeling Prep as the primary source with a
    fallback to a curated list of known high-impact recurring events.
    """

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize the fetcher.

        Args:
            api_key: Optional FMP API key for higher rate limits.
                     Works without a key on the free tier with limited requests.
        """
        self._api_key = api_key
        self._timeout = 15.0
        self._user_agent = "TradingAI/1.0"

    async def fetch_upcoming_events(
        self, hours_ahead: int = 24
    ) -> MacroCalendarResponse:
        """Fetch economic events scheduled within the next N hours.

        Args:
            hours_ahead: How many hours into the future to look (default 24).

        Returns:
            MacroCalendarResponse with a list of upcoming EconomicEvent items.
        """
        now = datetime.now(timezone.utc)
        end = now + timedelta(hours=hours_ahead)

        events = await self._fetch_from_fmp(now, end)

        if not events:
            logger.info("FMP returned no events; falling back to curated list")
            events = self._get_fallback_events(now, end)

        # Sort by date+time ascending
        events.sort(key=lambda e: (e.date, e.time))

        return MacroCalendarResponse(
            events=events,
            fetched_at=now.isoformat(),
            source="financialmodelingprep" if events else "fallback_curated",
            hours_ahead=hours_ahead,
        )

    async def _fetch_from_fmp(
        self, start: datetime, end: datetime
    ) -> list[EconomicEvent]:
        """Fetch events from Financial Modeling Prep economic calendar API.

        Args:
            start: Start datetime (UTC).
            end: End datetime (UTC).

        Returns:
            List of parsed EconomicEvent objects.
        """
        params: dict[str, str] = {
            "from": start.strftime("%Y-%m-%d"),
            "to": end.strftime("%Y-%m-%d"),
        }
        if self._api_key:
            params["apikey"] = self._api_key

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    _FMP_CALENDAR_URL,
                    params=params,
                    headers={"User-Agent": self._user_agent},
                )
                if resp.status_code != 200:
                    logger.warning(
                        "FMP calendar API returned status %d: %s",
                        resp.status_code,
                        resp.text[:200],
                    )
                    return []

                data = resp.json()
                if not isinstance(data, list):
                    logger.warning("FMP calendar returned unexpected format")
                    return []

                return self._parse_fmp_events(data, start, end)

        except httpx.RequestError as exc:
            logger.error("Failed to reach FMP calendar API: %s", exc)
            return []
        except Exception as exc:
            logger.error("Unexpected error fetching FMP calendar: %s", exc)
            return []

    def _parse_fmp_events(
        self,
        raw_events: list[dict],
        start: datetime,
        end: datetime,
    ) -> list[EconomicEvent]:
        """Parse raw FMP API response into EconomicEvent objects.

        Args:
            raw_events: Raw JSON list from FMP API.
            start: Filter start datetime.
            end: Filter end datetime.

        Returns:
            Filtered and parsed list of EconomicEvent.
        """
        events: list[EconomicEvent] = []

        for item in raw_events:
            try:
                event_date_str = item.get("date", "")
                if not event_date_str:
                    continue

                # FMP returns date as "YYYY-MM-DD HH:MM:SS" or just "YYYY-MM-DD"
                if " " in event_date_str:
                    date_part, time_part = event_date_str.split(" ", 1)
                    # Trim seconds if present for cleaner display
                    time_display = time_part[:5] if len(time_part) >= 5 else time_part
                else:
                    date_part = event_date_str[:10]
                    time_display = "00:00"

                # Determine impact from the 'impact' field
                raw_impact = str(item.get("impact", "")).upper()
                if raw_impact == "HIGH" or raw_impact == "3":
                    impact = ImpactLevel.HIGH
                elif raw_impact == "MEDIUM" or raw_impact == "2":
                    impact = ImpactLevel.MEDIUM
                else:
                    impact = ImpactLevel.LOW

                # Format numeric values or keep as string
                actual = self._format_value(item.get("actual"))
                forecast = self._format_value(item.get("estimate"))
                previous = self._format_value(item.get("previous"))

                events.append(
                    EconomicEvent(
                        date=date_part,
                        time=time_display,
                        currency=item.get("currency", item.get("country", "N/A")),
                        impact=impact,
                        event_name=item.get("event", "Unknown Event"),
                        actual=actual,
                        forecast=forecast,
                        previous=previous,
                    )
                )
            except (ValueError, KeyError, TypeError) as exc:
                logger.debug("Skipping malformed FMP event: %s — %s", item, exc)
                continue

        return events

    def _get_fallback_events(
        self, start: datetime, end: datetime
    ) -> list[EconomicEvent]:
        """Generate a curated list of known recurring high-impact events.

        This serves as a fallback when external APIs are unavailable. It
        returns the static list tagged with today's date so the UI can
        display a reminder to watch for these events.

        Args:
            start: Range start.
            end: Range end.

        Returns:
            List of placeholder EconomicEvent items.
        """
        today = start.strftime("%Y-%m-%d")
        events: list[EconomicEvent] = []

        for item in _HIGH_IMPACT_RECURRING:
            events.append(
                EconomicEvent(
                    date=today,
                    time="TBD",
                    currency=item["currency"],
                    impact=ImpactLevel(item["impact"]),
                    event_name=f"[Scheduled] {item['event_name']}",
                    actual=None,
                    forecast=None,
                    previous=None,
                )
            )

        return events

    @staticmethod
    def _format_value(value: object) -> str | None:
        """Format a numeric or string value for display.

        Args:
            value: Raw value from API (could be float, int, str, or None).

        Returns:
            Formatted string or None if the value is empty.
        """
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return str(round(value, 3))
        val_str = str(value).strip()
        return val_str if val_str else None


_fetcher: MacroCalendarFetcher | None = None


def get_macro_calendar_fetcher() -> MacroCalendarFetcher:
    """Get or create the singleton MacroCalendarFetcher instance."""
    global _fetcher
    if _fetcher is None:
        _fetcher = MacroCalendarFetcher()
    return _fetcher
