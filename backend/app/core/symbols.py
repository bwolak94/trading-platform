"""Shared symbol constants and dynamic Binance futures symbol loading."""

from __future__ import annotations

CRYPTO_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "DOGE/USDT", "ADA/USDT", "AVAX/USDT", "DOT/USDT", "LINK/USDT",
    "MATIC/USDT", "UNI/USDT", "ATOM/USDT", "LTC/USDT", "FIL/USDT",
    "APT/USDT", "ARB/USDT", "OP/USDT", "SUI/USDT", "PEPE/USDT",
]

FOREX_SYMBOLS = ["EUR/USD", "GBP/USD", "XAU/USD", "GBP/JPY"]

ALL_SYMBOLS = CRYPTO_SYMBOLS + FOREX_SYMBOLS

SYMBOL_TO_BINANCE = {s: s.replace("/", "") for s in CRYPTO_SYMBOLS}
BINANCE_TO_SYMBOL = {v: k for k, v in SYMBOL_TO_BINANCE.items()}

VALID_TIMEFRAMES = {"1m", "5m", "15m", "1h", "4h", "1d"}

# Runtime-loaded symbols — populated at startup via load_dynamic_symbols()
_dynamic_crypto_symbols: list[str] = []


async def load_dynamic_symbols(min_volume_usd: float = 10_000_000.0) -> list[str]:
    """Load all USDT perpetual futures from Binance and cache in memory.

    Falls back to the static CRYPTO_SYMBOLS list if the API call fails.
    Call this once at application startup.

    Args:
        min_volume_usd: Minimum 24h volume to include (default $10M).

    Returns:
        List of symbols in 'BASE/USDT' format.
    """
    global _dynamic_crypto_symbols

    from app.data.fetchers.binance_fetcher import get_all_futures_symbols

    fetched = await get_all_futures_symbols(min_volume_usd=min_volume_usd)
    if fetched:
        _dynamic_crypto_symbols = fetched
    else:
        _dynamic_crypto_symbols = list(CRYPTO_SYMBOLS)

    return _dynamic_crypto_symbols


def get_active_crypto_symbols() -> list[str]:
    """Return dynamically loaded symbols, falling back to static list.

    Always returns at least the static CRYPTO_SYMBOLS if dynamic loading
    has not been called yet.
    """
    return _dynamic_crypto_symbols if _dynamic_crypto_symbols else list(CRYPTO_SYMBOLS)
