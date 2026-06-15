"""Binance Futures Testnet API — place and manage real orders on testnet.binancefuture.com.

All endpoints require BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET
environment variables.  The testnet uses fake money — safe for strategy testing.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.data.binance_futures_testnet import BinanceFuturesTestnetError, get_testnet_client

router = APIRouter(prefix="/futures-testnet", tags=["futures-testnet"])
logger = get_logger(__name__)


def _require_configured() -> None:
    """Raise 503 if testnet credentials are missing."""
    client = get_testnet_client()
    if not client.is_configured:
        raise HTTPException(
            status_code=503,
            detail=(
                "Binance Testnet not configured. "
                "Set BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET "
                "from https://testnet.binancefuture.com"
            ),
        )


def _handle_testnet_error(exc: BinanceFuturesTestnetError) -> None:
    raise HTTPException(status_code=400, detail=f"Binance error {exc.code}: {exc.msg}")


# ------------------------------------------------------------------ #
# Status / account                                                     #
# ------------------------------------------------------------------ #

@router.get("/status")
async def testnet_status() -> dict[str, Any]:
    """Check testnet connectivity and credential status."""
    client = get_testnet_client()
    if not client.is_configured:
        return {
            "configured": False,
            "message": "Set BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET",
            "setup_url": "https://testnet.binancefuture.com",
        }
    try:
        account = await client.get_account()
        return {
            "configured": True,
            "connected": True,
            "balance_usdt": account["total_wallet_balance"],
            "available_usdt": account["available_balance"],
            "unrealized_pnl": account["total_unrealized_pnl"],
        }
    except BinanceFuturesTestnetError as exc:
        return {"configured": True, "connected": False, "error": exc.msg}
    except Exception as exc:
        return {"configured": True, "connected": False, "error": str(exc)}


@router.get("/account")
async def get_account() -> dict[str, Any]:
    """Return testnet account balances and margin summary."""
    _require_configured()
    try:
        return await get_testnet_client().get_account()
    except BinanceFuturesTestnetError as exc:
        _handle_testnet_error(exc)


# ------------------------------------------------------------------ #
# Positions                                                            #
# ------------------------------------------------------------------ #

@router.get("/positions")
async def get_positions(symbol: str | None = Query(default=None)) -> dict[str, Any]:
    """Return all open testnet positions."""
    _require_configured()
    try:
        positions = await get_testnet_client().get_positions(symbol)
        return {"positions": positions, "count": len(positions)}
    except BinanceFuturesTestnetError as exc:
        _handle_testnet_error(exc)


@router.post("/position/close")
async def close_position(symbol: str, quantity: float | None = None) -> dict[str, Any]:
    """Close an open position at market price.  If quantity omitted, closes full position."""
    _require_configured()
    try:
        result = await get_testnet_client().close_position(symbol.upper(), quantity)
        return {"status": "closed", "order": result}
    except BinanceFuturesTestnetError as exc:
        _handle_testnet_error(exc)


# ------------------------------------------------------------------ #
# Orders                                                               #
# ------------------------------------------------------------------ #

class PlaceOrderRequest(BaseModel):
    symbol: str
    side: str = Field(..., pattern="^(BUY|SELL)$")
    order_type: str = Field("MARKET", alias="type")
    quantity: float = Field(..., gt=0)
    price: float | None = None
    reduce_only: bool = False
    stop_price: float | None = None
    time_in_force: str = "GTC"

    model_config = {"populate_by_name": True}


@router.post("/order")
async def place_order(req: PlaceOrderRequest) -> dict[str, Any]:
    """Place a new futures order on the testnet."""
    _require_configured()
    try:
        result = await get_testnet_client().place_order(
            symbol=req.symbol.upper(),
            side=req.side,
            order_type=req.order_type,
            quantity=req.quantity,
            price=req.price,
            reduce_only=req.reduce_only,
            stop_price=req.stop_price,
            time_in_force=req.time_in_force,
        )
        return {"status": "placed", "order": result}
    except BinanceFuturesTestnetError as exc:
        _handle_testnet_error(exc)


@router.delete("/order/{order_id}")
async def cancel_order(symbol: str, order_id: int) -> dict[str, Any]:
    """Cancel an open order by symbol and order ID."""
    _require_configured()
    try:
        result = await get_testnet_client().cancel_order(symbol.upper(), order_id)
        return {"status": "cancelled", "order": result}
    except BinanceFuturesTestnetError as exc:
        _handle_testnet_error(exc)


@router.delete("/orders")
async def cancel_all_orders(symbol: str) -> dict[str, Any]:
    """Cancel all open orders for a symbol."""
    _require_configured()
    try:
        result = await get_testnet_client().cancel_all_orders(symbol.upper())
        return {"status": "cancelled_all", "result": result}
    except BinanceFuturesTestnetError as exc:
        _handle_testnet_error(exc)


@router.get("/orders")
async def get_open_orders(symbol: str | None = Query(default=None)) -> dict[str, Any]:
    """Return all open orders (or for a specific symbol)."""
    _require_configured()
    try:
        orders = await get_testnet_client().get_open_orders(symbol)
        return {"orders": orders, "count": len(orders)}
    except BinanceFuturesTestnetError as exc:
        _handle_testnet_error(exc)


@router.get("/orders/history")
async def get_order_history(
    symbol: str,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Return order history for a symbol."""
    _require_configured()
    try:
        orders = await get_testnet_client().get_order_history(symbol.upper(), limit)
        return {"orders": orders, "count": len(orders)}
    except BinanceFuturesTestnetError as exc:
        _handle_testnet_error(exc)


# ------------------------------------------------------------------ #
# Leverage                                                             #
# ------------------------------------------------------------------ #

@router.post("/leverage")
async def set_leverage(symbol: str, leverage: int = Query(..., ge=1, le=125)) -> dict[str, Any]:
    """Set leverage for a symbol (1–125x)."""
    _require_configured()
    try:
        result = await get_testnet_client().set_leverage(symbol.upper(), leverage)
        return {"status": "ok", **result}
    except BinanceFuturesTestnetError as exc:
        _handle_testnet_error(exc)


# ------------------------------------------------------------------ #
# Open from signal (one-click from dashboard)                          #
# ------------------------------------------------------------------ #

class OpenFromSignalRequest(BaseModel):
    symbol: str
    direction: str = Field(..., pattern="^(LONG|SHORT)$")
    entry_price: float | None = None   # None = market order
    stop_loss: float | None = None
    take_profit_1: float | None = None
    take_profit_2: float | None = None
    leverage: int = Field(default=5, ge=1, le=50)
    usdt_size: float = Field(default=100.0, gt=0, description="Position size in USDT")


@router.post("/from-signal")
async def open_from_signal(req: OpenFromSignalRequest) -> dict[str, Any]:
    """Open a testnet position directly from a strategy signal.

    Steps:
    1. Set leverage for the symbol
    2. Fetch mark price and exchange info for lot size
    3. Place MARKET (or LIMIT) entry order
    4. Place STOP_MARKET SL order (reduce-only)
    5. Place TAKE_PROFIT_MARKET TP1 order (reduce-only, 50% qty)
    6. Place TAKE_PROFIT_MARKET TP2 order if provided (reduce-only, 50% qty)
    """
    _require_configured()
    client = get_testnet_client()
    symbol = req.symbol.upper()
    side = "BUY" if req.direction == "LONG" else "SELL"
    close_side = "SELL" if req.direction == "LONG" else "BUY"

    try:
        # 1. Set leverage
        await client.set_leverage(symbol, req.leverage)

        # 2. Get mark price + lot precision
        mark_price = await client.get_mark_price(symbol)
        exchange_info = await client.get_exchange_info()
        info = exchange_info.get(symbol, {"step_size": 0.001, "qty_precision": 3})
        step = info["step_size"]
        precision = info["qty_precision"]

        # Calculate quantity from USDT size
        entry = req.entry_price or mark_price
        raw_qty = (req.usdt_size * req.leverage) / entry
        # Round down to nearest step size
        qty = round(raw_qty - (raw_qty % step), precision)
        if qty <= 0:
            raise HTTPException(status_code=400, detail="Calculated quantity is zero — increase usdt_size")

        results: dict[str, Any] = {
            "symbol": symbol,
            "direction": req.direction,
            "leverage": req.leverage,
            "entry_price": entry,
            "quantity": qty,
            "usdt_size": req.usdt_size,
            "orders": {},
        }

        # 3. Entry order
        order_type = "LIMIT" if req.entry_price else "MARKET"
        entry_order = await client.place_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=qty,
            price=req.entry_price,
        )
        results["orders"]["entry"] = entry_order

        # 4. Stop-loss order
        if req.stop_loss:
            sl_order = await client.place_order(
                symbol=symbol,
                side=close_side,
                order_type="STOP_MARKET",
                quantity=qty,
                stop_price=req.stop_loss,
                reduce_only=True,
            )
            results["orders"]["stop_loss"] = sl_order

        # 5. TP1 order (50% if TP2 also provided, else 100%)
        if req.take_profit_1:
            tp1_qty = round(qty * 0.5, precision) if req.take_profit_2 else qty
            tp1_order = await client.place_order(
                symbol=symbol,
                side=close_side,
                order_type="TAKE_PROFIT_MARKET",
                quantity=tp1_qty,
                stop_price=req.take_profit_1,
                reduce_only=True,
            )
            results["orders"]["take_profit_1"] = tp1_order

        # 6. TP2 order (remaining 50%)
        if req.take_profit_2 and req.take_profit_1:
            tp2_qty = round(qty - round(qty * 0.5, precision), precision)
            tp2_order = await client.place_order(
                symbol=symbol,
                side=close_side,
                order_type="TAKE_PROFIT_MARKET",
                quantity=tp2_qty,
                stop_price=req.take_profit_2,
                reduce_only=True,
            )
            results["orders"]["take_profit_2"] = tp2_order

        logger.info(
            "Testnet position opened from signal: %s %s %dx qty=%.4f",
            symbol, req.direction, req.leverage, qty,
        )
        return {"status": "opened", **results}

    except BinanceFuturesTestnetError as exc:
        _handle_testnet_error(exc)
