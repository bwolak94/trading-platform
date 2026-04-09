# Data Models & API Specification

## Database Schema

### Table: `market_data`
```sql
CREATE TABLE market_data (
    id BIGSERIAL PRIMARY KEY,
    asset VARCHAR(20) NOT NULL,          -- 'BTC/USDT'
    timeframe VARCHAR(5) NOT NULL,       -- '1h', '4h', '1D'
    timestamp TIMESTAMPTZ NOT NULL,
    open DECIMAL(20, 8) NOT NULL,
    high DECIMAL(20, 8) NOT NULL,
    low DECIMAL(20, 8) NOT NULL,
    close DECIMAL(20, 8) NOT NULL,
    volume DECIMAL(20, 4) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
-- TimescaleDB hypertable
SELECT create_hypertable('market_data', 'timestamp');
CREATE INDEX ON market_data (asset, timeframe, timestamp DESC);
```

### Table: `market_regimes`
```sql
CREATE TABLE market_regimes (
    id BIGSERIAL PRIMARY KEY,
    asset VARCHAR(20) NOT NULL,
    regime VARCHAR(30) NOT NULL,         -- 'TREND_BULL', 'TREND_BEAR', 'CONSOLIDATION', 'HIGH_VOL_CHOPPY'
    confidence DECIMAL(5, 2) NOT NULL,   -- 0-100
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    metadata JSONB                        -- additional metrics (ADX, ATR, etc.)
);
```

### Table: `signals`
```sql
CREATE TABLE signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL,      -- 'LONG', 'SHORT', 'NEUTRAL'
    confidence DECIMAL(5, 2) NOT NULL,
    regime VARCHAR(30) NOT NULL,
    entry_price DECIMAL(20, 8),
    stop_loss DECIMAL(20, 8),
    take_profit_1 DECIMAL(20, 8),
    take_profit_2 DECIMAL(20, 8),
    risk_reward DECIMAL(5, 2),
    position_size_pct DECIMAL(5, 2),

    -- Scoring breakdown
    technical_score DECIMAL(5, 2),
    onchain_score DECIMAL(5, 2),
    sentiment_score DECIMAL(5, 2),
    macro_score DECIMAL(5, 2),

    -- Factors (JSON array)
    factors JSONB NOT NULL,

    -- Status tracking
    status VARCHAR(20) DEFAULT 'ACTIVE', -- 'ACTIVE', 'TP1_HIT', 'TP2_HIT', 'SL_HIT', 'EXPIRED', 'CANCELLED'
    expires_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Table: `onchain_events`
```sql
CREATE TABLE onchain_events (
    id BIGSERIAL PRIMARY KEY,
    asset VARCHAR(20) NOT NULL,
    event_type VARCHAR(30) NOT NULL,     -- 'WHALE_TRANSFER', 'EXCHANGE_INFLOW', 'EXCHANGE_OUTFLOW'
    amount DECIMAL(20, 4) NOT NULL,
    amount_usd DECIMAL(20, 2),
    from_address VARCHAR(100),
    to_address VARCHAR(100),
    direction VARCHAR(10),               -- 'BULLISH', 'BEARISH', 'NEUTRAL'
    source VARCHAR(30),                  -- 'whale_alert', 'glassnode'
    raw_data JSONB,
    timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Table: `sentiment_data`
```sql
CREATE TABLE sentiment_data (
    id BIGSERIAL PRIMARY KEY,
    asset VARCHAR(20) NOT NULL,
    source VARCHAR(30) NOT NULL,         -- 'twitter', 'reddit'
    score DECIMAL(5, 4) NOT NULL,        -- -1.0 to +1.0
    volume INTEGER,                      -- number of posts in window
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Table: `backtest_results`
```sql
CREATE TABLE backtest_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_name VARCHAR(50) NOT NULL,
    asset VARCHAR(20) NOT NULL,
    timeframe VARCHAR(5) NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,

    -- Performance metrics
    win_rate DECIMAL(5, 2),
    profit_factor DECIMAL(8, 4),
    max_drawdown DECIMAL(5, 2),
    sharpe_ratio DECIMAL(8, 4),
    calmar_ratio DECIMAL(8, 4),
    total_trades INTEGER,

    -- Monte Carlo
    prob_ruin_20pct DECIMAL(5, 2),
    prob_ruin_30pct DECIMAL(5, 2),
    equity_curve JSONB,                  -- [{date, equity}, ...]

    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Table: `user_settings`
```sql
CREATE TABLE user_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(100) NOT NULL UNIQUE,
    capital DECIMAL(20, 2),
    risk_per_trade_pct DECIMAL(5, 2) DEFAULT 1.5,
    max_drawdown_pct DECIMAL(5, 2) DEFAULT 10.0,
    telegram_chat_id VARCHAR(50),
    enabled_assets JSONB DEFAULT '["BTC/USDT","ETH/USDT"]',
    system_status VARCHAR(20) DEFAULT 'ACTIVE',   -- 'ACTIVE', 'PAUSED'
    notifications_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## REST API Endpoints

### Base URL: `/api/v1`

### Signals

```
GET    /signals                    # List signals (with filtering)
GET    /signals/{id}               # Signal details
GET    /signals/active             # Active signals
```

**GET /signals Params:**
```
?asset=BTC/USDT
?direction=LONG
?status=ACTIVE
?from=2025-01-01
?limit=20
?offset=0
```

**Response 200:**
```json
{
  "data": [
    {
      "id": "uuid",
      "asset": "BTC/USDT",
      "direction": "LONG",
      "confidence": 72,
      "regime": "TREND_BULL",
      "entry_price": 67240,
      "stop_loss": 65800,
      "take_profit_1": 69500,
      "take_profit_2": 72000,
      "risk_reward": 2.1,
      "position_size_pct": 1.5,
      "factors": [
        {"name": "Whale Accumulation", "weight": 0.3, "score": 0.8, "label": "BULLISH"},
        {"name": "Twitter Sentiment", "weight": 0.2, "score": 0.65, "label": "POSITIVE"},
        {"name": "EMA Crossover", "weight": 0.4, "score": 0.9, "label": "BULLISH"}
      ],
      "status": "ACTIVE",
      "created_at": "2025-01-15T14:23:00Z"
    }
  ],
  "meta": {
    "total": 1,
    "limit": 20,
    "offset": 0
  }
}
```

### Market Data

```
GET    /market/regime              # Current regime for all assets
GET    /market/regime/{asset}      # Regime for a specific asset
GET    /market/sentiment           # Current sentiment
GET    /market/onchain             # Recent on-chain events
GET    /market/calendar            # Upcoming macro events
```

### Backtesting

```
POST   /backtest/run               # Run backtest
GET    /backtest/results           # List of results
GET    /backtest/results/{id}      # Result details
```

**POST /backtest/run Body:**
```json
{
  "strategy": "trend_following",
  "asset": "BTC/USDT",
  "timeframe": "4h",
  "from": "2023-01-01",
  "to": "2025-01-01",
  "initial_capital": 10000,
  "risk_per_trade_pct": 1.5
}
```

### Settings

```
GET    /settings                   # Get settings
PATCH  /settings                   # Update settings
POST   /settings/reset-killswitch  # Reset kill switch
```

### System

```
GET    /health                     # Health check
GET    /status                     # System status + drawdown
```

---

## WebSocket Events

**Endpoint:** `ws://host/ws`

### Subscribe to events:
```json
{"action": "subscribe", "channels": ["signals", "regime", "sentiment"]}
```

### Event: New signal
```json
{
  "type": "NEW_SIGNAL",
  "payload": { ...signal_object }
}
```

### Event: Regime change
```json
{
  "type": "REGIME_CHANGE",
  "payload": {
    "asset": "BTC/USDT",
    "old_regime": "CONSOLIDATION",
    "new_regime": "TREND_BULL",
    "confidence": 84
  }
}
```

### Event: Kill Switch
```json
{
  "type": "KILL_SWITCH_TRIGGERED",
  "payload": {
    "reason": "max_drawdown_exceeded",
    "drawdown_pct": 10.3
  }
}
```
