"""Features2 API — additional endpoints for new trading features (features 26-30)."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/features2", tags=["features2"])


# ---------------------------------------------------------------------------
# Response helpers (matches features.py pattern)
# ---------------------------------------------------------------------------

def _ok(data: Any, source: str = "computed") -> dict[str, Any]:
    """Standard success response envelope."""
    return {
        "status": "ok",
        "source": source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }


def _unavailable(reason: str) -> dict[str, Any]:
    """Standard unavailable response."""
    return {
        "status": "unavailable",
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": None,
    }


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class MarketModeRequest(BaseModel):
    """Request body for the market-mode override endpoint."""

    mode: str    # "AUTO", "TRENDING", "RANGING", "HIGH_VOLATILITY", "ACCUMULATION"
    reason: str = ""


# ---------------------------------------------------------------------------
# Market Mode
# ---------------------------------------------------------------------------

@router.get("/market-mode", summary="Get current market mode and config")
async def get_market_mode() -> dict[str, Any]:
    """Return the current market mode, who set it, and all config multipliers."""
    try:
        from app.core.market_mode import get_market_mode_manager
        mgr = get_market_mode_manager()
        return _ok(mgr.status_dict(), source="market_mode_manager")
    except Exception as exc:
        logger.error("market_mode GET error: %s", exc)
        return _unavailable(str(exc))


@router.post("/market-mode", summary="Override market mode manually")
async def set_market_mode(req: MarketModeRequest) -> dict[str, Any]:
    """Set the global market mode, adjusting strategy weights and confidence floors."""
    try:
        from app.core.market_mode import MarketMode, get_market_mode_manager
        mgr = get_market_mode_manager()
        try:
            mode = MarketMode(req.mode.upper())
        except ValueError:
            valid = [m.value for m in MarketMode]
            raise HTTPException(
                status_code=400,
                detail=f"Invalid mode '{req.mode}'. Valid values: {valid}",
            )
        mgr.set_mode(mode, reason=req.reason, set_by="api")
        return _ok(mgr.status_dict(), source="market_mode_manager")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("market_mode POST error: %s", exc)
        return _unavailable(str(exc))


# ---------------------------------------------------------------------------
# Pre-Entry Score
# ---------------------------------------------------------------------------

@router.get("/pre-entry-score/{symbol}", summary="Get pre-entry checklist score")
async def get_pre_entry_score(
    symbol: str,
    strategy: str = Query("trend_following", description="Strategy name"),
    confidence: float = Query(65.0, ge=0.0, le=100.0, description="Raw signal confidence"),
    direction: str = Query("LONG", description="LONG or SHORT"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Evaluate the 10-point pre-entry checklist for a symbol/direction/strategy combo.

    Fetches live market data from Binance and scores the hypothetical signal.
    """
    try:
        from app.ai.signals.pre_entry_scorer import PreEntryScorer
        from app.ai.strategies.base import MarketContext, SignalResult
        from app.data.fetchers.binance_fetcher import BinanceFetcher

        fetcher = BinanceFetcher()
        sym_clean = symbol.upper().replace("/", "")
        df = await fetcher.fetch_klines(sym_clean, "1h", limit=100)

        if df is None or len(df) < 20:
            return _unavailable("Insufficient market data")

        entry = float(df["close"].iloc[-1])
        atr_approx = float((df["high"] - df["low"]).rolling(14).mean().iloc[-1])

        direction_upper = direction.upper()
        if direction_upper == "LONG":
            stop_loss = entry - 2 * atr_approx
            tp1 = entry + 2 * atr_approx
            tp2 = entry + 4 * atr_approx
        else:
            stop_loss = entry + 2 * atr_approx
            tp1 = entry - 2 * atr_approx
            tp2 = entry - 4 * atr_approx

        rr = 2.0  # implied from ATR-symmetric placement

        signal = SignalResult(
            asset=symbol,
            timeframe="1h",
            direction=direction_upper,
            confidence=confidence,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit_1=tp1,
            take_profit_2=tp2,
            risk_reward=rr,
            factors=[],
            strategy_name=strategy,
        )

        context = MarketContext(regime="TRENDING")
        scorer = PreEntryScorer()
        result = scorer.score(signal, df, context)

        return _ok({
            "symbol": symbol,
            "direction": direction_upper,
            "strategy": strategy,
            "total_score": result.total_score,
            "grade": result.grade,
            "should_emit": result.should_emit,
            "confidence_adjustment": result.confidence_adjustment,
            "criteria_passed": result.criteria_passed,
            "criteria_failed": result.criteria_failed,
            "checklist": result.checklist_text,
        })
    except Exception as exc:
        logger.error("pre_entry_score error [%s]: %s", symbol, exc)
        return _unavailable(str(exc))


# ---------------------------------------------------------------------------
# Stop Hunt Prediction
# ---------------------------------------------------------------------------

@router.get("/stop-hunt/{symbol}", summary="Predict next stop hunt location")
async def get_stop_hunt_prediction(symbol: str) -> dict[str, Any]:
    """Return the most likely stop hunt price zone for the given symbol."""
    try:
        from app.ai.signals.stop_hunt_predictor import StopHuntPredictor
        from app.data.fetchers.binance_fetcher import BinanceFetcher

        fetcher = BinanceFetcher()
        df = await fetcher.fetch_klines(symbol.upper().replace("/", ""), "1h", limit=100)

        if df is None or len(df) < 20:
            return _unavailable("Insufficient market data")

        predictor = StopHuntPredictor()
        prediction = predictor.predict(symbol, df)

        if prediction is None:
            return _ok({"signal": None, "message": "No stop hunt setup detected"})

        return _ok({
            "direction": prediction.likely_hunt_direction,
            "target_price": prediction.target_price,
            "confidence": prediction.confidence,
            "quality": prediction.setup_quality,
            "timing": prediction.expected_timing,
            "description": prediction.description,
        })
    except Exception as exc:
        logger.error("stop_hunt error [%s]: %s", symbol, exc)
        return _unavailable(str(exc))


# ---------------------------------------------------------------------------
# Flash Crash Sniper
# ---------------------------------------------------------------------------

@router.get("/flash-crash/{symbol}", summary="Check for flash crash reversal opportunity")
async def get_flash_crash_signal(
    symbol: str,
    timeframe: str = Query("5m", description="Timeframe: 1m, 5m, 15m"),
) -> dict[str, Any]:
    """Detect flash crash reversal setups — enter against sharp drops with high R:R."""
    try:
        from app.ai.signals.flash_crash_sniper import FlashCrashSniper
        from app.data.fetchers.binance_fetcher import BinanceFetcher

        fetcher = BinanceFetcher()
        df = await fetcher.fetch_klines(symbol.upper().replace("/", ""), timeframe, limit=50)

        if df is None or len(df) < 10:
            return _unavailable("Insufficient market data")

        sniper = FlashCrashSniper()
        signal = sniper.scan(symbol, df)

        if signal is None:
            return _ok({"signal": None, "message": "No flash crash setup detected"})

        return _ok({
            "direction": signal.direction,
            "confidence": signal.confidence,
            "crash_price": signal.crash_price,
            "entry_price": signal.entry_price,
            "target": signal.target,
            "stop_loss": signal.stop_loss,
            "description": signal.description,
        })
    except Exception as exc:
        logger.error("flash_crash error [%s]: %s", symbol, exc)
        return _unavailable(str(exc))


# ---------------------------------------------------------------------------
# Carry Optimizer
# ---------------------------------------------------------------------------

@router.get("/carry-optimizer", summary="Get top carry trade opportunities")
async def get_carry_opportunities() -> dict[str, Any]:
    """Scan perpetual funding rates and return the top 3 carry trade opportunities."""
    try:
        from app.ai.strategies.carry_optimizer import CarryTradeOptimizer

        optimizer = CarryTradeOptimizer()
        portfolio = await optimizer.scan()

        return _ok({
            "top_3": [
                {
                    "symbol": o.symbol,
                    "funding_8h_pct": round(o.funding_rate_8h * 100, 4),
                    "annual_yield_pct": o.funding_yield_annual,
                    "risk_adjusted": o.risk_adjusted_yield,
                    "monthly_pct": o.estimated_monthly_pct,
                    "position": o.position_recommendation,
                }
                for o in portfolio.top_3_by_yield
            ],
            "portfolio_yield_annual": portfolio.estimated_portfolio_yield_annual,
        })
    except Exception as exc:
        logger.error("carry_optimizer error: %s", exc)
        return _unavailable(str(exc))


# ---------------------------------------------------------------------------
# Overnight Gap Risk
# ---------------------------------------------------------------------------

@router.get("/overnight-gap/{symbol}", summary="Overnight gap risk for a position")
async def get_overnight_gap_risk(
    symbol: str,
    direction: str = Query("LONG", description="LONG or SHORT"),
    stop_loss_price: float = Query(0.0, description="Stop loss price level"),
    entry_price: float = Query(0.0, description="Entry price"),
) -> dict[str, Any]:
    """Assess the gap-over-stop risk for holding a position overnight."""
    try:
        from app.ai.risk.overnight_gap_scanner import OvernightGapScanner
        from app.data.fetchers.binance_fetcher import BinanceFetcher

        fetcher = BinanceFetcher()
        df = await fetcher.fetch_klines(symbol.upper().replace("/", ""), "1d", limit=90)

        if df is None or len(df) < 10:
            return _unavailable("Insufficient daily OHLCV data")

        last_close = float(df["close"].iloc[-1])
        resolved_entry = entry_price if entry_price > 0 else last_close
        resolved_stop = stop_loss_price if stop_loss_price > 0 else resolved_entry * 0.97

        scanner = OvernightGapScanner()
        assessment = scanner.assess(
            symbol, df, direction.upper(), resolved_stop, resolved_entry
        )

        return _ok({
            "risk_level": assessment.risk_level,
            "recommendation": assessment.recommendation,
            "avg_gap_pct": assessment.avg_gap_pct,
            "max_gap_pct": assessment.max_gap_pct,
            "gap_exceeds_stop": assessment.gap_exceeds_stop,
            "next_event": assessment.next_gap_event,
            "hours_until": assessment.hours_until_gap,
            "description": assessment.description,
        })
    except Exception as exc:
        logger.error("overnight_gap error [%s]: %s", symbol, exc)
        return _unavailable(str(exc))


# ---------------------------------------------------------------------------
# Streak Circuit Breaker
# ---------------------------------------------------------------------------

@router.post("/streak-reset", summary="Reset the consecutive loss circuit breaker")
async def reset_streak_breaker(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Manually reset the streak circuit breaker (admin action)."""
    try:
        from app.ai.risk.streak_circuit_breaker import StreakCircuitBreaker

        breaker = StreakCircuitBreaker()
        # Reset by recording a synthetic win to break the losing streak
        breaker.record_result(is_win=True)
        state = breaker.get_state()
        return _ok({
            "reset": True,
            "consecutive_losses": state.consecutive_losses,
            "is_triggered": state.is_triggered,
            "message": "Circuit breaker reset successfully",
        })
    except Exception as exc:
        logger.error("streak_reset error: %s", exc)
        return _unavailable(str(exc))


@router.get("/streak-status", summary="Consecutive loss circuit breaker status")
async def get_streak_status(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Return the current streak circuit breaker state and whether trading is allowed."""
    try:
        from app.ai.risk.streak_circuit_breaker import StreakCircuitBreaker

        breaker = StreakCircuitBreaker()
        state = breaker.get_state()
        can_trade, reason = breaker.can_trade()

        return _ok({
            "can_trade": can_trade,
            "reason": reason,
            "consecutive_losses": state.consecutive_losses,
            "is_triggered": state.is_triggered,
            "position_scale": state.position_scale,
            "message": state.message,
        })
    except Exception as exc:
        logger.error("streak_status error: %s", exc)
        return _unavailable(str(exc))


# ---------------------------------------------------------------------------
# Pattern Performance Tracker
# ---------------------------------------------------------------------------

@router.get("/pattern-performance", summary="Which patterns are working in current market")
async def get_pattern_performance() -> dict[str, Any]:
    """Return win-rate and active status for all tracked chart patterns."""
    try:
        from app.ai.analytics.pattern_performance_tracker import PatternPerformanceTracker

        tracker = PatternPerformanceTracker()
        report = tracker.generate_report()

        return _ok({
            "top_patterns": [
                {
                    "name": p.pattern_name,
                    "win_rate": p.win_rate,
                    "sample": p.sample_size,
                    "active": p.is_active,
                }
                for p in report.top_patterns
            ],
            "disabled_patterns": [p.pattern_name for p in report.disabled_patterns],
        })
    except Exception as exc:
        logger.error("pattern_performance error: %s", exc)
        return _unavailable(str(exc))


# ---------------------------------------------------------------------------
# CVD Divergence
# ---------------------------------------------------------------------------

@router.get("/cvd-divergence/{symbol}", summary="CVD vs price divergence signal")
async def get_cvd_divergence(
    symbol: str,
    timeframe: str = Query("1h", description="Timeframe"),
) -> dict[str, Any]:
    """Detect cumulative volume delta divergence from price — early reversal signal."""
    try:
        from app.ai.signals.cvd_divergence import CVDDivergenceDetector
        from app.data.fetchers.binance_fetcher import BinanceFetcher

        fetcher = BinanceFetcher()
        df = await fetcher.fetch_klines(symbol.upper().replace("/", ""), timeframe, limit=100)

        if df is None or len(df) < 20:
            return _unavailable("Insufficient market data")

        detector = CVDDivergenceDetector()
        sig = detector.detect(symbol, df)

        if sig is None:
            return _ok({"signal": None, "message": "No CVD divergence detected"})

        return _ok({
            "divergence_type": sig.divergence_type,
            "direction": sig.direction,
            "confidence": sig.confidence,
            "candles_diverging": sig.candles_diverging,
            "description": sig.description,
        })
    except Exception as exc:
        logger.error("cvd_divergence error [%s]: %s", symbol, exc)
        return _unavailable(str(exc))


# ---------------------------------------------------------------------------
# Smart Money Flow
# ---------------------------------------------------------------------------

@router.get("/smart-money-flow/{symbol}", summary="Smart money vs retail flow index")
async def get_smart_money_flow(symbol: str) -> dict[str, Any]:
    """Compute the smart money flow index — measure institutional vs retail bias."""
    try:
        from app.ai.signals.smart_money_flow import SmartMoneyFlowIndex
        from app.data.fetchers.binance_fetcher import BinanceFetcher

        fetcher = BinanceFetcher()
        df = await fetcher.fetch_klines(
            symbol.upper().replace("/", ""), "1h", limit=168  # ~1 week
        )

        if df is None or len(df) < 24:
            return _unavailable("Insufficient market data")

        analyzer = SmartMoneyFlowIndex()
        result = analyzer.analyze(symbol, df)

        return _ok({
            "signal": result.signal,
            "bias": result.smart_money_bias,
            "institutional_buy_ratio": result.institutional_buy_ratio,
            "retail_buy_ratio": result.retail_buy_ratio,
            "confidence": result.confidence,
            "description": result.description,
        })
    except Exception as exc:
        logger.error("smart_money_flow error [%s]: %s", symbol, exc)
        return _unavailable(str(exc))


# ---------------------------------------------------------------------------
# Options Skew
# ---------------------------------------------------------------------------

@router.get("/options-skew/{symbol}", summary="25-delta put/call skew from Deribit")
async def get_options_skew(symbol: str) -> dict[str, Any]:
    """Fetch 25-delta risk-reversal skew from Deribit as a contrarian indicator."""
    try:
        from app.ai.signals.options_skew import OptionsSkewMonitor

        monitor = OptionsSkewMonitor()
        currency = "BTC" if "BTC" in symbol.upper() else "ETH"
        result = await monitor.analyze(currency)

        if result is None:
            return _unavailable("Options data unavailable for this asset")

        return _ok({
            "skew_25delta": result.skew_25delta,
            "classification": result.skew_classification,
            "term_structure_inverted": result.term_structure_inverted,
            "contrarian_signal": result.contrarian_signal,
            "confidence": result.confidence,
            "description": result.description,
        })
    except Exception as exc:
        logger.error("options_skew error [%s]: %s", symbol, exc)
        return _unavailable(str(exc))


# ---------------------------------------------------------------------------
# Invalidation Report
# ---------------------------------------------------------------------------

@router.get("/signal-invalidation/{symbol}", summary="What could invalidate a signal (alias)")
async def get_signal_invalidation(
    symbol: str,
    direction: str = Query("LONG", description="LONG or SHORT"),
    confidence: float = Query(70.0, ge=0.0, le=100.0),
    strategy: str = Query("trend_following"),
) -> dict[str, Any]:
    """Alias for /invalidation-report/{symbol} — returns signal invalidation conditions."""
    return await get_invalidation_report(
        symbol=symbol, direction=direction, confidence=confidence, strategy=strategy
    )


@router.get("/invalidation-report/{symbol}", summary="What could invalidate a signal")
async def get_invalidation_report(
    symbol: str,
    direction: str = Query("LONG", description="LONG or SHORT"),
    confidence: float = Query(70.0, ge=0.0, le=100.0),
    strategy: str = Query("trend_following"),
) -> dict[str, Any]:
    """Generate a risk invalidation report listing what could go wrong with this setup."""
    try:
        from app.ai.reports.signal_invalidation import SignalInvalidationReporter
        from app.ai.strategies.base import MarketContext, SignalResult
        from app.data.fetchers.binance_fetcher import BinanceFetcher

        fetcher = BinanceFetcher()
        df = await fetcher.fetch_klines(symbol.upper().replace("/", ""), "1h", limit=100)

        if df is None or len(df) < 20:
            return _unavailable("Insufficient market data")

        entry = float(df["close"].iloc[-1])
        atr = float((df["high"] - df["low"]).rolling(14).mean().iloc[-1])
        direction_upper = direction.upper()

        if direction_upper == "LONG":
            stop_loss = entry - 2 * atr
            tp1 = entry + 2 * atr
            tp2 = entry + 4 * atr
        else:
            stop_loss = entry + 2 * atr
            tp1 = entry - 2 * atr
            tp2 = entry - 4 * atr

        signal = SignalResult(
            asset=symbol,
            timeframe="1h",
            direction=direction_upper,
            confidence=confidence,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit_1=tp1,
            take_profit_2=tp2,
            risk_reward=2.0,
            factors=[],
            strategy_name=strategy,
        )

        context = MarketContext()
        reporter = SignalInvalidationReporter()
        report = reporter.generate(signal, df, context)

        return _ok({
            "overall_risk_level": report.overall_risk_level,
            "max_adverse_move_pct": report.max_adverse_move_pct,
            "top_risk": {
                "risk_name": report.top_risk.risk_name,
                "severity": report.top_risk.severity,
                "description": report.top_risk.description,
                "probability": report.top_risk.probability,
            } if report.top_risk else None,
            "factors": [
                {
                    "risk_name": f.risk_name,
                    "severity": f.severity,
                    "description": f.description,
                    "probability": f.probability,
                    "monitor_price": f.monitor_price,
                }
                for f in report.invalidation_factors
            ],
            "summary": report.summary,
        })
    except Exception as exc:
        logger.error("invalidation_report error [%s]: %s", symbol, exc)
        return _unavailable(str(exc))


# ---------------------------------------------------------------------------
# News Risk Guard
# ---------------------------------------------------------------------------

# Known high-impact macro events with approximate UTC schedule.
# In production these would come from an economic calendar API.
_MACRO_EVENTS: list[dict[str, Any]] = [
    {"name": "FOMC Rate Decision", "weekday": 3, "hour": 18, "minute": 0, "impact": "HIGH", "affects": ["BTC", "ETH", "SPY", "DXY"]},
    {"name": "US CPI Release", "weekday": 1, "hour": 12, "minute": 30, "impact": "HIGH", "affects": ["BTC", "ETH", "GOLD", "DXY"]},
    {"name": "US NFP (Non-Farm Payrolls)", "weekday": 4, "hour": 12, "minute": 30, "impact": "HIGH", "affects": ["BTC", "ETH", "SPY", "DXY"]},
    {"name": "US PPI Release", "weekday": 2, "hour": 12, "minute": 30, "impact": "MEDIUM", "affects": ["BTC", "SPY"]},
    {"name": "Fed Chair Speech", "weekday": 3, "hour": 17, "minute": 0, "impact": "HIGH", "affects": ["BTC", "ETH", "DXY"]},
    {"name": "US GDP (Advance)", "weekday": 3, "hour": 12, "minute": 30, "impact": "MEDIUM", "affects": ["BTC", "SPY", "DXY"]},
    {"name": "ECB Rate Decision", "weekday": 3, "hour": 12, "minute": 15, "impact": "MEDIUM", "affects": ["BTC", "ETH", "EUR"]},
]

_WARN_WINDOW_MINUTES = 120  # warn when event is within 2 hours


@router.get("/news-risk-guard", summary="High-impact macro event proximity warning")
async def get_news_risk_guard() -> dict[str, Any]:
    """
    Returns upcoming high-impact macro events within the next 2 hours.
    Recommends reducing position sizes when a high-impact event is imminent.
    """
    import datetime as dt

    now = dt.datetime.utcnow()
    upcoming: list[dict[str, Any]] = []

    for event in _MACRO_EVENTS:
        # Find the next occurrence of this event (search next 7 days)
        for day_offset in range(8):
            candidate = now + dt.timedelta(days=day_offset)
            if candidate.weekday() == event["weekday"]:
                event_dt = candidate.replace(
                    hour=event["hour"],
                    minute=event["minute"],
                    second=0,
                    microsecond=0,
                )
                if event_dt > now:
                    minutes_away = (event_dt - now).total_seconds() / 60
                    if minutes_away <= _WARN_WINDOW_MINUTES:
                        upcoming.append({
                            "name": event["name"],
                            "scheduled_at": event_dt.isoformat() + "Z",
                            "impact": event["impact"],
                            "affects": event["affects"],
                            "minutes_away": round(minutes_away),
                        })
                    break

    # Sort by proximity
    upcoming.sort(key=lambda e: e["minutes_away"])

    high_impact = any(e["impact"] == "HIGH" for e in upcoming)
    warning = (
        f"High-impact event in {upcoming[0]['minutes_away']}m — consider reducing exposure."
        if upcoming and high_impact
        else None
    )

    return _ok({
        "high_impact_soon": len(upcoming) > 0 and high_impact,
        "events": upcoming,
        "warning_message": warning,
    })
