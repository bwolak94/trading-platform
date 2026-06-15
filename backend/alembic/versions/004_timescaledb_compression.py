"""Enable TimescaleDB compression and data retention on market_data.

Revision ID: 004_timescaledb_compression
Revises: 003_strategy_params
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_timescaledb_compression"
down_revision: Union[str, None] = "003_strategy_params"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable TimescaleDB compression on market_data hypertable
    # Segments by asset so each asset's data is compressed independently,
    # ordered by timestamp descending for optimal query performance
    op.execute(
        """
        ALTER TABLE market_data SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'asset',
            timescaledb.compress_orderby = 'timestamp DESC'
        )
        """
    )

    # Automatically compress chunks older than 30 days
    op.execute(
        "SELECT add_compression_policy('market_data', INTERVAL '30 days')"
    )

    # Automatically drop chunks older than 365 days to manage storage
    op.execute(
        "SELECT add_retention_policy('market_data', INTERVAL '365 days')"
    )


def downgrade() -> None:
    # Remove retention policy first
    op.execute(
        "SELECT remove_retention_policy('market_data')"
    )

    # Remove compression policy
    op.execute(
        "SELECT remove_compression_policy('market_data')"
    )

    # Disable compression on the hypertable
    op.execute(
        "ALTER TABLE market_data SET (timescaledb.compress = false)"
    )
