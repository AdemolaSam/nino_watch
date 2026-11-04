"""Open-Meteo weather: heat plausibility checks + climate grids.

Free-tier note: Open-Meteo allows ~10k calls/day non-commercial (verify in
their docs). A full refresh costs ~25 calls per pilot region every 6h.
"""

import asyncio
import logging
from datetime import UTC, date, datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.cache import LlmCache, get_default_cache
from app.repos import climate as climate_repo
from app.repos import regions as regions_repo

logger = logging.getLogger("ninowatch.weather")

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
USER_AGENT = "NinoWatch/0.1 (El Nino public-health demo)"
GRID_COLS = 24
BASELINE_WINDOW_DAYS = 3
BASELINE_CACHE_TTL = 30 * 24 * 3600
OBSERVED_CACHE_TTL = 6 * 3600
FORECAST_BATCH = 50
BASELINE_BATCH = 10
FETCH_RETRIES = 3
FETCH_BACKOFF_SECONDS = 2.0
BATCH_PAUSE_SECONDS = 0.5
HEAT_TYPES = ("heat_death", "heat_illness")


async def fetch_json(url: str, params: dict) -> dict | list:
    last_error: Exception | None = None
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=60) as client:
        for attempt in range(FETCH_RETRIES):
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code not in (429, 500, 502, 503, 504):
                    raise
            except httpx.RequestError as e:
                last_error = e
            await asyncio.sleep(FETCH_BACKOFF_SECONDS * (attempt + 1))
    assert last_error is not None
    raise last_error


def _day_of_year(month: int, day: int) -> int:
    if month == 2 and day == 29:
        day = 28
    return date(2023, month, day).timetuple().tm_yday


def circular_day_distance(month_a: int, day_a: int, month_b: int, day_b: int) -> int:
    diff = abs(_day_of_year(month_a, day_a) - _day_of_year(month_b, day_b))
    return min(diff, 365 - diff)


def compute_window_mean(
    times: list[str],
    values: list[float | None],
    month: int,
    day: int,
    start_year: int,
    end_year: int,
    window_days: int = BASELINE_WINDOW_DAYS,
) -> float | None:
    picked = []
    for stamp, value in zip(times, values, strict=False):
        if value is None:
            continue
        try:
            parsed = date.fromisoformat(stamp[:10])
        except ValueError:
            continue
        if not start_year <= parsed.year <= end_year:
            continue
        if circular_day_distance(parsed.month, parsed.day, month, day) <= window_days:
            picked.append(value)
    if not picked:
        return None
    return sum(picked) / len(picked)


def _daily_series(payload: dict) -> tuple[list[str], list[float | None]]:
    daily = payload.get("daily") or {}
    return list(daily.get("time", [])), list(daily.get("temperature_2m_max", []))


def _as_list(payload: dict | list) -> list[dict]:
    return payload if isinstance(payload, list) else [payload]


def _baseline_key(
    coord: tuple[float, float], month: int, day: int, start_year: int, end_year: int
) -> str:
    lat, lng = coord
    return f"geo:base:{lat:.2f}:{lng:.2f}:{month:02d}{day:02d}:{start_year}-{end_year}"


async def baseline_means(
    coords: list[tuple[float, float]],
    month: int,
    day: int,
    start_year: int,
    end_year: int,
    cache: LlmCache | None = None,
) -> dict[tuple[float, float], float | None]:
    """Day-of-year baseline mean per coord (one archive call per ~20 coords)."""
    cache = cache or get_default_cache()
    results: dict[tuple[float, float], float | None] = {}
    missing: list[tuple[float, float]] = []
    for coord in coords:
        key = _baseline_key(coord, month, day, start_year, end_year)
        hit = await cache.get(key)
        if hit is None:
            missing.append(coord)
        else:
            try:
                results[coord] = float(hit)
            except ValueError:
                missing.append(coord)
    for i in range(0, len(missing), BASELINE_BATCH):
        if i:
            await asyncio.sleep(BATCH_PAUSE_SECONDS)
        batch = missing[i : i + BASELINE_BATCH]
        try:
            payload = await fetch_json(
                ARCHIVE_URL,
                {
                    "latitude": [c[0] for c in batch],
                    "longitude": [c[1] for c in batch],
                    "start_date": f"{start_year}-01-01",
                    "end_date": f"{end_year}-12-31",
                    "daily": "temperature_2m_max",
                    "timezone": "UTC",
                },
            )
        except Exception as e:
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429:
                logger.warning("archive rate-limited; skipping remaining baseline requests")
                for coord in missing[i:]:
                    results[coord] = None
                break
            logger.warning("archive fetch failed (%s)", e)
            for coord in batch:
                results[coord] = None
            continue
        for coord, item in zip(batch, _as_list(payload), strict=False):
            times, values = _daily_series(item)
            mean = compute_window_mean(times, values, month, day, start_year, end_year)
            results[coord] = mean
            if mean is not None:
                await cache.set(
                    _baseline_key(coord, month, day, start_year, end_year),
                    repr(mean),
                    ttl=BASELINE_CACHE_TTL,
                )
    return results


async def today_maxima(
    coords: list[tuple[float, float]],
) -> dict[tuple[float, float], float | None]:
    """Today's daily max per coord (batched forecast calls, no cache)."""
    results: dict[tuple[float, float], float | None] = {}
    today = datetime.now(UTC).date().isoformat()
    for i in range(0, len(coords), FORECAST_BATCH):
        if i:
            await asyncio.sleep(BATCH_PAUSE_SECONDS)
        batch = coords[i : i + FORECAST_BATCH]
        try:
            payload = await fetch_json(
                FORECAST_URL,
                {
                    "latitude": [c[0] for c in batch],
                    "longitude": [c[1] for c in batch],
                    "daily": "temperature_2m_max",
                    "timezone": "UTC",
                    "forecast_days": 1,
                },
            )
        except Exception as e:
            logger.warning("forecast fetch failed (%s)", e)
            for coord in batch:
                results[coord] = None
            continue
        for coord, item in zip(batch, _as_list(payload), strict=False):
            times, values = _daily_series(item)
            value = None
            for stamp, candidate in zip(times, values, strict=False):
                if stamp[:10] == today:
                    value = candidate
                    break
            results[coord] = value
    return results


async def daily_max_for(
    lat: float, lng: float, day: date, cache: LlmCache | None = None
) -> float | None:
    """Observed or forecast daily max for one place+date (cached 6h)."""
    cache = cache or get_default_cache()
    key = f"geo:obs:{lat:.2f}:{lng:.2f}:{day.isoformat()}"
    hit = await cache.get(key)
    if hit is not None:
        try:
            return float(hit)
        except ValueError:
            pass
    today = datetime.now(UTC).date()
    try:
        if (today - day).days > 7:
            payload = await fetch_json(
                ARCHIVE_URL,
                {
                    "latitude": lat,
                    "longitude": lng,
                    "start_date": day.isoformat(),
                    "end_date": day.isoformat(),
                    "daily": "temperature_2m_max",
                    "timezone": "UTC",
                },
            )
            _, values = _daily_series(_as_list(payload)[0])
            value = values[0] if values else None
        else:
            payload = await fetch_json(
                FORECAST_URL,
                {
                    "latitude": lat,
                    "longitude": lng,
                    "daily": "temperature_2m_max",
                    "timezone": "UTC",
                    "past_days": 7,
                    "forecast_days": 16,
                },
            )
            times, values = _daily_series(_as_list(payload)[0])
            value = None
            for stamp, candidate in zip(times, values, strict=False):
                if stamp[:10] == day.isoformat():
                    value = candidate
                    break
    except Exception as e:
        logger.warning("daily max fetch failed (%s)", e)
        return None
    if value is not None:
        await cache.set(key, repr(value), ttl=OBSERVED_CACHE_TTL)
    return value


async def heat_plausible(
    lat: float,
    lng: float,
    day: date | None,
    hot_threshold_c: float,
    anomaly_threshold_c: float,
    baseline_years: tuple[int, int],
    cache: LlmCache | None = None,
) -> tuple[bool | None, dict]:
    """Heat check: observed max >= hot threshold OR >= anomaly above baseline."""
    if day is None:
        return None, {"reason": "no event date"}
    observed = await daily_max_for(lat, lng, day, cache)
    if observed is None:
        return None, {"reason": "no weather data"}
    means = await baseline_means(
        [(lat, lng)], day.month, day.day, baseline_years[0], baseline_years[1], cache
    )
    baseline = means[(lat, lng)]
    anomaly = observed - baseline if baseline is not None else None
    plausible = observed >= hot_threshold_c or (
        anomaly is not None and anomaly >= anomaly_threshold_c
    )
    return plausible, {
        "observed_max_c": observed,
        "baseline_c": baseline,
        "anomaly_c": anomaly,
        "hot_threshold_c": hot_threshold_c,
        "anomaly_threshold_c": anomaly_threshold_c,
    }


async def plausibility_for(
    event_type: str,
    lat: float | None,
    lng: float | None,
    day: date | None,
    region_weather: dict,
    cache: LlmCache | None = None,
) -> tuple[bool | None, dict]:
    """Dispatch per event type; non-heat types are unchecked (null)."""
    if event_type not in HEAT_TYPES:
        return None, {"reason": f"no weather check for {event_type}"}
    if lat is None or lng is None:
        return None, {"reason": "no coordinates"}
    return await heat_plausible(
        lat,
        lng,
        day,
        float(region_weather.get("hot_threshold_c", 35)),
        float(region_weather.get("anomaly_threshold_c", 1.5)),
        (
            int(region_weather.get("baseline_start", 2015)),
            int(region_weather.get("baseline_end", 2025)),
        ),
        cache,
    )


def grid_for_bbox(bbox: list[float]) -> tuple[int, int, list[tuple[float, float]]]:
    """~24-column grid of cell centers across [west, south, east, north]."""
    west, south, east, north = bbox
    cols = GRID_COLS
    span_lng = max(east - west, 0.01)
    span_lat = max(north - south, 0.01)
    rows = min(24, max(4, round(cols * span_lat / span_lng)))
    cells = []
    for r in range(rows):
        lat = south + span_lat * (r + 0.5) / rows
        for c in range(cols):
            lng = west + span_lng * (c + 0.5) / cols
            cells.append((round(lat, 3), round(lng, 3)))
    return cols, rows, cells


async def refresh_region_grid(session: AsyncSession, region_id: str) -> int:
    """Recompute and store one region's climate grid. Returns cells stored."""
    region = await regions_repo.get_region(session, region_id)
    if region is None:
        return 0
    weather_cfg = (region.config or {}).get("weather", {})
    start_year = int(weather_cfg.get("baseline_start", 2015))
    end_year = int(weather_cfg.get("baseline_end", 2025))
    cols, rows, cells = grid_for_bbox(list(region.bbox))
    coords = [(lat, lng) for lat, lng in cells]
    today = datetime.now(UTC).date()
    existing = {
        (cell.lat, cell.lng): cell
        for cell in await climate_repo.list_region_cells(session, region_id)
    }
    maxima = await today_maxima(coords)
    means = await baseline_means(coords, today.month, today.day, start_year, end_year)
    stored = []
    for lat, lng in coords:
        temp = maxima.get((lat, lng))
        base = means.get((lat, lng))
        prior = existing.get((lat, lng))
        if base is None and prior is not None and prior.computed_at.date() == today:
            base = prior.baseline_c
        if temp is None:
            continue
        temp = round(temp, 1)
        base = round(base, 2) if base is not None else None
        stored.append(
            {
                "region_id": region_id,
                "lat": lat,
                "lng": lng,
                "temp_c": temp,
                "baseline_c": base,
                "anomaly_c": (round(temp - base, 2)) if base is not None else None,
            }
        )
    if not stored:
        logger.warning(
            "climate refresh for %s returned no temperatures; keeping prior grid", region_id
        )
        return 0
    await climate_repo.replace_region_cells(session, region_id, stored)
    logger.info("climate refresh for %s: %d/%d cells", region_id, len(stored), len(coords))
    return len(stored)
