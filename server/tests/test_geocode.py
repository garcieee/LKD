import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import CITY_BOUNDS
from app.main import create_app
from app.services import ors

WEST, SOUTH, EAST, NORTH = CITY_BOUNDS
AYALA = {
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [121.0244, 14.5547]},
    "properties": {"label": "Ayala Triangle Gardens, Makati, Philippines"},
}


def make_client(tmp_path, handler):
    """An app whose OpenRouteService calls go to `handler` instead of the internet."""
    app = create_app(tmp_path)
    app.state.ors_client = httpx.Client(transport=httpx.MockTransport(handler))
    return TestClient(app)


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setattr(ors, "ORS_API_KEY", "test-key")


def test_places_come_back_as_label_lat_lng(tmp_path):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"features": [AYALA]})

    r = make_client(tmp_path, handler).get("/geocode", params={"q": " Ayala "})
    assert r.status_code == 200
    assert r.json() == [{"label": AYALA["properties"]["label"], "lat": 14.5547, "lng": 121.0244}]
    sent = seen[0]
    assert sent.headers["authorization"] == "test-key"
    assert "test-key" not in str(sent.url), "the key must not be in the URL"
    q = dict(sent.url.params)
    assert q["text"] == "Ayala"
    assert [float(q[f"boundary.rect.{k}"]) for k in ("min_lon", "min_lat", "max_lon", "max_lat")] == [WEST, SOUTH, EAST, NORTH]
    assert "focus.point.lat" not in q


def test_user_position_becomes_the_focus_point(tmp_path):
    seen = []
    c = make_client(tmp_path, lambda req: seen.append(req) or httpx.Response(200, json={"features": []}))
    assert c.get("/geocode", params={"q": "Ayala", "lat": 14.55, "lng": 121.02}).json() == []
    q = dict(seen[0].url.params)
    assert (q["focus.point.lat"], q["focus.point.lon"]) == ("14.55", "121.02")


def test_malformed_features_are_skipped(tmp_path):
    bad = [{}, {"geometry": {"coordinates": []}, "properties": {"label": "x"}}, {"geometry": {"coordinates": [1, 2]}, "properties": {}}]
    c = make_client(tmp_path, lambda req: httpx.Response(200, json={"features": [*bad, AYALA]}))
    assert [p["label"] for p in c.get("/geocode", params={"q": "Ayala"}).json()] == [AYALA["properties"]["label"]]


def test_no_key_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(ors, "ORS_API_KEY", "")
    r = make_client(tmp_path, lambda req: pytest.fail("must not call ORS without a key")).get("/geocode", params={"q": "Ayala"})
    assert r.status_code == 503 and "ORS_API_KEY" in r.json()["detail"]


@pytest.mark.parametrize(
    "answer, status",
    [
        (lambda req: httpx.Response(429), 503),  # rate limited: try later
        (lambda req: httpx.Response(403), 502),  # bad key: the app only hears "unavailable"
        (lambda req: httpx.Response(500), 502),
        (lambda req: (_ for _ in ()).throw(httpx.ConnectTimeout("slow")), 502),
    ],
)
def test_orouteservice_trouble_is_a_clean_error(tmp_path, answer, status):
    r = make_client(tmp_path, answer).get("/geocode", params={"q": "Ayala"})
    assert r.status_code == status
    assert "test-key" not in r.text


def test_bad_input_is_rejected(tmp_path):
    c = make_client(tmp_path, lambda req: pytest.fail("must not call ORS"))
    assert c.get("/geocode", params={"q": "a"}).status_code == 422
    assert c.get("/geocode").status_code == 422
    assert c.get("/geocode", params={"q": "Ayala", "lat": 14.5}).status_code == 422
    assert c.get("/geocode", params={"q": "Ayala", "lat": 99, "lng": 121}).status_code == 422
