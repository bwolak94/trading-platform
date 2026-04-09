# AI Engine Specification

## Module 1: Market Regime Classifier

### Goal
Automatic classification of the current market state into one of 4 categories.

### Regimes
| Regime | Description | Preferred strategies |
|--------|-------------|---------------------|
| `TREND_BULL` | Strong uptrend, ADX >25, price above EMA200 | Trend Following, SMC Long |
| `TREND_BEAR` | Strong downtrend, ADX >25, price below EMA200 | Trend Following Short, SMC Short |
| `CONSOLIDATION` | Low volatility, price range <3% in 24h | Mean Reversion |
| `HIGH_VOL_CHOPPY` | High volatility without direction, ATR spike | No signals / position reduction |

### Input features (per timeframe: 1h, 4h)
```python
features = {
    # Trend
    'adx_14': float,              # Average Directional Index
    'ema_cross_signal': int,      # 1 (bull), -1 (bear), 0 (neutral)
    'price_vs_ema200': float,     # % above/below EMA200
    'slope_ema50': float,         # EMA50 slope (last 10 candles)

    # Volatility
    'atr_14_normalized': float,   # ATR / close (as %)
    'bb_width': float,            # Bollinger Band Width
    'hv_20': float,               # Historical Volatility 20-period

    # Volume
    'volume_vs_avg': float,       # Volume / 20-period avg volume
    'obv_trend': float,           # On-Balance Volume slope

    # Price structure
    'hh_hl_count': int,           # Higher Highs/Higher Lows count (last 10)
    'lh_ll_count': int,           # Lower Highs/Lower Lows count
    'range_vs_atr': float,        # Daily range / ATR
}
```

### Model
- **Algorithm:** LightGBM Classifier (multi-class)
- **Training:** Labeled historical data (manual labeling + rule-based bootstrap)
- **Evaluation:** F1-score per class, Confusion Matrix
- **Retrain:** Every 30 days or when F1 <0.65

### Output
```python
{
    'regime': 'TREND_BULL',
    'confidence': 84.3,
    'probabilities': {
        'TREND_BULL': 0.843,
        'TREND_BEAR': 0.04,
        'CONSOLIDATION': 0.08,
        'HIGH_VOL_CHOPPY': 0.037
    }
}
```

---

## Module 2: Strategy Library

### Interface (every strategy must implement):
```python
class BaseStrategy:
    name: str
    supported_regimes: list[str]
    min_confidence: float = 50.0

    def generate_signal(
        self,
        asset: str,
        timeframe: str,
        market_data: pd.DataFrame,
        context: MarketContext
    ) -> Signal | None:
        """
        Returns Signal or None if no signal.
        context contains: regime, sentiment, onchain_data, macro_events
        """
        raise NotImplementedError
```

### Strategy 1: Trend Following (EMA + ADX)
**Regimes:** `TREND_BULL`, `TREND_BEAR`

**LONG Logic:**
1. EMA20 > EMA50 > EMA200 (bullish alignment)
2. ADX > 25 (strong trend)
3. RSI(14) between 45-70 (not overbought)
4. Price retests EMA20 (pullback to support)
5. Volume on the last candle > 1.2x average

**Levels:**
- Entry: Close of the current candle
- SL: Below the last swing low or EMA50 - 1 ATR
- TP1: +1.5 * (Entry - SL)
- TP2: +3.0 * (Entry - SL)

### Strategy 2: Mean Reversion (RSI Divergence + BB)
**Regimes:** `CONSOLIDATION`

**LONG Logic:**
1. Price near the lower Bollinger Band (<2%)
2. RSI(14) < 35
3. Bullish divergence (price makes a lower low, RSI makes a higher low)
4. Last candle: close above open (reversal candle)

**Levels:**
- Entry: Close
- SL: Below the last low - 0.5 ATR
- TP1: EMA20 (middle BB)
- TP2: Upper Bollinger Band

### Strategy 3: SMC — Order Blocks + FVG
**Regimes:** `TREND_BULL`, `TREND_BEAR`

**LONG Logic:**
1. Identify Order Block: last bearish candle before an upward impulse
2. Price returns to OB (retest)
3. Fair Value Gap (FVG) below the current price (magnet)
4. No significant supply zone between OB and the next resistance

**Levels:**
- Entry: Middle of the Order Block
- SL: Below Order Block - 0.3% buffer
- TP1: Next FVG / resistance
- TP2: Swing High

### Strategy 4: Volume Breakout
**Regimes:** All (priority: `CONSOLIDATION`)

**LONG Logic:**
1. Consolidation: 10+ candles in a range <2% ATR
2. Breakout: candle closes above the upper range boundary
3. Volume > 2x 20-period average
4. Retest: price returns to the breakout level and holds (optional)

---

## Module 3: Signal Aggregator

### Weighted Scoring System

```python
WEIGHTS = {
    'technical': 0.40,   # Strategy signals
    'onchain': 0.30,     # Blockchain data
    'sentiment': 0.20,   # NLP social media
    'macro': 0.10        # Economic calendar
}

def calculate_final_score(components: dict) -> float:
    """
    Each component: value from -1.0 (strongly bearish) to +1.0 (strongly bullish)
    Final result: -1.0 to +1.0, mapped to confidence 0-100
    """
    weighted = sum(score * WEIGHTS[key] for key, score in components.items())
    confidence = (weighted + 1) / 2 * 100  # mapping [-1,1] -> [0,100]
    return confidence
```

### Signal filters (do not emit if):
- `confidence < 50%`
- `regime == HIGH_VOL_CHOPPY`
- Macro event in <15 minutes (HIGH impact)
- Identical signal emitted in the last 4 hours
- System in `PAUSED` state (kill switch)

---

## Module 4: Sentiment Analyzer

### NLP Pipeline
```
Twitter API -> collect tweets -> clean -> FinBERT -> score [-1,+1] -> rolling avg
```

### Model: FinBERT
- Pre-trained: `ProsusAI/finbert` (HuggingFace)
- Output classes: `positive`, `negative`, `neutral`
- Score calculation: `score = P(positive) - P(negative)`

### Aggregation
- Window: last 1 hour of tweets
- Min sample: 50 tweets (below -> insufficient data, score = 0)
- Keywords per asset:
  - BTC: `bitcoin, btc, #btc, #bitcoin`
  - ETH: `ethereum, eth, #eth, #ethereum`
  - Forex: keyword sets for currency pairs

---

## Module 5: On-Chain Analyzer

### Scoring Rules

| Event | Type | Score | Rationale |
|-------|------|-------|-----------|
| Transfer >100 BTC TO exchange | EXCHANGE_INFLOW | -0.7 | Sell pressure |
| Transfer >100 BTC FROM exchange | EXCHANGE_OUTFLOW | +0.7 | Accumulation |
| Whale buy >$10M (spot) | WHALE_BUY | +0.8 | Smart money entering |
| Mining outflow spike | MINER_SELL | -0.5 | Miners selling |
| Exchange reserves decline | RESERVE_DECLINE | +0.6 | Less supply on exchanges |

### Decay Function
Older events lose weight over time:
```python
def decayed_score(event_score, hours_ago):
    half_life = 6  # hours
    return event_score * (0.5 ** (hours_ago / half_life))
```

---

## Module 6: Risk Engine

### Kill Switch Logic
```python
def check_kill_switch(user_settings, signal_history):
    if user_settings.system_status == 'PAUSED':
        return True  # already stopped

    recent_signals = get_signals_last_30_days(user_settings.user_id)
    drawdown = calculate_drawdown(recent_signals, user_settings.capital)

    if drawdown >= user_settings.max_drawdown_pct:
        pause_system(user_settings.user_id)
        notify_user(user_settings, drawdown)
        return True

    return False
```

### Position Sizing (simplified Kelly Criterion)
```python
def calculate_position_size(capital, risk_pct, entry, stop_loss):
    risk_amount = capital * (risk_pct / 100)
    price_risk = abs(entry - stop_loss)
    units = risk_amount / price_risk
    position_value = units * entry
    position_pct = (position_value / capital) * 100
    return {
        'units': units,
        'position_value': position_value,
        'position_pct': position_pct,
        'risk_amount': risk_amount
    }
```
