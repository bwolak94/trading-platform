"""Shared symbol constants used across the application."""

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
