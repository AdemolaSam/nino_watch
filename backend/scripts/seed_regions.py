"""Upsert configured regions without adding demonstration incidents."""

import asyncio

from app.core.db import get_session_factory
from scripts.seed import seed_regions


async def main() -> None:
    async with get_session_factory()() as session:
        count = await seed_regions(session)
        await session.commit()
    print(f"upserted {count} regions")


if __name__ == "__main__":
    asyncio.run(main())
