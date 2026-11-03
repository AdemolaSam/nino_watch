from app.services import ingest
from app.services.ingest import (
    normalize_url,
    parse_feed,
    strip_html,
    truncate,
)
from app.workers.schedule import beat_schedule

SAMPLE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Test Outlet</title>
<link>https://example.com</link>
<item>
<title>Heat wave hits <b>Kano</b></title>
<link>https://example.com/kano-heat?utm_source=rss&amp;x=1</link>
<pubDate>Tue, 28 Oct 2026 10:00:00 GMT</pubDate>
<description><p>Temperatures <i>rose</i> above 42C.</p></description>
</item>
<item>
<title>No link here</title>
<description>Skipped, no URL.</description>
</item>
</channel>
</rss>
"""


def test_normalize_url_strips_tracking_and_fragment():
    assert (
        normalize_url("https://example.com/a?utm_source=rss&x=1#frag")
        == "https://example.com/a?x=1"
    )


def test_strip_html():
    assert strip_html("<p>Hello <b>world</b> &amp; co.</p>") == "Hello world & co."


def test_truncate_short():
    assert truncate("short") == "short"


def test_truncate_long_breaks_on_word():
    assert truncate("alpha beta gamma delta", 12) == "alpha beta…"


def test_parse_feed_items():
    items = parse_feed(SAMPLE_RSS, "https://example.com/feed")
    assert len(items) == 1
    item = items[0]
    assert item["url"] == "https://example.com/kano-heat?x=1"
    assert item["title"] == "Heat wave hits Kano"
    assert item["excerpt"] == "Temperatures rose above 42C."
    assert item["published_at"] is not None
    assert item["published_at"].year == 2026


def test_parse_feed_unparseable_raises():
    import pytest

    with pytest.raises(ValueError):
        parse_feed(b"this is not xml at all {{{", "https://example.com/bad")


def test_beat_schedules_ingest():
    assert beat_schedule["ingest-all"]["task"] == "ninowatch.ingest_all"
    assert beat_schedule["ingest-all"]["schedule"] == 2700


def test_detect_language_english():
    assert ingest.detect_language("The city council met on Tuesday to discuss water.") == "en"


def test_detect_language_garbage_returns_none():
    assert ingest.detect_language("") is None


def test_host_delay_defaults_to_floor():
    ingest._robots_cache.clear()
    ingest._host_last_fetch.clear()
    assert ingest._host_delay("https://example.com/feed") == ingest.MIN_HOST_INTERVAL_SECONDS


def test_host_delay_honors_robots_crawl_delay():
    from urllib.robotparser import RobotFileParser

    parser = RobotFileParser()
    parser.parse(["User-agent: *", "Crawl-delay: 10"])
    ingest._robots_cache["https://example.com"] = (0.0, parser)
    try:
        assert ingest._host_delay("https://example.com/feed") == 10
    finally:
        ingest._robots_cache.clear()
