from collections import Counter

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import transit

ONE_AYALA = {"lat": 14.55048, "lng": 121.02817}
LRT_GIL_PUYAT = {"lat": 14.55407, "lng": 120.99757}


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path))


def test_distance_is_the_great_circle_in_metres():
    assert transit.distance_m(14.55, 121.02, 14.55, 121.02) == 0
    assert 111_100 < transit.distance_m(14.0, 121.0, 15.0, 121.0) < 111_300  # a degree of latitude
    assert transit.distance_m(14.55, 121.0, 14.56, 121.01) == pytest.approx(transit.distance_m(14.56, 121.01, 14.55, 121.0))


def test_without_a_position_it_lists_hubs_in_file_order_with_no_distance(client):
    r = client.get("/transit/hubs", params={"limit": 50})
    assert r.status_code == 200
    hubs = r.json()
    assert len(hubs) == 43, "35 PUV points, 3 of them replaced by the stations they stand at, plus 11 stations"
    assert all(h["distance_m"] is None for h in hubs)
    assert Counter(h["kind"] for h in hubs) == {"terminal": 18, "station": 11, "stop": 14}
    kinds = [h["kind"] for h in hubs]
    assert kinds == sorted(kinds, key=lambda k: k == "stop"), "terminals and stations come before the bus stops"


def test_with_a_position_the_nearest_come_first(client):
    hubs = client.get("/transit/hubs", params={**ONE_AYALA, "limit": 5}).json()
    assert len(hubs) == 5
    assert hubs[0]["name"] == "One Ayala" and hubs[0]["distance_m"] < 50
    assert [h["distance_m"] for h in hubs] == sorted(h["distance_m"] for h in hubs)
    assert hubs[0]["error_m"] > 0 and "jeepney" in hubs[0]["modes"]


def test_kind_and_mode_narrow_the_list_before_the_limit(client):
    stops = client.get("/transit/hubs", params={**LRT_GIL_PUYAT, "kind": "stop", "limit": 50}).json()
    assert len(stops) == 14 and all(h["kind"] == "stop" for h in stops)
    assert stops[0]["name"] == "Dian", "the stop nearest the LRT-1 station, not the station itself"
    uv = client.get("/transit/hubs", params={"mode": "uv_express", "limit": 50}).json()
    assert {h["name"] for h in uv} == {"Circuit Makati", "Gil Puyat Station (LRT-1)", "One Ayala", "Paseo Center", "Valero 2 Carpark", "Dela Rosa Carpark 1"}
    trains = client.get("/transit/hubs", params={"kind": "station", "limit": 50}).json()
    assert {m for h in trains for m in h["modes"] if m in ("mrt3", "lrt1")} == {"mrt3", "lrt1"}
    assert len([h for h in trains if "mrt3" in h["modes"]]) == 6 and len([h for h in trains if "lrt1" in h["modes"]]) == 5


def test_a_station_replaces_the_puv_terminal_at_it_and_takes_on_its_modes(client):
    hubs = {h["name"]: h for h in client.get("/transit/hubs", params={"limit": 50}).json()}
    gil_puyat = hubs["Gil Puyat Station (LRT-1)"]
    assert gil_puyat["modes"] == ["lrt1", "city_bus", "jeepney", "p2p_bus", "uv_express"], "the train first, then every PUV that stops there"
    assert gil_puyat["error_m"] == 40, "the station's own position, not the PDF estimate"
    ayala = hubs["Ayala Station (MRT-3)"]
    assert ayala["modes"] == ["mrt3", "city_bus"]
    assert hubs["Buendia Station (MRT-3)"]["modes"] == ["mrt3", "city_bus"]
    for gone in ("LRT1-Gil Puyat", "MRT3-Ayala/BGC Bus Terminal", "MRT3-Buendia"):
        assert gone not in hubs


def test_bad_requests_are_rejected(client):
    for params in [{"lat": 14.5}, {"lng": 121.0}, {"lat": 99, "lng": 121}, {"limit": 0}, {"limit": 51}, {"kind": "airport"}, {"mode": "ferry"}]:
        assert client.get("/transit/hubs", params=params).status_code == 422, params


def test_a_missing_data_file_gives_an_empty_list_not_a_crash(tmp_path):
    assert transit.load_hubs(tmp_path) == []
    (tmp_path / "terminals.geojson").write_text("not json")
    assert transit.load_hubs(tmp_path) == []


def test_missing_stations_leave_the_puv_points_alone(tmp_path):
    (tmp_path / "terminals.geojson").write_text(
        '{"features": [{"geometry": {"coordinates": [121.0, 14.55]}, "properties": {"id": "a", "name": "A", "kind": "terminal", "modes": ["jeepney"], "error_m": 60}}]}'
    )
    hubs = transit.load_hubs(tmp_path)
    assert [h["name"] for h in hubs] == ["A"] and "merges" not in hubs[0]
