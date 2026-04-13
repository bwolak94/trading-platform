"""Day Trading Engine — M1/M5/M15 analysis with VWAP, session levels, and liquidity sweeps."""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx
import numpy as np
import pandas as pd

from app.data.processors.feature_engineer import compute_features
from app.ai.strategies.smc_strategy import find_order_blocks, find_fair_value_gaps

logger = logging.getLogger(__name__)

SYMBOL_MAP = {"BTC/USDT": "BTCUSDT", "ETH/USDT": "ETHUSDT", "SOL/USDT": "SOLUSDT"}
MONITOR_INTERVAL = 5  # check TP/SL every 5 seconds
SCAN_INTERVAL = 30  # full analysis every 30 seconds
DAY_TRADE_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]


@dataclass
class SessionLevels:
    """Key intraday levels."""
    session_high: float
    session_low: float
    pdh: float  # Previous Day High
    pdl: float  # Previous Day Low
    vwap: float
    vwap_upper: float  # VWAP + 1 std dev
    vwap_lower: float  # VWAP - 1 std dev


@dataclass
class DayTradeSignal:
    symbol: str
    action: str  # LONG / SHORT / HOLD
    entry: float
    stop_loss: float
    tp_levels: list[float]  # [TP1, TP2, TP3]
    be_trigger: float  # Move SL to BE when this price is hit (usually TP1)
    confidence: float
    hold_time_minutes: int  # Estimated hold duration
    reasoning: str
    strategy_type: str  # "liquidity_sweep", "ob_bounce", "vwap_reversion", "delta_divergence"
    session_levels: dict
    regime: str
    readiness: int
    conditions: list[dict]
    ui_elements: dict
    timestamp: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol, "action": self.action,
            "entry": self.entry, "stop_loss": self.stop_loss,
            "tp_levels": self.tp_levels, "be_trigger": self.be_trigger,
            "confidence": self.confidence, "hold_time_minutes": self.hold_time_minutes,
            "reasoning": self.reasoning, "strategy_type": self.strategy_type,
            "session_levels": self.session_levels, "regime": self.regime,
            "readiness": self.readiness, "conditions": self.conditions,
            "ui_elements": self.ui_elements, "timestamp": self.timestamp,
        }


class DayTradingEngine:
    """Intraday scalping/day trading engine scanning M1/M5/M15."""

    def __init__(self):
        self._running = False
        self._scan_task: asyncio.Task[None] | None = None
        self._active_signals: dict[str, DayTradeSignal] = {}
        self._signal_history: deque = deque(maxlen=500)
        self._blocked_setups: dict[str, datetime] = {}
        self._scan_count = 0
        self._last_scan = ""
        self._trade_results: deque = deque(maxlen=200)
        self._be_activated: set[str] = set()
        self._lessons: deque = deque(maxlen=100)

    async def start(self):
        self._running = True
        self._scan_task = asyncio.create_task(self._scan_loop())
        logger.info("Day Trading Engine started")

    async def stop(self):
        self._running = False
        if self._scan_task:
            self._scan_task.cancel()
        logger.info("Day Trading Engine stopped")

    async def _scan_loop(self):
        ticks_since_scan = 0
        while self._running:
            try:
                # Monitor active trades every 5s
                await self._monitor_prices()

                # Full scan every 30s (every 6th tick)
                ticks_since_scan += 1
                if ticks_since_scan >= SCAN_INTERVAL // MONITOR_INTERVAL:
                    await self._scan_new_setups()
                    ticks_since_scan = 0
            except Exception as exc:
                logger.error("Day trade scan error: %s", exc)
            await asyncio.sleep(MONITOR_INTERVAL)

    async def _monitor_prices(self):
        """Fast price check every 5s — detect TP/SL hits quickly."""
        for sym in list(self._active_signals.keys()):
            sig = self._active_signals[sym]
            try:
                price = await self._get_price(sym)
                if price <= 0:
                    continue
                hit = self._check_levels(sig, price, sym)
                if hit:
                    self._close_trade(sym, price, hit)
            except Exception as exc:
                logger.error("Day trade monitor error %s: %s", sym, exc)

    async def _scan_new_setups(self):
        """Full analysis every 30s — only scan pairs without active trades."""
        self._scan_count += 1
        self._last_scan = datetime.now(timezone.utc).isoformat()

        free = [s for s in DAY_TRADE_SYMBOLS if s not in self._active_signals]
        if not free:
            return

        tasks = [self._analyze(sym) for sym in free]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for sym, result in zip(free, results):
            if isinstance(result, Exception):
                logger.error("Day trade scan failed %s: %s", sym, result)
                continue
            if result:
                self._active_signals[sym] = result
                self._signal_history.append(result.to_dict())
                logger.info("DAY TRADE SIGNAL: %s %s @ $%s", sym, result.action, result.entry)

    async def _get_price(self, symbol: str) -> float:
        binance_sym = SYMBOL_MAP.get(symbol, symbol.replace("/", ""))
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get("https://api.binance.com/api/v3/ticker/price",
                    params={"symbol": binance_sym})
                resp.raise_for_status()
                return float(resp.json().get("price", 0))
        except Exception:
            return 0.0

    def _check_levels(self, sig: DayTradeSignal, price: float, symbol: str) -> str | None:
        """Check TP/SL. TP1 only activates BE, does NOT close trade."""
        is_long = sig.action == "LONG"
        effective_sl = sig.entry if symbol in self._be_activated else sig.stop_loss

        # SL or BE hit — closes trade
        if is_long and price <= effective_sl:
            return "BE" if symbol in self._be_activated else "SL"
        if not is_long and price >= effective_sl:
            return "BE" if symbol in self._be_activated else "SL"

        tps = sig.tp_levels
        # TP3 — closes trade
        if len(tps) >= 3:
            if (is_long and price >= tps[2]) or (not is_long and price <= tps[2]):
                return "TP3"
        # TP2 — closes trade
        if len(tps) >= 2:
            if (is_long and price >= tps[1]) or (not is_long and price <= tps[1]):
                return "TP2"
        # TP1 — only activates BE, does NOT return a hit (trade stays open)
        if len(tps) >= 1 and symbol not in self._be_activated:
            if (is_long and price >= tps[0]) or (not is_long and price <= tps[0]):
                self._be_activated.add(symbol)
                logger.info("DAY TP1 hit %s — SL moved to BE ($%s). Waiting for TP2/TP3.", symbol, sig.entry)
        return None

    def _close_trade(self, symbol: str, exit_price: float, hit: str):
        sig = self._active_signals.get(symbol)
        if not sig:
            return
        pnl = ((exit_price - sig.entry) / sig.entry * 100) if sig.action == "LONG" else ((sig.entry - exit_price) / sig.entry * 100)

        # Reward
        reward = {"TP3": 3.0, "TP2": 2.0, "TP1": 1.0, "BE": 0.1, "SL": -1.0}.get(hit, 0)
        if pnl > 0 and sig.confidence > 80:
            reward += 0.5
        if pnl < 0 and sig.confidence > 80:
            reward -= 1.0

        lesson = f"{symbol} {sig.action} {hit} ({pnl:+.2f}%) via {sig.strategy_type}. Reward: {reward:+.1f}"
        self._trade_results.append({
            "symbol": symbol, "action": sig.action, "entry": sig.entry,
            "exit": exit_price, "pnl_pct": round(pnl, 2), "hit": hit,
            "reward": round(reward, 2), "lesson": lesson,
            "strategy": sig.strategy_type, "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self._lessons.append(lesson)

        # If SL hit, check if it was a wick (false breakout) — block for 4h
        if hit == "SL" and sig.strategy_type == "liquidity_sweep":
            self.record_loss(symbol, was_wick=True)

        self._active_signals.pop(symbol, None)
        self._be_activated.discard(symbol)
        emoji = "✅" if pnl > 0 else "❌"
        logger.info("%s DAY TRADE CLOSED: %s %s %s PnL=%.2f%% R=%.1f", emoji, symbol, sig.action, hit, pnl, reward)

    async def _fetch_klines(self, symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
        binance_sym = SYMBOL_MAP.get(symbol, symbol.replace("/", ""))
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get("https://api.binance.com/api/v3/klines",
                params={"symbol": binance_sym, "interval": interval, "limit": limit})
            resp.raise_for_status()
            raw = resp.json()
        return pd.DataFrame([{
            "timestamp": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc),
            "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
            "close": float(k[4]), "volume": float(k[5]),
        } for k in raw])

    def _calculate_session_levels(self, df_1h: pd.DataFrame, df_m1: pd.DataFrame) -> SessionLevels:
        """Calculate VWAP, session high/low, PDH/PDL."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)

        # Session candles (today)
        if "timestamp" in df_m1.columns:
            today_mask = df_m1["timestamp"] >= today_start
            today_data = df_m1[today_mask]
            yesterday_mask = (df_m1["timestamp"] >= yesterday_start) & (df_m1["timestamp"] < today_start)
            yesterday_data = df_m1[yesterday_mask]
        else:
            today_data = df_m1.tail(60)  # fallback: last 60 M1 candles
            yesterday_data = df_m1.iloc[-1500:-60] if len(df_m1) > 1500 else df_m1.head(100)

        session_high = float(today_data["high"].max()) if not today_data.empty else float(df_m1.iloc[-1]["high"])
        session_low = float(today_data["low"].min()) if not today_data.empty else float(df_m1.iloc[-1]["low"])
        pdh = float(yesterday_data["high"].max()) if not yesterday_data.empty else session_high
        pdl = float(yesterday_data["low"].min()) if not yesterday_data.empty else session_low

        # VWAP = cumulative(price * volume) / cumulative(volume)
        if not today_data.empty and "volume" in today_data.columns:
            typical_price = (today_data["high"] + today_data["low"] + today_data["close"]) / 3
            cum_vol = today_data["volume"].cumsum()
            cum_tp_vol = (typical_price * today_data["volume"]).cumsum()
            vwap = float(cum_tp_vol.iloc[-1] / cum_vol.iloc[-1]) if cum_vol.iloc[-1] > 0 else float(df_m1.iloc[-1]["close"])

            # VWAP bands (1 std dev)
            squared_diff = ((typical_price - vwap) ** 2 * today_data["volume"]).cumsum()
            variance = float(squared_diff.iloc[-1] / cum_vol.iloc[-1]) if cum_vol.iloc[-1] > 0 else 0
            std = variance ** 0.5
        else:
            vwap = float(df_m1.iloc[-1]["close"])
            std = float(df_m1["close"].std()) * 0.1

        return SessionLevels(
            session_high=round(session_high, 2),
            session_low=round(session_low, 2),
            pdh=round(pdh, 2), pdl=round(pdl, 2),
            vwap=round(vwap, 2),
            vwap_upper=round(vwap + std, 2),
            vwap_lower=round(vwap - std, 2),
        )

    async def _analyze(self, symbol: str) -> DayTradeSignal | None:
        """Multi-timeframe day trading analysis."""
        # Check if blocked (false breakout cooldown)
        blocked_until = self._blocked_setups.get(symbol)
        if blocked_until and datetime.now(timezone.utc) < blocked_until:
            return None

        # Fetch M1, M5, M15 data in parallel
        m1_task = self._fetch_klines(symbol, "1m", 500)
        m5_task = self._fetch_klines(symbol, "5m", 200)
        m15_task = self._fetch_klines(symbol, "15m", 100)

        m1_df, m5_df, m15_df = await asyncio.gather(m1_task, m5_task, m15_task)

        if m1_df.empty or m5_df.empty:
            return None

        # Compute features on M5 (primary timeframe for day trading)
        m5_featured = compute_features(m5_df)
        if m5_featured.empty:
            return None

        last = m5_featured.iloc[-1]
        close = float(last["close"])
        atr = float(last.get("atr_14", close * 0.005))
        rsi = float(last.get("rsi_14", 50))
        adx = float(last.get("adx_14", 0))
        ema20 = float(last.get("ema_20", close))
        bb_upper = float(last.get("bb_upper", close + atr))
        bb_lower = float(last.get("bb_lower", close - atr))
        vol_ratio = float(last.get("volume_vs_avg", 1))

        # Session levels
        session = self._calculate_session_levels(m15_df, m1_df)

        # Order blocks on M5
        obs = find_order_blocks(m5_featured, lookback=30)
        fvgs = find_fair_value_gaps(m5_featured, lookback=30)

        # Calculate cumulative delta from M1 (buy vol - sell vol proxy)
        m1_delta = sum(
            float(row["volume"]) * (1 if float(row["close"]) >= float(row["open"]) else -1)
            for _, row in m1_df.tail(30).iterrows()
        )

        # --- Day Trading Strategy Selection ---
        signal = None

        # 1. Liquidity Sweep: price wicks beyond PDH/PDL then reverses
        signal = signal or self._check_liquidity_sweep(symbol, close, atr, session, m1_df, rsi)

        # 2. Order Block Bounce: price touches an M5 OB in the direction of the trend
        signal = signal or self._check_ob_bounce(symbol, close, atr, session, obs, m5_featured, rsi, adx)

        # 3. VWAP Reversion: price far from VWAP snaps back
        signal = signal or self._check_vwap_reversion(symbol, close, atr, session, rsi, vol_ratio)

        # 4. Delta Divergence: price makes new high/low but delta disagrees
        signal = signal or self._check_delta_divergence(symbol, close, atr, session, m1_df, m1_delta, m5_featured)

        return signal

    def _check_liquidity_sweep(self, symbol: str, close: float, atr: float, session: SessionLevels, m1_df: pd.DataFrame, rsi: float) -> DayTradeSignal | None:
        """Detect liquidity sweep beyond PDH/PDL."""
        conditions: list[tuple[str, bool]] = []

        # Check if price swept above PDH then came back below
        recent_high = float(m1_df.tail(10)["high"].max())
        if recent_high > session.pdh and close < session.pdh:
            # Swept PDH and reversed — SHORT setup
            conditions = [
                ("Swept above PDH", True),
                ("Price back below PDH", close < session.pdh),
                ("RSI > 50 (overbought zone)", rsi > 50),
                ("Volume spike", float(m1_df.tail(5)["volume"].mean()) > float(m1_df.tail(30)["volume"].mean()) * 1.3),
            ]
            met = sum(1 for _, m in conditions if m)
            if met >= 3:
                entry = round(session.pdh, 2)
                sl = round(recent_high + atr * 0.3, 2)
                risk = abs(entry - sl)
                return self._build_day_signal(symbol, "SHORT", entry, sl, risk,
                    "liquidity_sweep", f"Liquidity swept above PDH ${session.pdh:,.0f}, reversal confirmed",
                    session, conditions, hold_minutes=15)

        # Check if price swept below PDL then came back above
        recent_low = float(m1_df.tail(10)["low"].min())
        if recent_low < session.pdl and close > session.pdl:
            conditions = [
                ("Swept below PDL", True),
                ("Price back above PDL", close > session.pdl),
                ("RSI < 50 (oversold zone)", rsi < 50),
                ("Volume spike", float(m1_df.tail(5)["volume"].mean()) > float(m1_df.tail(30)["volume"].mean()) * 1.3),
            ]
            met = sum(1 for _, m in conditions if m)
            if met >= 3:
                entry = round(session.pdl, 2)
                sl = round(recent_low - atr * 0.3, 2)
                risk = abs(entry - sl)
                return self._build_day_signal(symbol, "LONG", entry, sl, risk,
                    "liquidity_sweep", f"Liquidity swept below PDL ${session.pdl:,.0f}, reversal confirmed",
                    session, conditions, hold_minutes=15)

        return None

    def _check_ob_bounce(self, symbol: str, close: float, atr: float, session: SessionLevels, obs: list[dict[str, Any]], featured: pd.DataFrame, rsi: float, adx: float) -> DayTradeSignal | None:
        """Check for Order Block bounce on M5."""
        bull_obs = [ob for ob in obs if ob["type"] == "bullish" and ob["low"] <= close <= ob["high"]]
        if bull_obs and close > session.vwap:
            ob = bull_obs[-1]
            conditions: list[tuple[str, bool]] = [
                ("Bullish OB retest", True),
                ("Above VWAP", close > session.vwap),
                ("RSI 40-65", 40 <= rsi <= 65),
                ("ADX > 20", adx > 20),
            ]
            met = sum(1 for _, m in conditions if m)
            if met >= 3:
                entry = round(ob["mid"], 2)
                sl = round(ob["low"] - atr * 0.3, 2)
                risk = abs(entry - sl)
                return self._build_day_signal(symbol, "LONG", entry, sl, risk,
                    "ob_bounce", f"M5 Bullish OB retest at ${ob['low']:,.0f}-${ob['high']:,.0f}, above VWAP",
                    session, conditions, hold_minutes=20)

        bear_obs = [ob for ob in obs if ob["type"] == "bearish" and ob["low"] <= close <= ob["high"]]
        if bear_obs and close < session.vwap:
            ob = bear_obs[-1]
            conditions = [
                ("Bearish OB retest", True),
                ("Below VWAP", close < session.vwap),
                ("RSI 35-60", 35 <= rsi <= 60),
                ("ADX > 20", adx > 20),
            ]
            met = sum(1 for _, m in conditions if m)
            if met >= 3:
                entry = round(ob["mid"], 2)
                sl = round(ob["high"] + atr * 0.3, 2)
                risk = abs(entry - sl)
                return self._build_day_signal(symbol, "SHORT", entry, sl, risk,
                    "ob_bounce", f"M5 Bearish OB retest at ${ob['low']:,.0f}-${ob['high']:,.0f}, below VWAP",
                    session, conditions, hold_minutes=20)

        return None

    def _check_vwap_reversion(self, symbol: str, close: float, atr: float, session: SessionLevels, rsi: float, vol_ratio: float) -> DayTradeSignal | None:
        """VWAP mean reversion when price is extended."""
        distance_from_vwap = (close - session.vwap) / session.vwap * 100

        if distance_from_vwap > 0.3 and close > session.vwap_upper and rsi > 65:
            conditions: list[tuple[str, bool]] = [
                ("Above VWAP upper band", True),
                (f"Extended {distance_from_vwap:.2f}% from VWAP", True),
                ("RSI > 65", rsi > 65),
                ("Volume declining", vol_ratio < 0.8),
            ]
            met = sum(1 for _, m in conditions if m)
            if met >= 3:
                entry = close
                sl = round(close + atr * 0.5, 2)
                risk = abs(entry - sl)
                return self._build_day_signal(symbol, "SHORT", round(entry, 2), sl, risk,
                    "vwap_reversion", f"Extended {distance_from_vwap:.1f}% above VWAP, mean reversion expected",
                    session, conditions, hold_minutes=10)

        if distance_from_vwap < -0.3 and close < session.vwap_lower and rsi < 35:
            conditions = [
                ("Below VWAP lower band", True),
                (f"Extended {abs(distance_from_vwap):.2f}% from VWAP", True),
                ("RSI < 35", rsi < 35),
                ("Volume declining", vol_ratio < 0.8),
            ]
            met = sum(1 for _, m in conditions if m)
            if met >= 3:
                entry = close
                sl = round(close - atr * 0.5, 2)
                risk = abs(entry - sl)
                return self._build_day_signal(symbol, "LONG", round(entry, 2), sl, risk,
                    "vwap_reversion", f"Extended {abs(distance_from_vwap):.1f}% below VWAP, mean reversion expected",
                    session, conditions, hold_minutes=10)

        return None

    def _check_delta_divergence(self, symbol: str, close: float, atr: float, session: SessionLevels, m1_df: pd.DataFrame, cum_delta: float, featured: pd.DataFrame) -> DayTradeSignal | None:
        """Detect divergence between price and cumulative delta."""
        if len(m1_df) < 30:
            return None

        # Price making higher high but delta making lower high = bearish divergence
        recent_prices = m1_df.tail(15)
        older_prices = m1_df.iloc[-30:-15]

        recent_high = float(recent_prices["high"].max())
        older_high = float(older_prices["high"].max())

        recent_low = float(recent_prices["low"].min())
        older_low = float(older_prices["low"].min())

        # Simple delta for recent vs older periods
        recent_delta = sum(
            float(r["volume"]) * (1 if float(r["close"]) >= float(r["open"]) else -1)
            for _, r in recent_prices.iterrows()
        )
        older_delta = sum(
            float(r["volume"]) * (1 if float(r["close"]) >= float(r["open"]) else -1)
            for _, r in older_prices.iterrows()
        )

        # Bearish divergence: higher high in price, lower high in delta
        if recent_high > older_high and recent_delta < older_delta:
            conditions: list[tuple[str, bool]] = [
                ("Price higher high", True),
                ("Delta lower high (divergence)", True),
                ("Near session high", abs(close - session.session_high) / close < 0.003),
            ]
            met = sum(1 for _, m in conditions if m)
            if met >= 2:
                entry = close
                sl = round(recent_high + atr * 0.3, 2)
                risk = abs(entry - sl)
                return self._build_day_signal(symbol, "SHORT", round(entry, 2), sl, risk,
                    "delta_divergence", "Bearish delta divergence: price HH but delta LH -- buyers exhausted",
                    session, conditions, hold_minutes=10)

        # Bullish divergence: lower low in price, higher low in delta
        if recent_low < older_low and recent_delta > older_delta:
            conditions = [
                ("Price lower low", True),
                ("Delta higher low (divergence)", True),
                ("Near session low", abs(close - session.session_low) / close < 0.003),
            ]
            met = sum(1 for _, m in conditions if m)
            if met >= 2:
                entry = close
                sl = round(recent_low - atr * 0.3, 2)
                risk = abs(entry - sl)
                return self._build_day_signal(symbol, "LONG", round(entry, 2), sl, risk,
                    "delta_divergence", "Bullish delta divergence: price LL but delta HL -- sellers exhausted",
                    session, conditions, hold_minutes=10)

        return None

    def _build_day_signal(self, symbol: str, action: str, entry: float, sl: float, risk: float, strategy_type: str, reasoning: str, session: SessionLevels, conditions: list[tuple[str, bool]], hold_minutes: int) -> DayTradeSignal:
        if risk <= 0:
            risk = abs(entry * 0.003)
        tp1 = round(entry + risk * 1.5, 2) if action == "LONG" else round(entry - risk * 1.5, 2)
        tp2 = round(entry + risk * 3.0, 2) if action == "LONG" else round(entry - risk * 3.0, 2)
        tp3 = round(entry + risk * 5.0, 2) if action == "LONG" else round(entry - risk * 5.0, 2)
        be_trigger = tp1  # Move SL to BE when TP1 is hit

        met = sum(1 for _, m in conditions if m)
        readiness = round(met / max(len(conditions), 1) * 100)
        confidence = min(90, readiness + 15)

        # Build UI elements
        ui = self._build_ui(entry, sl, [tp1, tp2, tp3], be_trigger, action, confidence, hold_minutes, session)

        return DayTradeSignal(
            symbol=symbol, action=action, entry=entry, stop_loss=sl,
            tp_levels=[tp1, tp2, tp3], be_trigger=be_trigger,
            confidence=confidence, hold_time_minutes=hold_minutes,
            reasoning=reasoning, strategy_type=strategy_type,
            session_levels={
                "session_high": session.session_high, "session_low": session.session_low,
                "pdh": session.pdh, "pdl": session.pdl,
                "vwap": session.vwap, "vwap_upper": session.vwap_upper, "vwap_lower": session.vwap_lower,
            },
            regime="INTRADAY", readiness=readiness,
            conditions=[{"label": l, "met": m} for l, m in conditions],
            ui_elements=ui,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _build_ui(self, entry: float, sl: float, tps: list[float], be_trigger: float, action: str, confidence: float, hold_min: int, session: SessionLevels) -> dict:
        sl_box = {"type": "box", "color": "#ff475730", "border_color": "#ff4757",
                   "price_top": entry if action == "LONG" else sl,
                   "price_bottom": sl if action == "LONG" else entry,
                   "label": f"SL ${sl:,.0f}"}
        tp_boxes = []
        prev = entry
        colors = ["#00d4aa25", "#00d4aa40", "#00d4aa60"]
        for i, tp in enumerate(tps):
            tp_boxes.append({"type": "box", "color": colors[min(i, 2)], "border_color": "#00d4aa",
                "price_top": tp if action == "LONG" else prev,
                "price_bottom": prev if action == "LONG" else tp,
                "label": f"TP{i + 1} ${tp:,.0f}"})
            prev = tp

        return {
            "sl_box": sl_box, "tp_boxes": tp_boxes,
            "entry_line": {"type": "line", "price": entry, "color": "#facc15", "label": f"Entry ${entry:,.0f}"},
            "be_line": {"type": "line", "price": be_trigger, "color": "#3b82f6", "style": "dashed", "label": f"BE Trigger ${be_trigger:,.0f}"},
            "vwap_line": {"type": "line", "price": session.vwap, "color": "#a855f7", "label": f"VWAP ${session.vwap:,.0f}"},
            "pdh_line": {"type": "line", "price": session.pdh, "color": "#f97316", "style": "dotted", "label": f"PDH ${session.pdh:,.0f}"},
            "pdl_line": {"type": "line", "price": session.pdl, "color": "#f97316", "style": "dotted", "label": f"PDL ${session.pdl:,.0f}"},
            "confidence_label": {"value": confidence, "text": f"{confidence}% Confidence"},
            "hold_time_label": {"value": hold_min, "text": f"~{hold_min} min hold"},
        }

    def record_loss(self, symbol: str, was_wick: bool) -> None:
        """After a loss, block the setup type for 4 hours if it was a false breakout."""
        if was_wick:
            self._blocked_setups[symbol] = datetime.now(timezone.utc) + timedelta(hours=4)
            logger.info("Blocked %s for 4h due to false breakout", symbol)

    def get_active_signals(self) -> dict[str, dict]:
        return {sym: sig.to_dict() for sym, sig in self._active_signals.items()}

    def get_status(self) -> dict:
        results = list(self._trade_results)
        wins = [r for r in results if r["pnl_pct"] > 0]
        losses = [r for r in results if r["pnl_pct"] <= 0]
        total_reward = sum(r["reward"] for r in results)
        be_symbols = list(self._be_activated)
        return {
            "running": self._running, "scan_count": self._scan_count,
            "last_scan": self._last_scan,
            "active_signals": len(self._active_signals),
            "blocked_symbols": {k: v.isoformat() for k, v in self._blocked_setups.items() if v > datetime.now(timezone.utc)},
            "total_trades": len(results),
            "wins": len(wins), "losses": len(losses),
            "win_rate": round(len(wins) / max(len(results), 1) * 100, 1),
            "total_reward": round(total_reward, 2),
            "be_active": be_symbols,
            "recent_lessons": list(self._lessons)[-5:],
            "recent_trades": results[-10:],
        }


# Singleton
_engine: DayTradingEngine | None = None


def get_day_trading_engine() -> DayTradingEngine:
    global _engine
    if _engine is None:
        _engine = DayTradingEngine()
    return _engine
