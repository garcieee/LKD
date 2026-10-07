import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import ors

AYALA = (14.5500, 121.0280)  # by Ayala MRT station
GIL_PUYAT = (14.5545, 120.9975)  # by Gil Puyat LRT station, 3 km west: too far to walk, and the Ayala-Gil Puyat bus runs it
PARAMS = {"from_lat": AYALA[0], "from_lng": AYALA[1], "to_lat": GIL_PUYAT[0], "to_lng": GIL_PUYAT[1]}
STREET = [[121.0244, 14.5547, 12.0], [121.0240, 14.5550, 12.0]]  # a 100 m, 80 s street walk


ROAD = [[121.0244, 14.5547, 12.0], [121.0240, 14.5552, 12.0], [121.0200, 14.5552, 12.0], [121.0190, 14.5556, 12.0]]  # a bent 1.2 km street ride


def ors_walk(req):
    if "driving" in req.url.path:
        return httpx.Response(500)  # the ride is not under test: it keeps its straight-line estimate
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
    assert all(req.url.path == "/v2/directions/foot-walking/geojson" for req in seen if "driving" not in req.url.path)
    assert len(seen) <= 12
    assert all(len(leg["geometry"]) == 2 for o in options for leg in o["legs"] if leg["kind"] != "walk"), "ORS was down for the ride"


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
        return [(req.url.path, json.loads(req.content)) for req in seen if "driving" not in req.url.path]

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


def test_a_walking_leg_carries_its_turn_steps_and_a_ride_has_none(tmp_path):
    step = {"distance": 100.0, "duration": 80.0, "type": 1, "instruction": "Turn right onto Ayala Avenue", "name": "Ayala Avenue", "way_points": [0, 1]}

    def handler(_req):
        body = {"features": [{"geometry": {"type": "LineString", "coordinates": STREET}, "properties": {"summary": {"distance": 100.0, "duration": 80.0}, "segments": [{"steps": [step]}]}}]}
        return httpx.Response(200, json=body)

    option = make_client(tmp_path, handler).get("/route/commute", params=PARAMS).json()[0]
    for leg in option["legs"]:
        if leg["kind"] == "walk":
            assert [(s["type"], s["name"], s["at"]) for s in leg["steps"]] == [(1, "Ayala Avenue", 0)]
        else:
            assert leg["steps"] == []


def _ride(kind):
    return {"kind": kind, "duration_s": 1.0, "distance_m": 1.0, "label": "A to B", "geometry": [[121.0244, 14.5547], [121.0190, 14.5556]]}


def test_a_road_ride_follows_the_streets_between_its_stops_and_a_train_stays_a_straight_line():
    from app.routers.commute import _refine

    seen = []

    def handler(req):
        seen.append((req.url.path, json.loads(req.content)))
        body = {"features": [{"geometry": {"type": "LineString", "coordinates": ROAD}, "properties": {"summary": {"distance": 1200.0, "duration": 150.0}, "segments": [{"steps": [{"distance": 1200.0, "duration": 150.0, "type": 11, "instruction": "Head west", "name": "Ayala", "way_points": [0, 3]}]}]}}]}
        return httpx.Response(200, json=body)

    options = [{"id": "x", "total_s": 2.0, "walk_s": 0.0, "tags": [], "legs": [_ride("jeepney"), _ride("mrt3")]}]
    rides = {"jeepney": {"speed_kmh": 12, "wait_min": 4}, "mrt3": {"speed_kmh": 33, "wait_min": 4}}
    _refine(options, "walkable", [], httpx.Client(transport=httpx.MockTransport(handler)), rides)
    jeepney, train = options[0]["legs"]
    assert [path for path, _ in seen] == ["/v2/directions/driving-car/geojson"], "one street route, none for the train"
    assert "options" not in seen[0][1], "no walking no-go zones on a road"
    assert jeepney["geometry"] == [[121.0244, 14.5547], [121.024, 14.5552], [121.02, 14.5552], [121.019, 14.5556]], "the bend is kept, elevation dropped"
    assert jeepney["distance_m"] == 1200.0
    assert jeepney["duration_s"] == 4 * 60 + 1200 / (12 / 3.6), "the wait plus the road at the jeepney's assumed speed, not the car's time"
    assert jeepney["steps"] == [], "a car's turns are not a rider's"
    assert len(train["geometry"]) == 2 and train["distance_m"] == 1.0
    assert options[0]["total_s"] == jeepney["duration_s"] + train["duration_s"]


def test_a_ride_whose_street_route_fails_keeps_its_straight_line(tmp_path):
    from app.routers.commute import _refine

    options = [{"id": "x", "total_s": 1.0, "walk_s": 0.0, "tags": [], "legs": [_ride("city_bus")]}]
    _refine(options, "walkable", [], httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(500))), {"city_bus": {"speed_kmh": 15, "wait_min": 6}})
    assert len(options[0]["legs"][0]["geometry"]) == 2 and options[0]["total_s"] == 1.0


def _rides_between(tmp_path, a_id, b_id):
    c = make_client(tmp_path, ors_walk)
    by_id = {h["id"]: h for h in c.app.state.hubs}
    a, b = by_id[a_id], by_id[b_id]
    r = c.get("/route/commute", params={"from_lat": a["lat"], "from_lng": a["lng"], "to_lat": b["lat"], "to_lng": b["lng"]})
    assert r.status_code == 200
    return [(leg["kind"], leg["label"]) for o in r.json() for leg in o["legs"] if leg["kind"] != "walk"]


def test_a_jeepney_ride_is_only_offered_on_a_route_the_study_lists(tmp_path):
    assert ("jeepney", "One Ayala to Washington Terminal") in _rides_between(tmp_path, "one-ayala", "washington-terminal")
    # Both are jeepney terminals, but no listed route joins them: the old straight-line guess invented that ride.
    # Washington Terminal reaches Landmark's end of town only by the real Ayala-Washington route, alighting at One Ayala.
    rides = _rides_between(tmp_path, "washington-terminal", "landmark-terminal")
    assert ("jeepney", "Washington Terminal to Landmark Terminal") not in rides
    assert ("jeepney", "Washington Terminal to One Ayala") in rides


def test_iacademy_glorietta_transfer_snaps_connect_and_keep_turn_indices():
    from app.routers.commute import _connect_transfers
    # ORS endpoints for Washington Terminal -> One Ayala, 7 Oct 2026.
    legs = [
        {"kind": "walk", "geometry": [[121.007969, 14.559923], [121.010285, 14.558631]],
         "distance_m": 300, "duration_s": 240, "steps": [
             {"type": 11, "at": 0, "text": "Start", "name": "Yakal", "distance_m": 300},
             {"type": 10, "at": 1, "text": "Arrive", "name": "", "distance_m": 0}]},
        {"kind": "jeepney", "geometry": [[121.01038, 14.558472], [121.028369, 14.550643]],
         "distance_m": 2500, "duration_s": 900},
        {"kind": "walk", "geometry": [[121.028151, 14.550464], [121.025139, 14.550356]],
         "distance_m": 400, "duration_s": 300, "steps": [
             {"type": 11, "at": 0, "text": "Start", "name": "Ayala", "distance_m": 400}]},
    ]
    _connect_transfers(legs)
    assert all(a["geometry"][-1] == b["geometry"][0] for a, b in zip(legs, legs[1:]))
    assert legs[0]["distance_m"] == pytest.approx(320.4, abs=0.2)
    assert legs[2]["distance_m"] == pytest.approx(430.8, abs=0.2)
    assert legs[2]["steps"][1]["at"] == 1
    assert "estimated" in legs[0]["steps"][-1]["text"]
    assert legs[1]["distance_m"] == 2500
    before = json.dumps(legs, sort_keys=True)
    _connect_transfers(legs)
    assert json.dumps(legs, sort_keys=True) == before


def test_transfer_connection_never_draws_a_long_unverified_shortcut():
    from app.routers.commute import _connect_transfers
    legs = [
        {"kind": "walk", "geometry": [[121.0, 14.55], [121.001, 14.55]], "distance_m": 100, "duration_s": 80},
        {"kind": "city_bus", "geometry": [[121.02, 14.55], [121.03, 14.55]], "distance_m": 1000, "duration_s": 200},
    ]
    before = json.dumps(legs)
    _connect_transfers(legs)
    assert json.dumps(legs) == before
