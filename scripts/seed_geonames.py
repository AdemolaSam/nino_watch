"""Seed hand-verified pilot-country cities into geonames (negative ids).

Populations are rough ranking weights, not published figures. The full
cities500 import (scripts/import_geonames.py) supplements these rows.

Usage: DATABASE_URL=... uv run python scripts/seed_geonames.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.db import get_session_factory  # noqa: E402
from app.repos import geonames as geonames_repo  # noqa: E402

# (name, asciiname, ISO, lat, lng, pop-weight)
CITIES = [
    ("Lagos", "Lagos", "NG", 6.45, 3.39, 9000000),
    ("Kano", "Kano", "NG", 12.0, 8.52, 2800000),
    ("Ibadan", "Ibadan", "NG", 7.38, 3.95, 2600000),
    ("Abuja", "Abuja", "NG", 9.06, 7.49, 1200000),
    ("Kaduna", "Kaduna", "NG", 10.52, 7.44, 1100000),
    ("Port Harcourt", "Port Harcourt", "NG", 4.77, 7.01, 1000000),
    ("Maiduguri", "Maiduguri", "NG", 11.83, 13.15, 800000),
    ("Sokoto", "Sokoto", "NG", 13.06, 5.25, 600000),
    ("Niamey", "Niamey", "NE", 13.51, 2.11, 900000),
    ("Zinder", "Zinder", "NE", 13.81, 8.99, 300000),
    ("Maradi", "Maradi", "NE", 13.5, 7.1, 300000),
    ("N'Djamena", "N'Djamena", "TD", 12.13, 15.05, 1000000),
    ("Moundou", "Moundou", "TD", 8.57, 16.07, 150000),
    ("Khartoum", "Khartoum", "SD", 15.5, 32.56, 2000000),
    ("Omdurman", "Omdurman", "SD", 15.65, 32.48, 1800000),
    ("Nyala", "Nyala", "SD", 12.05, 24.88, 500000),
    ("Bamako", "Bamako", "ML", 12.64, -8.0, 1800000),
    ("Gao", "Gao", "ML", 16.27, -0.04, 50000),
    ("Timbuktu", "Timbuktu", "ML", 16.77, -3.0, 50000),
    ("Ouagadougou", "Ouagadougou", "BF", 12.37, -1.52, 1600000),
    ("Bobo-Dioulasso", "Bobo-Dioulasso", "BF", 11.18, -4.28, 600000),
    ("Jakarta", "Jakarta", "ID", -6.21, 106.85, 10000000),
    ("Surabaya", "Surabaya", "ID", -7.25, 112.75, 2900000),
    ("Bandung", "Bandung", "ID", -6.92, 107.6, 2500000),
    ("Medan", "Medan", "ID", 3.59, 98.67, 2200000),
    ("Semarang", "Semarang", "ID", -6.99, 110.42, 1600000),
    ("Makassar", "Makassar", "ID", -5.13, 119.41, 1400000),
    ("Manila", "Manila", "PH", 14.6, 120.98, 1800000),
    ("Quezon City", "Quezon City", "PH", 14.68, 121.04, 2900000),
    ("Davao", "Davao", "PH", 7.19, 125.45, 1600000),
    ("Cebu City", "Cebu City", "PH", 10.29, 123.9, 900000),
    ("Zamboanga", "Zamboanga", "PH", 6.92, 122.08, 800000),
    ("Hanoi", "Hanoi", "VN", 21.03, 105.85, 4000000),
    ("Ho Chi Minh City", "Ho Chi Minh City", "VN", 10.82, 106.63, 7000000),
    ("Da Nang", "Da Nang", "VN", 16.05, 108.22, 1100000),
    ("Hai Phong", "Hai Phong", "VN", 20.84, 106.68, 1300000),
    ("Bangkok", "Bangkok", "TH", 13.76, 100.5, 8000000),
    ("Chiang Mai", "Chiang Mai", "TH", 18.79, 98.98, 400000),
    ("Khon Kaen", "Khon Kaen", "TH", 16.44, 102.83, 400000),
    ("Nairobi", "Nairobi", "KE", -1.29, 36.82, 4400000),
    ("Mombasa", "Mombasa", "KE", -4.05, 39.67, 1200000),
    ("Addis Ababa", "Addis Ababa", "ET", 9.02, 38.75, 3300000),
    ("Mogadishu", "Mogadishu", "SO", 2.03, 45.34, 2100000),
]


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        for i, (name, ascii_name, iso, lat, lng, pop) in enumerate(CITIES, start=1):
            await geonames_repo.upsert_seed(
                session,
                id=-i,
                name=name,
                asciiname=ascii_name,
                country=iso,
                lat=lat,
                lng=lng,
                population=pop,
            )
    print(f"seeded {len(CITIES)} gazetteer cities")


if __name__ == "__main__":
    asyncio.run(main())
