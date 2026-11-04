from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.models import Cluster


async def list_region_clusters(session: AsyncSession, region_id: str) -> list[Cluster]:
    result = await session.execute(
        select(Cluster).where(Cluster.region_id == region_id).order_by(Cluster.id)
    )
    return list(result.scalars().all())


async def create_cluster(session: AsyncSession, **fields) -> Cluster:
    cluster = Cluster(**fields)
    session.add(cluster)
    await session.commit()
    return cluster
