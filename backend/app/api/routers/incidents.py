from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import IncidentResponse
from app.core.db import get_session
from app.repos import regions as regions_repo
from app.services import incidents as incidents_service

router = APIRouter()


@router.get("/incidents", response_model=list[IncidentResponse])
async def list_incidents(
    regionId: str, session: AsyncSession = Depends(get_session)
) -> list[IncidentResponse]:
    if await regions_repo.get_region(session, regionId) is None:
        raise HTTPException(status_code=404, detail=f"unknown region {regionId!r}")
    return await incidents_service.list_incident_responses(session, regionId)
