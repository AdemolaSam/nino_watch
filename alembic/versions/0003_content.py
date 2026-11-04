"""Content tables: regions, articles, clusters, events, verifications.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "regions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("risk", sa.String(16), nullable=False),
        sa.Column("intensity", sa.Float, nullable=False, server_default="0"),
        sa.Column("center_lat", sa.Float, nullable=False),
        sa.Column("center_lng", sa.Float, nullable=False),
        sa.Column("bbox", JSONB, nullable=False),
        sa.Column("config", JSONB, nullable=False, server_default="{}"),
    )
    op.create_table(
        "articles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("region_id", sa.String(64), sa.ForeignKey("regions.id"), nullable=False),
        sa.Column("url", sa.Text, nullable=False, unique=True),
        sa.Column("url_hash", sa.String(64), nullable=False),
        sa.Column("publisher", sa.String(256), nullable=False),
        sa.Column("ownership_group", sa.String(256), nullable=True),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excerpt", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_articles_region_id", "articles", ["region_id"])
    op.create_index("ix_articles_url_hash", "articles", ["url_hash"])
    op.create_table(
        "clusters",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("region_id", sa.String(64), sa.ForeignKey("regions.id"), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("place_key", sa.String(256), nullable=False),
        sa.Column("date_key", sa.Date, nullable=True),
        sa.Column("canonical_event_id", sa.Integer, nullable=True),
    )
    op.create_index("ix_clusters_region_id", "clusters", ["region_id"])
    op.create_table(
        "events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("article_id", sa.Integer, sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("region_id", sa.String(64), sa.ForeignKey("regions.id"), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("place_name", sa.String(256), nullable=False),
        sa.Column("country", sa.String(128), nullable=True),
        sa.Column("lat", sa.Float, nullable=True),
        sa.Column("lng", sa.Float, nullable=True),
        sa.Column("event_date", sa.Date, nullable=True),
        sa.Column("count", sa.Integer, nullable=True),
        sa.Column("stated_cause", sa.Text, nullable=True),
        sa.Column("evidence_quote", sa.Text, nullable=True),
        sa.Column("extractor_model", sa.String(128), nullable=True),
        sa.Column("prompt_version", sa.String(16), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("cluster_id", sa.Integer, sa.ForeignKey("clusters.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_events_region_id", "events", ["region_id"])
    op.create_table(
        "verifications",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "cluster_id", sa.Integer, sa.ForeignKey("clusters.id"), nullable=False, unique=True
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("independent_outlets", sa.Integer, nullable=False, server_default="0"),
        sa.Column("official_match", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("weather_plausible", sa.Boolean, nullable=True),
        sa.Column("conflict", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("evidence", JSONB, nullable=False, server_default="{}"),
        sa.Column("rule_version", sa.String(16), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_verifications_cluster_id", "verifications", ["cluster_id"])


def downgrade() -> None:
    op.drop_table("verifications")
    op.drop_table("events")
    op.drop_table("clusters")
    op.drop_table("articles")
    op.drop_table("regions")
