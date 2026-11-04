from app.domain.cluster import (
    count_independent_outlets,
    haversine_km,
    normalize_place,
    shingle_similarity,
    wire_tag,
)


def test_haversine_lagos_ibadan():
    # ~117 km apart.
    assert 100 < haversine_km(6.45, 3.39, 7.38, 3.95) < 135


def test_haversine_same_point_zero():
    assert haversine_km(12.0, 8.5, 12.0, 8.5) == 0.0


def test_haversine_nearby_under_50km():
    # Kano city points a few km apart.
    assert haversine_km(12.0, 8.52, 12.03, 8.55) < 50


def test_shingle_identical():
    text = "heat wave hits the northern city hard today"
    assert shingle_similarity(text, text) == 1.0


def test_shingle_unrelated_low():
    assert shingle_similarity("heat wave hits Kano hard", "football team wins cup final") < 0.3


def test_shingle_empty_zero():
    assert shingle_similarity("", "something") == 0.0


def test_wire_tag_reuters():
    assert wire_tag("Floods hit Lagos", "Lagos (Reuters) - waters rose") == "reuters"


def test_wire_tag_none():
    assert wire_tag("Floods hit Lagos", "Our correspondent reports waters rose") is None


def test_normalize_place():
    assert normalize_place("  Quezon   City ") == "quezon city"


def article(publisher, group=None, title="t", excerpt="e"):
    return {"publisher": publisher, "ownership_group": group, "title": title, "excerpt": excerpt}


def test_independence_distinct_outlets():
    punch = article("Punch", "punch", "Heat grips Kano", "Traders fainted at noon")
    vanguard = article("Vanguard", "vanguard", "Governors meet", "Tariff talks in Abuja")
    assert count_independent_outlets([punch, vanguard]) == 2


def test_independence_collapses_ownership_group():
    articles = [article("Paper A", "group"), article("Paper B", "group")]
    assert count_independent_outlets(articles) == 1


def test_independence_collapses_same_publisher():
    articles = [article("Punch"), article("Punch")]
    assert count_independent_outlets(articles) == 1


def test_independence_collapses_syndication():
    text = "waters rose fast in the riverside districts overnight Tuesday"
    articles = [article("A", "g1", "Flood", text), article("B", "g2", "Flood", text)]
    assert count_independent_outlets(articles) == 1


def test_independence_collapses_wire_copies():
    articles = [
        article("A", "g1", "Flood", "Lagos (Reuters) - waters rose fast overnight"),
        article("B", "g2", "Deluge", "LAGOS (Reuters) - rivers burst banks at dawn"),
    ]
    assert count_independent_outlets(articles) == 1


def test_independence_excludes_official():
    articles = [article("Ministry", "official"), article("Punch", "punch")]
    assert count_independent_outlets(articles) == 1


def test_independence_empty_zero():
    assert count_independent_outlets([]) == 0
