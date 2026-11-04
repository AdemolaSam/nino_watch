from datetime import date

from app.repos.models import Cluster, Event, Verification
from app.services.incidents import compose_evidence, compose_title


def make_event(**overrides) -> Event:
    defaults = {
        "article_id": 1,
        "region_id": "sahel-nigeria",
        "event_type": "heat_illness",
        "place_name": "Kano",
        "event_date": date(2026, 10, 28),
    }
    defaults.update(overrides)
    return Event(**defaults)


def make_verification(**overrides) -> Verification:
    defaults = {
        "cluster_id": 1,
        "status": "corroborated",
        "independent_outlets": 2,
        "official_match": False,
        "weather_plausible": True,
        "conflict": False,
        "evidence": {},
        "rule_version": "v1",
    }
    defaults.update(overrides)
    return Verification(**defaults)


def test_title_from_facts():
    title = compose_title(make_event(), sample=False)
    assert title == "Heat illness reported in Kano on 2026-10-28"


def test_title_without_date():
    title = compose_title(make_event(event_date=None), sample=False)
    assert title == "Heat illness reported in Kano"


def test_title_marks_sample():
    title = compose_title(make_event(), sample=True)
    assert title.startswith("[Sample] ")


def test_evidence_full():
    cluster = Cluster(region_id="sahel-nigeria", event_type="heat_illness", place_key="kano")
    text = compose_evidence(cluster, make_verification())
    assert text == (
        "2 independent outlets; no official statement; weather data plausible"
    )


def test_evidence_conflict_and_sample():
    cluster = Cluster(region_id="sahel-nigeria", event_type="heat_death", place_key="x")
    verification = make_verification(
        independent_outlets=1,
        official_match=False,
        weather_plausible=False,
        conflict=True,
        evidence={"sample": True},
    )
    text = compose_evidence(cluster, verification)
    assert text.startswith("Sample data; 1 independent outlet;")
    assert "conflicting evidence" in text
