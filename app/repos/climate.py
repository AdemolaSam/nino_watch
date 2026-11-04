from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.models import ClimateCell


async def replace_region_cells(
    session: AsyncSession, region_id: str, cells: list[dict]
) -> None:
    await session.execute(delete(ClimateCell).where(ClimateCell.region_id == region_id))
    session.add_all(ClimateCell(**cell) for cell in cells)
    await session.commit()


async def list_region_cells(session: AsyncSession, region_id: str) -> list[ClimateCell]:
    result = await session.execute(
        select(ClimateCell)
        .where(ClimateCell.region_id == region_id)
        .order_by(ClimateCell.lat, ClimateCell.lng)
    )
    return list(result.scalars().all())
