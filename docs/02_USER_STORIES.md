# User Stories & Acceptance Criteria

## Epics Overview

1. **EP-01** Data Ingestion & Pipeline
2. **EP-02** Market Regime Detection
3. **EP-03** Strategy Library & Signal Generation
4. **EP-04** Risk Engine
5. **EP-05** Backtesting Module
6. **EP-06** Dashboard (Web UI)
7. **EP-07** Notifications (Telegram)

---

## EP-01: Data Ingestion

### US-01: Fetching OHLCV Data
**As** an AI system
**I want** to fetch OHLCV price data every 1 minute for selected pairs
**So that** I have an up-to-date base for technical analysis

**AC:**
- [ ] Data fetched from Binance API (WebSocket for real-time, REST for historical)
- [ ] Supported pairs: BTC/USDT, ETH/USDT, SOL/USDT, EUR/USD, GBP/USD
- [ ] Supported timeframes: 1m, 5m, 15m, 1h, 4h, 1D
- [ ] API error -> retry with exponential backoff (max 5 attempts)
- [ ] Missing data >60s -> alert to log + admin notification

### US-02: On-Chain Data (Whale Monitoring)
**As** a trader
**I want** to see whale activity (transfers >100 BTC)
**So that** I understand sell pressure before making a decision

**AC:**
- [ ] Integration with Whale Alert API (or alternatively Glassnode)
- [ ] Threshold configurable (default: 100 BTC / 1000 ETH)
- [ ] Transfer to exchange = bearish signal (sell pressure)
- [ ] Transfer from exchange = bullish signal (accumulation)
- [ ] Data stored in DB with timestamp

### US-03: Sentiment Analysis
**As** a trader
**I want** to know the market sentiment from social media
**So that** I can detect FOMO/FUD before a price move

**AC:**
- [ ] Scraping/API: Twitter (X) + Reddit (r/CryptoCurrency, r/Bitcoin)
- [ ] NLP Model: FinBERT (fine-tuned on financial data)
- [ ] Output: sentiment score [-1.0 to +1.0] per asset
- [ ] Aggregation: 1h rolling average
- [ ] Data updated every 15 minutes

### US-04: Macro Calendar (Forex)
**As** a forex trader
**I want** to see upcoming economic events
**So that** I avoid entering a position before high-impact news

**AC:**
- [ ] Integration with Forex Factory API or Investing.com calendar
- [ ] Filters: only HIGH impact events
- [ ] Alerts 30 minutes and 5 minutes before the event
- [ ] Auto-flagging of signals generated 15 min before/after the event

---

## EP-02: Market Regime Detection

### US-05: Market Regime Classification
**As** a trader
**I want** to know what regime the market is in
**So that** the AI selects the appropriate strategy

**AC:**
- [ ] 4 regimes: `TREND_BULL`, `TREND_BEAR`, `CONSOLIDATION`, `HIGH_VOL_CHOPPY`
- [ ] Input model: ATR, ADX, Bollinger Band Width, Volume Profile
- [ ] Classifier: LightGBM (trained on labeled historical data)
- [ ] Confidence score [0-100%] for each regime
- [ ] Regime change -> event emitted to system
- [ ] Regime history stored in DB

### US-06: Displaying Regime on Dashboard
**As** a trader
**I want** to see the current market regime on the main screen
**So that** I immediately understand the signal context

**AC:**
- [ ] Visual badge with color: green (bull), red (bear), yellow (consolidation), orange (choppy)
- [ ] Displayed duration of the current regime
- [ ] Mini-chart of the last 7 regime changes

---

## EP-03: Strategy Library & Signal Generation

### US-07: Strategy Library (MVP)
**As** an AI system
**I want** to have a set of ready-made strategies
**So that** I can match them to the current market regime

**AC:**
- [ ] Strategy 1: **Trend Following** (EMA crossover + ADX filter) -> for TREND_BULL/BEAR
- [ ] Strategy 2: **Mean Reversion** (RSI divergence + Bollinger Bands) -> for CONSOLIDATION
- [ ] Strategy 3: **Breakout Detection** (Volume spike + range breakout) -> for all regimes
- [ ] Strategy 4: **SMC (Smart Money Concepts)** — Order blocks + Fair Value Gaps -> for TREND
- [ ] Each strategy: separate Python module with `generate_signal()` interface

### US-08: Signal Aggregation and Scoring
**As** a trader
**I want** to receive one resulting signal with reasoning
**So that** I do not have to aggregate 10 indicators myself

**AC:**
- [ ] Weighted scoring: technical (40%) + on-chain (30%) + sentiment (20%) + macro (10%)
- [ ] Output format:
  ```json
  {
    "asset": "BTC/USDT",
    "direction": "LONG",
    "confidence": 72,
    "regime": "TREND_BULL",
    "factors": [
      {"name": "Whale Accumulation", "weight": 0.3, "value": 0.8},
      {"name": "Positive Sentiment", "weight": 0.2, "value": 0.65},
      {"name": "EMA Crossover", "weight": 0.4, "value": 0.9}
    ],
    "suggested_entry": 67240,
    "suggested_sl": 65800,
    "suggested_tp": [69500, 72000],
    "risk_reward": 2.1,
    "timestamp": "2025-01-15T14:23:00Z"
  }
  ```
- [ ] Signals with confidence <50% -> not emitted
- [ ] Every signal logged to DB with full reasoning

---

## EP-04: Risk Engine

### US-09: Drawdown Kill Switch
**As** a trader
**I want** the system to automatically stop issuing signals when losses are too high
**So that** I protect capital in difficult market conditions

**AC:**
- [ ] Configurable parameter: `MAX_DRAWDOWN_PCT` (default 10%)
- [ ] Calculated based on the user's signal history
- [ ] Exceeding the threshold -> system status changes to `PAUSED`
- [ ] Dashboard shows a clear message: "System paused — drawdown 10.2%"
- [ ] Manual reset by user with confirmation

### US-10: Position Sizing Recommendation
**As** a trader
**I want** to receive a position size suggestion
**So that** I do not risk more than x% per trade

**AC:**
- [ ] Configurable risk per trade (default 1-2% of capital)
- [ ] Calculation: `position_size = (capital * risk_pct) / (entry - stop_loss)`
- [ ] Displayed on the signal card
- [ ] Accounts for volatility (ATR) — higher volatility = smaller position

---

## EP-05: Backtesting Module

### US-11: Walk-Forward Testing
**As** a trader
**I want** to see how the strategy performed historically
**So that** I can trust the AI signals

**AC:**
- [ ] Minimum 2 years of historical data
- [ ] Walk-forward: training window 6 months, test 1 month, step 1 month
- [ ] Metrics: Win Rate, Profit Factor, Max Drawdown, Sharpe Ratio, Calmar Ratio
- [ ] Results visualized on an equity curve chart
- [ ] Export results to CSV

### US-12: Monte Carlo Simulation
**As** a trader
**I want** to see a simulation of various scenarios
**So that** I understand the risk of ruin

**AC:**
- [ ] Min 1000 simulation iterations
- [ ] Parameters: random trade order from history
- [ ] Output: Probability of Ruin (at drawdown >20%, >30%, >50%)
- [ ] Equity curve percentiles: 5th, 25th, 50th, 75th, 95th
- [ ] Execution time: <60 seconds for 1000 iterations

---

## EP-06: Web Dashboard

### US-13: Main Dashboard — Signal Feed
**As** a trader
**I want** to see active signals in real time
**So that** I can quickly react to market opportunities

**AC:**
- [ ] Main message: "Probability of upward breakout: 72%"
- [ ] List of contributing factors (max 3 main ones)
- [ ] Suggested levels: Entry, SL, TP1, TP2
- [ ] Risk/Reward ratio
- [ ] Signal generation time
- [ ] Signal status: `ACTIVE`, `TP_HIT`, `SL_HIT`, `EXPIRED`
- [ ] WebSocket update — no page refresh needed

### US-14: Market Regime Panel
**As** a trader
**I want** to see the market regime panel on the dashboard
**So that** I understand the context of all signals

**AC:**
- [ ] Real-time update
- [ ] Sentiment heatmap for each asset

### US-15: Risk Dashboard
**As** a trader
**I want** to see my current P&L and drawdown
**So that** I can monitor portfolio risk

**AC:**
- [ ] Equity curve chart (based on tracked signals)
- [ ] Current drawdown %
- [ ] Kill switch status
- [ ] Win/Loss streak

---

## EP-07: Telegram Notifications

### US-16: Signal Notifications
**As** a trader
**I want** to receive signals on Telegram
**So that** I can react even when I am not at the computer

**AC:**
- [ ] Message format:
  ```
  SIGNAL: BTC/USDT LONG
  Confidence: 72%
  Entry: $67,240
  SL: $65,800
  TP1: $69,500 | TP2: $72,000
  R/R: 2.1

  Factors:
  Whale Accumulation (30%)
  Positive X Sentiment (20%)
  EMA Crossover + ADX (40%)

  14:23 UTC | Regime: TREND_BULL
  ```
- [ ] Command `/signals` — last 5 signals
- [ ] Command `/status` — system state + drawdown
- [ ] Command `/pause` — pause notifications
- [ ] Minimum interval between notifications: 5 minutes (anti-spam)
