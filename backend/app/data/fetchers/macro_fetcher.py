"""Macro data fetcher using Yahoo Finance via yfinance."""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

_cache: Optional[dict] = None
_cache_time: float = 0.0
_CACHE_TTL = 3600  # 1 hour


@dataclass
class MacroData:
    """Container for key macro market indicators."""

    dxy_price: Optional[float]
    dxy_change_pct: Optional[float]
    us10y_yield: Optional[float]
    us10y_change_pct: Optional[float]
    spx_price: Optional[float]
    spx_change_pct: Optional[float]
    btc_correlation_dxy: Optional[float]  # -1 to 1, 7-day rolling
    last_updated: float


async def get_macro_data() -> MacroData:
    """Fetch DXY, US10Y, SPX from yfinance. Results are cached for 1 hour.

    Returns:
        MacroData with all fields populated, or None values on failure.
    """
    global _cache, _cache_time

    now = time.time()
    if _cache and now - _cache_time < _CACHE_TTL:
        return _cache["data"]

    result = await asyncio.to_thread(_fetch_macro_sync)
    _cache = {"data": result}
    _cache_time = now
    return result


def _fetch_macro_sync() -> MacroData:
    """Synchronous worker for yfinance download (runs in thread pool).

    Returns:
        MacroData populated from Yahoo Finance, or empty MacroData on any error.
    """
    try:
        import numpy as np
        import yfinance as yf

        tickers = yf.download(
            ["DX-Y.NYB", "^TNX", "^GSPC", "BTC-USD"],
            period="7d",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )

        closes = tickers["Close"] if "Close" in tickers.columns else tickers

        def get_price_change(ticker: str) -> tuple[Optional[float], Optional[float]]:
            """Extract latest price and 1-day percentage change for a ticker.

            Args:
                ticker: Yahoo Finance ticker symbol.

            Returns:
                Tuple of (price, change_pct), with None for missing data.
            """
            if ticker not in closes.columns:
                return None, None
            col = closes[ticker].dropna()
            if len(col) < 2:
                return None, None
            price = float(col.iloc[-1])
            change = (col.iloc[-1] - col.iloc[-2]) / col.iloc[-2] * 100
            return price, float(change)

        dxy_price, dxy_chg = get_price_change("DX-Y.NYB")
        us10y_price, us10y_chg = get_price_change("^TNX")
        spx_price, spx_chg = get_price_change("^GSPC")

        # BTC vs DXY 7-day rolling correlation
        btc_corr: Optional[float] = None
        if "DX-Y.NYB" in closes.columns and "BTC-USD" in closes.columns:
            dxy_series = closes["DX-Y.NYB"].dropna()
            btc_series = closes["BTC-USD"].dropna()
            common_idx = dxy_series.index.intersection(btc_series.index)
            if len(common_idx) >= 3:
                corr = np.corrcoef(
                    dxy_series[common_idx].values,
                    btc_series[common_idx].values,
                )
                btc_corr = round(float(corr[0, 1]), 3)

        return MacroData(
            dxy_price=round(dxy_price, 2) if dxy_price is not None else None,
            dxy_change_pct=round(dxy_chg, 3) if dxy_chg is not None else None,
            us10y_yield=round(us10y_price, 3) if us10y_price is not None else None,
            us10y_change_pct=round(us10y_chg, 3) if us10y_chg is not None else None,
            spx_price=round(spx_price, 2) if spx_price is not None else None,
            spx_change_pct=round(spx_chg, 3) if spx_chg is not None else None,
            btc_correlation_dxy=btc_corr,
            last_updated=time.time(),
        )
    except Exception as e:
        logger.warning("Macro fetch failed: %s", e)
        return MacroData(
            dxy_price=None,
            dxy_change_pct=None,
            us10y_yield=None,
            us10y_change_pct=None,
            spx_price=None,
            spx_change_pct=None,
            btc_correlation_dxy=None,
            last_updated=time.time(),
        )
