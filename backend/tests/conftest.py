"""Shared test fixtures and pytest configuration."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session", autouse=True)
def use_null_pool():
    """Replace the SQLAlchemy async engine with a NullPool variant for tests.

    NullPool creates a brand-new asyncpg connection per DB request — nothing
    is ever cached in a pool.  This eliminates the "Future attached to a
    different loop" error that occurs when:

      1. Sync TestClient tests run the ASGI app in a worker thread, which
         spins up its own asyncio event loop.
      2. That loop closes after the test.
      3. A later async test (pytest-asyncio event loop) asks the pool for a
         connection and gets one whose internal Future is bound to the now-
         dead thread loop.

    With NullPool, step 3 always creates a fresh connection on the active
    loop, so event-loop identity is never an issue.
    """
    from sqlalchemy.pool import NullPool
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core import database
    from app.core.config import settings

    test_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    test_session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    # Patch module-level names that get_db() reads at call-time (not import-time)
    database.engine = test_engine
    database.async_session = test_session_factory

    yield


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
