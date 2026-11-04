from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.models import Advisory


async def latest_english(session: AsyncSession, region_id: str) -> Advisory | None:
    result = await session.execute(
        select(Advisory)
        .where(Advisory.region_id == region_id, Advisory.lang == "en")
        .order_by(desc(Advisory.version))
        .limit(1)
    )
    return result.scalars().first()


async def get_translation(
    session: AsyncSession, region_id: str, lang: str, version: int
) -> Advisory | None:
    result = await session.execute(
        select(Advisory).where(
            Advisory.region_id == region_id,
            Advisory.lang == lang,
            Advisory.version == version,
        )
    )
    return result.scalars().first()


async def create_advisory(session: AsyncSession, **fields) -> Advisory:
    advisory = Advisory(**fields)
    session.add(advisory)
    await session.commit()
    return advisory
