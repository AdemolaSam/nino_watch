from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.models import Region


async def list_regions(session: AsyncSession) -> list[Region]:
    result = await session.execute(select(Region).order_by(Region.id))
    return list(result.scalars().all())


async def get_region(session: AsyncSession, region_id: str) -> Region | None:
    return await session.get(Region, region_id)


async def upsert_region(session: AsyncSession, **fields) -> Region:
    region = await session.get(Region, fields["id"])
    if region is None:
        region = Region(**fields)
        session.add(region)
    else:
        for key, value in fields.items():
            if key != "id":
                setattr(region, key, value)
    await session.commit()
    return region
