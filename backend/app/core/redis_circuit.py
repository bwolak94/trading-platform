"""E3: Redis circuit breaker (async).

Wraps all Redis calls with a circuit breaker:
  - CLOSED   → normal operation
  - OPEN     → after 3 consecutive failures; falls back to LRU in-memory cache
  - HALF-OPEN → after 30 s reset window; next call tests Redis

The in-memory fallback is bounded by ``MAX_MEMORY_KEYS`` using an LRU eviction
policy so it cannot grow unboundedly during extended Redis outages.

Usage::

    cache = get_redis_circuit_cache()

    # Instead of direct Redis calls:
    value = await cache.get("my_key")
    await cache.set("my_key", "value", ttl=60)
"""

import time
from collections import OrderedDict
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

FAILURE_THRESHOLD = 3
RESET_TIMEOUT_SECONDS = 30
MAX_MEMORY_KEYS = 2048  # LRU cap — prevents unbounded growth during outages


class _LRUCache:
    """Simple bounded LRU dict with O(1) get/set/delete."""

    def __init__(self, maxsize: int) -> None:
        self._maxsize = maxsize
        self._cache: OrderedDict[str, Any] = OrderedDict()

    def get(self, key: str) -> Any:
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        return self._cache[key]

    def set(self, key: str, value: Any) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def delete(self, key: str) -> None:
        self._cache.pop(key, None)

    def __len__(self) -> int:
        return len(self._cache)


class RedisCircuitCache:
    """Async Redis-backed cache with circuit breaker and LRU in-memory fallback.

    The circuit opens after ``FAILURE_THRESHOLD`` consecutive Redis errors
    and resets after ``RESET_TIMEOUT_SECONDS`` seconds.

    When the circuit is open, reads come from an LRU in-memory cache bounded
    by ``MAX_MEMORY_KEYS`` entries.
    """

    def __init__(self, redis_url: str | None = None) -> None:
        from app.core.config import settings

        self._redis_url = redis_url or settings.REDIS_URL
        self._redis: Any = None
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._state: str = "CLOSED"  # CLOSED | OPEN | HALF_OPEN
        self._memory = _LRUCache(MAX_MEMORY_KEYS)

    # ------------------------------------------------------------------
    # Circuit state management
    # ------------------------------------------------------------------

    def _get_redis(self):
        """Lazy-initialise the async Redis client."""
        if self._redis is None:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    def _record_success(self) -> None:
        self._failure_count = 0
        if self._state != "CLOSED":
            logger.info("RedisCircuit: circuit CLOSED — Redis recovered")
        self._state = "CLOSED"

    def _record_failure(self, exc: Exception) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        logger.warning("RedisCircuit: failure #%d — %s", self._failure_count, exc)
        if self._failure_count >= FAILURE_THRESHOLD:
            if self._state == "CLOSED":
                logger.error(
                    "RedisCircuit: circuit OPEN after %d failures — falling back to LRU memory cache",
                    self._failure_count,
                )
            self._state = "OPEN"

    def _should_attempt(self) -> bool:
        """Determine whether a Redis call should be attempted."""
        if self._state == "CLOSED":
            return True
        if self._state == "OPEN":
            elapsed = time.monotonic() - (self._last_failure_time or 0)
            if elapsed >= RESET_TIMEOUT_SECONDS:
                logger.info("RedisCircuit: entering HALF_OPEN — testing Redis")
                self._state = "HALF_OPEN"
                return True
            return False
        # HALF_OPEN — allow one probe
        return True

    # ------------------------------------------------------------------
    # Public API (all async)
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Any:
        """Get a value by key, falling back to the LRU in-memory cache if open."""
        if not self._should_attempt():
            return self._memory.get(key)
        try:
            value = await self._get_redis().get(key)
            self._record_success()
            return value
        except Exception as exc:
            self._record_failure(exc)
            return self._memory.get(key)

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """Set a value with TTL; writes to LRU memory cache when circuit is open."""
        self._memory.set(key, value)  # always update memory
        if not self._should_attempt():
            return
        try:
            await self._get_redis().setex(key, ttl, value)
            self._record_success()
        except Exception as exc:
            self._record_failure(exc)

    async def delete(self, key: str) -> None:
        """Delete a key from Redis and the in-memory cache."""
        self._memory.delete(key)
        if not self._should_attempt():
            return
        try:
            await self._get_redis().delete(key)
            self._record_success()
        except Exception as exc:
            self._record_failure(exc)

    async def set_nx(self, key: str, value: Any, ttl: int = 300) -> bool:
        """SET NX (set only if not exists) — used for distributed locks.

        Returns True if the key was set (lock acquired), False otherwise.
        Falls back to in-memory check when circuit is open.
        """
        if not self._should_attempt():
            if self._memory.get(key) is not None:
                return False
            self._memory.set(key, value)
            return True
        try:
            result = await self._get_redis().set(key, value, nx=True, ex=ttl)
            self._record_success()
            return result is not None
        except Exception as exc:
            self._record_failure(exc)
            if self._memory.get(key) is not None:
                return False
            self._memory.set(key, value)
            return True

    @property
    def circuit_state(self) -> str:
        """Current circuit state: CLOSED | OPEN | HALF_OPEN."""
        return self._state

    def status(self) -> dict:
        """Return a JSON-serialisable status dict for monitoring endpoints."""
        return {
            "circuit_state": self._state,
            "failure_count": self._failure_count,
            "memory_keys": len(self._memory),
            "memory_max": MAX_MEMORY_KEYS,
        }


# Module-level singleton
_circuit_cache: RedisCircuitCache | None = None


def get_redis_circuit_cache() -> RedisCircuitCache:
    """Return the module-level :class:`RedisCircuitCache` singleton."""
    global _circuit_cache
    if _circuit_cache is None:
        _circuit_cache = RedisCircuitCache()
    return _circuit_cache
