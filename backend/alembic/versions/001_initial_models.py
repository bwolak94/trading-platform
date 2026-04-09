"""Initial database models.

Revision ID: 001_initial
Revises:
Create Date: 2026-04-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # TimescaleDB extension
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")

    # market_data
    op.create_table(
        "market_data",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("asset", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(5), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(20, 8), nullable=False),
        sa.Column("high", sa.Numeric(20, 8), nullable=False),
        sa.Column("low", sa.Numeric(20, 8), nullable=False),
        sa.Column("close", sa.Numeric(20, 8), nullable=False),
        sa.Column("volume", sa.Numeric(20, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_market_data_asset_tf_ts",
        "market_data",
        ["asset", "timeframe", sa.text("timestamp DESC")],
    )
    # Convert to TimescaleDB hypertable
    op.execute("SELECT create_hypertable('market_data', 'timestamp', migrate_data => true)")

    # market_regimes
    op.create_table(
        "market_regimes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("asset", sa.String(20), nullable=False),
        sa.Column("regime", sa.String(30), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # signals
    op.create_table(
        "signals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("asset", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False),
        sa.Column("regime", sa.String(30), nullable=False),
        sa.Column("entry_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("stop_loss", sa.Numeric(20, 8), nullable=True),
        sa.Column("take_profit_1", sa.Numeric(20, 8), nullable=True),
        sa.Column("take_profit_2", sa.Numeric(20, 8), nullable=True),
        sa.Column("risk_reward", sa.Numeric(5, 2), nullable=True),
        sa.Column("position_size_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("technical_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("onchain_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("sentiment_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("macro_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("factors", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(20), server_default="ACTIVE"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    # onchain_events
    op.create_table(
        "onchain_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("asset", sa.String(20), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("amount_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("from_address", sa.String(100), nullable=True),
        sa.Column("to_address", sa.String(100), nullable=True),
        sa.Column("direction", sa.String(10), nullable=True),
        sa.Column("source", sa.String(30), nullable=True),
        sa.Column("raw_data", postgresql.JSONB(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    # sentiment_data
    op.create_table(
        "sentiment_data",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("asset", sa.String(20), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("score", sa.Numeric(5, 4), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    # backtest_results
    op.create_table(
        "backtest_results",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("strategy_name", sa.String(50), nullable=False),
        sa.Column("asset", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(5), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("win_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("profit_factor", sa.Numeric(8, 4), nullable=True),
        sa.Column("max_drawdown", sa.Numeric(5, 2), nullable=True),
        sa.Column("sharpe_ratio", sa.Numeric(8, 4), nullable=True),
        sa.Column("calmar_ratio", sa.Numeric(8, 4), nullable=True),
        sa.Column("total_trades", sa.Integer(), nullable=True),
        sa.Column("prob_ruin_20pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("prob_ruin_30pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("equity_curve", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    # user_settings
    op.create_table(
        "user_settings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(100), nullable=False, unique=True),
        sa.Column("capital", sa.Numeric(20, 2), nullable=True),
        sa.Column("risk_per_trade_pct", sa.Numeric(5, 2), server_default="1.5"),
        sa.Column("max_drawdown_pct", sa.Numeric(5, 2), server_default="10.0"),
        sa.Column("telegram_chat_id", sa.String(50), nullable=True),
        sa.Column(
            "enabled_assets",
            postgresql.JSONB(),
            server_default='["BTC/USDT","ETH/USDT"]',
        ),
        sa.Column("system_status", sa.String(20), server_default="ACTIVE"),
        sa.Column("notifications_enabled", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("user_settings")
    op.drop_table("backtest_results")
    op.drop_table("sentiment_data")
    op.drop_table("onchain_events")
    op.drop_table("signals")
    op.drop_table("market_regimes")
    op.drop_index("ix_market_data_asset_tf_ts", table_name="market_data")
    op.drop_table("market_data")
