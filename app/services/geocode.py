"""Place-name geocoding: local GeoNames table first, cached Nominatim fallback.

Events that cannot be placed are discarded (deleted) and logged.
"""

import hashlib
import logging
import time

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.cache import get_default_cache
from app.repos import events as events_repo
from app.repos import geonames as geonames_repo

logger = logging.getLogger("ninowatch.geocode")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_AGENT = "NinoWatch/0.1 (El Nino public-health demo)"
NOMINATIM_MIN_INTERVAL = 1.1
GEOCODE_CACHE_TTL = 30 * 24 * 3600

COUNTRY_ISO = {
    "nigeria": "NG",
    "niger": "NE",
    "chad": "TD",
    "sudan": "SD",
    "mali": "ML",
    "burkina faso": "BF",
    "burkina": "BF",
    "indonesia": "ID",
    "philippines": "PH",
    "vietnam": "VN",
    "viet nam": "VN",
    "thailand": "TH",
    "kenya": "KE",
    "ethiopia": "ET",
    "somalia": "SO",
    "uganda": "UG",
    "tanzania": "TZ",
    "south sudan": "SS",
    "peru": "PE",
    "perú": "PE",
    "ecuador": "EC",
    "guatemala": "GT",
    "honduras": "HN",
    "el salvador": "SV",
    "nicaragua": "NI",
    "costa rica": "CR",
    "panama": "PA",
    "panamá": "PA",
    "belize": "BZ",
    "south africa": "ZA",
    "sudáfrica": "ZA",
    "zimbabwe": "ZW",
    "zambia": "ZM",
    "mozambique": "MZ",
    "botswana": "BW",
    "namibia": "NA",
    "malawi": "MW",
    "angola": "AO",
}

_last_nominatim_call = 0.0


def country_to_iso(country: str | None) -> str | None:
    if not country:
        return None
    return COUNTRY_ISO.get(country.strip().lower())


async def nominatim_lookup(place: str, country: str | None) -> tuple[float, float] | None:
    """Cached, throttled Nominatim lookup. None on any failure."""
    query = f"{place}, {country}" if country else place
    key = "geo:" + hashlib.sha256(query.lower().encode()).hexdigest()
    cache = get_default_cache()
    hit = await cache.get(key)
    if hit:
        try:
            lat_s, lng_s = hit.split(",")
            return float(lat_s), float(lng_s)
        except ValueError:
            pass
    global _last_nominatim_call
    wait = NOMINATIM_MIN_INTERVAL - (time.monotonic() - _last_nominatim_call)
    if wait > 0:
        import asyncio

        await asyncio.sleep(wait)
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": NOMINATIM_AGENT}, timeout=15
        ) as client:
            resp = await client.get(
                NOMINATIM_URL, params={"q": query, "format": "jsonv2", "limit": 1}
            )
            resp.raise_for_status()
            results = resp.json()
    except Exception as e:
        logger.info("nominatim lookup failed for %r (%s)", query, e)
        return None
    finally:
        _last_nominatim_call = time.monotonic()
    if not results:
        return None
    try:
        coords = (float(results[0]["lat"]), float(results[0]["lon"]))
    except (KeyError, ValueError, TypeError):
        return None
    await cache.set(key, f"{coords[0]},{coords[1]}", ttl=GEOCODE_CACHE_TTL)
    return coords


async def geocode_event(session: AsyncSession, event_id: int) -> bool:
    """Place an event; discard (delete) it when unplaceable. Returns placed?"""
    event = await events_repo.get_event(session, event_id)
    if event is None:
        return False
    if event.lat is not None and event.lng is not None:
        return True
    place = (event.place_name or "").strip()
    if not place:
        logger.info("discarding event %d: empty place", event_id)
        await events_repo.delete_event(session, event)
        return False
    row = await geonames_repo.lookup(session, place, country_to_iso(event.country))
    if row is not None:
        event.lat, event.lng = row.lat, row.lng
        await session.commit()
        return True
    coords = await nominatim_lookup(place, event.country)
    if coords is not None:
        event.lat, event.lng = coords
        await session.commit()
        return True
    logger.info("discarding event %d: unplaceable %r", event_id, place)
    await events_repo.delete_event(session, event)
    return False
