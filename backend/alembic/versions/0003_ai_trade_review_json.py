"""add ai trade review json

Revision ID: 0003_ai_trade_review_json
Revises: 0002_indicator_snapshot_unique
Create Date: 2026-05-26 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_ai_trade_review_json"
down_revision: str | None = "0002_indicator_snapshot_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_trade_reviews",
        sa.Column(
            "review_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("ai_trade_reviews", "review_json")
