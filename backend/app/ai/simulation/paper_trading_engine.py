"""Paper Trading Engine — 24/7 simulation bot that runs all strategies on all symbols.

The engine scans every SCAN_INTERVAL seconds, generates signals using the same
SignalAggregator + strategies as the live agent, and auto-enters/exits virtual
positions. All positions are stored in PostgreSQL for historical analysis.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from app.ai.risk.risk_engine import get_risk_engine
from app.ai.simulation.performance_tracker import PerformanceTracker, PerformanceSnapshot
from app.ai.simulation.position_manager import PositionManager, SimPosition
from app.core.logging import get_logger
from app.core.symbols import get_active_crypto_symbols

logger = get_logger(__name__)

SCAN_INTERVAL = 30          # seconds between full symbol scans
MIN_CONFIDENCE = 55         # minimum confidence to enter a simulated position
MAX_POSITIONS = 100         # max concurrent open positions
PRICE_CHECK_INTERVAL = 10  # seconds between TP/SL price checks
COOLDOWN_HOURS = 4             # hours before re-entering same symbol after close
MIN_24H_VOLUME_USD = 50_000_000  # minimum 24h volume in USD to scan symbol
SESSION_FILTER = None          # None = all sessions, "LONDON", "NEWYORK", "ASIAN"


class PaperTradingEngine:
    """Asynchronous paper-trading engine that runs 24/7 in the background.

    Flow:
        1. Every SCAN_INTERVAL: fetch latest data for all symbols, run strategies.
        2. For signals with confidence >= MIN_CONFIDENCE, open a SimPosition.
        3. Every PRICE_CHECK_INTERVAL: fetch current prices, check TP/SL.
        4. Close positions that hit TP or SL. Persist to PostgreSQL.
        5. Broadcast position updates via WebSocket.
    """

    def __init__(self) -> None:
        self._running = False
        self._scan_task: asyncio.Task | None = None
        self._monitor_task: asyncio.Task | None = None
        self._session_id: uuid.UUID = uuid.uuid4()
        self.position_manager = PositionManager(max_positions=MAX_POSITIONS)
        self.performance_tracker = PerformanceTracker()
        self.risk_engine = get_risk_engine()
        # --- Filters ---
        self._cooldown_map: dict[str, datetime] = {}   # symbol → earliest re-entry time
        self._symbol_blacklist: set[str] = set()
        self._symbol_whitelist: set[str] = set()       # if non-empty, only scan these
        self._auto_blacklist: dict[str, list[datetime]] = {}  # symbol → recent SL times

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        """Start the paper trading engine background tasks."""
        if self._running:
            logger.warning("PaperTradingEngine already running")
            return
        self._running = True
        self._session_id = uuid.uuid4()
        await self._persist_session_start()
        self._scan_task = asyncio.create_task(self._scan_loop(), name="sim_scan")
        self._monitor_task = asyncio.create_task(self._monitor_loop(), name="sim_monitor")
        logger.info("PaperTradingEngine started — session %s", self._session_id)

    async def stop(self) -> None:
        """Stop the engine and persist the final session summary."""
        self._running = False
        if self._scan_task:
            self._scan_task.cancel()
        if self._monitor_task:
            self._monitor_task.cancel()
        await self._persist_session_end()
        logger.info("PaperTradingEngine stopped — session %s", self._session_id)

    # ------------------------------------------------------------------ #
    # Background loops                                                     #
    # ------------------------------------------------------------------ #

    async def _scan_loop(self) -> None:
        """Periodically scan all symbols and open new positions on strong signals."""
        while self._running:
            try:
                await self._scan_all_symbols()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Error in PaperTradingEngine scan loop: %s", exc)
            await asyncio.sleep(SCAN_INTERVAL)

    async def _monitor_loop(self) -> None:
        """Periodically check open positions against current prices."""
        while self._running:
            try:
                await self._check_positions()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Error in PaperTradingEngine monitor loop: %s", exc)
            await asyncio.sleep(PRICE_CHECK_INTERVAL)

    # ------------------------------------------------------------------ #
    # Signal scanning                                                      #
    # ------------------------------------------------------------------ #

    async def _scan_all_symbols(self) -> None:
        """Run all strategies on all active symbols and open positions for good signals."""
        # Check risk engine circuit breaker first
        if self.risk_engine.is_paused:
            logger.warning(
                "PaperTradingEngine paused by risk engine: %s",
                self.risk_engine._pause_reason,
            )
            return

        # Session filter
        if SESSION_FILTER and not self._is_session_active(SESSION_FILTER):
            logger.debug("Session filter active — not in %s session", SESSION_FILTER)
            return

        symbols = get_active_crypto_symbols()
        import random
        symbols_shuffled = list(symbols)
        random.shuffle(symbols_shuffled)

        for symbol in symbols_shuffled:
            if not self._running:
                break
            if not self.position_manager.can_open(symbol):
                continue
            if self._is_blacklisted(symbol):
                continue
            if self._symbol_whitelist and symbol not in self._symbol_whitelist:
                continue
            if self._is_on_cooldown(symbol):
                continue
            try:
                signal = await self._analyze_symbol(symbol)
                if signal and signal.get("confidence", 0) >= MIN_CONFIDENCE:
                    await self._open_position_from_signal(symbol, signal)
            except Exception as exc:
                logger.debug("Error scanning %s: %s", symbol, exc)
            await asyncio.sleep(0.1)

    async def _analyze_symbol(self, symbol: str) -> dict[str, Any] | None:
        """Run the trading agent analysis on a single symbol.

        Returns the best signal dict or None if no setup found.
        """
        from app.ai.agent.trading_agent import get_trading_agent
        agent = get_trading_agent()
        try:
            result = await agent._analyze_pair(symbol)
            if result and result.action in ("LONG", "SHORT"):
                return result.to_dict()
        except Exception as exc:
            logger.debug("Analysis failed for %s: %s", symbol, exc)
        return None

    async def _open_position_from_signal(self, symbol: str, signal: dict[str, Any]) -> None:
        """Create and persist a new simulated position from a trade signal."""
        tp_levels = signal.get("tp_levels", [])
        tp1 = tp_levels[0] if len(tp_levels) > 0 else signal.get("entry", 0) * 1.01
        tp2 = tp_levels[1] if len(tp_levels) > 1 else None
        tp3 = tp_levels[2] if len(tp_levels) > 2 else None

        pos = SimPosition(
            id=uuid.uuid4(),
            symbol=symbol,
            direction=signal["action"],  # LONG or SHORT
            strategy=signal.get("strategy_name", "unknown"),
            regime=signal.get("regime", "UNKNOWN"),
            confidence=int(signal.get("confidence", 0)),
            entry_price=float(signal.get("entry", 0)),
            stop_loss=float(signal.get("stop_loss", 0)),
            take_profit_1=float(tp1),
            take_profit_2=float(tp2) if tp2 else None,
            take_profit_3=float(tp3) if tp3 else None,
            session_id=self._session_id,
            factors=signal.get("conditions", []),
        )

        if pos.entry_price <= 0 or pos.stop_loss <= 0:
            return

        self.position_manager.open_position(pos)
        await self._persist_position(pos)
        await self._broadcast_position_update(pos, "opened")

    # ------------------------------------------------------------------ #
    # Position monitoring                                                  #
    # ------------------------------------------------------------------ #

    async def _check_positions(self) -> None:
        """Fetch latest prices for all open positions and check TP/SL."""
        open_pos = self.position_manager.open_positions
        if not open_pos:
            return

        symbols = list({p.symbol for p in open_pos})
        prices = await self._fetch_current_prices(symbols)
        if not prices:
            return

        triggered = self.position_manager.update_prices(prices)
        for pos, reason in triggered:
            exit_price = prices.get(pos.symbol, pos.current_price)
            closed = self.position_manager.close_position(pos.id, exit_price, reason)
            if closed:
                self.performance_tracker.record_close(closed)
                self.risk_engine.record_trade(closed.pnl_pct)
                await self._persist_position_close(closed)
                await self._broadcast_position_update(closed, "closed")
                await self._update_session_stats()
                # Post-close filters
                self._set_cooldown(closed.symbol)
                if closed.exit_reason == "SL_HIT":
                    self._auto_blacklist.setdefault(closed.symbol, []).append(datetime.now(timezone.utc))
                    self._check_auto_blacklist(closed.symbol)

        # Broadcast running PnL updates for all open positions
        if open_pos:
            await self._broadcast_open_positions()

    async def _fetch_current_prices(self, symbols: list[str]) -> dict[str, float]:
        """Fetch latest prices for a list of symbols from Binance."""
        import httpx
        from app.data.fetchers.binance_fetcher import FUTURES_REST_URL, _check_circuit_breaker, _get_client, _record_success, _record_failure

        if not _check_circuit_breaker():
            return {}

        # Build comma-separated list of Binance symbols
        binance_symbols = [s.replace("/", "") for s in symbols]
        prices: dict[str, float] = {}

        client = _get_client()
        try:
            resp = await client.get(
                f"{FUTURES_REST_URL}/fapi/v1/ticker/price",
            )
            resp.raise_for_status()
            data = resp.json()
            _record_success()
            # data is a list of {symbol, price}
            sym_map = {item["symbol"]: float(item["price"]) for item in data}
            for our_sym, binance_sym in zip(symbols, binance_symbols):
                if binance_sym in sym_map:
                    prices[our_sym] = sym_map[binance_sym]
        except Exception as exc:
            _record_failure()
            logger.warning("Failed to fetch prices for position check: %s", exc)

        return prices

    # ------------------------------------------------------------------ #
    # Filtering helpers                                                    #
    # ------------------------------------------------------------------ #

    def _is_on_cooldown(self, symbol: str) -> bool:
        """Return True if the symbol is within its cooldown period."""
        cutoff = self._cooldown_map.get(symbol)
        if cutoff is None:
            return False
        if datetime.now(timezone.utc) < cutoff:
            return True
        del self._cooldown_map[symbol]
        return False

    def _set_cooldown(self, symbol: str) -> None:
        """Set a cooldown for a symbol after a position closes."""
        from datetime import timedelta
        self._cooldown_map[symbol] = datetime.now(timezone.utc) + timedelta(hours=COOLDOWN_HOURS)
        logger.debug("SIM | Cooldown set for %s until %s", symbol, self._cooldown_map[symbol].isoformat())

    def _is_blacklisted(self, symbol: str) -> bool:
        """Return True if the symbol is in the manual or auto blacklist."""
        return symbol in self._symbol_blacklist

    def _check_auto_blacklist(self, symbol: str) -> None:
        """Auto-blacklist a symbol if it has 3+ stop-outs in the last 24h."""
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)
        hits = self._auto_blacklist.get(symbol, [])
        # Keep only recent hits
        hits = [t for t in hits if t > cutoff]
        self._auto_blacklist[symbol] = hits
        if len(hits) >= 3:
            self._symbol_blacklist.add(symbol)
            logger.warning(
                "SIM | Auto-blacklisted %s after %d stop-outs in 24h", symbol, len(hits)
            )

    @staticmethod
    def _is_session_active(session: str) -> bool:
        """Return True if the given trading session is currently active (UTC hours)."""
        utc_hour = datetime.now(timezone.utc).hour
        if session == "LONDON":
            return 8 <= utc_hour < 17
        elif session == "NEWYORK":
            return 13 <= utc_hour < 22
        elif session == "ASIAN":
            return 0 <= utc_hour < 9
        return True

    # ------------------------------------------------------------------ #
    # Public filter controls                                               #
    # ------------------------------------------------------------------ #

    def blacklist_symbol(self, symbol: str) -> None:
        """Manually blacklist a symbol."""
        self._symbol_blacklist.add(symbol)
        logger.info("SIM | Blacklisted symbol: %s", symbol)

    def whitelist_symbol(self, symbol: str) -> None:
        """Add a symbol to the whitelist (if whitelist is used)."""
        self._symbol_whitelist.add(symbol)

    def clear_blacklist(self) -> None:
        """Clear the manual blacklist."""
        self._symbol_blacklist.clear()

    def get_filter_state(self) -> dict:
        """Return current filter state for API."""
        return {
            "blacklisted_symbols": sorted(self._symbol_blacklist),
            "whitelisted_symbols": sorted(self._symbol_whitelist),
            "cooldowns": {k: v.isoformat() for k, v in self._cooldown_map.items()},
            "session_filter": SESSION_FILTER,
            "cooldown_hours": COOLDOWN_HOURS,
        }

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    async def _persist_position(self, pos: SimPosition) -> None:
        """Insert a new SimulatedPosition row into the database."""
        try:
            from app.core.database import async_session
            from app.models.simulated_position import SimulatedPosition as SimPosModel

            async with async_session() as session:
                row = SimPosModel(
                    id=pos.id,
                    session_id=pos.session_id,
                    symbol=pos.symbol,
                    direction=pos.direction,
                    strategy=pos.strategy,
                    regime=pos.regime,
                    confidence=pos.confidence,
                    entry_price=pos.entry_price,
                    stop_loss=pos.stop_loss,
                    take_profit_1=pos.take_profit_1,
                    take_profit_2=pos.take_profit_2,
                    take_profit_3=pos.take_profit_3,
                    current_price=pos.entry_price,
                    pnl_pct=0.0,
                    status="OPEN",
                    factors=pos.factors,
                    opened_at=pos.opened_at,
                )
                session.add(row)
                await session.commit()
        except Exception as exc:
            logger.warning("Failed to persist position %s: %s", pos.id, exc)

    async def _persist_position_close(self, pos: SimPosition) -> None:
        """Update the SimulatedPosition row when a position is closed."""
        try:
            from app.core.database import async_session
            from app.models.simulated_position import SimulatedPosition as SimPosModel
            from sqlalchemy import select

            async with async_session() as session:
                result = await session.execute(
                    select(SimPosModel).where(SimPosModel.id == pos.id)
                )
                row = result.scalar_one_or_none()
                if row:
                    row.exit_price = pos.exit_price
                    row.pnl_pct = pos.pnl_pct
                    row.status = pos.status
                    row.exit_reason = pos.exit_reason
                    row.closed_at = pos.closed_at
                    row.current_price = pos.exit_price
                    row.max_adverse_excursion = pos.mae_pct
                    row.max_favorable_excursion = pos.mfe_pct
                    await session.commit()
        except Exception as exc:
            logger.warning("Failed to persist position close %s: %s", pos.id, exc)

    async def _persist_session_start(self) -> None:
        """Create a BotSession row on engine start."""
        try:
            from app.core.database import async_session
            from app.models.bot_session import BotSession

            async with async_session() as session:
                row = BotSession(id=self._session_id, is_active=True)
                session.add(row)
                await session.commit()
        except Exception as exc:
            logger.warning("Failed to persist session start: %s", exc)

    async def _persist_session_end(self) -> None:
        """Update BotSession on engine shutdown."""
        try:
            from app.core.database import async_session
            from app.models.bot_session import BotSession
            from sqlalchemy import select

            snap = self.performance_tracker.snapshot(self.position_manager.open_positions)

            async with async_session() as session:
                result = await session.execute(
                    select(BotSession).where(BotSession.id == self._session_id)
                )
                row = result.scalar_one_or_none()
                if row:
                    row.ended_at = datetime.now(timezone.utc)
                    row.is_active = False
                    row.total_trades = snap.total_trades
                    row.winning_trades = snap.winning_trades
                    row.total_pnl_pct = snap.total_pnl_pct
                    row.max_drawdown_pct = snap.max_drawdown_pct
                    row.sharpe_ratio = snap.sharpe_ratio
                    row.win_rate = snap.win_rate
                    await session.commit()
        except Exception as exc:
            logger.warning("Failed to persist session end: %s", exc)

    async def _update_session_stats(self) -> None:
        """Update live session stats in the database after each closed trade."""
        try:
            from app.core.database import async_session
            from app.models.bot_session import BotSession
            from sqlalchemy import select

            snap = self.performance_tracker.snapshot(self.position_manager.open_positions)

            async with async_session() as session:
                result = await session.execute(
                    select(BotSession).where(BotSession.id == self._session_id)
                )
                row = result.scalar_one_or_none()
                if row:
                    row.total_trades = snap.total_trades
                    row.winning_trades = snap.winning_trades
                    row.total_pnl_pct = snap.total_pnl_pct
                    row.max_drawdown_pct = snap.max_drawdown_pct
                    row.sharpe_ratio = snap.sharpe_ratio
                    row.win_rate = snap.win_rate
                    await session.commit()
        except Exception as exc:
            logger.debug("Failed to update session stats: %s", exc)

    # ------------------------------------------------------------------ #
    # WebSocket broadcasts                                                 #
    # ------------------------------------------------------------------ #

    async def _broadcast_position_update(self, pos: SimPosition, event: str) -> None:
        """Broadcast a position open/close event to WebSocket subscribers."""
        try:
            from app.core.websocket import manager
            await manager.broadcast(
                {
                    "type": "SIMULATION_POSITION",
                    "event": event,
                    "position": self._pos_to_dict(pos),
                },
                channel="simulation",
            )
        except Exception:
            pass

    async def _broadcast_open_positions(self) -> None:
        """Broadcast current state of all open positions."""
        try:
            from app.core.websocket import manager
            snap = self.performance_tracker.snapshot(self.position_manager.open_positions)
            await manager.broadcast(
                {
                    "type": "SIMULATION_UPDATE",
                    "positions": [self._pos_to_dict(p) for p in self.position_manager.open_positions],
                    "performance": self._snap_to_dict(snap),
                },
                channel="simulation",
            )
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def get_open_positions(self) -> list[dict[str, Any]]:
        """Return all open positions as serializable dicts."""
        return [self._pos_to_dict(p) for p in self.position_manager.open_positions]

    def get_performance(self) -> dict[str, Any]:
        """Return performance snapshot as serializable dict."""
        snap = self.performance_tracker.snapshot(self.position_manager.open_positions)
        return self._snap_to_dict(snap)

    def get_recent_closed(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return last N closed positions."""
        closed = self.position_manager.closed_positions[-limit:]
        return [self._pos_to_dict(p) for p in reversed(closed)]

    @property
    def is_running(self) -> bool:
        """True if the engine is currently running."""
        return self._running

    @property
    def session_id(self) -> str:
        """Current session UUID as string."""
        return str(self._session_id)

    # ------------------------------------------------------------------ #
    # Serialisation helpers                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _pos_to_dict(pos: SimPosition) -> dict[str, Any]:
        return {
            "id": str(pos.id),
            "symbol": pos.symbol,
            "direction": pos.direction,
            "strategy": pos.strategy,
            "regime": pos.regime,
            "confidence": pos.confidence,
            "entry_price": pos.entry_price,
            "stop_loss": pos.stop_loss,
            "take_profit_1": pos.take_profit_1,
            "take_profit_2": pos.take_profit_2,
            "take_profit_3": pos.take_profit_3,
            "current_price": pos.current_price,
            "exit_price": pos.exit_price,
            "pnl_pct": round(pos.pnl_pct, 4),
            "status": pos.status,
            "exit_reason": pos.exit_reason,
            "opened_at": pos.opened_at.isoformat(),
            "closed_at": pos.closed_at.isoformat() if pos.closed_at else None,
            "trailing_active": pos.trailing_active,
            "trailing_stop": pos.trailing_stop,
            "tp1_hit": pos.tp1_hit,
            "mae_pct": pos.mae_pct,
            "mfe_pct": pos.mfe_pct,
            "remaining_size_pct": pos.remaining_size_pct,
            "tp1_partial_closed": pos.tp1_partial_closed,
            "tp2_partial_closed": pos.tp2_partial_closed,
            "realized_pnl_pct": round(pos.realized_pnl_pct, 4),
        }

    @staticmethod
    def _snap_to_dict(snap: PerformanceSnapshot) -> dict[str, Any]:
        return {
            "total_trades": snap.total_trades,
            "winning_trades": snap.winning_trades,
            "losing_trades": snap.losing_trades,
            "win_rate": snap.win_rate,
            "total_pnl_pct": snap.total_pnl_pct,
            "avg_win_pct": snap.avg_win_pct,
            "avg_loss_pct": snap.avg_loss_pct,
            "profit_factor": snap.profit_factor,
            "max_drawdown_pct": snap.max_drawdown_pct,
            "sharpe_ratio": snap.sharpe_ratio,
            "best_trade": snap.best_trade,
            "worst_trade": snap.worst_trade,
            "open_positions": snap.open_positions,
            "running_pnl": snap.running_pnl,
        }


# Module-level singleton
_paper_engine: PaperTradingEngine | None = None


def get_paper_trading_engine() -> PaperTradingEngine:
    """Return the global PaperTradingEngine singleton."""
    global _paper_engine
    if _paper_engine is None:
        _paper_engine = PaperTradingEngine()
    return _paper_engine
