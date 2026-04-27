"""Post-deploy smoke test.

Hits the key endpoints and the WebSocket to verify the deployment succeeded.
Exits with code 0 on success, 1 on any failure.

Usage:
    python scripts/smoke_test.py [BASE_URL]

    BASE_URL defaults to http://localhost:8000
"""

import asyncio
import json
import sys
import urllib.request
import urllib.error

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"


def _get(path: str, expected_status: int = 200) -> dict:
    url = f"{BASE_URL}{path}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            if resp.status != expected_status:
                raise AssertionError(
                    f"GET {url} returned {resp.status}, expected {expected_status}"
                )
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == expected_status:
            return json.loads(e.read())
        raise AssertionError(f"GET {url} failed with HTTP {e.code}: {e.reason}") from e
    except Exception as exc:
        raise AssertionError(f"GET {url} failed: {exc}") from exc


def _post(path: str, body: dict, expected_status: int = 200) -> dict:
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != expected_status:
                raise AssertionError(
                    f"POST {url} returned {resp.status}, expected {expected_status}"
                )
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == expected_status:
            return json.loads(e.read())
        raise AssertionError(f"POST {url} failed with HTTP {e.code}: {e.reason}") from e
    except Exception as exc:
        raise AssertionError(f"POST {url} failed: {exc}") from exc


async def _check_websocket() -> None:
    """Connect to /ws and verify the subscribe handshake works."""
    try:
        import websockets  # type: ignore
    except ImportError:
        print("  [SKIP] websockets not installed — skipping WS check")
        return

    ws_url = BASE_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
    async with websockets.connect(ws_url, open_timeout=5) as ws:
        await ws.send(json.dumps({"action": "subscribe", "channels": ["signals"]}))
        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        assert resp.get("type") == "SUBSCRIBED", f"Unexpected WS response: {resp}"


def run() -> None:
    failures: list[str] = []

    checks: list[tuple[str, object]] = [
        ("Health check", lambda: _get("/api/v1/health")),
        ("System status", lambda: _get("/api/v1/status")),
        ("Signals endpoint", lambda: _get("/api/v1/signals")),
        ("Market endpoint", lambda: _get("/api/v1/market/regime")),
        ("Monitoring tasks", lambda: _get("/api/v1/monitoring/tasks")),
    ]

    for name, fn in checks:
        try:
            fn()  # type: ignore[operator]
            print(f"  [OK]   {name}")
        except Exception as exc:
            print(f"  [FAIL] {name}: {exc}")
            failures.append(name)

    # WebSocket check
    try:
        asyncio.run(_check_websocket())
        print("  [OK]   WebSocket subscribe handshake")
    except Exception as exc:
        print(f"  [FAIL] WebSocket: {exc}")
        failures.append("WebSocket")

    print()
    if failures:
        print(f"SMOKE TEST FAILED — {len(failures)} check(s) failed: {', '.join(failures)}")
        sys.exit(1)
    else:
        print(f"SMOKE TEST PASSED — all checks green against {BASE_URL}")
        sys.exit(0)


if __name__ == "__main__":
    print(f"Running smoke tests against {BASE_URL}...\n")
    run()
