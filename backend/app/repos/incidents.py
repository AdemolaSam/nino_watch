from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.models import Cluster, Event, Verification

IncidentRow = tuple[Cluster, Event, Verification]


async def list_incidents(session: AsyncSession, region_id: str) -> list[IncidentRow]:
    """Clusters with their canonical event and verification, newest first."""
    stmt = (
        select(Cluster, Event, Verification)
        .join(Event, Event.id == Cluster.canonical_event_id)
        .join(Verification, Verification.cluster_id == Cluster.id)
        .where(Cluster.region_id == region_id)
        .order_by(Cluster.id.desc())
    )
    result = await session.execute(stmt)
    return [(row[0], row[1], row[2]) for row in result.all()]
