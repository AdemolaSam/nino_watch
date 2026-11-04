from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ClimateCellResponse, ClimateResponse
from app.core.db import get_session
from app.repos import climate as climate_repo
from app.repos import regions as regions_repo
from app.services.weather import GRID_COLS, grid_for_bbox

router = APIRouter()


@router.get("/regions/{region_id}/climate", response_model=ClimateResponse)
async def get_climate(
    region_id: str, session: AsyncSession = Depends(get_session)
) -> ClimateResponse:
    region = await regions_repo.get_region(session, region_id)
    if region is None:
        raise HTTPException(status_code=404, detail=f"unknown region {region_id!r}")
    cells = await climate_repo.list_region_cells(session, region_id)
    if not cells:
        raise HTTPException(status_code=503, detail="climate grid not computed yet")
    weather_cfg = (region.config or {}).get("weather", {})
    start = weather_cfg.get("baseline_start", 2015)
    end = weather_cfg.get("baseline_end", 2025)
    baseline_years = f"{start}-{end}"
    _, rows, _ = grid_for_bbox(list(region.bbox))
    latest = max(c.computed_at for c in cells)
    return ClimateResponse(
        bbox=list(region.bbox),
        cols=GRID_COLS,
        rows=rows,
        baseline_years=baseline_years,
        generated_at=latest,
        cells=[
            ClimateCellResponse(lat=c.lat, lng=c.lng, temp=c.temp_c, anomaly=c.anomaly_c)
            for c in cells
        ],
    )
