"""Climate grid cache table.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-01

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "climate_cells",
        sa.Column("region_id", sa.String(64), sa.ForeignKey("regions.id"), primary_key=True),
        sa.Column("lat", sa.Float, primary_key=True),
        sa.Column("lng", sa.Float, primary_key=True),
        sa.Column("temp_c", sa.Float, nullable=False),
        sa.Column("baseline_c", sa.Float, nullable=True),
        sa.Column("anomaly_c", sa.Float, nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("climate_cells")
