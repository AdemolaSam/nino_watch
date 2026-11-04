from app.domain.verification import RULE_VERSION, compute_verification


def test_rule_version():
    assert RULE_VERSION == "v1"


def test_confirmed_official_plus_plausible():
    assert compute_verification(
        independent_outlets=1, official_match=True,
        official_contradict=False, weather_plausible=True,
    ) == {"status": "confirmed", "conflict": False}


def test_confirmed_weather_unchecked():
    assert compute_verification(
        independent_outlets=1, official_match=True,
        official_contradict=False, weather_plausible=None,
    ) == {"status": "confirmed", "conflict": False}


def test_corroborated_two_outlets():
    assert compute_verification(
        independent_outlets=2, official_match=False,
        official_contradict=False, weather_plausible=True,
    ) == {"status": "corroborated", "conflict": False}


def test_corroborated_weather_unchecked():
    assert compute_verification(
        independent_outlets=3, official_match=False,
        official_contradict=False, weather_plausible=None,
    ) == {"status": "corroborated", "conflict": False}


def test_unverified_single_source():
    assert compute_verification(
        independent_outlets=1, official_match=False,
        official_contradict=False, weather_plausible=None,
    ) == {"status": "unverified", "conflict": False}


def test_unverified_implausible_weather_conflicts():
    assert compute_verification(
        independent_outlets=3, official_match=False,
        official_contradict=False, weather_plausible=False,
    ) == {"status": "unverified", "conflict": True}


def test_unverified_official_contradiction_conflicts():
    assert compute_verification(
        independent_outlets=3, official_match=False,
        official_contradict=True, weather_plausible=True,
    ) == {"status": "unverified", "conflict": True}


def test_official_match_blocked_by_conflict():
    assert compute_verification(
        independent_outlets=1, official_match=True,
        official_contradict=True, weather_plausible=True,
    ) == {"status": "unverified", "conflict": True}


def test_official_match_blocked_by_implausible_weather():
    assert compute_verification(
        independent_outlets=1, official_match=True,
        official_contradict=False, weather_plausible=False,
    ) == {"status": "unverified", "conflict": True}
