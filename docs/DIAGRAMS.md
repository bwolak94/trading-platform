# Architecture Diagrams

> All diagrams use [Mermaid](https://mermaid.js.org/) syntax. Render in GitHub, GitLab, or the [Mermaid Live Editor](https://mermaid.live).

---

## 1. System Architecture

```mermaid
graph TB
    subgraph External["External Data Sources"]
        BIN["Binance\nWebSocket / REST"]
        NEWS["News Aggregator\n(RSS / scraping)"]
        WHALE["Whale Alert\nAPI"]
        FOREX["Forex Provider\n(real-time rates)"]
        GLASSNODE["Glassnode\nOn-chain"]
    end

    subgraph Backend["Backend — FastAPI (Python 3.12)"]
        direction TB
        FE["FeatureEngineer\n50+ indicators"]
        RC["RegimeClassifier\nRule-based + LightGBM"]
        AGG["SignalAggregator\nWeighted multi-strategy"]
        RISK["RiskEngine\nKelly / Drawdown / CorrelCap"]
        API["REST API\n/api/v1/*"]
        WSM["WebSocket Manager\nChannel-based pub/sub"]
        CELERY["Celery Worker\n+ Beat Scheduler"]
        PAPER["PaperTradingEngine"]
    end

    subgraph AI["AI Engine Modules"]
        direction LR
        STRAT["Strategies\nTrend · SMC · MeanRev\nVolumeBreakout · DualMomentum"]
        SIGS["Signal Modules\nCVD · Wyckoff · Elliott\nLiquidation · OrderFlow · …"]
        LEARN["LearningEngine\nRedis-backed memory"]
        ANAL["Analytics\nBayesian · HMM · Calibrator"]
    end

    subgraph Infra["Infrastructure"]
        PG[("TimescaleDB\nPostgreSQL 16")]
        RD[("Redis 7\nCache · Pub/Sub")]
        OT["OpenTelemetry\nTracing"]
    end

    subgraph Frontend["Frontend — React 18 + Vite 5"]
        DASH["Dashboard\n100+ panels"]
        SC["SignalCard"]
        RI["RegimeIndicator"]
        CHARTS["Lightweight Charts\nRecharts"]
        STORE["Zustand Store\n(persist)"]
        WS_CLIENT["WebSocket Client\n(auto-reconnect)"]
    end

    subgraph Notifications
        TG["Telegram Bot"]
        WH["Webhook\nDispatcher"]
    end

    BIN --> FE
    NEWS --> AGG
    WHALE --> AGG
    FOREX --> FE
    GLASSNODE --> AGG

    FE --> RC
    FE --> STRAT
    STRAT --> AGG
    SIGS --> AGG
    ANAL --> RC
    AGG --> RISK
    RISK --> API
    RISK --> WSM
    RISK --> TG
    RISK --> WH
    PAPER --> LEARN

    API --> PG
    API --> RD
    CELERY --> STRAT
    CELERY --> PAPER
    OT --> API

    WSM -->|"JSON frames"| WS_CLIENT
    API -->|"HTTP/JSON"| DASH
    WS_CLIENT --> STORE
    STORE --> SC
    STORE --> RI
    STORE --> CHARTS
```

---

## 2. Signal Pipeline

```mermaid
flowchart LR
    A["OHLCV\n(Binance)"]
    B["Feature\nEngineer"]
    C{"Regime\nClassifier"}
    D["Strategy\nSuite"]
    E["Signal\nModules"]
    F["Signal\nAggregator"]
    G{"Risk\nEngine"}
    H["Final Signal\ndirection · confidence\nentry · SL · TP1/TP2 · R/R"]
    I["Kill\nSwitch"]

    A --> B
    B --> C
    B --> D
    B --> E
    D --> F
    E --> F
    C -->|"regime label"| F
    F --> G
    G -->|"pass"| H
    G -->|"block"| I
```

---

## 3. Database Schema

```mermaid
erDiagram
    market_data {
        bigserial   id           PK
        varchar     asset
        varchar     timeframe
        timestamptz timestamp
        numeric     open
        numeric     high
        numeric     low
        numeric     close
        numeric     volume
    }

    market_regime {
        bigserial   id           PK
        varchar     asset
        varchar     regime
        float       confidence
        jsonb       probabilities
        timestamptz started_at
        timestamptz updated_at
    }

    signal {
        uuid        id           PK
        varchar     asset
        varchar     direction
        float       confidence
        varchar     regime
        numeric     entry_price
        numeric     stop_loss
        numeric     take_profit_1
        numeric     take_profit_2
        float       risk_reward
        float       position_size_pct
        float       technical_score
        float       onchain_score
        float       sentiment_score
        float       macro_score
        jsonb       factors
        varchar     status
        timestamptz expires_at
        timestamptz created_at
        timestamptz updated_at
    }

    backtest_result {
        uuid        id           PK
        varchar     strategy
        varchar     asset
        varchar     timeframe
        float       total_return_pct
        float       sharpe_ratio
        float       max_drawdown_pct
        int         total_trades
        float       win_rate
        float       profit_factor
        jsonb       equity_curve
        jsonb       params
        timestamptz created_at
    }

    sentiment_data {
        bigserial   id           PK
        varchar     asset
        varchar     source
        float       score
        varchar     raw_text
        timestamptz timestamp
    }

    onchain_event {
        bigserial   id           PK
        varchar     asset
        varchar     event_type
        numeric     amount_usd
        varchar     from_address
        varchar     to_address
        timestamptz timestamp
    }

    user_settings {
        uuid        id           PK
        float       capital
        float       risk_per_trade_pct
        float       max_drawdown_pct
        varchar     telegram_chat_id
        bool        notifications_enabled
        jsonb       enabled_assets
        timestamptz updated_at
    }

    simulation_session {
        uuid        id           PK
        float       initial_capital
        float       current_equity
        float       realized_pnl
        float       unrealized_pnl
        int         total_trades
        int         winning_trades
        timestamptz created_at
        timestamptz updated_at
    }

    market_data      ||--o{  market_regime     : "classifies"
    market_data      ||--o{  signal            : "generates"
    signal           ||--o{  backtest_result   : "validates against"
    simulation_session ||--o{ signal           : "paper-trades"
```

---

## 4. Celery Task Topology

```mermaid
graph LR
    subgraph Beat["Celery Beat (Scheduler)"]
        T1["fetch_ohlcv\nevery 1 min"]
        T2["run_signals\nevery 5 min"]
        T3["daily_briefing\n07:00 UTC daily"]
        T4["weekly_report\nMonday 08:00 UTC"]
    end

    subgraph Workers["Celery Workers"]
        W1["Worker 1\n(concurrency=2)"]
        W2["DLQ Worker\n(failed tasks)"]
    end

    subgraph Queues["Redis Queues"]
        Q1["default"]
        Q2["dlq"]
    end

    T1 --> Q1
    T2 --> Q1
    T3 --> Q1
    T4 --> Q1
    Q1 --> W1
    W1 -->|"max_retries exceeded"| Q2
    Q2 --> W2
```

---

## 5. WebSocket Channel Model

```mermaid
sequenceDiagram
    participant B as Browser
    participant WS as /ws endpoint
    participant M as ConnectionManager
    participant A as TradingAgent

    B->>WS: connect(?token=...)
    WS->>M: connect(websocket)
    B->>WS: {"action":"subscribe","channels":["signals","regime"]}
    WS->>M: subscribe(ws, ["signals","regime"])
    WS-->>B: {"type":"SUBSCRIBED","channels":["signals","regime"]}

    loop Real-time updates
        A->>M: broadcast("signals", signal_payload)
        M-->>B: {"type":"SIGNAL_NEW", "data": {...}}
        A->>M: broadcast("regime", regime_payload)
        M-->>B: {"type":"REGIME_CHANGE", "data": {...}}
    end

    B->>WS: {"action":"unsubscribe","channels":["regime"]}
    WS->>M: unsubscribe(ws, ["regime"])
    B--xWS: disconnect
    WS->>M: disconnect(websocket)
```

---

## 6. Risk Engine Decision Tree

```mermaid
flowchart TD
    S["Candidate Signal"] --> DD{"Drawdown\n> threshold?"}
    DD -->|"Yes — Kill Switch"| BLOCK["BLOCKED\n503 returned"]
    DD -->|"No"| DL{"Daily loss\n> limit?"}
    DL -->|"Yes"| BLOCK
    DL -->|"No"| ST{"Streak\ncircuit breaker?"}
    ST -->|"Yes"| BLOCK
    ST -->|"No"| CORR{"Correlation\ncap exceeded?"}
    CORR -->|"Yes"| BLOCK
    CORR -->|"No"| EV{"EV filter\nEV > 0?"}
    EV -->|"No"| BLOCK
    EV -->|"Yes"| KELLY["Kelly sizing\n+ vol adjustment"]
    KELLY --> PASS["PASS\nSignal published"]
```

---

## 7. CI/CD Pipeline

```mermaid
flowchart LR
    subgraph Trigger
        PR["Pull Request / Push"]
    end

    subgraph Jobs
        direction TB
        BE["Backend Job\npytest · ruff · bandit"]
        FE["Frontend Job\ntsc · eslint · vitest · size-limit"]
        SEC["Security Job\ntrivy · bandit SARIF"]
        LH["Lighthouse CI\n(perf budget)"]
        DOC["Docker Build\n(main branch only)"]
    end

    PR --> BE
    PR --> FE
    PR --> SEC
    FE --> LH
    BE --> DOC
    FE --> DOC
```
