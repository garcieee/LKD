from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import footfall, forecast

NOW = "2026-10-06T20:00:00+08:00"  # Tuesday


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path))


def series(client, **params):
    r = client.get("/footfall/series", params={"at": NOW, **params})
    assert r.status_code == 200, r.text
    return r.json()


def test_history_then_forecast_one_point_per_hour(client):
    body = series(client, past_days=2, future_days=1)
    kinds = [p["kind"] for p in body["points"]]
    assert kinds == ["history"] * 48 + ["forecast"] * 24
    times = [datetime.fromisoformat(p["t"]) for p in body["points"]]
    assert all((b - a).total_seconds() == 3600 for a, b in zip(times, times[1:]))
    assert body["points"][47]["t"] == NOW, "the last history point is this hour"


def test_the_past_is_labeled_simulated(client):
    body = series(client)
    assert body["history_source"] == "simulated" and body["method"] == forecast.METHOD


def test_the_same_request_gives_the_same_series(client):
    assert series(client, zone="poblacion") == series(client, zone="poblacion")


def test_the_forecast_band_brackets_the_forecast_and_stays_in_range(client):
    fc = [p for p in series(client, zone="ayala-cbd")["points"] if p["kind"] == "forecast"]
    assert all(0 <= p["lower"] <= p["index"] <= p["upper"] <= 100 for p in fc)
    assert fc[-1]["upper"] - fc[-1]["lower"] > fc[0]["upper"] - fc[0]["lower"], "further out is less certain"


def test_the_forecast_keeps_the_weekly_rhythm(client):
    fc = {p["t"]: p["index"] for p in series(client, zone="ayala-cbd", future_days=3)["points"] if p["kind"] == "forecast"}
    wed_6pm, wed_3am = fc["2026-10-07T18:00:00+08:00"], fc["2026-10-07T03:00:00+08:00"]
    assert wed_6pm > 3 * wed_3am


def test_poblacion_peaks_late_on_a_friday_night(client):
    body = series(client, zone="poblacion", past_days=1, future_days=7, at="2026-10-06T20:00:00+08:00")
    fri = [p for p in body["points"] if p["t"].startswith("2026-10-09") and p["kind"] == "forecast"]
    peak = max(fri, key=lambda p: p["index"])
    assert peak["t"][11:13] in ("22", "23", "00", "21")


def test_the_whole_city_is_a_zone_too(client):
    body = series(client, zone="all")
    assert body["name"] == "All of Makati" and body["backtest_smape_pct"] < 40


def test_unknown_zone_is_404_and_out_of_range_days_are_422(client):
    assert client.get("/footfall/series", params={"zone": "narnia"}).status_code == 404
    assert client.get("/footfall/series", params={"past_days": 99}).status_code == 422


def test_a_naive_time_is_read_as_manila_time(client):
    a = series(client, at="2026-10-06T20:00:00")
    assert a["now"] == NOW


def test_rain_days_are_quieter_on_average():
    days = [datetime(2026, 9, 1 + i).date() for i in range(28)]
    f = [forecast.day_factor("ayala-cbd", d) for d in days]
    assert min(f) < 0.9 < 1.0 < max(f), "some days are rainy, some are not"


def test_the_forecast_returns_to_the_weekly_pattern_after_a_bad_day():
    model = footfall.load_model(footfall.Path("data/footfall"), footfall.Path("data/transit"), [])
    assert model is not None  # no hubs: district anchors only, enough to build a series
    now = datetime(2026, 10, 6, 20, tzinfo=footfall.MANILA)
    hist = forecast.simulate(model, "ayala-cbd", now)
    hist[-24:] = [(t, v * 0.5) for t, v in hist[-24:]]  # a washed-out last day
    fc = forecast.forecast(hist, 72)
    seasonal_next_week = [v for t, v in hist if t.weekday() == fc[48]["t"].weekday() and t.hour == fc[48]["t"].hour]
    assert fc[48]["index"] > 0.8 * (sum(seasonal_next_week) / len(seasonal_next_week)), "the dip fades within two days"
