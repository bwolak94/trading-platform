"""Signal Quality API — endpoints for advanced signal analysis tools."""

from fastapi import APIRouter, Query

router = APIRouter(prefix="/signal-quality", tags=["signal-quality"])


@router.get("/order-flow-imbalance")
async def get_order_flow_imbalance(
    symbol: str = Query(default="BTCUSDT", description="Trading pair symbol"),
    depth: int = Query(default=20, ge=1, le=20, description="Order book depth levels"),
) -> dict:
    """Get real-time order book buy/sell imbalance score."""
    from app.ai.signals.order_flow_imbalance import get_order_flow_imbalance as _get
    return await _get(symbol=symbol, depth=depth)


@router.get("/volume-profile")
async def get_volume_profile(
    symbol: str = Query(default="BTCUSDT"),
    interval: str = Query(default="1h"),
    limit: int = Query(default=100, ge=20, le=500),
) -> dict:
    """Get Volume Profile (VPVR) with POC, VAH, and VAL levels."""
    from app.ai.signals.volume_profile import get_volume_profile as _get
    return await _get(symbol=symbol, interval=interval, limit=limit)


@router.get("/liquidity-map")
async def get_liquidity_map(
    symbol: str = Query(default="BTCUSDT"),
    interval: str = Query(default="1h"),
    lookback: int = Query(default=100, ge=20, le=300),
) -> dict:
    """Get smart liquidity map with stop-loss cluster zones."""
    from app.ai.signals.liquidity_map import get_liquidity_map as _get
    return await _get(symbol=symbol, interval=interval, lookback=lookback)


@router.get("/mtf-confluence")
async def get_mtf_confluence(
    symbol: str = Query(default="BTCUSDT"),
) -> dict:
    """Get multi-timeframe confluence score (0-100) for a symbol."""
    from app.ai.signals.mtf_confluence_scorer import get_mtf_confluence_score
    return await get_mtf_confluence_score(symbol=symbol)


@router.get("/divergence-chain")
async def get_divergence_chain(
    symbol: str = Query(default="BTCUSDT"),
    interval: str = Query(default="1h"),
) -> dict:
    """Detect RSI + MACD + OBV triple divergence (chain score 0-3)."""
    from app.ai.signals.divergence_chain import detect_divergence_chain
    return await detect_divergence_chain(symbol=symbol, interval=interval)


@router.get("/compression")
async def get_compression(
    symbol: str = Query(default="BTCUSDT"),
    interval: str = Query(default="1h"),
    lookback: int = Query(default=50, ge=20, le=200),
) -> dict:
    """Detect NR7, inside bars, and ATR compression patterns."""
    from app.ai.signals.compression_detector import detect_compression
    return await detect_compression(symbol=symbol, interval=interval, lookback=lookback)


@router.get("/pairs-arbitrage")
async def get_pairs_arbitrage(
    symbol_a: str = Query(default="BTCUSDT"),
    symbol_b: str = Query(default="ETHUSDT"),
    interval: str = Query(default="1d"),
    lookback: int = Query(default=200),
) -> dict:
    """Compute z-score of log price ratio for statistical arbitrage pairs."""
    from app.ai.signals.statistical_arbitrage import get_pairs_zscore
    return await get_pairs_zscore(
        symbol_a=symbol_a,
        symbol_b=symbol_b,
        interval=interval,
        lookback=lookback,
    )


@router.get("/regime-matrix")
async def get_regime_matrix() -> dict:
    """Return the full regime-strategy performance matrix."""
    from app.ai.signals.regime_signal_filter import get_regime_performance_matrix
    return await get_regime_performance_matrix()


@router.get("/adaptive-params")
async def get_adaptive_params(
    strategy: str = Query(default="trend_following", description="Strategy name"),
) -> dict:
    """Get best-performing parameters for a strategy based on rolling history."""
    from app.ai.signals.adaptive_parameters import get_adaptive_optimizer
    optimizer = get_adaptive_optimizer()
    return {
        "strategy": strategy,
        "best_params": optimizer.get_best_params(strategy),
        "stats": optimizer.get_all_strategy_stats().get(strategy, {}),
    }
