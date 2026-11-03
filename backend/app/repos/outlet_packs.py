from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.models import OutletPack


async def get_by_advisory(session: AsyncSession, advisory_id: int) -> OutletPack | None:
    result = await session.execute(
        select(OutletPack).where(OutletPack.advisory_id == advisory_id)
    )
    return result.scalars().first()


async def create_pack(session: AsyncSession, **fields) -> OutletPack:
    pack = OutletPack(**fields)
    session.add(pack)
    await session.commit()
    return pack
