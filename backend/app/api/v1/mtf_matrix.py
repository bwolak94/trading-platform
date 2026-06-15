"""Multi-timeframe signal matrix endpoint.

Returns a grid: rows=assets, columns=timeframes, each cell = signal direction + confidence.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.signal import Signal

router = APIRouter(tags=["mtf-matrix"])

TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]
DEFAULT_ASSETS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "AVAXUSDT",
    "ADAUSDT",
    "DOGEUSDT",
]

# Heuristic mapping of strategy name keywords to timeframes
_STRATEGY_TIMEFRAME_MAP: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
    "daily": "1d",
    "hourly": "1h",
}


def _infer_timeframe(signal: Signal) -> str:
    """Infer the timeframe from strategy name or return '1h' as default."""
    strategy = (signal.strategy_name if hasattr(signal, "strategy_name") else "") or ""
    for keyword, tf in _STRATEGY_TIMEFRAME_MAP.items():
        if keyword in strategy.lower():
            return tf
    # Fall back to reading a 'timeframe' key if it exists in factors
    if signal.factors and isinstance(signal.factors, list):
        for f in signal.factors:
            if isinstance(f, dict) and f.get("timeframe"):
                return str(f["timeframe"])
    return "1h"


@router.get("/mtf-matrix")
async def get_mtf_signal_matrix(
    assets: str = Query(default=",".join(DEFAULT_ASSETS), description="Comma-separated asset symbols"),
    timeframes: str = Query(default="1m,5m,15m,1h,4h,1d", description="Comma-separated timeframes"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return a matrix of signals for each asset/timeframe combination.

    Queries the signals table for recent signals (last 4 hours) per asset.
    Each cell contains the most recent signal's direction and confidence.
    Missing cells default to NEUTRAL with 0 confidence.

    Returns:
        {
            "matrix": {
                "BTCUSDT": {
                    "1h": {"direction": "LONG", "confidence": 78, "signal_id": "uuid-..."},
                    "4h": {"direction": "NEUTRAL", "confidence": 0, "signal_id": null},
                    ...
                },
                ...
            },
            "assets": [...],
            "timeframes": [...],
            "generated_at": "ISO8601"
        }
    """
    asset_list = [a.strip().upper() for a in assets.split(",") if a.strip()]
    tf_list = [t.strip() for t in timeframes.split(",") if t.strip()]

    cutoff = datetime.now(timezone.utc) - timedelta(hours=4)

    # Fetch recent signals for all requested assets in one query
    stmt = (
        select(Signal)
        .where(Signal.asset.in_(asset_list))
        .where(Signal.created_at >= cutoff)
        .order_by(Signal.asset, Signal.created_at.desc())
    )
    result = await db.execute(stmt)
    recent_signals: list[Signal] = list(result.scalars().all())

    # Build a lookup: (asset, timeframe) -> latest signal
    cell_map: dict[tuple[str, str], Signal] = {}
    for sig in recent_signals:
        tf = _infer_timeframe(sig)
        key = (sig.asset, tf)
        if key not in cell_map:  # already ordered desc, first is latest
            cell_map[key] = sig

    # Construct the matrix
    matrix: dict[str, dict[str, dict[str, Any]]] = {}
    for asset in asset_list:
        matrix[asset] = {}
        for tf in tf_list:
            sig = cell_map.get((asset, tf))
            if sig:
                matrix[asset][tf] = {
                    "direction": sig.direction,
                    "confidence": int(sig.confidence),
                    "signal_id": str(sig.id),
                    "status": sig.status,
                    "created_at": sig.created_at.isoformat() if sig.created_at else None,
                }
            else:
                matrix[asset][tf] = {
                    "direction": "NEUTRAL",
                    "confidence": 0,
                    "signal_id": None,
                    "status": None,
                    "created_at": None,
                }

    return {
        "matrix": matrix,
        "assets": asset_list,
        "timeframes": tf_list,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_hours": 4,
        "total_signals_found": len(recent_signals),
    }
