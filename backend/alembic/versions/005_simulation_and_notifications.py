"""Add simulation and notification history tables.

Revision ID: 005_simulation_and_notifications
Revises: 004_timescaledb_compression
Create Date: 2026-04-20 00:00:00.000000

Purpose:
    - Adds simulated_positions table for paper trading positions
    - Adds bot_sessions table for simulation engine run metadata
    - Adds notification_history table for Telegram message logging
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = "005_simulation_and_notifications"
down_revision = "004_timescaledb_compression"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # bot_sessions                                                         #
    # ------------------------------------------------------------------ #
    op.create_table(
        "bot_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("total_trades", sa.Integer(), nullable=False, default=0),
        sa.Column("winning_trades", sa.Integer(), nullable=False, default=0),
        sa.Column("total_pnl_pct", sa.Numeric(precision=10, scale=4), nullable=False, default=0.0),
        sa.Column("max_drawdown_pct", sa.Numeric(precision=10, scale=4), nullable=False, default=0.0),
        sa.Column("sharpe_ratio", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("win_rate", sa.Numeric(precision=6, scale=4), nullable=False, default=0.0),
    )
    op.create_index("ix_bot_sessions_is_active", "bot_sessions", ["is_active"])

    # ------------------------------------------------------------------ #
    # simulated_positions                                                  #
    # ------------------------------------------------------------------ #
    op.create_table(
        "simulated_positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("strategy", sa.String(50), nullable=False),
        sa.Column("regime", sa.String(30), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False, default=0),
        sa.Column("entry_price", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("stop_loss", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("take_profit_1", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("take_profit_2", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("take_profit_3", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("current_price", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("exit_price", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("pnl_pct", sa.Numeric(precision=10, scale=4), nullable=False, default=0.0),
        sa.Column("status", sa.String(20), nullable=False, default="OPEN"),
        sa.Column("exit_reason", sa.String(50), nullable=True),
        sa.Column("factors", postgresql.JSONB(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_simpos_symbol", "simulated_positions", ["symbol"])
    op.create_index("ix_simpos_session_id", "simulated_positions", ["session_id"])
    op.create_index("ix_simpos_status", "simulated_positions", ["status"])
    op.create_index("ix_simpos_symbol_status", "simulated_positions", ["symbol", "status"])
    op.create_index("ix_simpos_opened_at", "simulated_positions", ["opened_at"])

    # ------------------------------------------------------------------ #
    # notification_history                                                 #
    # ------------------------------------------------------------------ #
    op.create_table(
        "notification_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("chat_id", sa.String(50), nullable=False),
        sa.Column("message_type", sa.String(30), nullable=False, default="SIGNAL"),
        sa.Column("asset", sa.String(20), nullable=True),
        sa.Column("direction", sa.String(10), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("strategy", sa.String(50), nullable=True),
        sa.Column("entry_price", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("stop_loss", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("take_profit_1", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=True, default="PENDING"),
        sa.Column("pnl_pct", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("simulated_position_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_notif_chat_id", "notification_history", ["chat_id"])
    op.create_index("ix_notif_asset", "notification_history", ["asset"])
    op.create_index("ix_notif_chat_sent", "notification_history", ["chat_id", "sent_at"])
    op.create_index("ix_notif_asset_outcome", "notification_history", ["asset", "outcome"])


def downgrade() -> None:
    # Drop in reverse order
    op.drop_table("notification_history")
    op.drop_table("simulated_positions")
    op.drop_table("bot_sessions")
