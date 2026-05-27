"""add crypto baskets and automatic sync audit

Revision ID: 0006_crypto_baskets
Revises: 0005_transaction_time_reviews
Create Date: 2026-05-27 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_crypto_baskets"
down_revision: str | None = "0005_transaction_time_reviews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crypto_baskets",
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
            name=op.f("fk_crypto_baskets_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crypto_baskets")),
        sa.UniqueConstraint("user_id", name="uq_crypto_baskets_user_id"),
    )
    op.create_table(
        "crypto_basket_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("basket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sync_status", sa.String(length=16), server_default="idle", nullable=False),
        sa.Column("last_sync_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_start_time_ms", sa.BigInteger(), nullable=True),
        sa.Column("last_sync_end_time_ms", sa.BigInteger(), nullable=True),
        sa.Column("last_imported", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "last_skipped_duplicates",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "last_positions_created",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "last_open_positions",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "last_closed_positions",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "last_warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "sync_status in ('idle', 'running', 'success', 'error')",
            name="crypto_basket_item_sync_status_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["basket_id"],
            ["crypto_baskets.id"],
            name=op.f("fk_crypto_basket_items_basket_id_crypto_baskets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crypto_basket_items")),
        sa.UniqueConstraint("basket_id", "symbol", name="uq_crypto_basket_items_basket_symbol"),
    )
    op.create_table(
        "crypto_basket_sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("basket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("basket_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("run_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("start_time_ms", sa.BigInteger(), nullable=True),
        sa.Column("end_time_ms", sa.BigInteger(), nullable=True),
        sa.Column("imported", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "skipped_duplicates",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("positions_created", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("open_positions", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("closed_positions", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "run_type in ('manual', 'automatic')",
            name="crypto_basket_sync_run_type_allowed",
        ),
        sa.CheckConstraint(
            "status in ('running', 'success', 'error', 'skipped')",
            name="crypto_basket_sync_run_status_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["basket_id"],
            ["crypto_baskets.id"],
            name=op.f("fk_crypto_basket_sync_runs_basket_id_crypto_baskets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["basket_item_id"],
            ["crypto_basket_items.id"],
            name=op.f("fk_crypto_basket_sync_runs_basket_item_id_crypto_basket_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crypto_basket_sync_runs")),
    )


def downgrade() -> None:
    op.drop_table("crypto_basket_sync_runs")
    op.drop_table("crypto_basket_items")
    op.drop_table("crypto_baskets")
