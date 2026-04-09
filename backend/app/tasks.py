"""Celery task definitions and configuration."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "trading_ai",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "fetch-market-data": {
            "task": "app.tasks.fetch_market_data",
            "schedule": 60.0,  # every 1 minute
        },
        "analyze-sentiment": {
            "task": "app.tasks.analyze_sentiment",
            "schedule": 900.0,  # every 15 minutes
        },
        "fetch-onchain": {
            "task": "app.tasks.fetch_onchain",
            "schedule": 60.0,  # every 60 seconds
        },
        "run-signal-pipeline": {
            "task": "app.tasks.run_signal_pipeline",
            "schedule": 300.0,  # every 5 minutes
        },
        "check-signal-status": {
            "task": "app.tasks.check_signal_status",
            "schedule": 900.0,  # every 15 minutes
        },
    },
)


@celery_app.task
def fetch_market_data():
    """Fetch OHLCV data from Binance."""
    # TODO: Implement in TASK-201
    pass


@celery_app.task
def analyze_sentiment():
    """Run sentiment analysis on social media data."""
    # TODO: Implement in TASK-203
    pass


@celery_app.task
def fetch_onchain():
    """Fetch on-chain whale activity data."""
    # TODO: Implement in TASK-204
    pass


@celery_app.task
def run_signal_pipeline():
    """Run the full signal generation pipeline."""
    # TODO: Implement in TASK-306
    pass


@celery_app.task
def check_signal_status():
    """Check if active signals hit TP/SL levels."""
    # TODO: Implement in TASK-307
    pass
