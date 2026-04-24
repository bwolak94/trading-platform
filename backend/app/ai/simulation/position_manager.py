"""Position manager — tracks open and closed simulated positions in memory."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from app.core.logging import get_logger

logger = get_logger(__name__)

PositionStatus = Literal["OPEN", "CLOSED", "STOPPED_OUT", "TP1_HIT", "TP2_HIT", "TP3_HIT"]
Direction = Literal["LONG", "SHORT"]

# Realistic Binance Futures fee schedule (taker)
FEE_TAKER_PCT = 0.04   # 0.04% per side
# Funding rate applied every 8 hours (approximate average)
FUNDING_RATE_8H = 0.01  # 0.01% per 8h interval (positive = longs pay shorts)


@dataclass
class SimPosition:
    """In-memory representation of a paper trading position."""

    id: uuid.UUID
    symbol: str
    direction: Direction
    strategy: str
    regime: str
    confidence: int
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float | None
    take_profit_3: float | None
    session_id: uuid.UUID
    factors: list[dict] = field(default_factory=list)
    current_price: float = 0.0
    exit_price: float | None = None
    pnl_pct: float = 0.0
    status: PositionStatus = "OPEN"
    exit_reason: str | None = None
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: datetime | None = None
    trailing_active: bool = False
    trailing_stop: float = 0.0       # dynamic SL that moves with price
    trail_distance: float = 0.0      # distance = |entry - original_sl|
    tp1_hit: bool = False             # True after first TP is reached
    mae_pct: float = 0.0   # Maximum Adverse Excursion (worst unrealized loss %)
    mfe_pct: float = 0.0   # Maximum Favorable Excursion (best unrealized profit %)
    # --- Partial TP ladder (25 / 50 / 25 split) ---
    remaining_size_pct: float = 1.0    # fraction of original position still open
    tp1_partial_closed: bool = False   # True after 25% closed at TP1
    tp2_partial_closed: bool = False   # True after another 50% closed at TP2
    realized_pnl_pct: float = 0.0      # cumulative PnL from partial closes (weighted)
    # --- Option B: Leverage + fees + funding ---
    leverage: float = 1.0              # position leverage multiplier
    position_size_usdt: float = 100.0  # notional USD value of position
    fee_paid_pct: float = 0.0          # total fees charged (entry + exit), as % of notional
    funding_charged_pct: float = 0.0   # cumulative funding rate charges as % of margin
    liquidation_price: float = 0.0     # estimated liquidation price
    last_funding_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        """Calculate liquidation price and apply entry fee after construction."""
        self._recalculate_liquidation()
        # Entry fee: taker fee on both sides pre-charged at open
        entry_fee = FEE_TAKER_PCT * 2  # entry + expected exit fee
        self.fee_paid_pct += entry_fee

    def _recalculate_liquidation(self) -> None:
        """Estimate liquidation price based on leverage and margin."""
        if self.leverage <= 1 or self.entry_price == 0:
            self.liquidation_price = 0.0
            return
        # Simplified: liquidation when unrealized loss = initial margin (1/leverage)
        # Long: entry * (1 - 1/leverage + maintenance_margin)
        # Short: entry * (1 + 1/leverage - maintenance_margin)
        maintenance_margin = 0.004  # 0.4% maintenance margin rate
        margin_fraction = 1.0 / self.leverage
        if self.direction == "LONG":
            self.liquidation_price = round(
                self.entry_price * (1 - margin_fraction + maintenance_margin), 8
            )
        else:
            self.liquidation_price = round(
                self.entry_price * (1 + margin_fraction - maintenance_margin), 8
            )

    def apply_funding_rate(self, funding_rate: float = FUNDING_RATE_8H) -> None:
        """Charge (or credit) funding rate against the position.

        Longs pay when rate > 0; shorts receive. Rate is expressed as a
        percentage of the notional (e.g. 0.01 = 0.01%).
        """
        if self.direction == "LONG":
            self.funding_charged_pct += funding_rate
        else:
            self.funding_charged_pct -= funding_rate  # shorts receive funding

    @property
    def leveraged_pnl_pct(self) -> float:
        """PnL percentage on the *margin* (not notional), after fees and funding."""
        raw = self.pnl_pct * self.leverage
        total_costs = self.fee_paid_pct + self.funding_charged_pct
        return round(raw - total_costs, 4)

    @property
    def margin_usdt(self) -> float:
        """Initial margin in USDT."""
        return round(self.position_size_usdt / self.leverage, 2)

    @property
    def unrealized_pnl_usdt(self) -> float:
        """Unrealized PnL in USDT based on leveraged PnL."""
        return round(self.margin_usdt * self.leveraged_pnl_pct / 100, 2)

    @property
    def distance_to_liquidation_pct(self) -> float | None:
        """Distance from current price to liquidation price as % of current price."""
        if not self.liquidation_price or not self.current_price:
            return None
        return round(
            abs(self.current_price - self.liquidation_price) / self.current_price * 100, 2
        )

    def update_pnl(self, current_price: float) -> None:
        """Recalculate running PnL given the latest price. Updates MAE/MFE."""
        self.current_price = current_price
        if self.entry_price == 0:
            return
        if self.direction == "LONG":
            self.pnl_pct = (current_price - self.entry_price) / self.entry_price * 100
        else:
            self.pnl_pct = (self.entry_price - current_price) / self.entry_price * 100
        # Update MAE (worst loss) and MFE (best profit)
        if self.pnl_pct < self.mae_pct:
            self.mae_pct = self.pnl_pct
        if self.pnl_pct > self.mfe_pct:
            self.mfe_pct = self.pnl_pct

    def _record_partial_close(self, closed_fraction: float, price: float) -> None:
        """Accumulate realized PnL for a partial close.

        Args:
            closed_fraction: Fraction of the *original* position being closed now.
            price: Exit price for this partial close.
        """
        if self.entry_price == 0:
            return
        if self.direction == "LONG":
            slice_pnl = (price - self.entry_price) / self.entry_price * 100
        else:
            slice_pnl = (self.entry_price - price) / self.entry_price * 100
        # Weight by the fraction of the original position being realized
        self.realized_pnl_pct += slice_pnl * closed_fraction

    def check_tp_sl(self, current_price: float) -> str | None:
        """Check if TP or SL was hit.  Implements a 25/50/25 partial-close ladder.

        Partial close sequence:
          TP1 hit → close 25 % of position, move SL to entry (risk-free), activate trailing.
                    Return None — position stays OPEN.
          TP2 hit → close 50 % more (25 % of original remains), keep trailing.
                    Return None — position stays OPEN.
          TP3 hit → close final 25 %, position fully closed.
                    Return "TP3_HIT".
          Trailing SL hit (after TP1) → close whatever fraction remains.
                    Return "SL_HIT".
          Hard SL hit (before TP1) → close full position.
                    Return "SL_HIT".

        Returns:
            Exit reason string if the position should be closed, else None.
        """
        self.update_pnl(current_price)

        if self.direction == "LONG":
            # --- Trailing stop check (active after TP1) ---
            if self.trailing_active:
                new_trail = current_price - self.trail_distance
                if new_trail > self.trailing_stop:
                    self.trailing_stop = new_trail
                if current_price <= self.trailing_stop:
                    # Close remaining size at trailing stop
                    self._record_partial_close(self.remaining_size_pct, current_price)
                    self.remaining_size_pct = 0.0
                    return "SL_HIT"
            else:
                if current_price <= self.stop_loss:
                    self._record_partial_close(self.remaining_size_pct, current_price)
                    self.remaining_size_pct = 0.0
                    return "SL_HIT"

            # --- TP3: close final 25 % ---
            if self.take_profit_3 and self.tp2_partial_closed and current_price >= self.take_profit_3:
                self._record_partial_close(self.remaining_size_pct, current_price)
                self.remaining_size_pct = 0.0
                return "TP3_HIT"

            # --- TP2: close 50 % of original (second slice) ---
            if self.take_profit_2 and self.tp1_partial_closed and not self.tp2_partial_closed and current_price >= self.take_profit_2:
                self.tp2_partial_closed = True
                self._record_partial_close(0.50, current_price)
                self.remaining_size_pct = 0.25
                logger.debug(
                    "SIM | %s TP2 hit @ %.4f — 50%% partial closed, remaining=25%%",
                    self.symbol, current_price,
                )
                return None  # position still open with 25 %

            # --- TP1: close 25 % of original (first slice) ---
            if not self.tp1_hit and current_price >= self.take_profit_1:
                self.tp1_hit = True
                self.tp1_partial_closed = True
                self._record_partial_close(0.25, current_price)
                self.remaining_size_pct = 0.75
                # Move SL to entry (risk-free) and activate trailing
                self.trailing_active = True
                self.trail_distance = abs(self.entry_price - self.stop_loss)
                self.trailing_stop = self.entry_price
                logger.debug(
                    "SIM | %s TP1 hit @ %.4f — 25%% partial closed, trailing at entry %.4f",
                    self.symbol, current_price, self.trailing_stop,
                )

        else:  # SHORT
            # --- Trailing stop check ---
            if self.trailing_active:
                new_trail = current_price + self.trail_distance
                if new_trail < self.trailing_stop:
                    self.trailing_stop = new_trail
                if current_price >= self.trailing_stop:
                    self._record_partial_close(self.remaining_size_pct, current_price)
                    self.remaining_size_pct = 0.0
                    return "SL_HIT"
            else:
                if current_price >= self.stop_loss:
                    self._record_partial_close(self.remaining_size_pct, current_price)
                    self.remaining_size_pct = 0.0
                    return "SL_HIT"

            # --- TP3: close final 25 % ---
            if self.take_profit_3 and self.tp2_partial_closed and current_price <= self.take_profit_3:
                self._record_partial_close(self.remaining_size_pct, current_price)
                self.remaining_size_pct = 0.0
                return "TP3_HIT"

            # --- TP2: close 50 % of original ---
            if self.take_profit_2 and self.tp1_partial_closed and not self.tp2_partial_closed and current_price <= self.take_profit_2:
                self.tp2_partial_closed = True
                self._record_partial_close(0.50, current_price)
                self.remaining_size_pct = 0.25
                logger.debug(
                    "SIM | %s TP2 hit @ %.4f — 50%% partial closed, remaining=25%%",
                    self.symbol, current_price,
                )
                return None

            # --- TP1: close 25 % of original ---
            if not self.tp1_hit and current_price <= self.take_profit_1:
                self.tp1_hit = True
                self.tp1_partial_closed = True
                self._record_partial_close(0.25, current_price)
                self.remaining_size_pct = 0.75
                self.trailing_active = True
                self.trail_distance = abs(self.entry_price - self.stop_loss)
                self.trailing_stop = self.entry_price
                logger.debug(
                    "SIM | %s TP1 hit @ %.4f — 25%% partial closed, trailing at entry %.4f",
                    self.symbol, current_price, self.trailing_stop,
                )

        return None

    def close(self, exit_price: float, reason: str) -> None:
        """Close the position and record exit details.

        The final pnl_pct is the weighted realized PnL accumulated across all
        partial closes.  If remaining_size_pct > 0 (e.g. trailing SL closed the
        rest), the last slice was already recorded in check_tp_sl before close()
        is called, so realized_pnl_pct already holds the full result.
        """
        self.exit_price = exit_price
        self.exit_reason = reason
        self.closed_at = datetime.now(timezone.utc)
        self.update_pnl(exit_price)
        # Override pnl_pct with the accumulated weighted realized PnL when
        # partial closes were used; fall back to the simple pnl_pct otherwise.
        if self.tp1_partial_closed:
            self.pnl_pct = round(self.realized_pnl_pct, 4)
        if reason == "SL_HIT":
            self.status = "STOPPED_OUT"
        elif reason in ("TP2_HIT", "TP3_HIT"):
            self.status = reason  # type: ignore[assignment]
        else:
            self.status = "CLOSED"


class PositionManager:
    """Manages a collection of simulated positions with thread-safe operations."""

    def __init__(self, max_positions: int = 10) -> None:
        self.max_positions = max_positions
        self._open_positions: dict[uuid.UUID, SimPosition] = {}
        self._closed_positions: list[SimPosition] = []
        # Track one position per symbol to avoid duplicates
        self._symbol_positions: dict[str, uuid.UUID] = {}

    def can_open(self, symbol: str) -> bool:
        """Return True if a new position can be opened for this symbol."""
        if symbol in self._symbol_positions:
            return False  # Already have an open position for this symbol
        return len(self._open_positions) < self.max_positions

    def open_position(self, pos: SimPosition) -> None:
        """Register a new open position."""
        self._open_positions[pos.id] = pos
        self._symbol_positions[pos.symbol] = pos.id
        logger.info(
            "SIM | Opened %s %s @ %.4f (strategy=%s conf=%d%%)",
            pos.symbol, pos.direction, pos.entry_price, pos.strategy, pos.confidence,
        )

    def close_position(self, pos_id: uuid.UUID, exit_price: float, reason: str) -> SimPosition | None:
        """Close an open position and move it to closed list."""
        pos = self._open_positions.pop(pos_id, None)
        if not pos:
            return None
        pos.close(exit_price, reason)
        self._closed_positions.append(pos)
        self._symbol_positions.pop(pos.symbol, None)
        logger.info(
            "SIM | Closed %s %s @ %.4f reason=%s pnl=%.2f%%",
            pos.symbol, pos.direction, exit_price, reason, pos.pnl_pct,
        )
        return pos

    def update_prices(self, prices: dict[str, float]) -> list[tuple[SimPosition, str]]:
        """Update all open positions with latest prices and return those that hit TP/SL."""
        triggered: list[tuple[SimPosition, str]] = []
        for pos in list(self._open_positions.values()):
            price = prices.get(pos.symbol)
            if price is None:
                continue
            reason = pos.check_tp_sl(price)
            if reason:
                triggered.append((pos, reason))
        return triggered

    @property
    def open_positions(self) -> list[SimPosition]:
        """Return all currently open positions."""
        return list(self._open_positions.values())

    @property
    def closed_positions(self) -> list[SimPosition]:
        """Return all closed positions (most recent last)."""
        return list(self._closed_positions)

    @property
    def open_count(self) -> int:
        """Number of currently open positions."""
        return len(self._open_positions)
