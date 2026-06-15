"""Shared test fixtures and pytest configuration."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def dispose_db_pool():
    """Dispose the async engine pool after every test.

    Sync TestClient tests each spin up their own anyio event loop in a thread.
    When a sync test finishes, that loop closes — but asyncpg connections
    remain pooled against the now-dead loop.  The next truly-async test
    (pytest-asyncio event loop) then hits "Future attached to a different
    loop" when pool_pre_ping tries to reuse those stale connections.

    AsyncEngine.dispose() is synchronous in SQLAlchemy 2.x — it resets the
    pool immediately without needing an event loop.  Using a sync fixture
    means it runs correctly for both sync and async tests.
    """
    yield
    try:
        from app.core.database import engine
        engine.dispose()
    except Exception:
        pass


@pytest.fixture(scope="session")
def app():
    """Return the FastAPI application instance (session-scoped for speed)."""
    from app.main import app as _app
    return _app


@pytest.fixture(scope="session")
def client(app):
    """Return a TestClient for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def sample_trades():
    """A small list of synthetic Trade objects for backtesting tests."""
    from app.backtesting.walk_forward import Trade
    return [Trade(pnl_pct=2.0 if i % 2 == 0 else -1.0) for i in range(20)]
