"""Deterministic verification labels. Models supply signals, never the label."""

RULE_VERSION = "v1"


def compute_verification(
    *,
    independent_outlets: int,
    official_match: bool,
    official_contradict: bool,
    weather_plausible: bool | None,
) -> dict:
    """Apply the public label rules (PROJECT.md section 6).

    conflict is derived: an official contradiction or clearly implausible
    weather. Labels describe strength of evidence, not certainty.
    """
    conflict = bool(official_contradict) or weather_plausible is False
    if official_match and weather_plausible is not False and not conflict:
        status = "confirmed"
    elif independent_outlets >= 2 and weather_plausible is not False and not conflict:
        status = "corroborated"
    else:
        status = "unverified"
    return {"status": status, "conflict": conflict}
