from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.models import Article, Cluster, Event, Verification


async def get_by_cluster(session: AsyncSession, cluster_id: int) -> Verification | None:
    result = await session.execute(
        select(Verification).where(Verification.cluster_id == cluster_id)
    )
    return result.scalars().first()


async def upsert_verification(session: AsyncSession, cluster_id: int, **fields) -> Verification:
    verification = await get_by_cluster(session, cluster_id)
    if verification is None:
        verification = Verification(cluster_id=cluster_id, **fields)
        session.add(verification)
    else:
        for key, value in fields.items():
            setattr(verification, key, value)
    await session.commit()
    return verification


async def list_unverified_clusters(
    session: AsyncSession, region_id: str | None = None, limit: int = 20
) -> list[Cluster]:
    stmt = (
        select(Cluster)
        .outerjoin(Verification, Verification.cluster_id == Cluster.id)
        .where(Verification.id.is_(None))
        .order_by(Cluster.id)
        .limit(limit)
    )
    if region_id is not None:
        stmt = stmt.where(Cluster.region_id == region_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_cluster_events(session: AsyncSession, cluster_id: int) -> list[Event]:
    result = await session.execute(
        select(Event).where(Event.cluster_id == cluster_id).order_by(Event.id)
    )
    return list(result.scalars().all())


async def list_official_articles(
    session: AsyncSession, region_id: str, limit: int = 10
) -> list[Article]:
    result = await session.execute(
        select(Article)
        .where(Article.region_id == region_id, Article.ownership_group == "official")
        .order_by(Article.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
