"""Correlation matrix computation for multiple trading symbols."""

import logging

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

# Binance kline interval to approximate milliseconds mapping
_INTERVAL_MS: dict[str, int] = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"


async def _fetch_close_series(
    client: httpx.AsyncClient,
    symbol: str,
    interval: str,
    limit: int,
) -> pd.Series | None:
    """Fetch close prices for a single symbol from Binance.

    Returns a pandas Series indexed by open-time (epoch ms), or None on failure.
    """
    try:
        resp = await client.get(
            BINANCE_KLINES_URL,
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        resp.raise_for_status()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        logger.warning("Failed to fetch klines for %s: %s", symbol, exc)
        return None

    raw: list[list] = resp.json()
    if not raw:
        return None

    times = [int(k[0]) for k in raw]
    closes = [float(k[4]) for k in raw]
    return pd.Series(closes, index=times, name=symbol)


async def compute_correlation_matrix(
    symbols: list[str],
    timeframe: str = "4h",
    lookback_days: int = 30,
) -> dict:
    """Compute Pearson correlation matrix of close prices for given symbols.

    Fetches kline data from Binance for each symbol, aligns them by
    timestamp, and computes pairwise Pearson correlations on
    percent-change returns.

    Args:
        symbols: List of Binance trading pair symbols (e.g. ["BTCUSDT", "ETHUSDT"]).
        timeframe: Kline interval string accepted by Binance (e.g. "1h", "4h", "1d").
        lookback_days: Number of days of historical data to use.

    Returns:
        Dictionary with keys:
            - symbols: list of symbols that had valid data
            - matrix: 2D list of correlation coefficients (floats)
            - timeframe: the timeframe used
            - lookback_days: the lookback period used
    """
    if not symbols:
        return {
            "symbols": [],
            "matrix": [],
            "timeframe": timeframe,
            "lookback_days": lookback_days,
        }

    interval_ms = _INTERVAL_MS.get(timeframe, 14_400_000)
    limit = min(int(lookback_days * 86_400_000 / interval_ms), 1000)

    async with httpx.AsyncClient(timeout=15.0) as client:
        series_list: list[pd.Series | None] = []
        for symbol in symbols:
            series = await _fetch_close_series(client, symbol, timeframe, limit)
            series_list.append(series)

    # Filter out symbols that returned no data
    valid_symbols: list[str] = []
    valid_series: list[pd.Series] = []
    for symbol, series in zip(symbols, series_list):
        if series is not None and not series.empty:
            valid_symbols.append(symbol)
            valid_series.append(series)

    if len(valid_series) < 2:
        # Not enough data to compute correlations — return identity-like result
        n = len(valid_symbols)
        identity = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
        return {
            "symbols": valid_symbols,
            "matrix": identity,
            "timeframe": timeframe,
            "lookback_days": lookback_days,
        }

    # Build a DataFrame aligned on the shared timestamps
    df = pd.concat(valid_series, axis=1, join="inner")
    df.columns = valid_symbols

    # Use percent-change returns to measure co-movement rather than raw prices
    returns = df.pct_change().dropna()

    if returns.empty or len(returns) < 2:
        n = len(valid_symbols)
        identity = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
        return {
            "symbols": valid_symbols,
            "matrix": identity,
            "timeframe": timeframe,
            "lookback_days": lookback_days,
        }

    corr: pd.DataFrame = returns.corr(method="pearson")

    # Replace any NaN with 0.0 for JSON serialisation safety
    corr = corr.fillna(0.0)

    matrix = [[round(float(corr.iloc[i, j]), 4) for j in range(len(valid_symbols))] for i in range(len(valid_symbols))]

    return {
        "symbols": valid_symbols,
        "matrix": matrix,
        "timeframe": timeframe,
        "lookback_days": lookback_days,
    }
