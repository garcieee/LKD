import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import ors

AYALA = (14.5547, 121.0244)
GIL_PUYAT = (14.5560, 121.0020)  # 2.4 km west: too far to walk, so a ride is the answer
PARAMS = {"from_lat": AYALA[0], "from_lng": AYALA[1], "to_lat": GIL_PUYAT[0], "to_lng": GIL_PUYAT[1]}
STREET = [[121.0244, 14.5547, 12.0], [121.0240, 14.5550, 12.0]]  # a 100 m, 80 s street walk


def ors_walk(_req):
    body = {"features": [{"geometry": {"type": "LineString", "coordinates": STREET}, "properties": {"summary": {"distance": 100.0, "duration": 80.0}}}]}
    return httpx.Response(200, json=body)


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setattr(ors, "ORS_API_KEY", "test-key")


def report(rid, lat, lng, category="pothole"):
    return {"id": rid, "category": category, "lat": lat, "lng": lng, "heading": None, "note": "", "photo_url": f"/photos/{rid}.jpg", "status": "open", "created_at": "2026-10-06T00:00:00+00:00", "updated_at": "2026-10-06T00:00:00+00:00"}


def make_client(tmp_path, handler, reports=()):
    app = create_app(tmp_path)
    for r in reports:
        app.state.store.add(r)
    app.state.ors_client = httpx.Client(transport=httpx.MockTransport(handler))
    return TestClient(app)


def test_walk_legs_get_street_routes_and_the_ride_stays_an_estimate(tmp_path):
    seen = []
    c = make_client(tmp_path, lambda req: seen.append(req) or ors_walk(req))
    r = c.get("/route/commute", params=PARAMS)
    assert r.status_code == 200
    options = r.json()
    assert 1 <= len(options) <= 3
    assert options[0]["tags"][0] == "earliest"
    assert [o["total_s"] for o in options] == sorted(o["total_s"] for o in options)
    for o in options:
        walks = [leg for leg in o["legs"] if leg["kind"] == "walk"]
        rides = [leg for leg in o["legs"] if leg["kind"] != "walk"]
        assert len(rides) == 1 and len(walks) == 2
        assert all(w["duration_s"] == 80.0 and len(w["geometry"][0]) == 2 for w in walks), "ORS route in, elevation dropped"
        assert o["walk_s"] == 160.0
        assert o["total_s"] == 160.0 + rides[0]["duration_s"]
    assert all(req.url.path == "/v2/directions/foot-walking/geojson" for req in seen)
    assert len(seen) <= 6


def test_the_list_survives_ors_being_down(tmp_path):
    c = make_client(tmp_path, lambda req: httpx.Response(500))
    options = c.get("/route/commute", params=PARAMS).json()
    assert options, "estimates stand in for the street routes"
    assert all(leg["duration_s"] > 0 for o in options for leg in o["legs"])


def test_both_ends_must_be_in_makati(tmp_path):
    c = make_client(tmp_path, ors_walk)
    r = c.get("/route/commute", params={**PARAMS, "to_lat": 14.7, "to_lng": 121.2})
    assert r.status_code == 422


def test_walking_legs_follow_the_picked_mode(tmp_path):
    seen = []
    # A pothole by the start, so the walk out of Ayala has a zone to steer around.
    pothole = report("p", 14.5546, 121.0243)
    c = make_client(tmp_path, lambda req: seen.append(req) or ors_walk(req), [pothole])

    def sent(mode):
        seen.clear()
        assert c.get("/route/commute", params={**PARAMS, "mode": mode}).status_code == 200
        return [(req.url.path, json.loads(req.content)) for req in seen]

    assert all(path.endswith("/wheelchair/geojson") for path, _ in sent("accessible"))
    walkable = sent("walkable")
    assert all(path.endswith("/foot-walking/geojson") for path, _ in walkable)
    assert any("options" in body for _, body in walkable), "the pothole becomes a no-go zone"
    fastest = sent("fastest")
    assert all(path.endswith("/foot-walking/geojson") and "options" not in body for path, body in fastest)
    assert all(body["preference"] == "fastest" for _, body in fastest)


def test_the_accessible_mode_skips_a_station_with_a_barrier_at_it(tmp_path):
    c = make_client(tmp_path, ors_walk)

    def boarding(mode):  # where each option's ride starts, [lng, lat]
        options = c.get("/route/commute", params={**PARAMS, "mode": mode}).json()
        return [next(leg for leg in o["legs"] if leg["kind"] != "walk")["geometry"][0] for o in options]

    lng, lat = boarding("accessible")[0]
    c.app.state.store.add(report("lift", lat, lng, category="broken_elevator"))
    assert [lng, lat] not in boarding("accessible"), "no boarding there in a wheelchair"
    assert [lng, lat] in boarding("walkable"), "on foot the stairs still work"


def test_mode_defaults_to_walkable_and_rejects_unknown_modes(tmp_path):
    seen = []
    c = make_client(tmp_path, lambda req: seen.append(req) or ors_walk(req))
    assert c.get("/route/commute", params=PARAMS).status_code == 200
    assert all(json.loads(req.content)["preference"] == "recommended" for req in seen)
    assert c.get("/route/commute", params={**PARAMS, "mode": "teleport"}).status_code == 422
