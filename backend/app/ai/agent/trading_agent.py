"""Core AI Trading Agent — scans multiple pairs, generates structured trade signals,
and learns from trade outcomes via a reward function."""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
import pandas as pd

from app.ai.regime.classifier import RegimeClassifier
from app.ai.strategies.base import MarketContext
from app.ai.strategies.trend_following import TrendFollowingStrategy
from app.ai.strategies.mean_reversion import MeanReversionStrategy
from app.ai.strategies.smc_strategy import SMCStrategy, find_order_blocks, find_fair_value_gaps
from app.ai.strategies.rsi_scalping import RSIScalpingStrategy
from app.ai.strategies.trend_trader import TrendTraderStrategy
from app.ai.strategies.volume_breakout import VolumeBreakoutStrategy
from app.data.processors.feature_engineer import compute_features

logger = logging.getLogger(__name__)

SCAN_INTERVAL = 30  # seconds
SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "DOGE/USDT", "ADA/USDT", "AVAX/USDT", "DOT/USDT", "LINK/USDT",
    "MATIC/USDT", "UNI/USDT", "ATOM/USDT", "LTC/USDT", "FIL/USDT",
    "APT/USDT", "ARB/USDT", "OP/USDT", "SUI/USDT", "PEPE/USDT",
]
SYMBOL_MAP = {s: s.replace("/", "") for s in SYMBOLS}
MIN_CONFIDENCE = 40  # minimum confidence to emit signal (lowered to show setups)


@dataclass
class TradeSignal:
    """Structured trade signal with entry/SL/TP levels and UI annotation data."""

    symbol: str
    action: str  # LONG / SHORT / HOLD
    entry: float
    stop_loss: float
    tp_levels: list[float]  # [TP1, TP2, TP3]
    confidence: float  # 0-100
    reasoning: str
    strategy_name: str
    regime: str
    risk_reward: float
    readiness: int  # 0-100
    conditions: list[dict]  # [{label, met}]
    ui_elements: dict  # sl_box, tp_boxes for chart rendering
    timestamp: str
    trailing_stop_pct: float = 0.0  # 0 = disabled, e.g. 0.02 = 2% trail

    def to_dict(self) -> dict:
        """Serialize signal to a plain dictionary."""
        return {
            "symbol": self.symbol,
            "action": self.action,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "tp_levels": self.tp_levels,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "strategy_name": self.strategy_name,
            "regime": self.regime,
            "risk_reward": self.risk_reward,
            "readiness": self.readiness,
            "conditions": self.conditions,
            "ui_elements": self.ui_elements,
            "timestamp": self.timestamp,
            "trailing_stop_pct": self.trailing_stop_pct,
        }


@dataclass
class TradeOutcome:
    """Recorded outcome of a closed trade."""

    signal: TradeSignal
    exit_price: float
    exit_time: str
    pnl_pct: float
    hit_level: str  # "SL", "TP1", "TP2", "TP3", "BE", "MANUAL"
    reward: float  # calculated reward score
    lessons: str  # what went right/wrong


class RewardEngine:
    """Calculates rewards for trade outcomes to feed the learning loop."""

    def calculate_reward(self, outcome: TradeOutcome) -> float:
        """Return a numeric reward based on how the trade resolved."""
        reward = 0.0
        # Positive rewards
        if outcome.hit_level == "TP3":
            reward += 3.0
        elif outcome.hit_level == "TP2":
            reward += 2.0
        elif outcome.hit_level == "TP1":
            reward += 1.0
        elif outcome.hit_level == "BE":
            reward += 0.1
        # Negative rewards
        elif outcome.hit_level == "SL":
            reward -= 1.0

        # Bonus for high confidence + correct direction
        if outcome.pnl_pct > 0 and outcome.signal.confidence > 80:
            reward += 0.5
        # Penalty for high confidence + wrong direction
        if outcome.pnl_pct < 0 and outcome.signal.confidence > 80:
            reward -= 1.0

        return round(reward, 2)

    def generate_lesson(self, outcome: TradeOutcome, market_context: dict) -> str:
        """Generate a text lesson from the trade outcome."""
        if outcome.pnl_pct > 0:
            return (
                f"{outcome.signal.symbol} {outcome.signal.action} hit "
                f"{outcome.hit_level} (+{outcome.pnl_pct:.1f}%). "
                f"Strategy {outcome.signal.strategy_name} worked in "
                f"{outcome.signal.regime}. Confidence was "
                f"{outcome.signal.confidence:.0f}%."
            )
        return (
            f"{outcome.signal.symbol} {outcome.signal.action} stopped out "
            f"({outcome.pnl_pct:.1f}%). Strategy "
            f"{outcome.signal.strategy_name} failed in "
            f"{outcome.signal.regime}. Review: conditions readiness was "
            f"{outcome.signal.readiness}%."
        )


class TradingAgent:
    """Multi-pair agentic AI that scans markets and generates trade signals."""

    def __init__(self) -> None:
        self._strategies = {
            "trend_following": TrendFollowingStrategy(),
            "mean_reversion": MeanReversionStrategy(),
            "smc": SMCStrategy(),
            "volume_breakout": VolumeBreakoutStrategy(),
            "rsi_scalping": RSIScalpingStrategy(),
            "trend_trader": TrendTraderStrategy(),
        }
        self._classifier = RegimeClassifier()
        self._reward_engine = RewardEngine()
        self._running = False
        self._scan_task: asyncio.Task | None = None

        # State
        self._active_signals: dict[str, TradeSignal] = {}  # symbol -> LOCKED signal
        self._signal_history: deque = deque(maxlen=500)
        self._trade_outcomes: deque = deque(maxlen=200)
        self._lessons_learned: deque = deque(maxlen=100)
        self._scan_count = 0
        self._last_scan_time: str = ""
        self._be_activated: set[str] = set()  # symbols where SL moved to BE

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background scanning loop."""
        if self._running:
            logger.warning("TradingAgent already running — ignoring start()")
            return
        self._running = True
        self._scan_task = asyncio.create_task(self._scan_loop())
        logger.info("TradingAgent started")

    async def stop(self) -> None:
        """Stop the background scanning loop."""
        self._running = False
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
            self._scan_task = None
        logger.info("TradingAgent stopped")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _scan_loop(self) -> None:
        """Main loop: monitor prices every 5s, full scan every 30s."""
        ticks = 0
        while self._running:
            try:
                # Monitor active trades every 5s
                await self._monitor_active_trades()
                # Full scan every 30s
                ticks += 1
                if ticks >= SCAN_INTERVAL // 5:
                    await self._scan_new_pairs()
                    ticks = 0
            except Exception as exc:
                logger.error("Agent scan error: %s", exc, exc_info=True)
            await asyncio.sleep(5)

    async def _scan_new_pairs(self) -> None:
        """Scan free pairs for new setups (every 30s)."""
        self._scan_count += 1
        self._last_scan_time = datetime.now(timezone.utc).isoformat()

        free_symbols = [s for s in SYMBOLS if s not in self._active_signals]
        if not free_symbols:
            logger.info("Scan #%d — all pairs have active trades, monitoring only", self._scan_count)
            return

        tasks = [self._analyze_pair(symbol) for symbol in free_symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for symbol, result in zip(free_symbols, results):
            if isinstance(result, Exception):
                logger.error("Scan failed for %s: %s", symbol, result)
                continue
            if result and result.confidence >= MIN_CONFIDENCE:
                self._active_signals[symbol] = result
                self._signal_history.append(result.to_dict())
                logger.info(
                    "NEW SIGNAL: %s %s @ $%s (conf=%s%%, strategy=%s)",
                    symbol, result.action, result.entry,
                    result.confidence, result.strategy_name,
                )

        logger.info(
            "Scan #%d — %d active trades, %d free pairs scanned",
            self._scan_count, len(self._active_signals), len(free_symbols),
        )

    async def _monitor_active_trades(self) -> None:
        """Check current price against active signals' TP/SL levels."""
        if not self._active_signals:
            return

        for symbol in list(self._active_signals.keys()):
            signal = self._active_signals[symbol]
            try:
                current_price = await self._get_current_price(symbol)
                if current_price <= 0:
                    continue

                hit = self._check_trade_levels(signal, current_price)
                if hit:
                    self._close_trade(symbol, current_price, hit)
            except Exception as exc:
                logger.error("Monitor error for %s: %s", symbol, exc)

    async def _get_current_price(self, symbol: str) -> float:
        """Fetch current price from Binance."""
        binance_sym = SYMBOL_MAP.get(symbol, symbol.replace("/", ""))
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    "https://api.binance.com/api/v3/ticker/price",
                    params={"symbol": binance_sym},
                )
                resp.raise_for_status()
                return float(resp.json().get("price", 0))
        except Exception:
            return 0.0

    def _check_trade_levels(self, signal: TradeSignal, price: float) -> str | None:
        """Check if price hit any TP/SL level.

        Returns a hit level string ONLY for trade-closing events.
        TP1 only activates Break Even — it does NOT close the trade.
        """
        is_long = signal.action == "LONG"
        symbol = signal.symbol

        # Check SL (or BE if activated)
        effective_sl = signal.entry if symbol in self._be_activated else signal.stop_loss
        if is_long and price <= effective_sl:
            return "BE" if symbol in self._be_activated else "SL"
        if not is_long and price >= effective_sl:
            return "BE" if symbol in self._be_activated else "SL"

        # Check TP3 first (closes trade)
        tp_levels = signal.tp_levels
        if len(tp_levels) >= 3:
            if (is_long and price >= tp_levels[2]) or (not is_long and price <= tp_levels[2]):
                return "TP3"

        # Check TP2 (closes trade)
        if len(tp_levels) >= 2:
            if (is_long and price >= tp_levels[1]) or (not is_long and price <= tp_levels[1]):
                return "TP2"

        # Check TP1 — does NOT close trade, only activates BE (once)
        if len(tp_levels) >= 1 and symbol not in self._be_activated:
            if (is_long and price >= tp_levels[0]) or (not is_long and price <= tp_levels[0]):
                self._be_activated.add(symbol)
                logger.info(
                    "TP1 hit for %s — SL moved to Break Even ($%s). Waiting for TP2/TP3 or BE.",
                    symbol, signal.entry,
                )

        # Trailing stop: update SL if price has moved favorably
        trailing_pct = getattr(signal, "trailing_stop_pct", 0)
        if trailing_pct > 0:
            trail = signal.entry * trailing_pct
            if is_long:
                new_sl = price - trail
                if new_sl > signal.stop_loss:
                    signal.stop_loss = round(new_sl, 8)
            else:
                new_sl = price + trail
                if new_sl < signal.stop_loss:
                    signal.stop_loss = round(new_sl, 8)

        return None

    def _close_trade(self, symbol: str, exit_price: float, hit_level: str) -> None:
        """Close a trade, calculate reward, record lesson, remove from active."""
        signal = self._active_signals.get(symbol)
        if not signal:
            return

        # Calculate P&L
        if signal.action == "LONG":
            pnl_pct = (exit_price - signal.entry) / signal.entry * 100
        else:
            pnl_pct = (signal.entry - exit_price) / signal.entry * 100

        # Calculate reward
        outcome = TradeOutcome(
            signal=signal, exit_price=exit_price,
            exit_time=datetime.now(timezone.utc).isoformat(),
            pnl_pct=round(pnl_pct, 2), hit_level=hit_level,
            reward=0, lessons="",
        )
        outcome.reward = self._reward_engine.calculate_reward(outcome)
        outcome.lessons = self._reward_engine.generate_lesson(outcome, {})

        # Feed the learning engine
        from app.ai.agent.learning_engine import get_learning_engine
        learning = get_learning_engine()
        adjustments = learning.record_outcome(
            strategy=signal.strategy_name,
            regime=signal.regime,
            pnl_pct=outcome.pnl_pct,
            reward=outcome.reward,
            hit_level=hit_level,
            market_snapshot={},
        )

        # Store outcome with learning data
        self._trade_outcomes.append({
            "symbol": symbol, "action": signal.action,
            "entry": signal.entry, "exit": exit_price,
            "pnl_pct": outcome.pnl_pct, "hit_level": hit_level,
            "reward": outcome.reward, "lessons": outcome.lessons,
            "strategy": signal.strategy_name, "confidence": signal.confidence,
            "timestamp": outcome.exit_time,
            "learning": adjustments,
        })
        self._lessons_learned.append(outcome.lessons)

        # Remove from active + BE tracking
        self._active_signals.pop(symbol, None)
        self._be_activated.discard(symbol)

        emoji = "✅" if pnl_pct > 0 else "❌"
        logger.info(
            "%s TRADE CLOSED: %s %s | %s | PnL: %.2f%% | Reward: %.2f | %s",
            emoji, symbol, signal.action, hit_level, pnl_pct, outcome.reward, outcome.lessons,
        )

    # ------------------------------------------------------------------
    # Per-pair analysis
    # ------------------------------------------------------------------

    async def _analyze_pair(self, symbol: str) -> TradeSignal | None:
        """Full analysis for a single pair: fetch data, compute features,
        classify regime, run strategies, build setup."""
        # Fetch live klines from Binance
        binance_sym = SYMBOL_MAP.get(symbol, symbol.replace("/", ""))
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://api.binance.com/api/v3/klines",
                params={"symbol": binance_sym, "interval": "4h", "limit": 500},
            )
            resp.raise_for_status()
            raw = resp.json()

        df = pd.DataFrame(
            [
                {
                    "timestamp": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                }
                for k in raw
            ]
        )

        featured = compute_features(df)
        if featured.empty or len(featured) < 50:
            return None

        last = featured.iloc[-1]
        close = float(last["close"])
        atr = float(last.get("atr_14", close * 0.01))

        # Classify regime
        regime = self._classifier.predict_df(featured)
        context = MarketContext(regime=regime.regime, regime_confidence=regime.confidence)

        # Try all strategies, collect signals with setups
        best_signal: TradeSignal | None = None
        best_confidence: float = 0

        from app.ai.agent.learning_engine import get_learning_engine
        learning = get_learning_engine()

        for name, strategy in self._strategies.items():
            compatible = strategy.is_compatible(regime.regime)

            # Check if learning engine has blocked this combo
            if learning.is_blocked(name, regime.regime):
                logger.debug("LEARNING BLOCKED: %s in %s for %s", name, regime.regime, symbol)
                continue

            # Generate signal
            signal = None
            if compatible:
                try:
                    signal = strategy.generate_signal(symbol, "4h", featured, context)
                except Exception as exc:
                    logger.debug("Strategy %s failed for %s: %s", name, symbol, exc)

            # Build setup regardless
            setup = self._build_setup(name, featured, last, close, atr, regime.regime)

            # Apply learned confidence adjustment
            if signal:
                signal_conf = learning.adjust_confidence(name, signal.confidence)
            else:
                signal_conf = 0

            if signal and signal_conf > best_confidence:
                best_confidence = signal.confidence
                best_signal = self._signal_from_strategy(signal, setup, regime.regime)
            elif setup["readiness"] > 30 and not best_signal:
                # Use suggested setup if readiness is decent
                confidence = setup["readiness"] * 0.9
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_signal = self._signal_from_setup(
                        symbol, setup, regime.regime, name, confidence,
                    )

        return best_signal

    # ------------------------------------------------------------------
    # Setup builder
    # ------------------------------------------------------------------

    def _build_setup(
        self,
        strategy_name: str,
        featured: pd.DataFrame,
        last: pd.Series,
        close: float,
        atr: float,
        regime: str,
    ) -> dict:
        """Build a complete setup with conditions for any strategy."""
        ema20 = float(last.get("ema_20", close))
        ema50 = float(last.get("ema_50", close))
        ema200 = float(last.get("ema_200", close))
        rsi = float(last.get("rsi_14", 50))
        adx = float(last.get("adx_14", 0))
        bb_upper = float(last.get("bb_upper", close + atr))
        bb_lower = float(last.get("bb_lower", close - atr))
        vol_ratio = float(last.get("volume_vs_avg", 1))

        # Defaults that every branch must set
        bias: str
        entry: float
        sl: float
        conditions: list[tuple[str, bool]]

        if strategy_name == "trend_following":
            if ema20 > ema50 > ema200:
                bias, entry = "LONG", round(ema20, 2)
                sl = round(
                    min(ema50 - atr, float(last.get("low", close)) - atr * 0.5), 2,
                )
                conditions = [
                    ("EMA 20>50>200", True),
                    ("ADX>25", adx > 25),
                    ("RSI 45-70", 45 <= rsi <= 70),
                    ("Volume>1.2x", vol_ratio > 1.2),
                ]
            elif ema20 < ema50 < ema200:
                bias, entry = "SHORT", round(ema20, 2)
                sl = round(
                    max(ema50 + atr, float(last.get("high", close)) + atr * 0.5), 2,
                )
                conditions = [
                    ("EMA 20<50<200", True),
                    ("ADX>25", adx > 25),
                    ("RSI 30-55", 30 <= rsi <= 55),
                    ("Volume>1.2x", vol_ratio > 1.2),
                ]
            else:
                bias = "LONG" if close > ema200 else "SHORT"
                entry = close
                sl = (
                    round(close - atr * 1.5, 2)
                    if bias == "LONG"
                    else round(close + atr * 1.5, 2)
                )
                conditions = [("EMA Alignment", False), ("ADX>25", adx > 25)]

        elif strategy_name == "mean_reversion":
            if rsi < 40 or close < bb_lower * 1.02:
                bias, entry = "LONG", round(bb_lower, 2)
                sl = round(bb_lower - atr * 0.5, 2)
                conditions = [
                    ("Near lower BB", close <= bb_lower * 1.02),
                    ("RSI<35", rsi < 35),
                    (
                        "Reversal candle",
                        close > float(last.get("open", close)),
                    ),
                ]
            else:
                bias, entry = "SHORT", round(bb_upper, 2)
                sl = round(bb_upper + atr * 0.5, 2)
                conditions = [
                    ("Near upper BB", close >= bb_upper * 0.98),
                    ("RSI>65", rsi > 65),
                    (
                        "Reversal candle",
                        close < float(last.get("open", close)),
                    ),
                ]

        elif strategy_name == "smc":
            obs = find_order_blocks(featured, lookback=30)
            bull_obs = [ob for ob in obs if ob["type"] == "bullish" and ob["mid"] < close]
            bear_obs = [ob for ob in obs if ob["type"] == "bearish" and ob["mid"] > close]
            if bull_obs:
                ob = bull_obs[-1]
                bias, entry = "LONG", round(ob["mid"], 2)
                sl = round(ob["low"] * 0.997, 2)
                conditions = [
                    ("Bullish OB found", True),
                    ("Price retesting", ob["low"] <= close <= ob["high"]),
                    (
                        "No supply above",
                        not bear_obs
                        or (bear_obs[0]["low"] - close) / close > 0.03,
                    ),
                ]
            elif bear_obs:
                ob = bear_obs[-1]
                bias, entry = "SHORT", round(ob["mid"], 2)
                sl = round(ob["high"] * 1.003, 2)
                conditions = [
                    ("Bearish OB found", True),
                    ("Price retesting", ob["low"] <= close <= ob["high"]),
                    (
                        "No demand below",
                        not bull_obs
                        or (close - bull_obs[-1]["high"]) / close > 0.03,
                    ),
                ]
            else:
                bias = "LONG" if close > ema200 else "SHORT"
                entry = close
                sl = (
                    round(close - atr * 1.5, 2)
                    if bias == "LONG"
                    else round(close + atr * 1.5, 2)
                )
                conditions = [("No OB found", False)]

        else:  # volume_breakout
            recent = featured.tail(15)
            rh = float(recent["high"].max())
            rl = float(recent["low"].min())
            if close > (rh + rl) / 2:
                bias, entry = "LONG", round(rh, 2)
                sl = round(rl - atr, 2)
            else:
                bias, entry = "SHORT", round(rl, 2)
                sl = round(rh + atr, 2)
            conditions = [
                ("Tight range", (rh - rl) / atr < 2 if atr > 0 else False),
                ("Volume>2x", vol_ratio > 2),
                ("Breakout", close > rh or close < rl),
            ]

        risk = abs(entry - sl) or atr
        if bias == "LONG":
            tp1 = round(entry + risk * 1.5, 2)
            tp2 = round(entry + risk * 3.0, 2)
            tp3 = round(entry + risk * 5.0, 2)
        else:
            tp1 = round(entry - risk * 1.5, 2)
            tp2 = round(entry - risk * 3.0, 2)
            tp3 = round(entry - risk * 5.0, 2)

        met = sum(1 for _, m in conditions if m)
        readiness = round(met / max(len(conditions), 1) * 100)

        return {
            "bias": bias,
            "entry": entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "risk": round(risk, 2),
            "rr": round(abs(tp1 - entry) / risk, 1) if risk > 0 else 0,
            "readiness": readiness,
            "conditions": [{"label": l, "met": m} for l, m in conditions],
        }

    # ------------------------------------------------------------------
    # UI elements builder
    # ------------------------------------------------------------------

    def _build_ui_elements(
        self,
        entry: float,
        sl: float,
        tp_levels: list[float],
        bias: str,
    ) -> dict:
        """Build UI annotation boxes for chart rendering."""
        sl_box = {
            "type": "box",
            "color": "#ff475740",
            "border_color": "#ff4757",
            "price_top": entry,
            "price_bottom": sl,
            "label": f"SL ${sl:,.0f}",
        }
        tp_boxes = []
        colors = ["#00d4aa30", "#00d4aa50", "#00d4aa70"]
        prev = entry
        for i, tp in enumerate(tp_levels):
            tp_boxes.append(
                {
                    "type": "box",
                    "color": colors[min(i, 2)],
                    "border_color": "#00d4aa",
                    "price_top": tp if bias == "LONG" else prev,
                    "price_bottom": prev if bias == "LONG" else tp,
                    "label": f"TP{i + 1} ${tp:,.0f}",
                }
            )
            prev = tp

        entry_line = {
            "type": "line",
            "price": entry,
            "color": "#facc15",
            "label": f"Entry ${entry:,.0f}",
        }
        be_line = {
            "type": "line",
            "price": entry,
            "color": "#3b82f6",
            "style": "dashed",
            "label": "Break Even (after TP1)",
        }

        return {
            "sl_box": sl_box,
            "tp_boxes": tp_boxes,
            "entry_line": entry_line,
            "be_line": be_line,
        }

    # ------------------------------------------------------------------
    # Signal constructors
    # ------------------------------------------------------------------

    def _signal_from_strategy(
        self, signal: Any, setup: dict, regime: str,
    ) -> TradeSignal:
        """Build a TradeSignal from a strategy SignalResult + setup data."""
        tp3 = setup["tp3"]
        ui = self._build_ui_elements(
            signal.entry_price,
            signal.stop_loss,
            [signal.take_profit_1, signal.take_profit_2, tp3],
            signal.direction,
        )
        return TradeSignal(
            symbol=signal.asset,
            action=signal.direction,
            entry=signal.entry_price,
            stop_loss=signal.stop_loss,
            tp_levels=[signal.take_profit_1, signal.take_profit_2, tp3],
            confidence=signal.confidence,
            reasoning="Strategy signal: "
            + ", ".join(f["name"] for f in signal.factors),
            strategy_name=signal.strategy_name,
            regime=regime,
            risk_reward=signal.risk_reward,
            readiness=setup["readiness"],
            conditions=setup["conditions"],
            ui_elements=ui,
            timestamp=datetime.now(timezone.utc).isoformat(),
            trailing_stop_pct=getattr(signal, "trailing_stop_pct", 0.0),
        )

    def _signal_from_setup(
        self,
        symbol: str,
        setup: dict,
        regime: str,
        strategy_name: str,
        confidence: float,
    ) -> TradeSignal:
        """Build a TradeSignal purely from a setup dict."""
        ui = self._build_ui_elements(
            setup["entry"],
            setup["sl"],
            [setup["tp1"], setup["tp2"], setup["tp3"]],
            setup["bias"],
        )
        return TradeSignal(
            symbol=symbol,
            action=setup["bias"],
            entry=setup["entry"],
            stop_loss=setup["sl"],
            tp_levels=[setup["tp1"], setup["tp2"], setup["tp3"]],
            confidence=confidence,
            reasoning=f"Setup from {strategy_name}: {setup['readiness']}% ready",
            strategy_name=strategy_name,
            regime=regime,
            risk_reward=setup["rr"],
            readiness=setup["readiness"],
            conditions=setup["conditions"],
            ui_elements=ui,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # ------------------------------------------------------------------
    # Trade outcome recording & learning
    # ------------------------------------------------------------------

    def record_outcome(
        self, symbol: str, exit_price: float, hit_level: str,
    ) -> TradeOutcome | None:
        """Record a trade outcome and trigger learning."""
        signal = self._active_signals.get(symbol)
        if not signal:
            return None

        if signal.action == "LONG":
            pnl_pct = (exit_price - signal.entry) / signal.entry * 100
        else:
            pnl_pct = (signal.entry - exit_price) / signal.entry * 100

        outcome = TradeOutcome(
            signal=signal,
            exit_price=exit_price,
            exit_time=datetime.now(timezone.utc).isoformat(),
            pnl_pct=round(pnl_pct, 2),
            hit_level=hit_level,
            reward=0,
            lessons="",
        )
        outcome.reward = self._reward_engine.calculate_reward(outcome)
        outcome.lessons = self._reward_engine.generate_lesson(outcome, {})

        self._trade_outcomes.append(
            {
                "symbol": symbol,
                "action": signal.action,
                "entry": signal.entry,
                "exit": exit_price,
                "pnl_pct": outcome.pnl_pct,
                "hit_level": hit_level,
                "reward": outcome.reward,
                "lessons": outcome.lessons,
                "strategy": signal.strategy_name,
                "confidence": signal.confidence,
                "timestamp": outcome.exit_time,
            }
        )
        self._lessons_learned.append(outcome.lessons)

        # Remove from active
        self._active_signals.pop(symbol, None)
        return outcome

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def get_active_signals(self) -> dict[str, dict]:
        """Return all active signals as plain dicts."""
        return {sym: sig.to_dict() for sym, sig in self._active_signals.items()}

    def get_signal_history(self) -> list[dict]:
        """Return recent signal history."""
        return list(self._signal_history)

    def get_status(self) -> dict:
        """Return agent status including win/loss stats and recent lessons."""
        total_outcomes = list(self._trade_outcomes)
        wins = [o for o in total_outcomes if o["pnl_pct"] > 0]
        losses = [o for o in total_outcomes if o["pnl_pct"] <= 0]
        total_reward = sum(o["reward"] for o in total_outcomes)
        return {
            "running": self._running,
            "scan_count": self._scan_count,
            "last_scan": self._last_scan_time,
            "active_signals": len(self._active_signals),
            "total_trades": len(total_outcomes),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / max(len(total_outcomes), 1) * 100, 1),
            "total_reward": round(total_reward, 2),
            "avg_reward": round(total_reward / max(len(total_outcomes), 1), 2),
            "recent_lessons": list(self._lessons_learned)[-5:],
        }


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_agent: TradingAgent | None = None


def get_trading_agent() -> TradingAgent:
    """Return the global TradingAgent singleton (created on first call)."""
    global _agent
    if _agent is None:
        _agent = TradingAgent()
    return _agent
