"""Integration tests for the WebSocket endpoint.

Uses Starlette's TestClient WebSocket support (no running server needed).
Tests: connection, subscribe/unsubscribe, authentication in production mode.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """Return a TestClient with the FastAPI app."""
    from app.main import app
    return TestClient(app)


class TestWebSocketConnection:
    def test_connect_in_dev_mode(self, client: TestClient):
        """WebSocket connects without a token in development mode."""
        with client.websocket_connect("/ws") as ws:
            # Should connect successfully (no auth required in dev)
            ws.send_json({"action": "subscribe", "channels": ["signals"]})
            response = ws.receive_json()
            assert response["type"] == "SUBSCRIBED"
            assert "signals" in response["channels"]

    def test_subscribe_and_unsubscribe(self, client: TestClient):
        """Subscribe then unsubscribe from a channel."""
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"action": "subscribe", "channels": ["regime"]})
            sub_resp = ws.receive_json()
            assert sub_resp["type"] == "SUBSCRIBED"

            ws.send_json({"action": "unsubscribe", "channels": ["regime"]})
            unsub_resp = ws.receive_json()
            assert unsub_resp["type"] == "UNSUBSCRIBED"
            assert "regime" in unsub_resp["channels"]

    def test_unknown_action_is_ignored(self, client: TestClient):
        """Sending an unknown action should not raise or close the connection."""
        with client.websocket_connect("/ws") as ws:
            # Send unknown action — connection should remain open
            ws.send_json({"action": "unknown_action", "channels": []})
            # Subscribe to verify connection is still alive
            ws.send_json({"action": "subscribe", "channels": ["signals"]})
            resp = ws.receive_json()
            assert resp["type"] == "SUBSCRIBED"


class TestWebSocketAuth:
    def test_production_requires_token(self, monkeypatch, client: TestClient):
        """In production mode, connecting without a token returns 4001."""
        import app.core.config as cfg_module
        monkeypatch.setattr(cfg_module.settings, "ENVIRONMENT", "production")
        # Should be rejected with close code 4001
        with pytest.raises(Exception):
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()

    def test_production_accepts_valid_token(self, monkeypatch, client: TestClient):
        """In production mode, a valid JWT token allows connection."""
        import app.core.config as cfg_module
        import app.core.auth as auth_module

        monkeypatch.setattr(cfg_module.settings, "ENVIRONMENT", "production")
        token = auth_module.create_access_token({"sub": "test-user", "role": "admin"})

        with client.websocket_connect(f"/ws?token={token}") as ws:
            ws.send_json({"action": "subscribe", "channels": ["signals"]})
            resp = ws.receive_json()
            assert resp["type"] == "SUBSCRIBED"
