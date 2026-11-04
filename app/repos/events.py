from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.models import Event


async def create_event(session: AsyncSession, **fields) -> Event:
    event = Event(**fields)
    session.add(event)
    await session.commit()
    return event


async def get_event(session: AsyncSession, event_id: int) -> Event | None:
    return await session.get(Event, event_id)


async def delete_event(session: AsyncSession, event: Event) -> None:
    await session.delete(event)
    await session.commit()


async def list_unclustered(session: AsyncSession, region_id: str, limit: int = 500) -> list[Event]:
    result = await session.execute(
        select(Event)
        .where(Event.region_id == region_id, Event.cluster_id.is_(None))
        .order_by(Event.id)
        .limit(limit)
    )
    return list(result.scalars().all())
