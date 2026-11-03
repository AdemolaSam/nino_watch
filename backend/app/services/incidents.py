from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import IncidentResponse
from app.repos import incidents as incidents_repo
from app.repos.models import Cluster, Event, Verification

EVENT_LABELS = {
    "heat_death": "Heat deaths reported",
    "heat_illness": "Heat illness reported",
    "crop_failure": "Crop failure reported",
    "flood": "Flooding reported",
    "drought": "Drought reported",
    "wildfire": "Wildfire reported",
    "disease": "Disease outbreak reported",
    "other": "Incident reported",
}


def compose_title(event: Event, sample: bool) -> str:
    """Neutral headline from extracted facts, never copied article text."""
    label = EVENT_LABELS.get(event.event_type, EVENT_LABELS["other"])
    parts = [label, f"in {event.place_name}"]
    if event.event_date:
        parts.append(f"on {event.event_date.isoformat()}")
    title = " ".join(parts)
    return f"[Sample] {title}" if sample else title


def compose_evidence(cluster: Cluster, verification: Verification) -> str:
    bits = []
    if verification.evidence.get("sample"):
        bits.append("Sample data")
    n = verification.independent_outlets
    bits.append(f"{n} independent outlet{'s' if n != 1 else ''}")
    if verification.official_match:
        bits.append("official source confirms")
    else:
        bits.append("no official statement")
    if verification.weather_plausible is True:
        bits.append("weather data plausible")
    elif verification.weather_plausible is False:
        bits.append("weather data implausible")
    else:
        bits.append("weather unchecked")
    if verification.conflict:
        bits.append("conflicting evidence — treat with caution")
    return "; ".join(bits)


def to_incident_response(
    cluster: Cluster, event: Event, verification: Verification
) -> IncidentResponse:
    sample = bool(verification.evidence.get("sample"))
    return IncidentResponse(
        id=str(cluster.id),
        region_id=cluster.region_id,
        lat=event.lat or 0.0,
        lng=event.lng or 0.0,
        title=compose_title(event, sample),
        status=verification.status,
        evidence=compose_evidence(cluster, verification),
    )


async def list_incident_responses(
    session: AsyncSession, region_id: str
) -> list[IncidentResponse]:
    rows = await incidents_repo.list_incidents(session, region_id)
    return [
        to_incident_response(c, e, v)
        for c, e, v in rows
        if not v.evidence.get("sample")
    ]
