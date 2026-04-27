"""E6: Structured error codes for the AI Trading Navigator platform.

All API error responses should include one of these codes so that the frontend
can display specific, actionable messages instead of generic "Something went
wrong" text.

Error code format:  E{category}{number}
  E1xx — Database / persistence errors
  E2xx — External API / data-feed errors
  E3xx — Signal / AI pipeline errors
  E4xx — Risk management errors
  E5xx — Authentication / authorisation errors
  E6xx — Rate limit / quota errors
  E7xx — Validation / input errors
"""

from enum import Enum


class ErrorCode(str, Enum):
    """Typed error codes emitted by the platform."""

    # Database
    DB_TIMEOUT = "E101"
    DB_CONNECTION_FAILED = "E102"
    DB_QUERY_FAILED = "E103"

    # External APIs
    BINANCE_RATE_LIMIT = "E201"
    BINANCE_UNAVAILABLE = "E202"
    DATA_FETCH_FAILED = "E203"
    WEBSOCKET_DISCONNECTED = "E204"

    # Signal / AI pipeline
    SIGNAL_REJECTED = "E301"
    SIGNAL_QUALITY_GATE_FAILED = "E302"
    SIGNAL_DUPLICATE = "E303"
    SIGNAL_CONTRADICTION = "E304"
    INSUFFICIENT_DATA = "E305"
    REGIME_UNKNOWN = "E306"
    STRATEGY_TIMEOUT = "E307"

    # Risk management
    KILL_SWITCH_ACTIVE = "E401"
    DAILY_LOSS_LIMIT_HIT = "E402"
    CORRELATION_CAP_EXCEEDED = "E403"
    MAX_CONCURRENT_SIGNALS = "E404"
    DRAWDOWN_LIMIT_HIT = "E405"

    # Auth
    INVALID_CREDENTIALS = "E501"
    TOKEN_EXPIRED = "E502"
    INSUFFICIENT_PERMISSIONS = "E503"

    # Rate limits
    RATE_LIMIT_EXCEEDED = "E601"
    QUOTA_EXHAUSTED = "E602"

    # Validation
    INVALID_SYMBOL = "E701"
    INVALID_TIMEFRAME = "E702"
    INVALID_DATE_RANGE = "E703"
    PAYLOAD_TOO_LARGE = "E704"


# Human-readable descriptions for each error code
ERROR_DESCRIPTIONS: dict[ErrorCode, str] = {
    ErrorCode.DB_TIMEOUT: "Database query timed out — try again shortly",
    ErrorCode.DB_CONNECTION_FAILED: "Cannot connect to database",
    ErrorCode.DB_QUERY_FAILED: "Database query failed",
    ErrorCode.BINANCE_RATE_LIMIT: "Binance API rate limit reached — requests throttled",
    ErrorCode.BINANCE_UNAVAILABLE: "Binance API is currently unavailable",
    ErrorCode.DATA_FETCH_FAILED: "Failed to fetch market data from external source",
    ErrorCode.WEBSOCKET_DISCONNECTED: "Real-time data feed disconnected",
    ErrorCode.SIGNAL_REJECTED: "Signal was rejected by the aggregator",
    ErrorCode.SIGNAL_QUALITY_GATE_FAILED: "Signal did not meet minimum quality criteria",
    ErrorCode.SIGNAL_DUPLICATE: "Duplicate signal suppressed by cooldown filter",
    ErrorCode.SIGNAL_CONTRADICTION: "Contradictory signals detected for same asset",
    ErrorCode.INSUFFICIENT_DATA: "Not enough historical data to generate a signal",
    ErrorCode.REGIME_UNKNOWN: "Market regime could not be classified",
    ErrorCode.STRATEGY_TIMEOUT: "Strategy took too long to execute",
    ErrorCode.KILL_SWITCH_ACTIVE: "Kill switch is active — trading halted due to drawdown",
    ErrorCode.DAILY_LOSS_LIMIT_HIT: "Daily loss limit reached — new signals suppressed",
    ErrorCode.CORRELATION_CAP_EXCEEDED: "Correlated position exposure cap exceeded",
    ErrorCode.MAX_CONCURRENT_SIGNALS: "Maximum concurrent active signals reached",
    ErrorCode.DRAWDOWN_LIMIT_HIT: "Drawdown limit hit — position sizes reduced",
    ErrorCode.INVALID_CREDENTIALS: "Invalid username or password",
    ErrorCode.TOKEN_EXPIRED: "Access token has expired — please log in again",
    ErrorCode.INSUFFICIENT_PERMISSIONS: "Insufficient permissions for this action",
    ErrorCode.RATE_LIMIT_EXCEEDED: "Too many requests — please slow down",
    ErrorCode.QUOTA_EXHAUSTED: "API quota exhausted for this period",
    ErrorCode.INVALID_SYMBOL: "Unknown or unsupported trading symbol",
    ErrorCode.INVALID_TIMEFRAME: "Invalid timeframe — use 1m, 5m, 15m, 1h, 4h, or 1D",
    ErrorCode.INVALID_DATE_RANGE: "Invalid date range — end must be after start",
    ErrorCode.PAYLOAD_TOO_LARGE: "Request payload exceeds the 1 MB limit",
}


def error_response(code: ErrorCode, detail: str | None = None) -> dict:
    """Build a standardised error response dict.

    Args:
        code:   :class:`ErrorCode` to include in the response.
        detail: Optional override for the human-readable message.

    Returns:
        Dict with ``error_code``, ``message``, and optionally ``detail``.
    """
    msg = detail or ERROR_DESCRIPTIONS.get(code, str(code))
    return {"error_code": code.value, "message": msg}
