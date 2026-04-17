"""Create strategy_params table for configurable strategy settings.

Revision ID: 003_strategy_params
Revises: 002_composite_indexes
Create Date: 2026-04-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_strategy_params"
down_revision: Union[str, None] = "002_composite_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "strategy_params",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("strategy_name", sa.String(50), unique=True, nullable=False),
        sa.Column("params", postgresql.JSONB, nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Index on strategy_name for fast lookups (unique constraint already creates one,
    # but being explicit for clarity)
    op.create_index(
        "ix_strategy_params_strategy_name",
        "strategy_params",
        ["strategy_name"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_strategy_params_strategy_name", table_name="strategy_params")
    op.drop_table("strategy_params")
