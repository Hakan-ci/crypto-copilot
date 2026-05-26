"""add indicator snapshot position timeframe unique constraint

Revision ID: 0002_indicator_snapshot_unique
Revises: 0001_initial_schema
Create Date: 2026-05-26 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0002_indicator_snapshot_unique"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_indicator_snapshots_position_timeframe",
        "indicator_snapshots",
        ["position_id", "timeframe"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_indicator_snapshots_position_timeframe",
        "indicator_snapshots",
        type_="unique",
    )
