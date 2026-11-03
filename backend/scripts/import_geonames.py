"""Import GeoNames cities500 (population > 500) into geonames.

Source: https://download.geonames.org/export/dump/cities500.zip (CC BY 4.0,
credit "GeoNames"). Skips rows already present. Run once per database.

Usage: DATABASE_URL=... uv run python scripts/import_geonames.py
"""

import asyncio
import io
import os
import sys
import zipfile
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402
import httpx  # noqa: E402

DUMP_URL = "https://download.geonames.org/export/dump/cities500.zip"


def to_psycopg_url(async_url: str) -> str:
    parts = urlparse(async_url)
    scheme = "postgresql"
    netloc = parts.netloc
    return f"{scheme}://{netloc}{parts.path}"


def parse_rows(text: str) -> list[tuple]:
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        cols = line.split("\t")
        try:
            rows.append(
                (
                    int(cols[0]),
                    cols[1][:256],
                    cols[2][:256],
                    cols[8][:2],
                    float(cols[4]),
                    float(cols[5]),
                    int(cols[14]) if cols[14] else 0,
                )
            )
        except (IndexError, ValueError):
            continue
    return rows


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    print(f"downloading {DUMP_URL} ...", flush=True)
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.get(DUMP_URL)
        resp.raise_for_status()
        data = resp.content
    print(f"downloaded {len(data) / 1e6:.1f} MB", flush=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = [n for n in zf.namelist() if n.endswith(".txt")]
        text = zf.read(names[0]).decode("utf-8")
    rows = parse_rows(text)
    print(f"parsed {len(rows)} places", flush=True)
    conn = await asyncpg.connect(to_psycopg_url(database_url))
    try:
        await conn.execute(
            """
            CREATE TEMP TABLE geonames_import (
                id integer, name text, asciiname text, country text,
                lat double precision, lng double precision, population integer
            )
            """
        )
        await conn.copy_records_to_table("geonames_import", records=rows)
        result = await conn.execute(
            """
            INSERT INTO geonames (id, name, asciiname, country, lat, lng, population)
            SELECT id, name, asciiname, country, lat, lng, population FROM geonames_import
            ON CONFLICT (id) DO NOTHING
            """
        )
        print(f"import done: {result}", flush=True)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
