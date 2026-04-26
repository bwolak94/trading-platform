"""AI Post-Trade Commentary endpoint.

Generates a concise critique of a closed simulated position:
entry quality, MAE, exit timing, and regime alignment.
Does NOT call an external LLM — uses deterministic rules for MVP speed.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.core.database import async_session

router = APIRouter(prefix="/simulation", tags=["ai-commentary"])
logger = logging.getLogger(__name__)


def _generate_commentary(pos: Any) -> str:
    """Produce a rule-based post-trade commentary string."""
    lines: list[str] = []

    # Entry quality
    pnl = float(pos.pnl_pct or 0)
    mae = float(getattr(pos, "mae_pct", 0) or 0)
    direction = getattr(pos, "direction", "LONG")
    confidence = float(getattr(pos, "confidence", 70) or 70)

    if confidence >= 75:
        lines.append(f"High-confidence ({confidence:.0f}%) {direction} signal.")
    elif confidence >= 55:
        lines.append(f"Medium-confidence ({confidence:.0f}%) {direction} signal — borderline entry.")
    else:
        lines.append(f"Low-confidence ({confidence:.0f}%) entry; review signal filters.")

    # MAE assessment
    if abs(mae) < 0.5:
        lines.append("Minimal adverse excursion — excellent entry timing.")
    elif abs(mae) < 1.5:
        lines.append(f"MAE of {abs(mae):.1f}% was acceptable; stop placement reasonable.")
    else:
        lines.append(f"MAE of {abs(mae):.1f}% was high — consider tighter entry or wider stop.")

    # Exit assessment
    if pnl > 2:
        lines.append(f"Strong exit at +{pnl:.1f}% — TP target captured well.")
    elif pnl > 0:
        lines.append(f"Modest gain of +{pnl:.1f}%. Consider trailing stop to extend winners.")
    elif pnl > -1:
        lines.append(f"Small loss of {pnl:.1f}%. Risk management held; nothing unusual.")
    else:
        lines.append(f"Loss of {pnl:.1f}% exceeded target. Assess whether regime was aligned at entry.")

    return " ".join(lines)


@router.get("/positions/{position_id}/commentary", summary="AI post-trade commentary")
async def get_position_commentary(position_id: str) -> dict[str, Any]:
    """Generate a brief AI critique for a closed simulated position."""
    from app.models.simulation import SimulatedPosition

    async with async_session() as session:
        result = await session.execute(
            select(SimulatedPosition).where(SimulatedPosition.id == position_id)
        )
        pos = result.scalar_one_or_none()

    if pos is None:
        raise HTTPException(status_code=404, detail="Position not found")

    if pos.status not in ("CLOSED", "STOPPED"):
        return {
            "status": "ok",
            "data": {
                "position_id": position_id,
                "commentary": "Position is still open — commentary available after close.",
                "grade": None,
            },
        }

    commentary = _generate_commentary(pos)

    pnl = float(pos.pnl_pct or 0)
    mae = abs(float(getattr(pos, "mae_pct", 0) or 0))
    if pnl > 1.5 and mae < 1.0:
        grade = "A"
    elif pnl > 0 and mae < 1.5:
        grade = "B"
    elif pnl > -0.5:
        grade = "C"
    else:
        grade = "D"

    return {
        "status": "ok",
        "source": "rule_based",
        "data": {
            "position_id": position_id,
            "asset": pos.asset,
            "direction": pos.direction,
            "pnl_pct": round(pnl, 2),
            "mae_pct": round(mae, 2),
            "grade": grade,
            "commentary": commentary,
        },
    }
