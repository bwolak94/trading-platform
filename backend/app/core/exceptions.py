"""Custom exception hierarchy for the AI Trading Navigator platform.

All domain-specific exceptions inherit from TradingPlatformError, making it
easy to catch platform errors uniformly (e.g. in FastAPI exception handlers)
while still allowing granular handling when needed.
"""

from typing import Optional


class TradingPlatformError(Exception):
    """Base exception for all trading platform errors.

    Attributes:
        message: Human-readable error description.
        error_code: Optional machine-readable error code for API consumers.
    """

    def __init__(self, message: str, error_code: Optional[str] = None) -> None:
        self.message = message
        self.error_code = error_code or "TRADING_PLATFORM_ERROR"
        super().__init__(self.message)


class DataFetchError(TradingPlatformError):
    """Raised when an external data source fails to return data.

    Attributes:
        source: Name of the data source that failed (e.g. 'binance', 'glassnode').
    """

    def __init__(self, message: str, source: str, error_code: Optional[str] = None) -> None:
        self.source = source
        super().__init__(
            message=message,
            error_code=error_code or "DATA_FETCH_ERROR",
        )


class InsufficientDataError(TradingPlatformError):
    """Raised when there is not enough data to perform an analysis.

    Attributes:
        required: Minimum number of data points required.
        available: Number of data points actually available.
    """

    def __init__(
        self,
        message: str,
        required: int = 0,
        available: int = 0,
        error_code: Optional[str] = None,
    ) -> None:
        self.required = required
        self.available = available
        super().__init__(
            message=message,
            error_code=error_code or "INSUFFICIENT_DATA",
        )


class KillSwitchActiveError(TradingPlatformError):
    """Raised when the drawdown kill switch prevents an operation.

    This exception signals that the risk management system has halted
    trading activity due to excessive drawdown.
    """

    def __init__(self, message: str = "Kill switch is active — trading halted", error_code: Optional[str] = None) -> None:
        super().__init__(
            message=message,
            error_code=error_code or "KILL_SWITCH_ACTIVE",
        )


class RateLimitError(TradingPlatformError):
    """Raised when an external API rate limit has been exceeded.

    Attributes:
        retry_after: Suggested number of seconds to wait before retrying.
    """

    def __init__(
        self,
        message: str,
        retry_after: float = 60.0,
        error_code: Optional[str] = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(
            message=message,
            error_code=error_code or "RATE_LIMIT_EXCEEDED",
        )
