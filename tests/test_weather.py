from datetime import date

from app.llm.cache import LlmCache
from app.services import weather


def test_circular_day_distance_same():
    assert weather.circular_day_distance(10, 28, 10, 28) == 0


def test_circular_day_distance_wraps_year():
    assert weather.circular_day_distance(1, 1, 12, 30) == 2


def test_compute_window_mean_picks_window():
    times = ["2020-10-26", "2020-10-28", "2020-10-30", "2020-11-05", "2021-10-28"]
    values = [40.0, 42.0, 44.0, 50.0, 41.0]
    mean = weather.compute_window_mean(times, values, 10, 28, 2015, 2025)
    assert mean == (40.0 + 42.0 + 44.0 + 41.0) / 4


def test_compute_window_mean_skips_missing_and_outside_years():
    times = ["2020-10-28", "2020-10-28", "2030-10-28"]
    values = [None, 40.0, 99.0]
    assert weather.compute_window_mean(times, values, 10, 28, 2015, 2025) == 40.0


def test_compute_window_mean_empty_none():
    assert weather.compute_window_mean([], [], 10, 28, 2015, 2025) is None


def test_grid_for_bbox_shape():
    cols, rows, cells = weather.grid_for_bbox([-17, 2, 40, 24])
    assert cols == 24
    assert 4 <= rows <= 24
    assert len(cells) == cols * rows
    lats = [c[0] for c in cells]
    lngs = [c[1] for c in cells]
    assert min(lats) >= 2 and max(lats) <= 24
    assert min(lngs) >= -17 and max(lngs) <= 40


async def test_heat_plausible_hot_day(monkeypatch):
    async def fake_max(lat, lng, day, cache=None):
        return 41.0

    async def fake_means(coords, month, day, start, end, cache=None):
        return {c: 33.0 for c in coords}

    monkeypatch.setattr(weather, "daily_max_for", fake_max)
    monkeypatch.setattr(weather, "baseline_means", fake_means)
    ok, numbers = await weather.heat_plausible(
        12.0, 8.5, date(2026, 10, 28), 35, 1.5, (2015, 2025), LlmCache()
    )
    assert ok is True
    assert numbers["observed_max_c"] == 41.0
    assert numbers["anomaly_c"] == 8.0


async def test_heat_plausible_anomaly_only(monkeypatch):
    async def fake_max(lat, lng, day, cache=None):
        return 30.0

    async def fake_means(coords, month, day, start, end, cache=None):
        return {c: 27.0 for c in coords}

    monkeypatch.setattr(weather, "daily_max_for", fake_max)
    monkeypatch.setattr(weather, "baseline_means", fake_means)
    ok, numbers = await weather.heat_plausible(
        12.0, 8.5, date(2026, 10, 28), 35, 1.5, (2015, 2025), LlmCache()
    )
    assert ok is True
    assert numbers["anomaly_c"] == 3.0


async def test_heat_implausible_mild_day(monkeypatch):
    async def fake_max(lat, lng, day, cache=None):
        return 28.0

    async def fake_means(coords, month, day, start, end, cache=None):
        return {c: 27.5 for c in coords}

    monkeypatch.setattr(weather, "daily_max_for", fake_max)
    monkeypatch.setattr(weather, "baseline_means", fake_means)
    ok, _ = await weather.heat_plausible(
        12.0, 8.5, date(2026, 10, 28), 35, 1.5, (2015, 2025), LlmCache()
    )
    assert ok is False


async def test_heat_no_data_none(monkeypatch):
    async def no_max(lat, lng, day, cache=None):
        return None

    monkeypatch.setattr(weather, "daily_max_for", no_max)
    ok, numbers = await weather.plausibility_for(
        "heat_illness", 12.0, 8.5, date(2026, 10, 28), {}, LlmCache()
    )
    assert ok is None
    assert numbers["reason"] == "no weather data"


async def test_non_heat_unchecked():
    ok, numbers = await weather.plausibility_for(
        "flood", 6.5, 3.4, date(2026, 10, 20), {}, LlmCache()
    )
    assert ok is None
    assert "flood" in numbers["reason"]


async def test_missing_coords_none():
    ok, _ = await weather.plausibility_for(
        "heat_death", None, None, date(2026, 10, 28), {}, LlmCache()
    )
    assert ok is None


async def test_daily_max_forecast_path(monkeypatch):
    from datetime import UTC, datetime

    today = datetime.now(UTC).date()

    async def fake_fetch(url, params):
        assert "forecast" in url
        return {"daily": {"time": [today.isoformat()], "temperature_2m_max": [39.5]}}

    monkeypatch.setattr(weather, "fetch_json", fake_fetch)
    value = await weather.daily_max_for(12.0, 8.5, today, LlmCache())
    assert value == 39.5


async def test_fetch_json_retries_on_429(monkeypatch):
    import httpx

    calls = []

    class FakeResponse:
        def __init__(self, status_code):
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code != 200:
                raise httpx.HTTPStatusError(
                    f"{self.status_code}", request=None, response=self  # type: ignore[arg-type]
                )

        def json(self):
            return {"ok": True}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            calls.append(url)
            return FakeResponse(429 if len(calls) < 2 else 200)

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(weather, "FETCH_BACKOFF_SECONDS", 0.0)
    assert await weather.fetch_json("https://example.com", {}) == {"ok": True}
    assert len(calls) == 2


async def test_daily_max_archive_path(monkeypatch):
    async def fake_fetch(url, params):
        assert "archive" in url
        return {"daily": {"time": ["2020-05-01"], "temperature_2m_max": [36.0]}}

    monkeypatch.setattr(weather, "fetch_json", fake_fetch)
    value = await weather.daily_max_for(12.0, 8.5, date(2020, 5, 1), LlmCache())
    assert value == 36.0
