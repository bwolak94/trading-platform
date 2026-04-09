# System Architecture: AI Trading Navigator

## High-Level Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    DATA INGESTION LAYER                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Market Data  │  │  On-Chain    │  │   Sentiment      │  │
│  │ (OHLCV)      │  │  (Glassnode) │  │  (Twitter/NLP)   │  │
│  │ Binance API  │  │  Whale Alert │  │  Reddit API      │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
└─────────┼─────────────────┼───────────────────┼────────────┘
          │                 │                   │
          ▼                 ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    DATA PIPELINE                             │
│  Redis Streams / Kafka (event queue)                        │
│  PostgreSQL (historical) + TimescaleDB (time-series)        │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    AI ENGINE                                 │
│  ┌───────────────────┐    ┌──────────────────────────────┐  │
│  │  Market Regime    │    │   Strategy Selector          │  │
│  │  Classifier       │───▶│   (Library-based MVP)        │  │
│  │  (ML Model)       │    │   - Trend Following          │  │
│  └───────────────────┘    │   - Mean Reversion           │  │
│                           │   - Breakout Detection       │  │
│  ┌───────────────────┐    └──────────────────────────────┘  │
│  │  Risk Engine      │                                      │
│  │  - Drawdown Kill  │    ┌──────────────────────────────┐  │
│  │  - Position Size  │    │   Signal Aggregator          │  │
│  │  - Monte Carlo    │    │   (Weighted scoring)         │  │
│  └───────────────────┘    └──────────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    DELIVERY LAYER                            │
│  ┌──────────────────┐    ┌───────────────────────────────┐  │
│  │  REST API        │    │  WebSocket Server             │  │
│  │  (FastAPI)       │    │  (Real-time updates)          │  │
│  └──────────────────┘    └───────────────────────────────┘  │
│  ┌──────────────────┐    ┌───────────────────────────────┐  │
│  │  Telegram Bot    │    │  Web Dashboard (React)        │  │
│  └──────────────────┘    └───────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Technology Stack

### Backend
| Component | Technology | Rationale |
|-----------|-----------|-----------|
| API Server | FastAPI (Python) | Async, fast, great for ML |
| Task Queue | Celery + Redis | Scheduled data fetching |
| Database | PostgreSQL + TimescaleDB | Time-series optimized |
| Cache | Redis | Hot data, signal cache |
| ML/AI | scikit-learn + LightGBM | MVP; swappable for torch |
| NLP Sentiment | transformers (HuggingFace) | FinBERT model |

### Frontend
| Component | Technology |
|-----------|-----------|
| Framework | React + TypeScript |
| Charts | TradingView Lightweight Charts |
| State | Zustand |
| Real-time | WebSocket (native) |
| Styling | Tailwind CSS |

### Infrastructure
| Component | Technology |
|-----------|-----------|
| Containerization | Docker + docker-compose |
| Deploy | VPS / Railway / Render |
| Monitoring | Grafana + Prometheus |
| Logging | Structured JSON logs |

## Project Directory Structure

```
trading-ai-navigator/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI routes
│   │   ├── core/             # Config, security
│   │   ├── data/
│   │   │   ├── fetchers/     # Binance, Glassnode, Twitter
│   │   │   └── processors/   # Normalization, feature engineering
│   │   ├── ai/
│   │   │   ├── regime/       # Market regime classifier
│   │   │   ├── strategies/   # Strategy library
│   │   │   ├── signals/      # Signal aggregation
│   │   │   └── risk/         # Risk engine
│   │   ├── backtesting/      # Walk-forward, Monte Carlo
│   │   ├── notifications/    # Telegram bot
│   │   └── models/           # DB models (SQLAlchemy)
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Dashboard/
│   │   │   ├── SignalCard/
│   │   │   ├── RegimeIndicator/
│   │   │   └── RiskPanel/
│   │   ├── hooks/
│   │   ├── store/
│   │   └── types/
│   └── package.json
├── docker-compose.yml
├── .env.example
└── docs/
```
