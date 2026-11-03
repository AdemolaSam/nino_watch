from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.models import GeoName


async def lookup(
    session: AsyncSession, place: str, country_iso: str | None = None
) -> GeoName | None:
    name = place.strip().lower()
    if not name:
        return None
    stmt = select(GeoName).where(
        or_(func.lower(GeoName.name) == name, func.lower(GeoName.asciiname) == name)
    )
    if country_iso:
        stmt = stmt.where(GeoName.country == country_iso.upper())
    stmt = stmt.order_by(GeoName.population.desc()).limit(1)
    result = await session.execute(stmt)
    return result.scalars().first()


async def upsert_seed(session: AsyncSession, **fields) -> None:
    stmt = insert(GeoName).values(**fields)
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={k: v for k, v in fields.items() if k != "id"},
    )
    await session.execute(stmt)
    await session.commit()
