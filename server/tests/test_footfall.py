import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import footfall


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path))


def get(client, **params):
    r = client.get("/footfall", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_it_says_it_is_an_estimate(client):
    body = get(client, day="mon", hour=8)
    assert body["kind"] == "estimate" and body["method"] == footfall.METHOD


def test_every_hub_gets_a_point_plus_one_anchor_per_district(client):
    body = get(client, day="mon", hour=8)
    hubs = client.get("/transit/hubs", params={"limit": 50}).json()
    assert sum(p["kind"] == "hub" for p in body["points"]) == len(hubs) == 43
    assert sum(p["kind"] == "anchor" for p in body["points"]) == len(body["districts"])


def test_ayala_is_the_top_district_and_tier_one(client):
    districts = get(client, day="mon", hour=8)["districts"]
    assert districts[0]["id"] == "ayala-cbd" and districts[0]["tier"] == 1
    assert districts[0]["route_ends"] == 9, "Ayala ends 9 of the 56 routes"
    assert all(d["tier"] in (1, 2, 3) for d in districts)


def test_the_strongest_point_peaks_at_100_and_bands_hold(client):
    points = get(client, day="mon", hour=18)["points"]
    assert max(p["index"] for p in points) <= 100
    assert all(0 <= p["lower"] <= p["index"] <= p["upper"] <= 100 for p in points)


def test_the_cbd_is_busier_on_a_weekday_commute_than_at_3am_or_on_a_sunday(client):
    def ayala(**when):
        return next(d for d in get(client, **when)["districts"] if d["id"] == "ayala-cbd")["index"]

    assert ayala(day="tue", hour=18) > 3 * ayala(day="tue", hour=3)
    assert ayala(day="tue", hour=18) > 1.5 * ayala(day="sun", hour=18)


def test_poblacion_is_a_friday_night_place_not_a_monday_morning_one(client):
    def poblacion(**when):
        return next(d for d in get(client, **when)["districts"] if d["id"] == "poblacion")["index"]

    assert poblacion(day="fri", hour=23) > 3 * poblacion(day="mon", hour=8)


def test_salcedo_and_legazpi_are_weekend_morning_places(client):
    def salcedo(**when):
        return next(d for d in get(client, **when)["districts"] if d["id"] == "salcedo-village")["index"]

    assert salcedo(day="sat", hour=10) > 2 * salcedo(day="wed", hour=10)


def test_day_and_hour_default_to_now_in_manila(client):
    body = get(client)
    assert body["day"] in footfall.DAYS and 0 <= body["hour"] < 24


def test_bad_day_or_hour_is_rejected(client):
    assert client.get("/footfall", params={"day": "funday"}).status_code == 422
    assert client.get("/footfall", params={"hour": 24}).status_code == 422


def test_late_night_peaks_wrap_past_midnight():
    profile = {"floor": 0.0, "weekday": [{"at": 23.5, "w": 1.0, "sd": 1.0}]}
    assert footfall.curve(profile, "mon", 0.5) == pytest.approx(footfall.curve(profile, "mon", 22.5))


def test_a_missing_model_file_answers_503(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.FOOTFALL_DIR", tmp_path)
    r = TestClient(create_app(tmp_path)).get("/footfall")
    assert r.status_code == 503
