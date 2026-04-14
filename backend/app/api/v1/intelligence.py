"""Market Intelligence API — news, sentiment, whale tracking."""

from fastapi import APIRouter

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get("/news")
async def get_news(limit: int = 50) -> dict:
    from app.data.fetchers.news_aggregator import get_news_aggregator
    agg = get_news_aggregator()
    return {"news": agg.get_news(limit)}


@router.get("/sentiment")
async def get_sentiment_snapshot() -> dict:
    from app.data.fetchers.news_aggregator import get_news_aggregator
    return get_news_aggregator().get_sentiment_snapshot()


@router.get("/whales")
async def get_whale_data() -> dict:
    from app.data.fetchers.whale_tracker import get_whale_tracker
    return get_whale_tracker().get_data()


@router.get("/status")
async def get_intelligence_status() -> dict:
    from app.data.fetchers.news_aggregator import get_news_aggregator
    from app.data.fetchers.whale_tracker import get_whale_tracker
    return {
        "news": get_news_aggregator().get_status(),
        "whales": get_whale_tracker().get_status(),
    }


@router.post("/clear-emergency")
async def clear_emergency() -> dict:
    from app.data.fetchers.news_aggregator import get_news_aggregator
    get_news_aggregator().clear_emergency()
    return {"status": "cleared"}
