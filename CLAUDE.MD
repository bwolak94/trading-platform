# CLAUDE.md — Instructions for Claude Code / Cursor AI

## Project Context

You are building **AI Trading Navigator** — a crypto and forex market analysis system that:
- Classifies market regime (trend/consolidation/volatility)
- Generates trading signals with reasoning and confidence score
- Displays them on a web dashboard and sends them via Telegram
- Is NOT an autotrading system — a human always makes the final decision

## Reference Documents (read in this order)

1. `00_PRD.md` — What we are building and for whom
2. `01_ARCHITECTURE.md` — Tech stack and directory structure
3. `02_USER_STORIES.md` — What the system must be able to do (acceptance criteria)
4. `03_DATA_MODELS_API.md` — Database schema and API endpoints
5. `04_AI_ENGINE.md` — How the AI works (algorithms, strategies, scoring)
6. `05_IMPLEMENTATION_TASKS.md` — Specific tasks in order

## How to Use These Documents

### In Claude Code (terminal):
```bash
# Place all .md files in the project directory
# Run Claude Code in the project directory
claude

# Example starter prompts:
"Read CLAUDE.md and the reference documents, then execute TASK-000 from 05_IMPLEMENTATION_TASKS.md"

"Execute TASK-101 — create SQLAlchemy models according to the schema from 03_DATA_MODELS_API.md"

"Execute TASK-302 — implement TrendFollowingStrategy according to the specification from 04_AI_ENGINE.md"
```

### In Cursor:
1. Open the project in Cursor
2. Place .md files in the `docs/` directory
3. Use `@docs/05_IMPLEMENTATION_TASKS.md` in prompts
4. Example: `@docs/04_AI_ENGINE.md implement SignalAggregator from TASK-306`

## Coding Standards

### Backend (Python/FastAPI)
- Use **async/await** everywhere (FastAPI + asyncpg)
- Type hints on all functions
- Pydantic schemas for request/response validation
- Repository pattern for DB access
- Dependency injection for services
- Structured logging (JSON format)
- Every function with a docstring

### Frontend (React/TypeScript)
- Strict TypeScript (no `any`)
- Functional components with hooks
- Zustand for global state
- React Query for server state + caching
- Tailwind utility classes
- Accessibility (ARIA labels on interactive elements)

### General
- No hardcoded secrets — only `os.environ` / `.env`
- Tests for every AI module
- Error handling on all external API calls
- Comments in English (consistently)

## MVP Priorities (what is MUST HAVE)

MUST HAVE:
- Binance OHLCV data fetching
- Feature engineering (technical indicators)
- Market Regime Classifier (at least rule-based to start)
- Trend Following strategy
- Signal Aggregator (simplified — without on-chain at start)
- REST API (/signals, /market/regime)
- Basic React Dashboard (signal cards + regime badges)
- Telegram bot (basic notifications)
- Drawdown kill switch

SHOULD HAVE (but does not block MVP):
- Sentiment NLP (FinBERT)
- On-chain data
- Walk-forward backtesting
- Monte Carlo simulation
- SMC Strategy
- Full backtesting UI

WON'T HAVE (v2+):
- Autotrading / order execution
- Reinforcement Learning
- Mobile app
- Multi-user support

## Troubleshooting

### TimescaleDB not working
```bash
# Make sure the extension is enabled
docker exec -it postgres psql -U user -d trading_ai -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
```

### FinBERT too slow
- Use a smaller model: `yiyanghkust/finbert-tone` instead of the full FinBERT
- Or temporarily replace with VADER sentiment analyzer (pip install vaderSentiment)

### Binance WebSocket disconnects
- Binance WebSocket has a 24h limit — implement auto-reconnect
- Use `listen_key` renewal every 30 minutes for user data streams

### LightGBM — no training data
- First run `backfill_historical_data.py` (create this script)
- Minimum 6 months of OHLCV data before training the model
- At the start, use rule-based regime detection (without ML) as a fallback
