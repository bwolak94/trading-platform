"""Tape Reader — detects institutional-sized trades in real-time.

Reads the Binance Futures aggTrades REST endpoint and filters for large
("institutional") notional trades.  Aggregates buy vs sell pressure over
a rolling time window to generate directional bias signals.

Methodology:
  - Institutional threshold: notional ≥ $250,000 USD
  - Bias = (buy_count - sell_count) / total_large_trade_count
  - Strong signal when |bias| ≥ 0.65 (65%+ one-sided flow)

aggTrades endpoint used:
  GET https://fapi.binance.com/fapi/v1/aggTrades?symbol=BTCUSDT&limit=1000
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Final

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FUTURES_AGG_TRADES_URL: Final[str] = "https://fapi.binance.com/fapi/v1/aggTrades"
_HTTP_TIMEOUT: Final[float] = 8.0
_DEFAULT_LIMIT: Final[int] = 1000


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class LargeTrade:
    """A single institutional-sized trade from the tape."""

    symbol: str
    side: str           # "BUY" or "SELL"
    price: float
    quantity: float
    notional_usd: float
    timestamp: datetime
    is_institutional: bool  # True when notional ≥ threshold

    def __repr__(self) -> str:
        ts = self.timestamp.isoformat()
        return (
            f"LargeTrade(symbol={self.symbol!r}, side={self.side}, "
            f"price={self.price:.2f}, qty={self.quantity:.4f}, "
            f"notional=${self.notional_usd:,.0f}, ts={ts})"
        )


@dataclass
class TapeReaderResult:
    """Aggregated result from tape reading analysis."""

    symbol: str
    institutional_bias: float    # -1.0 to +1.0 (positive = buy pressure)
    buy_pressure_pct: float      # % of large trades that are buys
    large_trade_count: int       # total institutional trades in window
    largest_trade_usd: float     # single largest trade in window
    window_minutes: int
    signal: str                  # "STRONG_BUY_PRESSURE", "STRONG_SELL_PRESSURE",
                                 # "MODERATE_BUY_PRESSURE", "MODERATE_SELL_PRESSURE",
                                 # "NEUTRAL"

    def __repr__(self) -> str:
        return (
            f"TapeReaderResult(symbol={self.symbol!r}, "
            f"bias={self.institutional_bias:+.2f}, "
            f"buy_pct={self.buy_pressure_pct:.1f}%, "
            f"trades={self.large_trade_count}, "
            f"signal={self.signal!r})"
        )


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class TapeReader:
    """Analyzes recent aggTrades to detect institutional activity.

    Usage::

        reader = TapeReader()
        trades = await reader.fetch_recent_large_trades("BTCUSDT")
        result = reader.analyze("BTCUSDT", window_minutes=15)
    """

    INSTITUTIONAL_THRESHOLD_USD: float = 250_000.0  # $250K+
    STRONG_BIAS_THRESHOLD: float = 0.65             # 65%+ one-sided = strong signal
    MODERATE_BIAS_THRESHOLD: float = 0.55           # 55%+ = moderate signal

    def __init__(self) -> None:
        # Per-symbol ring buffer of large trades
        self._trade_history: dict[str, deque[LargeTrade]] = {}
        self._max_history: int = 1000

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    async def fetch_recent_large_trades(
        self,
        symbol: str,
        limit: int = _DEFAULT_LIMIT,
    ) -> list[LargeTrade]:
        """Fetch recent aggTrades from Binance Futures REST and filter for large ones.

        Args:
            symbol: Binance futures symbol, e.g. "BTCUSDT".
            limit:  Number of aggTrades to fetch (max 1000).

        Returns:
            List of LargeTrade objects with notional ≥ INSTITUTIONAL_THRESHOLD_USD.
        """
        symbol = symbol.upper()
        params = {"symbol": symbol, "limit": min(limit, 1000)}

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                response = await client.get(_FUTURES_AGG_TRADES_URL, params=params)
                response.raise_for_status()
                raw_trades: list[dict[str, Any]] = response.json()
        except httpx.TimeoutException:
            logger.warning("TapeReader: request timeout for %s", symbol)
            return []
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "TapeReader: HTTP error for %s",
                symbol,
                extra={"status_code": exc.response.status_code},
            )
            return []
        except Exception as exc:
            logger.error(
                "TapeReader: unexpected error fetching %s",
                symbol,
                extra={"error": str(exc)},
            )
            return []

        large_trades: list[LargeTrade] = []
        for raw in raw_trades:
            try:
                price = float(raw.get("p", 0.0))
                quantity = float(raw.get("q", 0.0))
                is_buyer_maker = bool(raw.get("m", False))
                trade_ts_ms = int(raw.get("T", 0))

                if price <= 0 or quantity <= 0:
                    continue

                notional_usd = price * quantity
                if notional_usd < self.INSTITUTIONAL_THRESHOLD_USD:
                    continue

                # aggTrade 'm' field: True = buyer is market maker → seller is aggressor = SELL
                side = "SELL" if is_buyer_maker else "BUY"
                timestamp = datetime.fromtimestamp(trade_ts_ms / 1000.0, tz=timezone.utc)

                trade = LargeTrade(
                    symbol=symbol,
                    side=side,
                    price=price,
                    quantity=quantity,
                    notional_usd=notional_usd,
                    timestamp=timestamp,
                    is_institutional=notional_usd >= self.INSTITUTIONAL_THRESHOLD_USD,
                )
                large_trades.append(trade)
            except (KeyError, TypeError, ValueError) as exc:
                logger.debug("TapeReader: skipping malformed trade record: %s", exc)
                continue

        # Store in history ring buffer
        if symbol not in self._trade_history:
            self._trade_history[symbol] = deque(maxlen=self._max_history)
        self._trade_history[symbol].extend(large_trades)

        logger.info(
            "TapeReader: fetched trades for %s",
            symbol,
            extra={
                "total_fetched": len(raw_trades),
                "large_trades": len(large_trades),
                "threshold_usd": self.INSTITUTIONAL_THRESHOLD_USD,
            },
        )
        return large_trades

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def analyze(
        self,
        symbol: str,
        window_minutes: int = 15,
    ) -> TapeReaderResult:
        """Analyze recent large trades within the time window.

        Args:
            symbol:         Binance futures symbol, e.g. "BTCUSDT".
            window_minutes: Look-back window in minutes.

        Returns:
            TapeReaderResult with bias, pressure metrics, and signal label.
        """
        symbol = symbol.upper()
        history = self._trade_history.get(symbol, deque())

        cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=window_minutes)
        window_trades = [t for t in history if t.timestamp >= cutoff]

        if not window_trades:
            logger.debug(
                "TapeReader.analyze: no large trades in window for %s", symbol
            )
            return TapeReaderResult(
                symbol=symbol,
                institutional_bias=0.0,
                buy_pressure_pct=50.0,
                large_trade_count=0,
                largest_trade_usd=0.0,
                window_minutes=window_minutes,
                signal="NEUTRAL",
            )

        buy_trades = [t for t in window_trades if t.side == "BUY"]
        sell_trades = [t for t in window_trades if t.side == "SELL"]
        total_count = len(window_trades)

        buy_count = len(buy_trades)
        sell_count = len(sell_trades)

        # Bias: +1 = all buys, -1 = all sells, 0 = balanced
        institutional_bias = (buy_count - sell_count) / max(total_count, 1)

        buy_pressure_pct = (buy_count / total_count) * 100.0

        largest_trade_usd = max(t.notional_usd for t in window_trades)

        signal = self.get_signal(
            TapeReaderResult(
                symbol=symbol,
                institutional_bias=institutional_bias,
                buy_pressure_pct=buy_pressure_pct,
                large_trade_count=total_count,
                largest_trade_usd=largest_trade_usd,
                window_minutes=window_minutes,
                signal="NEUTRAL",  # placeholder, overwritten below
            )
        )

        logger.info(
            "TapeReader analysis completed",
            extra={
                "symbol": symbol,
                "window_min": window_minutes,
                "total_trades": total_count,
                "bias": round(institutional_bias, 3),
                "signal": signal,
            },
        )

        return TapeReaderResult(
            symbol=symbol,
            institutional_bias=round(institutional_bias, 4),
            buy_pressure_pct=round(buy_pressure_pct, 1),
            large_trade_count=total_count,
            largest_trade_usd=round(largest_trade_usd, 2),
            window_minutes=window_minutes,
            signal=signal,
        )

    def get_signal(self, result: TapeReaderResult) -> str:
        """Convert a bias score to a descriptive signal label.

        Args:
            result: TapeReaderResult with institutional_bias set.

        Returns:
            Signal label string.
        """
        bias = result.institutional_bias

        if result.large_trade_count == 0:
            return "NEUTRAL"

        if bias >= self.STRONG_BIAS_THRESHOLD:
            return "STRONG_BUY_PRESSURE"
        if bias >= self.MODERATE_BIAS_THRESHOLD:
            return "MODERATE_BUY_PRESSURE"
        if bias <= -self.STRONG_BIAS_THRESHOLD:
            return "STRONG_SELL_PRESSURE"
        if bias <= -self.MODERATE_BIAS_THRESHOLD:
            return "MODERATE_SELL_PRESSURE"
        return "NEUTRAL"

    # ------------------------------------------------------------------
    # Convenience aggregation
    # ------------------------------------------------------------------

    def get_trade_stats(self, symbol: str, window_minutes: int = 15) -> dict:
        """Return detailed statistics about large trades in the window.

        Args:
            symbol:         Binance futures symbol.
            window_minutes: Look-back window in minutes.

        Returns:
            Dict with buy_notional, sell_notional, trade_count breakdown,
            and largest individual trades.
        """
        symbol = symbol.upper()
        history = self._trade_history.get(symbol, deque())
        cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=window_minutes)
        window_trades = [t for t in history if t.timestamp >= cutoff]

        if not window_trades:
            return {
                "symbol": symbol,
                "window_minutes": window_minutes,
                "total_count": 0,
                "buy_count": 0,
                "sell_count": 0,
                "buy_notional_usd": 0.0,
                "sell_notional_usd": 0.0,
                "largest_trades": [],
            }

        buy_trades = [t for t in window_trades if t.side == "BUY"]
        sell_trades = [t for t in window_trades if t.side == "SELL"]

        buy_notional = sum(t.notional_usd for t in buy_trades)
        sell_notional = sum(t.notional_usd for t in sell_trades)

        # Top 5 largest trades for context
        top_trades = sorted(window_trades, key=lambda t: t.notional_usd, reverse=True)[:5]

        return {
            "symbol": symbol,
            "window_minutes": window_minutes,
            "total_count": len(window_trades),
            "buy_count": len(buy_trades),
            "sell_count": len(sell_trades),
            "buy_notional_usd": round(buy_notional, 2),
            "sell_notional_usd": round(sell_notional, 2),
            "notional_bias": round(
                (buy_notional - sell_notional) / max(buy_notional + sell_notional, 1.0), 4
            ),
            "largest_trades": [
                {
                    "side": t.side,
                    "price": t.price,
                    "notional_usd": round(t.notional_usd, 2),
                    "timestamp": t.timestamp.isoformat(),
                }
                for t in top_trades
            ],
        }
