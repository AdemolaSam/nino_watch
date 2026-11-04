"""Community evidence is displayed after review but never changes verification labels."""

import secrets
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import CamelModel
from app.core.config import settings
from app.core.db import get_session
from app.repos.models import Cluster, CommunityReport, Region

router = APIRouter()


class ReportInput(CamelModel):
    region_id: str
    incident_id: int | None = None
    kind: str = Field(pattern="^(heat|flood|drought|wildfire|disease|crop|other)$")
    place_name: str = Field(min_length=2, max_length=256)
    occurred_at: date | None = None
    description: str = Field(min_length=20, max_length=2000)
    source_url: HttpUrl | None = None


class ReviewInput(CamelModel):
    decision: str = Field(pattern="^(approved|rejected)$")


def report_body(row: CommunityReport) -> dict:
    return {
        "id": row.id,
        "regionId": row.region_id,
        "incidentId": str(row.cluster_id) if row.cluster_id is not None else None,
        "kind": row.kind,
        "placeName": row.place_name,
        "occurredAt": row.occurred_at,
        "description": row.description,
        "sourceUrl": row.source_url,
        "status": row.status,
        "createdAt": row.created_at,
    }


def require_admin(authorization: str | None = Header(default=None)) -> None:
    if not settings.admin_token:
        raise HTTPException(status_code=503, detail="review token not configured")
    expected = f"Bearer {settings.admin_token}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="admin token required")


@router.post("/reports", status_code=201)
async def submit_report(payload: ReportInput, session: AsyncSession = Depends(get_session)) -> dict:
    if await session.get(Region, payload.region_id) is None:
        raise HTTPException(status_code=404, detail="unknown region")
    if payload.incident_id is not None:
        cluster = await session.get(Cluster, payload.incident_id)
        if cluster is None or cluster.region_id != payload.region_id:
            raise HTTPException(status_code=404, detail="incident not found in region")
    row = CommunityReport(
        region_id=payload.region_id,
        cluster_id=payload.incident_id,
        kind=payload.kind,
        place_name=payload.place_name.strip(),
        occurred_at=payload.occurred_at,
        description=payload.description.strip(),
        source_url=str(payload.source_url) if payload.source_url else None,
        status="pending",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return {"id": row.id, "status": row.status}


@router.get("/reports")
async def list_reports(
    regionId: str | None = None, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    query = select(CommunityReport).where(CommunityReport.status == "approved")
    if regionId:
        query = query.where(CommunityReport.region_id == regionId)
    rows = await session.scalars(query.order_by(CommunityReport.created_at.desc()).limit(100))
    return [report_body(row) for row in rows]


@router.get("/admin/reports", dependencies=[Depends(require_admin)])
async def pending_reports(session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = await session.scalars(
        select(CommunityReport).where(CommunityReport.status == "pending")
        .order_by(CommunityReport.created_at).limit(100)
    )
    return [report_body(row) for row in rows]


@router.post("/admin/reports/{report_id}/review", dependencies=[Depends(require_admin)])
async def review_report(
    report_id: int, payload: ReviewInput, session: AsyncSession = Depends(get_session)
) -> dict:
    row = await session.get(CommunityReport, report_id)
    if row is None:
        raise HTTPException(status_code=404, detail="report not found")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="report already reviewed")
    row.status = payload.decision
    row.reviewed_at = datetime.now(UTC)
    await session.commit()
    return {"id": row.id, "status": row.status}
