from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Region(Base):
    __tablename__ = "regions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    risk: Mapped[str] = mapped_column(String(16))
    intensity: Mapped[float] = mapped_column(Float, default=0.0)
    center_lat: Mapped[float] = mapped_column(Float)
    center_lng: Mapped[float] = mapped_column(Float)
    bbox: Mapped[list] = mapped_column(JSONB)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region_id: Mapped[str] = mapped_column(ForeignKey("regions.id"), index=True)
    url: Mapped[str] = mapped_column(Text, unique=True)
    url_hash: Mapped[str] = mapped_column(String(64), index=True)
    publisher: Mapped[str] = mapped_column(String(256))
    ownership_group: Mapped[str | None] = mapped_column(String(256), nullable=True)
    language: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    excerpt: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    extracted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class GeoName(Base):
    """Local gazetteer: GeoNames cities500 import plus hand-seeded pilot cities.

    Real rows use GeoNames geonameids; hand seeds use negative ids.
    """

    __tablename__ = "geonames"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(256), index=True)
    asciiname: Mapped[str] = mapped_column(String(256), index=True)
    country: Mapped[str] = mapped_column(String(2), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    population: Mapped[int] = mapped_column(Integer, default=0)


class Cluster(Base):
    __tablename__ = "clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region_id: Mapped[str] = mapped_column(ForeignKey("regions.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    place_key: Mapped[str] = mapped_column(String(256))
    date_key: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Plain int, no DB-level FK: clusters and events reference each other.
    canonical_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"))
    region_id: Mapped[str] = mapped_column(ForeignKey("regions.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    place_name: Mapped[str] = mapped_column(String(256))
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stated_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    extractor_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    cluster_id: Mapped[int | None] = mapped_column(ForeignKey("clusters.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Verification(Base):
    __tablename__ = "verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("clusters.id"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16))
    independent_outlets: Mapped[int] = mapped_column(Integer, default=0)
    official_match: Mapped[bool] = mapped_column(default=False)
    weather_plausible: Mapped[bool | None] = mapped_column(nullable=True)
    conflict: Mapped[bool] = mapped_column(default=False)
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)
    rule_version: Mapped[str] = mapped_column(String(16))
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ClimateCell(Base):
    __tablename__ = "climate_cells"

    region_id: Mapped[str] = mapped_column(ForeignKey("regions.id"), primary_key=True)
    lat: Mapped[float] = mapped_column(Float, primary_key=True)
    lng: Mapped[float] = mapped_column(Float, primary_key=True)
    temp_c: Mapped[float] = mapped_column(Float)
    baseline_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    anomaly_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Advisory(Base):
    __tablename__ = "advisories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region_id: Mapped[str] = mapped_column(ForeignKey("regions.id"), index=True)
    lang: Mapped[str] = mapped_column(String(16), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    content_hash: Mapped[str] = mapped_column(String(64))
    happening: Mapped[str] = mapped_column(Text)
    at_risk: Mapped[str] = mapped_column(Text)
    actions: Mapped[str] = mapped_column(Text)
    source_cluster_ids: Mapped[list] = mapped_column(JSONB, default=list)
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(32))
    reviewed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OutletPack(Base):
    __tablename__ = "outlet_packs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    advisory_id: Mapped[int] = mapped_column(ForeignKey("advisories.id"), unique=True)
    lang: Mapped[str] = mapped_column(String(16))
    radio_script: Mapped[str] = mapped_column(Text)
    sms: Mapped[str] = mapped_column(Text)
    sms_segments: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CommunityReport(Base):
    __tablename__ = "community_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region_id: Mapped[str] = mapped_column(ForeignKey("regions.id"), index=True)
    cluster_id: Mapped[int | None] = mapped_column(ForeignKey("clusters.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32))
    place_name: Mapped[str] = mapped_column(String(256))
    occurred_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LlmCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit: Mapped[bool] = mapped_column(default=False)
    cost_estimate: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
