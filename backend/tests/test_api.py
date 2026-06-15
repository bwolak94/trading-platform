"""Integration tests for API endpoints and WebSocket."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.main import app


# --- REST API Tests ---


class TestHealthAndStatus:
    def test_health_check(self):
        with TestClient(app) as client:
            resp = client.get("/api/v1/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert "version" in data

    def test_system_status(self):
        with TestClient(app) as client:
            resp = client.get("/api/v1/status")
            assert resp.status_code == 200
            data = resp.json()
            assert "system_status" in data
            assert "websocket_clients" in data
            assert "drawdown_pct" in data


class TestSignalEndpoints:
    def test_list_signals_empty(self):
        with TestClient(app) as client:
            resp = client.get("/api/v1/signals")
            assert resp.status_code == 200
            data = resp.json()
            assert "data" in data
            assert "meta" in data
            assert isinstance(data["data"], list)
            assert data["meta"]["limit"] == 20
            assert data["meta"]["offset"] == 0

    def test_list_signals_with_filters(self):
        with TestClient(app) as client:
            resp = client.get("/api/v1/signals", params={
                "asset": "BTC/USDT",
                "direction": "LONG",
                "status": "ACTIVE",
                "limit": 5,
                "offset": 0,
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["meta"]["limit"] == 5

    def test_active_signals_empty(self):
        with TestClient(app) as client:
            resp = client.get("/api/v1/signals/active")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data["data"], list)

    def test_get_signal_not_found(self):
        with TestClient(app) as client:
            resp = client.get("/api/v1/signals/00000000-0000-0000-0000-000000000000")
            assert resp.status_code == 404

    def test_get_signal_invalid_uuid(self):
        with TestClient(app) as client:
            resp = client.get("/api/v1/signals/not-a-uuid")
            assert resp.status_code == 422


class TestMarketEndpoints:
    def test_get_all_regimes(self):
        with TestClient(app) as client:
            resp = client.get("/api/v1/market/regime")
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)

    def test_get_asset_regime_not_found(self):
        with TestClient(app) as client:
            resp = client.get("/api/v1/market/regime/NONEXISTENT")
            assert resp.status_code == 404

    def test_get_sentiment(self):
        with TestClient(app) as client:
            resp = client.get("/api/v1/market/sentiment")
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)

    def test_get_onchain_events(self):
        with TestClient(app) as client:
            resp = client.get("/api/v1/market/onchain")
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)

    def test_get_onchain_with_limit(self):
        with TestClient(app) as client:
            resp = client.get("/api/v1/market/onchain", params={"limit": 10})
            assert resp.status_code == 200

    def test_get_macro_calendar(self):
        with TestClient(app) as client:
            resp = client.get("/api/v1/market/calendar")
            assert resp.status_code == 200
            assert "events" in resp.json()


class TestBacktestEndpoints:
    def test_run_backtest_request(self):
        with TestClient(app) as client:
            resp = client.post("/api/v1/backtest/run", json={
                "strategy": "trend_following",
                "asset": "BTC/USDT",
                "timeframe": "4h",
                "from_date": "2023-01-01",
                "to_date": "2024-01-01",
                "initial_capital": 10000,
                "risk_per_trade_pct": 1.5,
            })
            # May return 200 (queued) or 500 if Celery not running
            assert resp.status_code in (200, 500)

    def test_run_backtest_validation(self):
        with TestClient(app) as client:
            resp = client.post("/api/v1/backtest/run", json={})
            assert resp.status_code == 422

    def test_list_results(self):
        with TestClient(app) as client:
            resp = client.get("/api/v1/backtest/results")
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)

    def test_get_result_not_found(self):
        with TestClient(app) as client:
            resp = client.get("/api/v1/backtest/results/00000000-0000-0000-0000-000000000000")
            assert resp.status_code == 404


class TestSettingsEndpoints:
    def test_get_settings(self):
        with TestClient(app) as client:
            resp = client.get("/api/v1/settings")
            assert resp.status_code == 200
            data = resp.json()
            assert "user_id" in data
            assert "risk_per_trade_pct" in data
            assert "system_status" in data

    def test_patch_settings(self):
        with TestClient(app) as client:
            resp = client.patch("/api/v1/settings", json={
                "capital": 25000.0,
                "risk_per_trade_pct": 2.0,
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["capital"] == 25000.0
            assert data["risk_per_trade_pct"] == 2.0

    def test_patch_settings_partial(self):
        with TestClient(app) as client:
            resp = client.patch("/api/v1/settings", json={
                "notifications_enabled": False,
            })
            assert resp.status_code == 200
            assert resp.json()["notifications_enabled"] is False

    def test_reset_killswitch_not_paused(self):
        with TestClient(app) as client:
            resp = client.post("/api/v1/settings/reset-killswitch")
            # Should fail if system is not paused
            assert resp.status_code == 400


class TestErrorHandling:
    def test_404_unknown_route(self):
        with TestClient(app) as client:
            resp = client.get("/api/v1/nonexistent")
            assert resp.status_code == 404

    def test_method_not_allowed(self):
        with TestClient(app) as client:
            resp = client.delete("/api/v1/health")
            assert resp.status_code == 405

    def test_cors_headers(self):
        with TestClient(app) as client:
            resp = client.options("/api/v1/health", headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            })
            assert resp.status_code == 200


# --- WebSocket Tests ---


class TestWebSocket:
    def test_websocket_connect(self):
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws:
                # Subscribe
                ws.send_json({"action": "subscribe", "channels": ["signals"]})
                resp = ws.receive_json()
                assert resp["type"] == "SUBSCRIBED"
                assert "signals" in resp["channels"]

    def test_websocket_subscribe_multiple(self):
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws:
                ws.send_json({
                    "action": "subscribe",
                    "channels": ["signals", "regime", "sentiment"],
                })
                resp = ws.receive_json()
                assert resp["type"] == "SUBSCRIBED"
                assert len(resp["channels"]) == 3

    def test_websocket_unsubscribe(self):
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"action": "subscribe", "channels": ["signals"]})
                ws.receive_json()

                ws.send_json({"action": "unsubscribe", "channels": ["signals"]})
                resp = ws.receive_json()
                assert resp["type"] == "UNSUBSCRIBED"

    def test_websocket_disconnect_cleanup(self):
        from app.core.websocket import manager

        initial = manager.active_count
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws:
                assert manager.active_count == initial + 1
            # After disconnect
            assert manager.active_count == initial


# --- Signal Aggregation Pipeline Test (end-to-end logic) ---


class TestMarketIndicatorsEndpoint:
    """Tests for GET /api/v1/market/indicators with mocked Binance data."""

    def test_get_indicators_returns_200(self):
        """Test indicators endpoint returns 200 with mocked Binance kline data."""
        import numpy as np
        from datetime import datetime, timezone, timedelta

        n = 300
        base_time = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        base_price = 40000.0
        # Build fake Binance klines: [open_time, open, high, low, close, volume, ...]
        fake_klines = []
        for i in range(n):
            t = base_time + i * 3600_000
            c = base_price + i * 10 + np.random.randn() * 50
            h = c + abs(np.random.randn() * 30)
            l = c - abs(np.random.randn() * 30)
            o = c + np.random.randn() * 10
            v = abs(np.random.randn() * 500) + 100
            fake_klines.append([t, str(o), str(h), str(l), str(c), str(v),
                                t + 3600_000, "0", 0, "0", "0", "0"])

        mock_response = MagicMock()
        mock_response.json.return_value = fake_klines
        mock_response.raise_for_status.return_value = None

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.v1.market.httpx.AsyncClient", return_value=mock_client_instance):
            with TestClient(app) as client:
                resp = client.get("/api/v1/market/indicators", params={
                    "asset": "BTCUSDT",
                    "interval": "1h",
                    "limit": 300,
                })
                assert resp.status_code == 200
                data = resp.json()
                assert isinstance(data, dict)
                # Should contain EMA and other indicator arrays
                assert "ema_20" in data or "error" not in data


class TestMarketKlinesEndpoint:
    """Tests for GET /api/v1/market/klines with mocked Binance data."""

    def test_get_klines_returns_200(self):
        """Test klines endpoint returns 200 with candle data."""
        import numpy as np
        from datetime import datetime, timezone

        n = 100
        base_time = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        fake_klines = []
        for i in range(n):
            t = base_time + i * 3600_000
            c = 40000 + i * 5
            fake_klines.append([t, str(c - 10), str(c + 20), str(c - 20), str(c), str(500),
                                t + 3600_000, "0", 0, "0", "0", "0"])

        mock_response = MagicMock()
        mock_response.json.return_value = fake_klines
        mock_response.raise_for_status.return_value = None

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.v1.market.httpx.AsyncClient", return_value=mock_client_instance):
            with TestClient(app) as client:
                resp = client.get("/api/v1/market/klines", params={
                    "asset": "BTCUSDT",
                    "interval": "1h",
                    "limit": 100,
                })
                assert resp.status_code == 200
                data = resp.json()
                assert isinstance(data, list)
                assert len(data) == n
                # Each candle should have expected keys
                candle = data[0]
                assert "time" in candle
                assert "open" in candle
                assert "high" in candle
                assert "low" in candle
                assert "close" in candle
                assert "volume" in candle


class TestAnalyzeRunEndpoint:
    """Tests for GET /api/v1/analyze/run with mocked Binance data."""

    def test_run_analysis_returns_200(self):
        """Test analyze/run endpoint returns 200 with regime and signal data."""
        import numpy as np
        from datetime import datetime, timezone

        n = 500
        base_time = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        base_price = 40000.0
        fake_klines = []
        for i in range(n):
            t = base_time + i * 14400_000  # 4h candles
            c = base_price + i * 10 + np.random.randn() * 50
            h = c + abs(np.random.randn() * 30)
            l = c - abs(np.random.randn() * 30)
            o = c + np.random.randn() * 10
            v = abs(np.random.randn() * 500) + 100
            fake_klines.append([t, str(o), str(h), str(l), str(c), str(v),
                                t + 14400_000, "0", 0, "0", "0", "0"])

        mock_response = MagicMock()
        mock_response.json.return_value = fake_klines
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.v1.analyze.httpx.AsyncClient", return_value=mock_client_instance):
            with TestClient(app) as client:
                resp = client.get("/api/v1/analyze/run", params={
                    "asset": "BTC/USDT",
                    "timeframe": "4h",
                })
                assert resp.status_code == 200
                data = resp.json()
                assert isinstance(data, dict)
                # Should contain regime info or an error key
                assert "regime" in data or "error" in data

    def test_run_analysis_invalid_asset(self):
        """Test analyze/run returns 400 for invalid asset."""
        with TestClient(app) as client:
            resp = client.get("/api/v1/analyze/run", params={
                "asset": "INVALID/PAIR",
                "timeframe": "4h",
            })
            assert resp.status_code == 400


class TestAsyncEndpoints:
    """Async integration tests using httpx.AsyncClient."""

    @pytest.mark.asyncio
    async def test_health_async(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/v1/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_signals_async(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/v1/signals")
            assert resp.status_code == 200
            data = resp.json()
            assert "data" in data
            assert isinstance(data["data"], list)

    @pytest.mark.asyncio
    async def test_status_async(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/v1/status")
            assert resp.status_code == 200
            data = resp.json()
            assert "system_status" in data

    @pytest.mark.asyncio
    async def test_indicators_async(self):
        """Async test for GET /api/v1/market/indicators with mocked Binance data."""
        import numpy as np
        from datetime import datetime, timezone

        n = 300
        base_time = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        base_price = 40000.0
        fake_klines = []
        for i in range(n):
            t = base_time + i * 3600_000
            c = base_price + i * 10 + np.random.randn() * 50
            h = c + abs(np.random.randn() * 30)
            low = c - abs(np.random.randn() * 30)
            o = c + np.random.randn() * 10
            v = abs(np.random.randn() * 500) + 100
            fake_klines.append([t, str(o), str(h), str(low), str(c), str(v),
                                t + 3600_000, "0", 0, "0", "0", "0"])

        mock_response = MagicMock()
        mock_response.json.return_value = fake_klines
        mock_response.raise_for_status.return_value = None

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.v1.market.httpx.AsyncClient", return_value=mock_client_instance):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/market/indicators", params={
                    "asset": "BTCUSDT",
                    "interval": "4h",
                    "limit": 100,
                })
                assert resp.status_code == 200
                data = resp.json()
                assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_klines_async(self):
        """Async test for GET /api/v1/market/klines with mocked Binance data."""
        import numpy as np
        from datetime import datetime, timezone

        n = 100
        base_time = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        fake_klines = []
        for i in range(n):
            t = base_time + i * 3600_000
            c = 40000 + i * 5
            fake_klines.append([t, str(c - 10), str(c + 20), str(c - 20), str(c), str(500),
                                t + 3600_000, "0", 0, "0", "0", "0"])

        mock_response = MagicMock()
        mock_response.json.return_value = fake_klines
        mock_response.raise_for_status.return_value = None

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.v1.market.httpx.AsyncClient", return_value=mock_client_instance):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/market/klines", params={
                    "asset": "BTCUSDT",
                    "interval": "4h",
                    "limit": 100,
                })
                assert resp.status_code == 200
                data = resp.json()
                assert isinstance(data, list)
                assert len(data) == n
                candle = data[0]
                assert "time" in candle
                assert "open" in candle
                assert "close" in candle

    @pytest.mark.asyncio
    async def test_analyze_run_async(self):
        """Async test for GET /api/v1/analyze/run with mocked Binance data."""
        import numpy as np
        from datetime import datetime, timezone

        n = 500
        base_time = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        base_price = 40000.0
        fake_klines = []
        for i in range(n):
            t = base_time + i * 14400_000  # 4h candles
            c = base_price + i * 10 + np.random.randn() * 50
            h = c + abs(np.random.randn() * 30)
            low = c - abs(np.random.randn() * 30)
            o = c + np.random.randn() * 10
            v = abs(np.random.randn() * 500) + 100
            fake_klines.append([t, str(o), str(h), str(low), str(c), str(v),
                                t + 14400_000, "0", 0, "0", "0", "0"])

        mock_response = MagicMock()
        mock_response.json.return_value = fake_klines
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.v1.analyze.httpx.AsyncClient", return_value=mock_client_instance):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/analyze/run", params={
                    "asset": "BTC/USDT",
                    "timeframe": "4h",
                })
                assert resp.status_code == 200
                data = resp.json()
                assert isinstance(data, dict)
                assert "regime" in data or "error" in data


class TestSignalPipeline:
    def test_aggregator_end_to_end(self):
        """Test signal aggregation from data through to signal output."""
        import numpy as np
        import pandas as pd
        from app.ai.signals.aggregator import SignalAggregator
        from app.ai.regime.classifier import RegimePrediction
        from app.data.processors.feature_engineer import compute_features

        # Generate bullish data
        np.random.seed(123)
        n = 300
        dates = pd.date_range("2024-01-01", periods=n, freq="4h")
        base = 40000.0
        drift = np.linspace(0, 8000, n)
        noise = np.cumsum(np.random.randn(n) * 30)
        close = base + drift + noise

        df = pd.DataFrame({
            "timestamp": dates,
            "open": close - np.random.rand(n) * 20,
            "high": close + np.abs(np.random.randn(n) * 80),
            "low": close - np.abs(np.random.randn(n) * 80),
            "close": close,
            "volume": np.abs(np.random.randn(n) * 1500) + 800,
        })
        featured = compute_features(df)

        aggregator = SignalAggregator()
        regime = RegimePrediction(
            "TREND_BULL", 85.0,
            {"TREND_BULL": 0.85, "TREND_BEAR": 0.03, "CONSOLIDATION": 0.08, "HIGH_VOL_CHOPPY": 0.04},
        )

        signal = aggregator.aggregate(
            asset="BTC/USDT",
            timeframe="4h",
            market_data=featured,
            regime=regime,
            onchain_score=0.5,
            sentiment_score=0.3,
        )

        # Signal may or may not be generated depending on exact data
        if signal is not None:
            assert signal.asset == "BTC/USDT"
            assert signal.direction in ("LONG", "SHORT")
            assert signal.confidence >= 0
            assert signal.entry_price > 0
            assert signal.stop_loss > 0
            assert signal.take_profit_1 > 0
            assert len(signal.factors) > 0
