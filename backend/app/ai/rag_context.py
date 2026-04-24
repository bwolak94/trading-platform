"""RAG-powered contextual signal enrichment.

When explaining a signal, fetches live context:
- Recent news headlines for the asset
- Recent whale movements
- Recent on-chain events
- Macro calendar events

Then provides this context to Claude for grounded explanations.
"""

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


async def fetch_signal_context(asset: str, direction: str) -> dict[str, Any]:
    """Fetch live context for signal explanation.

    Attempts to pull data from available fetchers (news aggregator, whale tracker).
    Gracefully handles missing / uninitialised fetchers and returns an empty context
    for each component that fails.

    Args:
        asset: Asset symbol (e.g. "BTCUSDT").
        direction: Signal direction ("LONG" or "SHORT").

    Returns:
        {
            "news": [{"headline": str, "sentiment": str, "source": str}],
            "whale_activity": [{"event": str, "amount_usd": float}],
            "macro_events": [{"event": str, "impact": str, "date": str}],
            "funding_rate": float,
            "fear_greed_index": int,
        }
    """
    context: dict[str, Any] = {
        "news": [],
        "whale_activity": [],
        "macro_events": [],
        "funding_rate": 0.0,
        "fear_greed_index": 50,
    }

    asset_base = asset.replace("USDT", "").replace("USD", "").replace("BUSD", "")

    # --- News headlines ---
    try:
        from app.data.fetchers.news_aggregator import get_news_aggregator

        aggregator = get_news_aggregator()
        news_items: list[dict[str, Any]] = getattr(aggregator, "_latest_news", [])
        context["news"] = [
            {
                "headline": n.get("title", ""),
                "sentiment": n.get("sentiment", "neutral"),
                "source": n.get("source", ""),
            }
            for n in news_items[:10]
            if asset_base.lower() in n.get("title", "").lower()
        ][:3]
    except Exception as exc:
        logger.debug("Could not fetch news context: %s", exc)

    # --- Whale activity ---
    try:
        from app.data.fetchers.whale_tracker import get_whale_tracker

        tracker = get_whale_tracker()
        events: list[Any] = getattr(tracker, "_recent_events", [])
        # Normalise to a consistent dict shape
        normalised: list[dict[str, Any]] = []
        for e in events[:5]:
            if isinstance(e, dict):
                normalised.append(
                    {
                        "event": e.get("event", str(e)),
                        "amount_usd": float(e.get("amount_usd", 0)),
                    }
                )
            else:
                normalised.append({"event": str(e), "amount_usd": 0.0})
        context["whale_activity"] = normalised[:3]
    except Exception as exc:
        logger.debug("Could not fetch whale context: %s", exc)

    # --- Funding rate ---
    try:
        from app.ai.market.funding_regime import get_funding_regime

        regime_data = await get_funding_regime(symbols=[asset])
        rates: dict[str, float] = regime_data.get("funding_rates", {})
        context["funding_rate"] = float(rates.get(asset, 0.0))
    except Exception as exc:
        logger.debug("Could not fetch funding rate: %s", exc)

    # --- Fear & Greed ---
    try:
        from app.ai.market.fear_greed_signal import get_contrarian_signal

        fg_data = await get_contrarian_signal()
        context["fear_greed_index"] = int(fg_data.get("index", 50))
    except Exception as exc:
        logger.debug("Could not fetch fear/greed index: %s", exc)

    return context


async def build_rag_explanation_prompt(signal: dict[str, Any], context: dict[str, Any]) -> str:
    """Build a RAG-enhanced prompt for Claude signal explanation.

    Combines signal data with live context to create a grounded prompt
    that can be sent directly to Claude (or any LLM).

    Args:
        signal: Signal dictionary with keys: asset, direction, confidence,
                strategy_name, entry_price, stop_loss, take_profit_1, factors.
        context: Context dict as returned by :func:`fetch_signal_context`.

    Returns:
        Prompt string ready to be sent to a language model.
    """
    asset = signal.get("asset", "")
    direction = signal.get("direction", "")
    confidence = signal.get("confidence", 0)

    # Build context section
    context_parts: list[str] = []

    if context.get("news"):
        news_text = "\n".join(
            f"- {n['headline']} ({n['sentiment']})" for n in context["news"]
        )
        context_parts.append(f"Recent news:\n{news_text}")

    if context.get("whale_activity"):
        whale_text = "\n".join(
            f"- {w['event']}" + (f" (~${w['amount_usd']:,.0f})" if w.get("amount_usd") else "")
            for w in context["whale_activity"]
        )
        context_parts.append(f"Whale activity:\n{whale_text}")

    funding_rate = context.get("funding_rate", 0.0)
    if funding_rate:
        fr_pct = funding_rate * 100
        fr_desc = "positive (longs pay)" if funding_rate > 0 else "negative (shorts pay)"
        context_parts.append(f"Funding rate: {fr_pct:.4f}% per 8h ({fr_desc})")

    fg_index = context.get("fear_greed_index", 50)
    fg_label = (
        "Extreme Fear" if fg_index < 20
        else "Fear" if fg_index < 40
        else "Neutral" if fg_index < 60
        else "Greed" if fg_index < 80
        else "Extreme Greed"
    )
    context_parts.append(f"Fear & Greed Index: {fg_index} ({fg_label})")

    context_section = "\n\n".join(context_parts) if context_parts else "No recent context available."

    prompt = f"""Analyze this trading signal with the following live market context:

Signal: {direction} {asset} | Confidence: {confidence}%
Strategy: {signal.get('strategy_name', 'Unknown')}
Entry: {signal.get('entry_price', 'N/A')} | SL: {signal.get('stop_loss', 'N/A')} | TP: {signal.get('take_profit_1', 'N/A')}
Technical factors: {signal.get('factors', {})}

Live Context:
{context_section}

Provide a step-by-step chain-of-thought explanation:
1. What technical signals triggered this?
2. How does the market context support or contradict this signal?
3. Key risks to watch for
4. Overall assessment in 2 sentences

Be concise, grounded in the provided context, and avoid speculation."""

    return prompt
