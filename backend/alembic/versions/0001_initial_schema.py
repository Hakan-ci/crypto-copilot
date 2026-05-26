"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-26 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_table(
        "candles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exchange", sa.String(length=16), server_default="MEXC", nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timestamp_s", sa.BigInteger(), nullable=False),
        sa.Column("open", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("high", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("low", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("close", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("volume", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candles")),
        sa.UniqueConstraint(
            "exchange",
            "symbol",
            "timeframe",
            "timestamp_s",
            name="uq_candles_exchange_symbol_timeframe_timestamp",
        ),
    )
    op.create_table(
        "mexc_api_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("access_key_encrypted", sa.Text(), nullable=False),
        sa.Column("secret_key_encrypted", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_mexc_api_credentials_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mexc_api_credentials")),
    )
    op.create_table(
        "raw_mexc_order_deals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mexc_deal_id", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("side", sa.Integer(), nullable=False),
        sa.Column("vol", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("price", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("fee", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("fee_currency", sa.String(length=32), nullable=True),
        sa.Column("profit", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("category", sa.Integer(), nullable=True),
        sa.Column("order_id", sa.String(length=128), nullable=False),
        sa.Column("timestamp_ms", sa.BigInteger(), nullable=False),
        sa.Column("position_mode", sa.Integer(), nullable=True),
        sa.Column("taker", sa.Boolean(), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_raw_mexc_order_deals_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_mexc_order_deals")),
        sa.UniqueConstraint("user_id", "mexc_deal_id", name="uq_raw_mexc_order_deals_user_deal"),
    )
    op.create_table(
        "futures_positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exchange", sa.String(length=16), server_default="MEXC", nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("avg_entry_price", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("avg_exit_price", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("total_volume", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column(
            "realized_pnl",
            sa.Numeric(precision=38, scale=18),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "total_fees",
            sa.Numeric(precision=38, scale=18),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "funding_fees",
            sa.Numeric(precision=38, scale=18),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("leverage", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("raw_source", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "direction in ('long', 'short')",
            name=op.f("ck_futures_positions_direction_allowed"),
        ),
        sa.CheckConstraint(
            "status in ('open', 'closed')",
            name=op.f("ck_futures_positions_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_futures_positions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_futures_positions")),
    )
    op.create_table(
        "indicator_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("rsi_14", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("stoch_rsi_k", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("stoch_rsi_d", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("macd", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("macd_signal", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("macd_histogram", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("supertrend_value", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("supertrend_direction", sa.String(length=16), nullable=True),
        sa.Column("atr_14", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("volume_relative", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("trend_label", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["position_id"],
            ["futures_positions.id"],
            name=op.f("fk_indicator_snapshots_position_id_futures_positions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_indicator_snapshots")),
    )
    op.create_table(
        "ai_trade_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("rule_match_score", sa.Integer(), nullable=True),
        sa.Column("risk_score", sa.Integer(), nullable=True),
        sa.Column("execution_score", sa.Integer(), nullable=True),
        sa.Column(
            "mistake_tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["position_id"],
            ["futures_positions.id"],
            name=op.f("fk_ai_trade_reviews_position_id_futures_positions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_ai_trade_reviews_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_trade_reviews")),
    )


def downgrade() -> None:
    op.drop_table("ai_trade_reviews")
    op.drop_table("indicator_snapshots")
    op.drop_table("futures_positions")
    op.drop_table("raw_mexc_order_deals")
    op.drop_table("mexc_api_credentials")
    op.drop_table("candles")
    op.drop_table("users")
