"""Pydantic schemas for market data."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class OHLCV(BaseModel):
    """Single OHLCV candle."""

    asset: str
    timeframe: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
