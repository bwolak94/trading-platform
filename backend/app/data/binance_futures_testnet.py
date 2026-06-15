"""Binance Futures Testnet client.

Connects to https://testnet.binancefuture.com to place and manage real orders
using paper money. Requires free testnet API keys from:
  https://testnet.binancefuture.com  (register → API Management)

Set in environment:
  BINANCE_TESTNET_API_KEY=...
  BINANCE_TESTNET_API_SECRET=...
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://testnet.binancefuture.com"
RECV_WINDOW = 5000


class BinanceFuturesTestnetError(Exception):
    """Raised when the testnet API returns an error code."""

    def __init__(self, code: int, msg: str) -> None:
        self.code = code
        self.msg = msg
        super().__init__(f"Binance Testnet error {code}: {msg}")


class BinanceFuturesTestnet:
    """Async client for Binance Futures Testnet.

    All trading methods require BINANCE_TESTNET_API_KEY and
    BINANCE_TESTNET_API_SECRET to be set in the environment.
    """

    def __init__(self) -> None:
        self._api_key = os.environ.get("BINANCE_TESTNET_API_KEY", "")
        self._api_secret = os.environ.get("BINANCE_TESTNET_API_SECRET", "")
        self._client: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        """Return True if API credentials are present."""
        return bool(self._api_key and self._api_secret)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=BASE_URL,
                headers={"X-MBX-APIKEY": self._api_key},
                timeout=10.0,
            )
        return self._client

    def _sign(self, params: dict[str, Any]) -> dict[str, Any]:
        """Add timestamp and HMAC-SHA256 signature to params."""
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = RECV_WINDOW
        query = urlencode(params)
        signature = hmac.new(
            self._api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    async def _get(self, path: str, params: dict[str, Any] | None = None, signed: bool = True) -> Any:
        p = params or {}
        if signed:
            p = self._sign(p)
        resp = await self._get_client().get(path, params=p)
        return self._parse(resp)

    async def _post(self, path: str, params: dict[str, Any]) -> Any:
        params = self._sign(params)
        resp = await self._get_client().post(path, params=params)
        return self._parse(resp)

    async def _delete(self, path: str, params: dict[str, Any]) -> Any:
        params = self._sign(params)
        resp = await self._get_client().delete(path, params=params)
        return self._parse(resp)

    @staticmethod
    def _parse(resp: httpx.Response) -> Any:
        data = resp.json()
        if isinstance(data, dict) and "code" in data and data["code"] != 200 and data["code"] < 0:
            raise BinanceFuturesTestnetError(data["code"], data.get("msg", "unknown"))
        return data

    # ------------------------------------------------------------------ #
    # Account                                                              #
    # ------------------------------------------------------------------ #

    async def get_account(self) -> dict[str, Any]:
        """Return account balances and margin info."""
        data = await self._get("/fapi/v2/account")
        assets = {
            a["asset"]: {
                "wallet_balance": float(a["walletBalance"]),
                "unrealized_pnl": float(a["unrealizedProfit"]),
                "margin_balance": float(a["marginBalance"]),
                "available_balance": float(a["availableBalance"]),
            }
            for a in data.get("assets", [])
            if float(a["walletBalance"]) > 0
        }
        return {
            "total_wallet_balance": float(data.get("totalWalletBalance", 0)),
            "total_unrealized_pnl": float(data.get("totalUnrealizedProfit", 0)),
            "total_margin_balance": float(data.get("totalMarginBalance", 0)),
            "available_balance": float(data.get("availableBalance", 0)),
            "assets": assets,
        }

    # ------------------------------------------------------------------ #
    # Positions                                                            #
    # ------------------------------------------------------------------ #

    async def get_positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Return all open positions (or a specific symbol's position)."""
        params: dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol.upper()
        data = await self._get("/fapi/v2/positionRisk", params)
        positions = []
        for p in data:
            size = float(p["positionAmt"])
            if size == 0:
                continue
            direction = "LONG" if size > 0 else "SHORT"
            entry = float(p["entryPrice"])
            mark = float(p["markPrice"])
            liq = float(p["liquidationPrice"])
            leverage = int(p["leverage"])
            pnl = float(p["unRealizedProfit"])
            notional = abs(float(p["notional"]))
            pnl_pct = (pnl / (notional / leverage) * 100) if notional > 0 else 0.0
            positions.append({
                "symbol": p["symbol"],
                "direction": direction,
                "size": abs(size),
                "entry_price": entry,
                "mark_price": mark,
                "liquidation_price": liq,
                "leverage": leverage,
                "unrealized_pnl": pnl,
                "pnl_pct": round(pnl_pct, 2),
                "margin_type": p.get("marginType", "cross"),
                "isolated_margin": float(p.get("isolatedMargin", 0)),
            })
        return positions

    # ------------------------------------------------------------------ #
    # Orders                                                               #
    # ------------------------------------------------------------------ #

    async def get_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Return all open orders (or for a specific symbol)."""
        params: dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol.upper()
        data = await self._get("/fapi/v1/openOrders", params)
        return [
            {
                "order_id": o["orderId"],
                "symbol": o["symbol"],
                "side": o["side"],
                "type": o["type"],
                "price": float(o["price"]),
                "orig_qty": float(o["origQty"]),
                "executed_qty": float(o["executedQty"]),
                "status": o["status"],
                "time_in_force": o["timeInForce"],
                "reduce_only": o["reduceOnly"],
                "created_at": o["time"],
            }
            for o in data
        ]

    async def get_order_history(self, symbol: str, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent order history for a symbol."""
        data = await self._get("/fapi/v1/allOrders", {"symbol": symbol.upper(), "limit": limit})
        return [
            {
                "order_id": o["orderId"],
                "symbol": o["symbol"],
                "side": o["side"],
                "type": o["type"],
                "price": float(o["price"]),
                "avg_price": float(o.get("avgPrice", 0)),
                "orig_qty": float(o["origQty"]),
                "executed_qty": float(o["executedQty"]),
                "status": o["status"],
                "reduce_only": o["reduceOnly"],
                "created_at": o["time"],
                "updated_at": o.get("updateTime"),
            }
            for o in data
        ]

    async def place_order(
        self,
        symbol: str,
        side: str,           # BUY or SELL
        order_type: str,     # MARKET or LIMIT
        quantity: float,
        price: float | None = None,
        reduce_only: bool = False,
        stop_price: float | None = None,
        time_in_force: str = "GTC",
    ) -> dict[str, Any]:
        """Place a futures order on the testnet.

        Args:
            symbol: e.g. "BTCUSDT"
            side: "BUY" or "SELL"
            order_type: "MARKET", "LIMIT", "STOP_MARKET", "TAKE_PROFIT_MARKET"
            quantity: contract quantity (base asset)
            price: limit price (required for LIMIT orders)
            reduce_only: if True, order only closes an existing position
            stop_price: for STOP_MARKET / TAKE_PROFIT_MARKET orders
            time_in_force: "GTC", "IOC", "FOK" (for LIMIT orders)
        """
        params: dict[str, Any] = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": quantity,
            "reduceOnly": str(reduce_only).lower(),
        }
        if order_type.upper() == "LIMIT":
            if price is None:
                raise ValueError("price is required for LIMIT orders")
            params["price"] = price
            params["timeInForce"] = time_in_force
        if stop_price is not None:
            params["stopPrice"] = stop_price

        data = await self._post("/fapi/v1/order", params)
        logger.info(
            "Testnet order placed: %s %s %s qty=%.4f orderId=%s",
            symbol, side, order_type, quantity, data.get("orderId"),
        )
        return {
            "order_id": data["orderId"],
            "symbol": data["symbol"],
            "side": data["side"],
            "type": data["type"],
            "price": float(data.get("price", 0)),
            "avg_price": float(data.get("avgPrice", 0)),
            "orig_qty": float(data["origQty"]),
            "executed_qty": float(data["executedQty"]),
            "status": data["status"],
            "reduce_only": data["reduceOnly"],
        }

    async def cancel_order(self, symbol: str, order_id: int) -> dict[str, Any]:
        """Cancel an open order by ID."""
        data = await self._delete(
            "/fapi/v1/order",
            {"symbol": symbol.upper(), "orderId": order_id},
        )
        logger.info("Testnet order cancelled: %s orderId=%s", symbol, order_id)
        return {"order_id": data["orderId"], "status": data["status"]}

    async def cancel_all_orders(self, symbol: str) -> dict[str, Any]:
        """Cancel all open orders for a symbol."""
        data = await self._delete(
            "/fapi/v1/allOpenOrders",
            {"symbol": symbol.upper()},
        )
        return data

    async def close_position(self, symbol: str, quantity: float | None = None) -> dict[str, Any]:
        """Close an open position at market price.

        If quantity is None, closes the full position by fetching current size.
        """
        positions = await self.get_positions(symbol)
        if not positions:
            raise BinanceFuturesTestnetError(-1, f"No open position for {symbol}")

        pos = positions[0]
        qty = quantity or pos["size"]
        close_side = "SELL" if pos["direction"] == "LONG" else "BUY"

        return await self.place_order(
            symbol=symbol,
            side=close_side,
            order_type="MARKET",
            quantity=qty,
            reduce_only=True,
        )

    # ------------------------------------------------------------------ #
    # Leverage / Margin                                                    #
    # ------------------------------------------------------------------ #

    async def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        """Set leverage for a symbol (1–125x)."""
        leverage = max(1, min(125, leverage))
        data = await self._post(
            "/fapi/v1/leverage",
            {"symbol": symbol.upper(), "leverage": leverage},
        )
        logger.info("Testnet leverage set: %s %dx", symbol, leverage)
        return {"symbol": data["symbol"], "leverage": int(data["leverage"])}

    async def set_margin_type(self, symbol: str, margin_type: str) -> dict[str, Any]:
        """Set margin type: 'ISOLATED' or 'CROSSED'."""
        data = await self._post(
            "/fapi/v1/marginType",
            {"symbol": symbol.upper(), "marginType": margin_type.upper()},
        )
        return data

    # ------------------------------------------------------------------ #
    # Market data (public, no auth)                                        #
    # ------------------------------------------------------------------ #

    async def get_mark_price(self, symbol: str) -> float:
        """Return current mark price for a symbol."""
        data = await self._get(
            "/fapi/v1/premiumIndex",
            {"symbol": symbol.upper()},
            signed=False,
        )
        return float(data["markPrice"])

    async def get_exchange_info(self) -> dict[str, Any]:
        """Return exchange info with lot size filters for precision."""
        data = await self._get("/fapi/v1/exchangeInfo", signed=False)
        result = {}
        for s in data.get("symbols", []):
            filters = {f["filterType"]: f for f in s.get("filters", [])}
            lot = filters.get("LOT_SIZE", {})
            result[s["symbol"]] = {
                "min_qty": float(lot.get("minQty", 0.001)),
                "step_size": float(lot.get("stepSize", 0.001)),
                "price_precision": s.get("pricePrecision", 2),
                "qty_precision": s.get("quantityPrecision", 3),
            }
        return result

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Module-level singleton
_testnet_client: BinanceFuturesTestnet | None = None


def get_testnet_client() -> BinanceFuturesTestnet:
    """Return the shared testnet client singleton."""
    global _testnet_client
    if _testnet_client is None:
        _testnet_client = BinanceFuturesTestnet()
    return _testnet_client
