"""Community reports and review status.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "community_reports",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("region_id", sa.String(64), sa.ForeignKey("regions.id"), nullable=False),
        sa.Column("cluster_id", sa.Integer, sa.ForeignKey("clusters.id"), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("place_name", sa.String(256), nullable=False),
        sa.Column("occurred_at", sa.Date, nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_community_reports_region_id", "community_reports", ["region_id"])
    op.create_index("ix_community_reports_status", "community_reports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_community_reports_status", table_name="community_reports")
    op.drop_index("ix_community_reports_region_id", table_name="community_reports")
    op.drop_table("community_reports")
