"""Add composite indexes for common query patterns.

Revision ID: 002_composite_indexes
Revises: 001_initial
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_composite_indexes"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Composite index on signals(asset, status) — speeds up filtering active signals per asset
    op.create_index(
        "ix_signals_asset_status",
        "signals",
        ["asset", "status"],
    )

    # Composite index on sentiment_data(asset, created_at) — speeds up time-range sentiment lookups
    op.create_index(
        "ix_sentiment_data_asset_created_at",
        "sentiment_data",
        ["asset", "created_at"],
    )

    # Composite index on onchain_events(asset, timestamp) — speeds up time-range on-chain queries
    op.create_index(
        "ix_onchain_events_asset_timestamp",
        "onchain_events",
        ["asset", "timestamp"],
    )

    # Composite index on market_regimes(asset, ended_at) — speeds up finding current/recent regimes
    op.create_index(
        "ix_market_regimes_asset_ended_at",
        "market_regimes",
        ["asset", "ended_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_market_regimes_asset_ended_at", table_name="market_regimes")
    op.drop_index("ix_onchain_events_asset_timestamp", table_name="onchain_events")
    op.drop_index("ix_sentiment_data_asset_created_at", table_name="sentiment_data")
    op.drop_index("ix_signals_asset_status", table_name="signals")
