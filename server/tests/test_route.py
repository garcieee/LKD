import json
import math

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import hazards, ors

AYALA = (14.5547, 121.0244)
GREENBELT = (14.5530, 121.0210)
PARAMS = {"from_lat": AYALA[0], "from_lng": AYALA[1], "to_lat": GREENBELT[0], "to_lng": GREENBELT[1]}
# A short street with elevation as ORS sends it ([lng, lat, ele]).
LINE = [[121.0244, 14.5547, 12.0], [121.0230, 14.5540, 12.0], [121.0210, 14.5530, 11.0]]


def ors_route(distance=480.5, duration=345.2, coords=LINE):
    return {"features": [{"geometry": {"type": "LineString", "coordinates": coords}, "properties": {"summary": {"distance": distance, "duration": duration}}}]}


def report(rid, lat, lng, status="open", category="pothole"):
    return {"id": rid, "category": category, "lat": lat, "lng": lng, "heading": None, "note": "", "photo_url": f"/photos/{rid}.jpg", "status": status, "created_at": "2026-10-06T00:00:00+00:00", "updated_at": "2026-10-06T00:00:00+00:00"}


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setattr(ors, "ORS_API_KEY", "test-key")


def make_client(tmp_path, handler, reports=()):
    app = create_app(tmp_path)
    for r in reports:
        app.state.store.add(r)
    app.state.ors_client = httpx.Client(transport=httpx.MockTransport(handler))
    return TestClient(app)


def test_fastest_is_plain_foot_walking_with_no_zones(tmp_path):
    seen = []
    c = make_client(tmp_path, lambda req: seen.append(req) or httpx.Response(200, json=ors_route()), [report("a", 14.5540, 121.0230)])
    r = c.get("/route/walk", params={**PARAMS, "mode": "fastest"})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "fastest" and body["distance_m"] == 480.5 and body["duration_s"] == 345.2
    assert body["geometry"] == [[121.0244, 14.5547], [121.023, 14.554], [121.021, 14.553]], "elevation dropped"
    assert body["hazard_ids"] == ["a"], "it passes the pothole, and says so"
    assert body["avoids_hazards"] is False
    req = seen[0]
    assert req.url.path == "/v2/directions/foot-walking/geojson"
    assert req.headers["authorization"] == "test-key"
    sent = json.loads(req.content)
    assert sent["coordinates"] == [[AYALA[1], AYALA[0]], [GREENBELT[1], GREENBELT[0]]], "ORS takes [lng, lat]"
    assert sent["preference"] == "fastest" and "options" not in sent


def test_walkable_steers_around_unresolved_reports_only(tmp_path):
    seen = []
    c = make_client(
        tmp_path,
        lambda req: seen.append(json.loads(req.content)) or httpx.Response(200, json=ors_route(coords=[[121.0244, 14.5547], [121.0210, 14.5530]])),
        [report("open", 14.5538, 121.0225), report("fixed", 14.5541, 121.0232, status="fixed")],
    )
    body = c.get("/route/walk", params={**PARAMS, "mode": "walkable"}).json()
    sent = seen[0]
    zones = sent["options"]["avoid_polygons"]
    assert zones["type"] == "MultiPolygon" and len(zones["coordinates"]) == 1, "the fixed report gets no zone"
    assert sent["preference"] == "recommended"
    assert body["avoids_hazards"] is True


def test_accessible_uses_the_wheelchair_profile_and_the_same_zones(tmp_path):
    seen = []
    c = make_client(tmp_path, lambda req: seen.append(req) or httpx.Response(200, json=ors_route()), [report("a", 14.5538, 121.0225)])
    body = c.get("/route/walk", params={**PARAMS, "mode": "accessible"}).json()
    assert seen[0].url.path == "/v2/directions/wheelchair/geojson"
    assert "avoid_polygons" in json.loads(seen[0].content)["options"]
    assert body["mode"] == "accessible"


def zones(body: dict) -> int:
    return len(body.get("options", {}).get("avoid_polygons", {}).get("coordinates", []))


# A pothole and a missing ramp, both on LINE and far enough from either end to get a zone.
HOLE_AND_RAMP = (report("hole", 14.5540, 121.0230), report("ramp", 14.5535, 121.0220, category="missing_ramp"))


@pytest.mark.parametrize("mode, zone_count, passed", [("fastest", 0, ["hole"]), ("walkable", 1, ["hole"]), ("accessible", 2, ["hole", "ramp"])])
def test_an_accessibility_barrier_counts_only_on_the_accessible_route(tmp_path, mode, zone_count, passed):
    sent = []
    c = make_client(tmp_path, lambda req: sent.append(json.loads(req.content)) or httpx.Response(200, json=ors_route()), HOLE_AND_RAMP)
    body = c.get("/route/walk", params={**PARAMS, "mode": mode}).json()
    assert zones(sent[0]) == zone_count, "the ramp gets a zone only where a wheelchair cannot pass it"
    assert body["hazard_ids"] == passed


def test_boxed_in_by_barriers_the_accessible_route_still_keeps_clear_of_hazards(tmp_path):
    sent = []

    def handler(req):
        sent.append(zones(json.loads(req.content)))
        return httpx.Response(404, json={"error": {"code": 2009}}) if sent[-1] == 2 else httpx.Response(200, json=ors_route())

    body = make_client(tmp_path, handler, HOLE_AND_RAMP).get("/route/walk", params={**PARAMS, "mode": "accessible"}).json()
    assert sent == [2, 1], "the ramp's zone goes first, the pothole's stays"
    assert body["avoids_hazards"] is False and body["hazard_ids"] == ["hole", "ramp"]


def test_walkable_is_the_default_mode(tmp_path):
    c = make_client(tmp_path, lambda req: httpx.Response(200, json=ors_route()))
    assert c.get("/route/walk", params=PARAMS).json()["mode"] == "walkable"


@pytest.mark.parametrize("mode", ["walkable", "accessible"])
def test_a_zone_that_boxes_the_trip_in_is_dropped_and_the_route_says_so(tmp_path, mode):
    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(404, json={"error": {"code": 2009}}) if "options" in bodies[-1] else httpx.Response(200, json=ors_route())

    c = make_client(tmp_path, handler, [report("a", 14.5538, 121.0225)])
    body = c.get("/route/walk", params={**PARAMS, "mode": mode}).json()
    # With no barrier on the way, Accessible has nothing to drop first, so it asks ORS no more often than Walkable.
    assert len(bodies) == 2 and "options" in bodies[0] and "options" not in bodies[1]
    assert body["avoids_hazards"] is False


def test_no_route_even_without_zones_is_a_404(tmp_path):
    c = make_client(tmp_path, lambda req: httpx.Response(404, json={}))
    r = c.get("/route/walk", params={**PARAMS, "mode": "fastest"})
    assert r.status_code == 404 and "No walking route" in r.json()["detail"]


@pytest.mark.parametrize("status, expect", [(429, 503), (403, 502), (500, 502)])
def test_orouteservice_trouble_is_a_clean_error(tmp_path, status, expect):
    r = make_client(tmp_path, lambda req: httpx.Response(status)).get("/route/walk", params=PARAMS)
    assert r.status_code == expect and "test-key" not in r.text


def test_garbled_answer_is_a_502_not_a_crash(tmp_path):
    r = make_client(tmp_path, lambda req: httpx.Response(200, json={"features": []})).get("/route/walk", params=PARAMS)
    assert r.status_code == 502


def test_no_key_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(ors, "ORS_API_KEY", "")
    r = make_client(tmp_path, lambda req: pytest.fail("no call without a key")).get("/route/walk", params=PARAMS)
    assert r.status_code == 503 and "ORS_API_KEY" in r.json()["detail"]


@pytest.mark.parametrize("override", [{"to_lat": 14.70}, {"from_lng": 120.5}, {"from_lat": math.nan}])
def test_both_ends_must_be_in_makati(tmp_path, override):
    c = make_client(tmp_path, lambda req: pytest.fail("must not call ORS"))
    assert c.get("/route/walk", params={**PARAMS, **override}).status_code == 422


def test_unknown_mode_and_missing_points_are_rejected(tmp_path):
    c = make_client(tmp_path, lambda req: pytest.fail("must not call ORS"))
    assert c.get("/route/walk", params={**PARAMS, "mode": "teleport"}).status_code == 422
    assert c.get("/route/walk", params={"from_lat": 14.55}).status_code == 422
