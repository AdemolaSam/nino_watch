from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import RegionResponse
from app.core.db import get_session
from app.services import regions as regions_service

router = APIRouter()


@router.get("/regions", response_model=list[RegionResponse])
async def list_regions(session: AsyncSession = Depends(get_session)) -> list[RegionResponse]:
    return await regions_service.list_region_responses(session)


@router.get("/regions/{region_id}", response_model=RegionResponse)
async def get_region(
    region_id: str, session: AsyncSession = Depends(get_session)
) -> RegionResponse:
    region = await regions_service.get_region_response(session, region_id)
    if region is None:
        raise HTTPException(status_code=404, detail=f"unknown region {region_id!r}")
    return region
