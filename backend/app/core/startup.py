"""Service startup/shutdown utilities.

Provides a single ``start_service`` helper that wraps coroutines with
consistent try/except + logging, eliminating the repetitive boilerplate
that previously appeared ~8 times in main.py's lifespan.
"""

from app.core.logging import get_logger

logger = get_logger(__name__)


async def start_service(name: str, coro) -> None:
    """Start a background service coroutine, logging success or failure.

    Args:
        name: Human-readable service name for log messages.
        coro:  Awaitable to start the service (e.g. ``engine.start()``).
    """
    try:
        await coro
        logger.info("%s started", name)
    except Exception as exc:
        logger.warning("Failed to start %s: %s", name, exc)


async def stop_service(name: str, coro) -> None:
    """Stop a background service coroutine, logging any errors.

    Args:
        name: Human-readable service name for log messages.
        coro:  Awaitable to stop the service (e.g. ``engine.stop()``).
    """
    logger.info("Shutting down %s...", name)
    try:
        await coro
    except Exception as exc:
        logger.warning("Error shutting down %s: %s", name, exc)
