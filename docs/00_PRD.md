# PRD: AI Trading Navigator System
**Version:** 1.0 MVP
**Status:** Ready for Implementation
**System type:** Navigator (AI suggests -> human clicks, not autotrading)

---

## 1. Product Goal

Build an AI system that acts like an **experienced analyst sitting next to the trader** — it does not replace decisions, but provides an informational edge impossible to achieve manually.

**Core promise:** Instead of 100 indicators — one specific message with reasoning and a confidence level.

---

## 2. User Persona

### Primary: Swing Trader / Semi-Active Day Trader
- **Experience:** 3-15 years in the market (crypto + forex)
- **Sessions:** 1-3 analyses per day, does not sit in front of the screen 24/7
- **Pain point:** Spends hours on analysis, then still does not know if the market is in a trend or consolidation
- **Goal:** Wants to know *when* to enter, *why*, and what the *actual risk* is
- **Tech-savvy:** Uses TradingView, knows the basics; is not a programmer

### Secondary: Experienced Day Trader (scalper)
- Needs fast notifications (Telegram/Discord)
- Digs into details — wants to see the signal's contributing factors

---

## 3. MVP Scope

### IN SCOPE
- Analysis of 3-5 crypto pairs (BTC, ETH, SOL) + 2 forex pairs (EUR/USD, GBP/USD)
- Web dashboard with signals
- Telegram notifications
- Market regime detection
- Walk-forward backtesting
- Risk management (drawdown kill switch)

### OUT OF SCOPE (v2+)
- Autotrading / automatic execution
- Custom broker integration
- Reinforcement Learning (too early for MVP)
- Native mobile app

---

## 4. Key Success Metrics

| Metric | MVP Target |
|--------|------------|
| Signal accuracy (backtested) | >55% win rate |
| System max drawdown | <15% |
| Signal latency | <30 seconds from event |
| Dashboard load time | <2 seconds |
| System availability | >99% uptime |

---

## 5. Non-Functional Requirements

- **Security:** API keys server-side only, zero exposure in frontend
- **Scalability:** Event-driven architecture (prepared for more pairs)
- **Auditability:** Every signal must have logged reasoning (why the AI decided so)
- **Determinism:** Same input -> same output (no randomness in production)
