"""Verification: gather signals (outlets, official stance, weather), apply rules."""

import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.cluster import count_independent_outlets
from app.domain.verification import RULE_VERSION, compute_verification
from app.llm.cache import LlmCache
from app.llm.client import LlmError, complete_json
from app.llm.prompts import PROMPT_VERSIONS, load_prompt
from app.llm.schemas import LlmParseError, MatchSignal, OfficialStance
from app.repos import regions as regions_repo
from app.repos import verifications as verifications_repo
from app.repos.models import Article, Cluster, Event, Verification
from app.services import weather as weather_service

logger = logging.getLogger("ninowatch.verify")

VERIFY_TASK = "verify_signal"
OFFICIAL_WINDOW_DAYS = 7
OFFICIAL_CHECK_CAP = 5


def event_summary(event: Event) -> str:
    bits = [event.event_type, f"in {event.place_name}"]
    if event.country:
        bits.append(event.country)
    if event.event_date:
        bits.append(f"on {event.event_date.isoformat()}")
    if event.count is not None:
        bits.append(f"(count {event.count})")
    if event.evidence_quote:
        bits.append(f'Quote: "{event.evidence_quote}"')
    return " ".join(bits)


async def official_stance_for(summary: str, official: Article) -> OfficialStance:
    system = load_prompt("official_match")
    user = (
        f"Event summary:\n{summary}\n\nOfficial text ({official.publisher}):\n"
        f"Title: {official.title}\nExcerpt: {official.excerpt}"
    )
    result = await complete_json(
        VERIFY_TASK,
        system,
        user,
        OfficialStance,
        prompt_version=PROMPT_VERSIONS["official_match"],
        effort="low",
        max_tokens=300,
    )
    assert isinstance(result, OfficialStance)
    return result


async def same_event_signal(summary_a: str, summary_b: str) -> MatchSignal:
    system = load_prompt("same_event")
    user = f"Event A:\n{summary_a}\n\nEvent B:\n{summary_b}"
    result = await complete_json(
        VERIFY_TASK,
        system,
        user,
        MatchSignal,
        prompt_version=PROMPT_VERSIONS["same_event"],
        effort="low",
        max_tokens=300,
    )
    assert isinstance(result, MatchSignal)
    return result


def _official_in_window(official: Article, event_date: date | None) -> bool:
    if event_date is None or official.published_at is None:
        return True
    return abs((official.published_at.date() - event_date).days) <= OFFICIAL_WINDOW_DAYS


async def gather_official_stance(
    session: AsyncSession, canonical: Event
) -> tuple[bool, bool, list[dict]]:
    """Returns (any_match, any_contradict, checked details)."""
    officials = await verifications_repo.list_official_articles(session, canonical.region_id)
    checked = []
    any_match, any_contradict = False, False
    for official in officials:
        if not _official_in_window(official, canonical.event_date):
            continue
        if len(checked) >= OFFICIAL_CHECK_CAP:
            break
        try:
            stance = await official_stance_for(event_summary(canonical), official)
        except (LlmError, LlmParseError) as e:
            logger.warning("official stance check failed (%s)", e)
            checked.append({"publisher": official.publisher, "stance": "error"})
            continue
        checked.append(
            {
                "publisher": official.publisher,
                "stance": stance.stance,
                "reason": stance.reason,
                "excerpt": official.excerpt[:200],
            }
        )
        any_match = any_match or stance.stance == "match"
        any_contradict = any_contradict or stance.stance == "contradict"
    return any_match, any_contradict, checked


async def verify_cluster(
    session: AsyncSession, cluster_id: int, cache: LlmCache | None = None
) -> Verification | None:
    cluster = await session.get(Cluster, cluster_id)
    if cluster is None:
        return None
    events = await verifications_repo.list_cluster_events(session, cluster_id)
    if not events:
        return None
    canonical = next((e for e in events if e.id == cluster.canonical_event_id), events[0])
    articles = []
    for event in events:
        article = await session.get(Article, event.article_id)
        if article is not None:
            articles.append(article)
    outlets = count_independent_outlets(
        [
            {
                "publisher": a.publisher,
                "ownership_group": a.ownership_group,
                "title": a.title,
                "excerpt": a.excerpt,
            }
            for a in articles
        ]
    )
    official_match, official_contradict, official_checked = await gather_official_stance(
        session, canonical
    )
    region = await regions_repo.get_region(session, cluster.region_id)
    region_weather = (region.config or {}).get("weather", {}) if region else {}
    weather_plausible, weather_numbers = await weather_service.plausibility_for(
        canonical.event_type, canonical.lat, canonical.lng, canonical.event_date,
        region_weather, cache,
    )
    verdict = compute_verification(
        independent_outlets=outlets,
        official_match=official_match,
        official_contradict=official_contradict,
        weather_plausible=weather_plausible,
    )
    return await verifications_repo.upsert_verification(
        session,
        cluster_id,
        status=verdict["status"],
        independent_outlets=outlets,
        official_match=official_match,
        weather_plausible=weather_plausible,
        conflict=verdict["conflict"],
        evidence={
            "articles": [
                {"url": a.url, "publisher": a.publisher, "title": a.title} for a in articles
            ],
            "official_checked": official_checked,
            "official_contradict": official_contradict,
            "weather": weather_numbers,
        },
        rule_version=RULE_VERSION,
    )


async def verify_pending(
    session: AsyncSession, region_id: str | None = None, limit: int = 20,
    cache: LlmCache | None = None,
) -> dict:
    counts: dict = {"verified": 0, "failed": 0, "refresh_regions": set()}
    clusters = await verifications_repo.list_unverified_clusters(session, region_id, limit)
    for cluster in clusters:
        try:
            result = await verify_cluster(session, cluster.id, cache)
        except Exception as e:
            logger.warning("verify failed for cluster %d (%s)", cluster.id, e)
            counts["failed"] += 1
            continue
        if result is None:
            counts["failed"] += 1
        else:
            counts["verified"] += 1
            if result.status in ("confirmed", "corroborated"):
                counts["refresh_regions"].add(cluster.region_id)
    counts["refresh_regions"] = sorted(counts["refresh_regions"])
    return counts
