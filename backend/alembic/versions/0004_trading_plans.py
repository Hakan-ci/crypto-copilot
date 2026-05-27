"""add itemized trading plans

Revision ID: 0004_trading_plans
Revises: 0003_ai_trade_review_json
Create Date: 2026-05-27 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_trading_plans"
down_revision: str | None = "0003_ai_trade_review_json"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trading_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_trading_plans_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trading_plans")),
        sa.UniqueConstraint("user_id", name="uq_trading_plans_user_id"),
    )
    op.create_table(
        "trading_plan_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trading_plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("rule_type", sa.String(length=64), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["trading_plan_id"],
            ["trading_plans.id"],
            name=op.f("fk_trading_plan_items_trading_plan_id_trading_plans"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trading_plan_items")),
        sa.UniqueConstraint(
            "trading_plan_id",
            "sort_order",
            name="uq_trading_plan_items_plan_sort_order",
        ),
    )


def downgrade() -> None:
    op.drop_table("trading_plan_items")
    op.drop_table("trading_plans")
