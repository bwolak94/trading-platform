"""Add MAE, MFE, tags and notes columns to simulated_positions.

Revision ID: 006_mae_mfe_tags
Revises: 005_simulation_and_notifications
Create Date: 2026-04-20 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Revision identifiers
revision = "006_mae_mfe_tags"
down_revision = "005_simulation_and_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add MAE, MFE, tags, and notes columns to simulated_positions."""
    # Maximum Adverse Excursion — worst price during the trade (distance from entry)
    op.add_column(
        "simulated_positions",
        sa.Column(
            "max_adverse_excursion",
            sa.Numeric(precision=10, scale=6),
            nullable=True,
            comment="Maximum Adverse Excursion — worst unrealized loss % during trade",
        ),
    )

    # Maximum Favorable Excursion — best price during the trade
    op.add_column(
        "simulated_positions",
        sa.Column(
            "max_favorable_excursion",
            sa.Numeric(precision=10, scale=6),
            nullable=True,
            comment="Maximum Favorable Excursion — best unrealized profit % during trade",
        ),
    )

    # Tags array for manual trade categorization
    op.add_column(
        "simulated_positions",
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            nullable=True,
            server_default="{}",
            comment="User-defined tags for categorizing trades",
        ),
    )

    # Notes text field for manual trade journaling
    op.add_column(
        "simulated_positions",
        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
            comment="Free-text notes for trade journaling",
        ),
    )


def downgrade() -> None:
    """Remove MAE, MFE, tags, and notes columns from simulated_positions."""
    # -- Destructive: removes trade annotation data --
    op.drop_column("simulated_positions", "notes")
    op.drop_column("simulated_positions", "tags")
    op.drop_column("simulated_positions", "max_favorable_excursion")
    op.drop_column("simulated_positions", "max_adverse_excursion")
