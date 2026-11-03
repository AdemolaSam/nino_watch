"""Extraction bookkeeping on articles + local gazetteer table.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-01

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("articles", sa.Column("extraction_error", sa.Text, nullable=True))
    op.create_table(
        "geonames",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("name", sa.String(256), nullable=False, index=True),
        sa.Column("asciiname", sa.String(256), nullable=False, index=True),
        sa.Column("country", sa.String(2), nullable=False, index=True),
        sa.Column("lat", sa.Float, nullable=False),
        sa.Column("lng", sa.Float, nullable=False),
        sa.Column("population", sa.Integer, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("geonames")
    op.drop_column("articles", "extraction_error")
    op.drop_column("articles", "extracted_at")
