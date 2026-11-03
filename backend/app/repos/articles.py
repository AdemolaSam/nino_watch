from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.models import Article


async def get_by_url_hash(session: AsyncSession, url_hash: str) -> Article | None:
    result = await session.execute(select(Article).where(Article.url_hash == url_hash))
    return result.scalars().first()


async def list_pending(
    session: AsyncSession, region_id: str | None = None, limit: int = 20
) -> list[Article]:
    stmt = select(Article).where(Article.extracted_at.is_(None)).order_by(Article.id).limit(limit)
    if region_id is not None:
        stmt = stmt.where(Article.region_id == region_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def insert_article(session: AsyncSession, **fields) -> Article | None:
    """Insert unless the URL was seen; returns None for duplicates."""
    if await get_by_url_hash(session, fields["url_hash"]) is not None:
        return None
    article = Article(**fields)
    session.add(article)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return None
    return article
