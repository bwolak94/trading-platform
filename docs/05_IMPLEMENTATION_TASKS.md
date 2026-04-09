# Implementation Plan — Tasks for Claude Code

## Instructions for AI

The following tasks are arranged in dependency order. Implement them in this order.
Each task contains: goal, files to create, key technical requirements.

---

## PHASE 0: Project Setup (Day 1)

### TASK-000: Project initialization
```
Create the project directory structure:
trading-ai-navigator/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py           # FastAPI app entry point
│   │   ├── core/
│   │   │   ├── config.py     # Pydantic Settings (env vars)
│   │   │   └── database.py   # SQLAlchemy + async engine
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── signals.py
│   │   │       ├── market.py
│   │   │       ├── backtest.py
│   │   │       └── settings.py
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic schemas
│   │   ├── data/
│   │   │   ├── fetchers/
│   │   │   └── processors/
│   │   ├── ai/
│   │   │   ├── regime/
│   │   │   ├── strategies/
│   │   │   ├── signals/
│   │   │   └── risk/
│   │   ├── backtesting/
│   │   └── notifications/
│   ├── tests/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── alembic/              # DB migrations
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── store/
│   │   └── types/
│   └── package.json
├── docker-compose.yml
├── .env.example
└── README.md
```

**requirements.txt must contain:**
```
fastapi==0.115.0
uvicorn[standard]==0.30.0
sqlalchemy[asyncio]==2.0.36
asyncpg==0.30.0
alembic==1.14.0
pydantic-settings==2.6.0
redis==5.2.0
celery==5.4.0
pandas==2.2.3
numpy==2.0.2
scikit-learn==1.5.2
lightgbm==4.5.0
ta==0.11.0              # Technical Analysis library
transformers==4.46.3    # HuggingFace FinBERT
torch==2.5.1
python-telegram-bot==21.7
httpx==0.27.2
python-dotenv==1.0.1
pytest==8.3.3
pytest-asyncio==0.24.0
```

**docker-compose.yml must contain:**
- PostgreSQL 16 with TimescaleDB extension
- Redis 7
- Backend (FastAPI)
- Frontend (Node/Vite)
- Celery worker
- Celery beat (scheduler)

---

## PHASE 1: Backend Foundation (Days 2-4)

### TASK-101: Database Models
**File:** `backend/app/models/`

Create SQLAlchemy async models for tables from `03_DATA_MODELS_API.md`:
- `MarketData` — OHLCV data
- `MarketRegime` — regime classifications
- `Signal` — trading signals
- `OnChainEvent` — blockchain events
- `SentimentData` — NLP scores
- `BacktestResult` — backtest results
- `UserSettings` — user configuration

**Requirements:**
- Use `sqlalchemy.orm.DeclarativeBase`
- All models with `__tablename__`
- Indexes matching the schema from `03_DATA_MODELS_API.md`
- Alembic migration for each model

### TASK-102: Core Config
**File:** `backend/app/core/config.py`

```python
# Example Settings structure
class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    BINANCE_API_KEY: str
    BINANCE_SECRET: str
    WHALE_ALERT_API_KEY: str
    TWITTER_BEARER_TOKEN: str
    TELEGRAM_BOT_TOKEN: str
    MAX_DRAWDOWN_PCT: float = 10.0
    RISK_PER_TRADE_PCT: float = 1.5
    MIN_SIGNAL_CONFIDENCE: float = 50.0

    model_config = SettingsConfigDict(env_file=".env")
```

### TASK-103: FastAPI App + WebSocket
**Files:** `backend/app/main.py`, `backend/app/api/`

- FastAPI app with CORS
- WebSocket endpoint `/ws`
- Connection manager for WebSocket clients
- Router for all endpoints from `03_DATA_MODELS_API.md`
- Health check endpoint
- Error handling middleware

---

## PHASE 2: Data Fetchers (Days 3-5)

### TASK-201: Binance Market Data Fetcher
**File:** `backend/app/data/fetchers/binance_fetcher.py`

```python
# Implement two methods:
# 1. Historical OHLCV (REST API) — for backfill
# 2. Real-time stream (WebSocket) — production

class BinanceFetcher:
    async def fetch_historical_ohlcv(
        self, symbol: str, interval: str,
        start_time: datetime, end_time: datetime
    ) -> list[OHLCV]: ...

    async def start_stream(
        self, symbols: list[str], intervals: list[str],
        callback: Callable
    ) -> None: ...
```

**Pairs:** BTC/USDT, ETH/USDT, SOL/USDT
**Timeframes:** 1m, 5m, 15m, 1h, 4h, 1D
**Error handling:** Reconnect on disconnect, max 5 retries

### TASK-202: Feature Engineering
**File:** `backend/app/data/processors/feature_engineer.py`

Calculate the following technical indicators using the `ta` library:
```python
indicators = {
    # Trend
    'ema_20', 'ema_50', 'ema_200',
    'adx_14', 'adx_pos', 'adx_neg',

    # Momentum
    'rsi_14',
    'macd', 'macd_signal', 'macd_diff',

    # Volatility
    'atr_14',
    'bb_upper', 'bb_middle', 'bb_lower', 'bb_width',
    'hv_20',  # historical volatility

    # Volume
    'obv', 'volume_sma_20',

    # Derived (calculate manually)
    'atr_normalized',      # ATR / close
    'price_vs_ema200',     # (close - ema200) / ema200
    'volume_vs_avg',       # volume / volume_sma_20
    'ema_cross_signal',    # 1/-1/0
    'bb_position',         # (close - bb_lower) / bb_width
}
```

### TASK-203: Sentiment Fetcher
**File:** `backend/app/data/fetchers/sentiment_fetcher.py`

- Twitter API v2 (Bearer Token) — Recent Search endpoint
- Reddit PRAW — subreddits: r/CryptoCurrency, r/Bitcoin, r/ethereum
- Preprocessing: lowercase, remove URLs, emojis handling
- FinBERT inference: batch processing, GPU if available
- Save to `sentiment_data` table

### TASK-204: On-Chain Fetcher
**File:** `backend/app/data/fetchers/onchain_fetcher.py`

- Whale Alert API — webhook or polling every 60s
- Scoring logic from `04_AI_ENGINE.md` (scoring rules table + decay function)
- Save to `onchain_events`

### TASK-205: Celery Tasks (Schedulers)
**File:** `backend/app/tasks.py`

```python
# Scheduled tasks
@celery.task
def fetch_market_data():     # every 1 minute
    ...

@celery.task
def analyze_sentiment():     # every 15 minutes
    ...

@celery.task
def fetch_onchain():         # every 60 seconds
    ...

@celery.task
def run_signal_pipeline():   # every 5 minutes
    ...

@celery.task
def check_signal_status():   # every 15 minutes — check TP/SL hit
    ...
```

---

## PHASE 3: AI Engine (Days 5-8)

### TASK-301: Market Regime Classifier
**File:** `backend/app/ai/regime/classifier.py`

1. Prepare training dataset (rule-based labeling):
   ```python
   def label_regime(df: pd.DataFrame) -> str:
       # ADX > 25 + EMA alignment = TREND
       # ATR normalized > 0.03 + ADX < 25 = HIGH_VOL_CHOPPY
       # else = CONSOLIDATION
   ```

2. Train LightGBM:
   ```python
   model = lgb.LGBMClassifier(
       n_estimators=300,
       learning_rate=0.05,
       num_leaves=31,
       class_weight='balanced'
   )
   ```

3. Save model to `.pkl` / `.txt` file

4. `RegimeClassifier` class with `predict(features: dict) -> RegimePrediction` method

5. Save results to `market_regimes` table

### TASK-302: Strategy — Trend Following
**File:** `backend/app/ai/strategies/trend_following.py`

Implement `TrendFollowingStrategy(BaseStrategy)` with logic from `04_AI_ENGINE.md`.

Output: `Signal` object or `None`

### TASK-303: Strategy — Mean Reversion
**File:** `backend/app/ai/strategies/mean_reversion.py`

Implement `MeanReversionStrategy(BaseStrategy)`.

### TASK-304: Strategy — SMC
**File:** `backend/app/ai/strategies/smc_strategy.py`

Implement `SMCStrategy(BaseStrategy)`:
- Order Block detection: function `find_order_blocks(df, lookback=20)`
- FVG detection: function `find_fair_value_gaps(df)`
- Entry on OB retest

### TASK-305: Strategy — Volume Breakout
**File:** `backend/app/ai/strategies/volume_breakout.py`

Implement `VolumeBreakoutStrategy(BaseStrategy)`.

### TASK-306: Signal Aggregator
**File:** `backend/app/ai/signals/aggregator.py`

```python
class SignalAggregator:
    def aggregate(
        self,
        asset: str,
        regime: RegimePrediction,
        technical_signals: list[Signal],
        onchain_score: float,
        sentiment_score: float,
        macro_events: list[MacroEvent]
    ) -> Signal | None:
        # 1. Select strategies compatible with the regime
        # 2. Calculate weighted score
        # 3. Apply filters
        # 4. Create final Signal or return None
        ...
```

### TASK-307: Risk Engine
**File:** `backend/app/ai/risk/engine.py`

```python
class RiskEngine:
    def check_kill_switch(self, user_id: str) -> bool: ...
    def calculate_position_size(self, ...) -> PositionSize: ...
    def calculate_drawdown(self, user_id: str) -> float: ...
```

---

## PHASE 4: Backtesting (Days 6-7)

### TASK-401: Walk-Forward Backtester
**File:** `backend/app/backtesting/walk_forward.py`

```python
class WalkForwardBacktester:
    def run(
        self,
        strategy: BaseStrategy,
        asset: str,
        timeframe: str,
        start_date: date,
        end_date: date,
        train_window_months: int = 6,
        test_window_months: int = 1,
        initial_capital: float = 10000,
        risk_per_trade_pct: float = 1.5
    ) -> BacktestResult:
        # Split data into train/test windows
        # For each window: train model, test on out-of-sample
        # Aggregate metrics
        ...

    def calculate_metrics(self, trades: list[Trade]) -> Metrics:
        # win_rate, profit_factor, max_drawdown, sharpe, calmar
        ...
```

### TASK-402: Monte Carlo Simulator
**File:** `backend/app/backtesting/monte_carlo.py`

```python
class MonteCarloSimulator:
    def run(
        self,
        trades: list[Trade],
        iterations: int = 1000,
        initial_capital: float = 10000
    ) -> MonteCarloResult:
        # Randomize trade order, calculate equity curve
        # Return percentiles and probability of ruin
        ...
```

---

## PHASE 5: Notifications (Day 7)

### TASK-501: Telegram Bot
**File:** `backend/app/notifications/telegram_bot.py`

- python-telegram-bot library
- Commands: `/start`, `/signals`, `/status`, `/pause`, `/resume`
- Message format from `02_USER_STORIES.md` (US-16)
- Anti-spam: minimum 5 minutes between signals per user
- Async sending

---

## PHASE 6: Frontend Dashboard (Days 8-12)

### TASK-601: React Project Setup
```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install tailwindcss recharts lightweight-charts zustand
npm install @tanstack/react-query axios
```

### TASK-602: Types & API Client
**File:** `frontend/src/types/index.ts` and `frontend/src/api/client.ts`

TypeScript types based on the API from `03_DATA_MODELS_API.md`:
```typescript
interface Signal {
  id: string;
  asset: string;
  direction: 'LONG' | 'SHORT' | 'NEUTRAL';
  confidence: number;
  regime: MarketRegime;
  entry_price: number;
  stop_loss: number;
  take_profit_1: number;
  take_profit_2: number;
  risk_reward: number;
  factors: SignalFactor[];
  status: SignalStatus;
  created_at: string;
}

type MarketRegime = 'TREND_BULL' | 'TREND_BEAR' | 'CONSOLIDATION' | 'HIGH_VOL_CHOPPY';
```

### TASK-603: WebSocket Hook
**File:** `frontend/src/hooks/useWebSocket.ts`

```typescript
// Hook managing the WebSocket connection
// Auto-reconnect on disconnect
// Subscription management for channels
// Returns: { isConnected, lastMessage, subscribe, unsubscribe }
```

### TASK-604: Main Dashboard Layout
**File:** `frontend/src/components/Dashboard/`

**Design: Dark theme, professional trading terminal aesthetic**
- Background color: `#0d1117` (dark navy)
- Accents: `#00d4aa` (teal) for bullish, `#ff4757` (red) for bearish
- Font: `JetBrains Mono` for numbers, `Inter` for text
- Grid layout: 3 columns on desktop, 1 on mobile

**Sections:**
1. **Header:** Logo + system status (ACTIVE/PAUSED) + drawdown indicator
2. **Regime Panel:** 5 assets with regime badge each (real-time)
3. **Signal Feed:** List of signal cards (sorted by confidence desc)
4. **Sentiment Bar:** Sentiment heatmap
5. **Risk Panel:** Equity curve + drawdown gauge

### TASK-605: Signal Card Component
**File:** `frontend/src/components/SignalCard/SignalCard.tsx`

Displays:
- Large header: "BTC/USDT LONG"
- Confidence: progress bar + "72%"
- Main message: "Probability of upward breakout: 72%"
- Factors (max 3): icon + name + contribution percentage
- Levels: Entry / SL / TP1 / TP2 in a table
- R/R ratio badge
- Regime badge
- Timestamp

**Animation:** New signal -> slide-in + pulse for 3 seconds

### TASK-606: Backtesting Page
**File:** `frontend/src/pages/Backtest.tsx`

- Form: strategy selection, asset, timeframe, dates, capital
- Submit -> POST `/api/v1/backtest/run` -> status polling
- Results: Equity curve (recharts LineChart), metrics table, Monte Carlo percentiles
- Export CSV button

---

## PHASE 7: Testing (Days 10-12)

### TASK-701: Unit Tests — AI Engine
**File:** `backend/tests/test_strategies.py`

- Test each strategy with mock data
- Test regime classifier (known historical cases)
- Test risk engine (kill switch logic)

### TASK-702: Integration Tests — API
**File:** `backend/tests/test_api.py`

- Test all endpoints
- Test WebSocket events
- Test signal aggregation pipeline (end-to-end)

### TASK-703: Backtest Validation
- Run backtest on BTC/USDT 2023-2024
- Verify: win rate >50%, max drawdown <20%
- If results below threshold -> adjust strategy parameters

---

## Implementation order (for Claude Code)

```
TASK-000 -> TASK-101 -> TASK-102 -> TASK-103
         -> TASK-201 -> TASK-202 -> TASK-203 -> TASK-204 -> TASK-205
         -> TASK-301 -> TASK-302 -> TASK-303 -> TASK-304 -> TASK-305 -> TASK-306 -> TASK-307
         -> TASK-401 -> TASK-402
         -> TASK-501
         -> TASK-601 -> TASK-602 -> TASK-603 -> TASK-604 -> TASK-605 -> TASK-606
         -> TASK-701 -> TASK-702 -> TASK-703
```

## Environment variables (.env.example)

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/trading_ai
REDIS_URL=redis://localhost:6379/0

# Exchange APIs
BINANCE_API_KEY=your_key
BINANCE_SECRET=your_secret

# Data Sources
WHALE_ALERT_API_KEY=your_key
GLASSNODE_API_KEY=your_key

# Social Media
TWITTER_BEARER_TOKEN=your_token
REDDIT_CLIENT_ID=your_id
REDDIT_CLIENT_SECRET=your_secret

# Notifications
TELEGRAM_BOT_TOKEN=your_token

# Risk Settings
MAX_DRAWDOWN_PCT=10.0
RISK_PER_TRADE_PCT=1.5
MIN_SIGNAL_CONFIDENCE=50.0

# App
ENVIRONMENT=development
SECRET_KEY=your_secret_key
CORS_ORIGINS=http://localhost:5173
```
