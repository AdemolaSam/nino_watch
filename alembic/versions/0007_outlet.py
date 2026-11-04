"""Broadcaster packs table.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outlet_packs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "advisory_id", sa.Integer, sa.ForeignKey("advisories.id"),
            nullable=False, unique=True,
        ),
        sa.Column("lang", sa.String(16), nullable=False),
        sa.Column("radio_script", sa.Text, nullable=False),
        sa.Column("sms", sa.Text, nullable=False),
        sa.Column("sms_segments", sa.Integer, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("outlet_packs")
