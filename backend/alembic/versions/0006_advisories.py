"""Advisories table (English source + per-language translations).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "advisories",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("region_id", sa.String(64), sa.ForeignKey("regions.id"), nullable=False),
        sa.Column("lang", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("happening", sa.Text, nullable=False),
        sa.Column("at_risk", sa.Text, nullable=False),
        sa.Column("actions", sa.Text, nullable=False),
        sa.Column("source_cluster_ids", JSONB, nullable=False, server_default="[]"),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("reviewed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_advisories_region_id", "advisories", ["region_id"])
    op.create_index("ix_advisories_lang", "advisories", ["lang"])


def downgrade() -> None:
    op.drop_table("advisories")
