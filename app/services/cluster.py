"""Event clustering: same type + nearby place + close date -> one cluster."""

import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.cluster import haversine_km, normalize_place
from app.llm.client import LlmError
from app.llm.schemas import LlmParseError
from app.repos import clusters as clusters_repo
from app.repos import events as events_repo
from app.repos import verifications as verifications_repo
from app.repos.models import Cluster, Event
from app.services.regions import load_all_region_configs
from app.services.verify import event_summary, same_event_signal

logger = logging.getLogger("ninowatch.cluster")

NEARBY_KM = 50.0
DATE_WINDOW_DAYS = 2
MERGE_NEAR_KM = 150.0
MERGE_DATE_DAYS = 4
MERGE_PAIR_CAP = 10


def dates_match(a: date | None, b: date | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs((a - b).days) <= DATE_WINDOW_DAYS


def events_match(existing: Event, candidate: Event) -> bool:
    if existing.event_type != candidate.event_type:
        return False
    if existing.lat is None or existing.lng is None:
        return False
    if candidate.lat is None or candidate.lng is None:
        return False
    if haversine_km(existing.lat, existing.lng, candidate.lat, candidate.lng) > NEARBY_KM:
        return False
    return dates_match(existing.event_date, candidate.event_date)


async def cluster_events(session: AsyncSession, region_id: str) -> dict[str, int]:
    """Assign unclustered placed events to clusters. Returns counts."""
    counts = {"assigned": 0, "created": 0, "skipped": 0}
    clusters = await clusters_repo.list_region_clusters(session, region_id)
    canonical: dict[int, Event] = {}
    for cluster in clusters:
        if cluster.canonical_event_id is not None:
            event = await events_repo.get_event(session, cluster.canonical_event_id)
            if event is not None:
                canonical[cluster.id] = event
    for event in await events_repo.list_unclustered(session, region_id):
        if event.lat is None or event.lng is None:
            counts["skipped"] += 1
            continue
        target: Cluster | None = None
        for cluster in clusters:
            anchor = canonical.get(cluster.id)
            if anchor is not None and events_match(anchor, event):
                target = cluster
                break
        if target is None:
            target = await clusters_repo.create_cluster(
                session,
                region_id=region_id,
                event_type=event.event_type,
                place_key=normalize_place(event.place_name),
                date_key=event.event_date,
                canonical_event_id=event.id,
            )
            clusters.append(target)
            canonical[target.id] = event
            counts["created"] += 1
        event.cluster_id = target.id
        await session.commit()
        counts["assigned"] += 1
    return counts


async def cluster_all_regions(session: AsyncSession) -> dict[str, dict[str, int]]:
    results = {}
    for region in load_all_region_configs():
        counts = await cluster_events(session, region.id)
        counts["merged"] = await merge_same_events(session, region.id)
        results[region.id] = counts
    return results


def _merge_candidates(anchors: dict[int, Event]) -> list[tuple[int, int]]:
    ids = sorted(anchors)
    pairs = []
    for i, first in enumerate(ids):
        for second in ids[i + 1 :]:
            a, b = anchors[first], anchors[second]
            if a.event_type != b.event_type:
                continue
            if a.lat is None or b.lat is None:
                continue
            if haversine_km(a.lat, a.lng, b.lat, b.lng) > MERGE_NEAR_KM:
                continue
            if a.event_date and b.event_date:
                gap = abs((a.event_date - b.event_date).days)
                if gap > MERGE_DATE_DAYS:
                    continue
            pairs.append((first, second))
    return pairs[:MERGE_PAIR_CAP]


async def merge_same_events(session: AsyncSession, region_id: str) -> int:
    """Model-confirmed merge pass for near-miss clusters. Returns merges done."""
    clusters = await clusters_repo.list_region_clusters(session, region_id)
    anchors: dict[int, Event] = {}
    for cluster in clusters:
        if cluster.canonical_event_id is None:
            continue
        event = await events_repo.get_event(session, cluster.canonical_event_id)
        if event is not None:
            anchors[cluster.id] = event
    merged = 0
    for first_id, second_id in _merge_candidates(anchors):
        if first_id not in anchors or second_id not in anchors:
            continue
        try:
            signal = await same_event_signal(
                event_summary(anchors[first_id]), event_summary(anchors[second_id])
            )
        except LlmError as e:
            logger.warning("merge pass stopping, provider failed (%s)", e)
            break
        except LlmParseError as e:
            logger.warning("merge signal unparseable (%s)", e)
            continue
        if not signal.match:
            continue
        keep_id, drop_id = sorted((first_id, second_id))
        for event in await verifications_repo.list_cluster_events(session, drop_id):
            event.cluster_id = keep_id
        for verification in [
            await verifications_repo.get_by_cluster(session, keep_id),
            await verifications_repo.get_by_cluster(session, drop_id),
        ]:
            if verification is not None:
                await session.delete(verification)
        dropped = await session.get(Cluster, drop_id)
        if dropped is not None:
            await session.delete(dropped)
        await session.commit()
        del anchors[drop_id]
        merged += 1
        logger.info("merged cluster %d into %d (%s)", drop_id, keep_id, signal.reason)
    return merged
