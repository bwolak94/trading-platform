"""Abstract base class for all data fetchers with shared HTTP logic.

Provides a reusable httpx.AsyncClient with exponential-backoff retry,
structured JSON logging, and async context-manager support.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)


class BaseFetcher(ABC):
    """Base class for HTTP-based data fetchers.

    Handles connection pooling, retries with exponential backoff,
    and structured logging.  Subclasses must implement ``fetch``.

    Usage::

        class MyFetcher(BaseFetcher):
            def __init__(self) -> None:
                super().__init__(base_url="https://api.example.com")

            async def fetch(self, **kwargs) -> dict[str, Any]:
                return await self._request("GET", "/v1/data", params=kwargs)

        async with MyFetcher() as fetcher:
            data = await fetcher.fetch(symbol="BTC")
    """

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        """Initialise the fetcher with a shared ``httpx.AsyncClient``.

        Args:
            base_url: The base URL prepended to every request path.
            timeout: Default request timeout in seconds.
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        url: str,
        *,
        retries: int = 3,
        backoff_base: float = 2.0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute an HTTP request with exponential-backoff retry.

        Args:
            method: HTTP method (``GET``, ``POST``, etc.).
            url: Request path (appended to ``base_url``).
            retries: Maximum number of attempts before raising.
            backoff_base: Base multiplier for the exponential delay.
            **kwargs: Forwarded to ``httpx.AsyncClient.request``
                      (e.g. ``params``, ``json``, ``headers``).

        Returns:
            Parsed JSON response as a ``dict``.

        Raises:
            httpx.HTTPStatusError: After all retries on 4xx/5xx responses.
            httpx.RequestError: After all retries on connection failures.
            httpx.TimeoutException: After all retries on timeouts.
        """
        last_exc: BaseException | None = None

        for attempt in range(1, retries + 1):
            try:
                logger.info(
                    "HTTP %s %s (attempt %d/%d)",
                    method,
                    url,
                    attempt,
                    retries,
                    extra={
                        "http_method": method,
                        "url": url,
                        "attempt": attempt,
                        "max_retries": retries,
                    },
                )

                response = await self._client.request(method, url, **kwargs)
                response.raise_for_status()

                data: dict[str, Any] = response.json()
                return data

            except httpx.HTTPStatusError as exc:
                last_exc = exc
                logger.warning(
                    "HTTP %d for %s %s (attempt %d/%d): %s",
                    exc.response.status_code,
                    method,
                    url,
                    attempt,
                    retries,
                    str(exc),
                    extra={
                        "status_code": exc.response.status_code,
                        "attempt": attempt,
                    },
                )

            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.warning(
                    "Timeout for %s %s (attempt %d/%d): %s",
                    method,
                    url,
                    attempt,
                    retries,
                    str(exc),
                    extra={"attempt": attempt},
                )

            except httpx.RequestError as exc:
                last_exc = exc
                logger.warning(
                    "Request error for %s %s (attempt %d/%d): %s",
                    method,
                    url,
                    attempt,
                    retries,
                    str(exc),
                    extra={"attempt": attempt},
                )

            # Exponential backoff before next attempt
            if attempt < retries:
                delay = backoff_base * (2 ** (attempt - 1))
                logger.info(
                    "Retrying %s %s in %.1fs",
                    method,
                    url,
                    delay,
                    extra={"retry_delay": delay},
                )
                await asyncio.sleep(delay)

        # All retries exhausted
        logger.error(
            "All %d retries exhausted for %s %s",
            retries,
            method,
            url,
            extra={"http_method": method, "url": url, "retries": retries},
        )
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def fetch(self, **kwargs: Any) -> Any:
        """Fetch data from the external source.

        Subclasses must implement this method with their specific
        fetching logic.
        """
        ...

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client and release connections."""
        if not self._client.is_closed:
            await self._client.aclose()
            logger.info(
                "HTTP client closed for %s",
                self.__class__.__name__,
                extra={"fetcher": self.__class__.__name__},
            )

    async def __aenter__(self) -> "BaseFetcher":
        """Enter the async context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit the async context manager, closing the HTTP client."""
        await self.close()
