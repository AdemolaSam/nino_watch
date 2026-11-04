"""Pure clustering helpers: geo distance, syndication, outlet independence.

No I/O; heavily unit-tested. Used by services/cluster.py (B5) and the
verification engine (B7).
"""

import math
import re

EARTH_KM = 6371.0
SHINGLE_SIZE = 5
SYNDICATION_THRESHOLD = 0.85

WIRE_MARKERS = (
    "reuters",
    "associated press",
    "the associated press",
    " - ap ",
    "(ap)",
    "afp",
    "deutsche presse-agentur",
    " - dpa",
    "xinhua",
    "bloomberg",
)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    a1, o1, a2, o2 = map(math.radians, (lat1, lng1, lat2, lng2))
    dlat, dlng = a2 - a1, o2 - o1
    h = math.sin(dlat / 2) ** 2 + math.cos(a1) * math.cos(a2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(h))


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def shingles(text: str, size: int = SHINGLE_SIZE) -> set[tuple[str, ...]]:
    tokens = _words(text)
    if len(tokens) < size:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[i : i + size]) for i in range(len(tokens) - size + 1)}


def shingle_similarity(a: str, b: str) -> float:
    set_a, set_b = shingles(a), shingles(b)
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def wire_tag(title: str, excerpt: str) -> str | None:
    """Heuristic wire-service tag from byline markers; None when absent."""
    blob = f"{title}\n{excerpt}".lower()
    for marker in WIRE_MARKERS:
        if marker in blob:
            return marker.strip(" -()")
    return None


def normalize_place(place: str) -> str:
    return re.sub(r"\s+", " ", place.strip().lower())


def _find(parent: list[int], i: int) -> int:
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def _union(parent: list[int], i: int, j: int) -> None:
    parent[_find(parent, i)] = _find(parent, j)


def count_independent_outlets(articles: list[dict]) -> int:
    """Distinct publishers after collapsing ownership, syndication, officials.

    Each article: {publisher, ownership_group|None, title, excerpt}.
    Official-source items (ownership_group == "official") never count here;
    they feed the official_match signal instead.
    """
    news = [a for a in articles if (a.get("ownership_group") or "") != "official"]
    n = len(news)
    if n == 0:
        return 0
    parent = list(range(n))
    keys = []
    for i, item in enumerate(news):
        raw = item.get("ownership_group") or item.get("publisher") or f"#{i}"
        keys.append(raw.strip().lower())
    for i in range(n):
        for j in range(i + 1, n):
            if keys[i] == keys[j]:
                _union(parent, i, j)
                continue
            tag_i = wire_tag(news[i].get("title", ""), news[i].get("excerpt", ""))
            tag_j = wire_tag(news[j].get("title", ""), news[j].get("excerpt", ""))
            if tag_i and tag_i == tag_j:
                _union(parent, i, j)
                continue
            sim = shingle_similarity(
                f"{news[i].get('title', '')} {news[i].get('excerpt', '')}",
                f"{news[j].get('title', '')} {news[j].get('excerpt', '')}",
            )
            if sim > SYNDICATION_THRESHOLD:
                _union(parent, i, j)
    return len({_find(parent, i) for i in range(n)})
