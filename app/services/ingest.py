"""RSS ingest: fetch feeds, dedupe by URL hash, store short excerpts.

Only URLs from region YAML configs are ever fetched (SSRF-safe by construction).
Full article text is never stored or republished (copyright, BACKEND.md 11).
"""

import asyncio
import hashlib
import html
import logging
import re
import time
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import feedparser
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.repos import articles as articles_repo
from app.services.regions import RegionConfig, load_all_region_configs

logger = logging.getLogger("ninowatch.ingest")

# ASCII-only: HTTP headers cannot carry the ñ in NiñoWatch.
USER_AGENT = "NinoWatch/0.1 (El Nino public-health demo)"
ROBOTS_AGENT = "NinoWatch"
EXCERPT_MAX_CHARS = 500
FETCH_TIMEOUT_SECONDS = 15
MIN_HOST_INTERVAL_SECONDS = 1.0
ROBOTS_TTL_SECONDS = 3600
TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"}

_host_last_fetch: dict[str, float] = {}
_robots_cache: dict[str, tuple[float, RobotFileParser | None]] = {}


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = urlencode(
        [(k, v) for k, v in parse_qsl(parts.query) if k.lower() not in TRACKING_PARAMS]
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def truncate(text: str, limit: int = EXCERPT_MAX_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


async def fetch_url(url: str) -> bytes:
    await _respect_host_interval(url)
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        max_redirects=3,
        timeout=FETCH_TIMEOUT_SECONDS,
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


MAX_CRAWL_DELAY_SECONDS = 60


def _host_delay(url: str) -> float:
    """Per-host politeness delay: robots Crawl-delay when present, else the floor."""
    origin = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
    cached = _robots_cache.get(origin)
    delay = MIN_HOST_INTERVAL_SECONDS
    if cached and cached[1] is not None:
        for agent in (ROBOTS_AGENT, "*"):
            try:
                found = cached[1].crawl_delay(agent)
            except Exception:
                found = None
            if found:
                delay = float(found)
                break
    if delay > MAX_CRAWL_DELAY_SECONDS:
        logger.warning("crawl-delay %.0fs for %s exceeds cap", delay, origin)
        delay = MAX_CRAWL_DELAY_SECONDS
    return delay


async def _respect_host_interval(url: str) -> None:
    host = urlsplit(url).netloc
    now = time.monotonic()
    wait = _host_delay(url) - (now - _host_last_fetch.get(host, 0.0))
    if wait > 0:
        await asyncio.sleep(wait)
    _host_last_fetch[host] = time.monotonic()


async def robots_allowed(url: str) -> bool:
    """Cached robots.txt check; missing/unfetchable robots.txt means allowed."""
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    now = time.monotonic()
    cached = _robots_cache.get(origin)
    if cached and now - cached[0] < ROBOTS_TTL_SECONDS:
        parser = cached[1]
    else:
        parser = None
        try:
            body = await fetch_url(origin + "/robots.txt")
            parser = RobotFileParser()
            parser.parse(body.decode("utf-8", "ignore").splitlines())
        except Exception as e:
            logger.info("robots fetch failed for %s (%s); allowing", origin, e)
        _robots_cache[origin] = (now, parser)
    if parser is None:
        return True
    return parser.can_fetch(ROBOTS_AGENT, url)


def detect_language(text: str) -> str | None:
    try:
        from langdetect import detect

        return detect(text)
    except Exception:
        return None


def entry_published_at(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    try:
        return datetime.fromtimestamp(time.mktime(parsed), tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def parse_feed(content: bytes, source_url: str) -> list[dict]:
    feed = feedparser.parse(content)
    if feed.bozo and not feed.entries:
        raise ValueError(f"unparseable feed at {source_url}: {feed.bozo_exception}")
    items = []
    for entry in feed.entries:
        link = (entry.get("link") or "").strip()
        if not link:
            continue
        title = strip_html(entry.get("title", ""))
        summary = entry.get("summary") or entry.get("description") or ""
        excerpt = truncate(strip_html(summary)) or truncate(title)
        items.append(
            {
                "url": normalize_url(link),
                "title": title or "(untitled)",
                "excerpt": excerpt,
                "published_at": entry_published_at(entry),
            }
        )
    return items


async def ingest_source(
    session: AsyncSession,
    region: RegionConfig,
    source: dict,
    *,
    official: bool = False,
) -> int:
    """Fetch one configured source; returns the number of new articles stored."""
    url = source["url"]
    name = source.get("name", url)
    if not await robots_allowed(url):
        logger.info("robots disallow, skipping %s", url)
        return 0
    try:
        content = await fetch_url(url)
    except Exception as e:
        logger.warning("fetch failed for %s (%s)", url, e)
        return 0
    try:
        items = parse_feed(content, url)
    except ValueError as e:
        logger.warning("%s", e)
        return 0
    configured_lang = source.get("language", "")
    stored = 0
    for item in items[: int(source.get("max_items", len(items)))]:
        url_hash = sha256(item["url"])
        detected = detect_language(f"{item['title']} {item['excerpt']}")
        if configured_lang:
            if detected and detected != configured_lang:
                logger.info(
                    "language mismatch for %s: detected %s, configured %s (keeping configured)",
                    item["url"],
                    detected,
                    configured_lang,
                )
            language = configured_lang
        else:
            language = detected or "en"
        article = await articles_repo.insert_article(
            session,
            region_id=region.id,
            url=item["url"],
            url_hash=url_hash,
            publisher=name,
            ownership_group="official" if official else source.get("ownership_group"),
            language=language,
            title=item["title"][:2000],
            published_at=item["published_at"],
            excerpt=item["excerpt"],
            content_hash=sha256(item["title"] + "\x00" + item["excerpt"]),
        )
        if article is not None:
            stored += 1
    logger.info("ingested %d/%d new from %s (%s)", stored, len(items), name, region.id)
    return stored


async def ingest_region(session: AsyncSession, region: RegionConfig) -> int:
    total = 0
    for source in region.news_sources:
        total += await ingest_source(session, region, source)
    for source in region.official_sources:
        total += await ingest_source(session, region, source, official=True)
    return total


async def ingest_all_regions(session: AsyncSession) -> dict[str, int]:
    results = {}
    for region in load_all_region_configs():
        if not region.news_sources and not region.official_sources:
            continue
        try:
            results[region.id] = await ingest_region(session, region)
        except Exception as e:
            logger.warning("ingest failed for region %s (%s)", region.id, e)
            results[region.id] = 0
    return results
