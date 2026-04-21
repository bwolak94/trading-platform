"""Watchlist API — manage named symbol watchlists for focused scanning."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

# In-memory storage (production would use DB)
_watchlists: dict[str, list[str]] = {
    "default": [],
    "majors": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"],
    "defi": ["UNIUSDT", "AAVEUSDT", "MKRUSDT", "COMPUSDT", "CRVUSDT"],
    "layer2": ["MATICUSDT", "ARBUSDT", "OPUSDT", "STRKUSDT"],
}


class WatchlistCreate(BaseModel):
    """Schema for creating/updating a watchlist."""
    name: str
    symbols: list[str]


class WatchlistUpdate(BaseModel):
    """Schema for updating watchlist symbols."""
    symbols: list[str]


@router.get("/")
async def list_watchlists() -> dict[str, Any]:
    """Return all available watchlists."""
    return {
        "watchlists": [
            {"name": name, "symbols": syms, "count": len(syms)}
            for name, syms in _watchlists.items()
        ]
    }


@router.get("/{name}")
async def get_watchlist(name: str) -> dict[str, Any]:
    """Get a specific watchlist by name."""
    if name not in _watchlists:
        raise HTTPException(status_code=404, detail=f"Watchlist '{name}' not found")
    return {"name": name, "symbols": _watchlists[name], "count": len(_watchlists[name])}


@router.post("/")
async def create_watchlist(body: WatchlistCreate) -> dict[str, Any]:
    """Create a new watchlist."""
    if body.name in _watchlists:
        raise HTTPException(status_code=409, detail=f"Watchlist '{body.name}' already exists")
    normalized = [s.upper().strip() for s in body.symbols if s.strip()]
    _watchlists[body.name] = normalized
    return {"name": body.name, "symbols": normalized, "count": len(normalized)}


@router.put("/{name}")
async def update_watchlist(name: str, body: WatchlistUpdate) -> dict[str, Any]:
    """Replace the symbols in a watchlist."""
    if name not in _watchlists:
        raise HTTPException(status_code=404, detail=f"Watchlist '{name}' not found")
    normalized = [s.upper().strip() for s in body.symbols if s.strip()]
    _watchlists[name] = normalized
    return {"name": name, "symbols": normalized, "count": len(normalized)}


@router.delete("/{name}")
async def delete_watchlist(name: str) -> dict[str, str]:
    """Delete a watchlist."""
    if name == "default":
        raise HTTPException(status_code=400, detail="Cannot delete the default watchlist")
    if name not in _watchlists:
        raise HTTPException(status_code=404, detail=f"Watchlist '{name}' not found")
    del _watchlists[name]
    return {"status": "deleted", "name": name}


@router.post("/{name}/apply-to-bot")
async def apply_watchlist_to_bot(name: str) -> dict[str, Any]:
    """Set the paper trading bot to only scan symbols in this watchlist."""
    if name not in _watchlists:
        raise HTTPException(status_code=404, detail=f"Watchlist '{name}' not found")
    from app.ai.simulation.paper_trading_engine import get_paper_trading_engine
    engine = get_paper_trading_engine()
    engine._symbol_whitelist = set(_watchlists[name])
    return {
        "status": "applied",
        "name": name,
        "symbols_in_whitelist": len(_watchlists[name]),
    }


@router.post("/clear-bot-whitelist")
async def clear_bot_whitelist() -> dict[str, str]:
    """Clear the bot's whitelist so it scans all symbols."""
    from app.ai.simulation.paper_trading_engine import get_paper_trading_engine
    engine = get_paper_trading_engine()
    engine._symbol_whitelist.clear()
    return {"status": "cleared"}
