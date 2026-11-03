"""Create the nino_test database if missing (CI + local).

Connects to the maintenance DB derived from TEST_DATABASE_URL and issues
CREATE DATABASE. Safe to re-run.

Usage: uv run python scripts/create_test_db.py
"""

import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402


async def main() -> None:
    test_url = os.environ.get(
        "TEST_DATABASE_URL", "postgresql+asyncpg://nino:nino@localhost:5432/nino_test"
    )
    parts = urlparse(test_url)
    target_db = parts.path.lstrip("/")
    maint_url = urlunparse(parts._replace(path="/postgres"))
    engine = create_async_engine(maint_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        exists = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :db"), {"db": target_db}
        )
        if exists.scalar() is None:
            await conn.execute(text(f'CREATE DATABASE "{target_db}"'))
            print(f"created database {target_db}")
        else:
            print(f"database {target_db} exists")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
