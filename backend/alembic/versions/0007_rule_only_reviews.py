"""add rule only review metadata

Revision ID: 0007_rule_only_reviews
Revises: 0006_crypto_baskets
Create Date: 2026-05-28 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_rule_only_reviews"
down_revision: str | None = "0006_crypto_baskets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "indicator_snapshots",
        sa.Column(
            "candlestick_patterns",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_table(
        "position_trade_metadata",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("planned_stop_loss_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            ["position_id"],
            ["futures_positions.id"],
            name=op.f("fk_position_trade_metadata_position_id_futures_positions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_position_trade_metadata")),
        sa.UniqueConstraint("position_id", name="uq_position_trade_metadata_position_id"),
    )


def downgrade() -> None:
    op.drop_table("position_trade_metadata")
    op.drop_column("indicator_snapshots", "candlestick_patterns")
