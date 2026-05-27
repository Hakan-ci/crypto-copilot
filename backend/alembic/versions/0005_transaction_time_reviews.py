"""add transaction time review context and ai qna

Revision ID: 0005_transaction_time_reviews
Revises: 0004_trading_plans
Create Date: 2026-05-27 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_transaction_time_reviews"
down_revision: str | None = "0004_trading_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "indicator_snapshots",
        sa.Column(
            "anchor",
            sa.String(length=16),
            server_default="entry",
            nullable=False,
        ),
    )
    op.drop_constraint(
        "uq_indicator_snapshots_position_timeframe",
        "indicator_snapshots",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_indicator_snapshots_position_timeframe_anchor",
        "indicator_snapshots",
        ["position_id", "timeframe", "anchor"],
    )

    op.create_table(
        "futures_position_deals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_mexc_order_deal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["position_id"],
            ["futures_positions.id"],
            name=op.f("fk_futures_position_deals_position_id_futures_positions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["raw_mexc_order_deal_id"],
            ["raw_mexc_order_deals.id"],
            name="fk_futures_position_deals_raw_deal",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_futures_position_deals")),
        sa.UniqueConstraint(
            "position_id",
            "raw_mexc_order_deal_id",
            name="uq_futures_position_deals_position_raw_deal",
        ),
    )
    op.create_table(
        "ai_trade_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column(
            "context_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["position_id"],
            ["futures_positions.id"],
            name=op.f("fk_ai_trade_questions_position_id_futures_positions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_ai_trade_questions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_trade_questions")),
    )


def downgrade() -> None:
    op.drop_table("ai_trade_questions")
    op.drop_table("futures_position_deals")
    op.drop_constraint(
        "uq_indicator_snapshots_position_timeframe_anchor",
        "indicator_snapshots",
        type_="unique",
    )
    op.execute("delete from indicator_snapshots where anchor <> 'entry'")
    op.create_unique_constraint(
        "uq_indicator_snapshots_position_timeframe",
        "indicator_snapshots",
        ["position_id", "timeframe"],
    )
    op.drop_column("indicator_snapshots", "anchor")
