"""The transit routes file (data/transit/routes.json), taken from the 2025 PUV study PDF. The counts are the
study's own, so a slip while editing the file shows up here."""
import json
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "transit"
STUDY_COUNTS = {"jeepney": 17, "uv_express": 20, "city_bus": 8, "p2p_bus": 11}


def load():
    return json.loads((DATA / "routes.json").read_text())


def test_route_counts_match_the_study():
    data = load()
    assert dict(Counter(r["mode"] for r in data["routes"])) == STUDY_COUNTS
    assert data["counts"] == STUDY_COUNTS
    assert len(data["routes"]) == 56


def test_ids_are_unique_and_every_route_is_named():
    routes = load()["routes"]
    assert len({r["id"] for r in routes}) == len(routes)
    assert all(r["name"].strip() and r["id"].startswith(r["mode"]) for r in routes)


def test_two_ended_names_are_split_and_the_rest_are_not():
    by_name = {r["name"]: r for r in load()["routes"]}
    assert by_name["Ayala – Pateros"]["ends"] == ["Ayala", "Pateros"]
    assert by_name["Pasay – Balibago via Ayala"]["ends"] == ["Pasay", "Balibago"], "'via' is not an end"
    assert by_name["Makati Loop"]["ends"] == []
    assert by_name["Imus"]["ends"] == [] and by_name["Pacita – Binan"]["ends"] == [], "UV Express names are destinations"


def test_the_data_use_notice_travels_with_the_file():
    assert "do not share" in load()["source"].lower()


def terminals():
    return json.loads((DATA / "terminals.geojson").read_text())


def test_terminals_are_all_in_makati_with_unique_ids():
    from app.config import in_city

    feats = terminals()["features"]
    assert len(feats) == 35 and len({f["properties"]["id"] for f in feats}) == 35
    for f in feats:
        lng, lat = f["geometry"]["coordinates"]
        assert in_city(lat, lng), f["properties"]["name"]


def test_terminal_points_say_how_they_were_found_and_flag_the_doubtful_ones():
    feats = terminals()["features"]
    kinds = Counter(f["properties"]["kind"] for f in feats)
    assert kinds == {"terminal": 20, "stop": 15}
    for f in feats:
        p = f["properties"]
        assert p["method"] in {"venue search", "map fit"} and p["modes"] and p["error_m"] > 0
        assert set(p["modes"]) <= set(STUDY_COUNTS)
        if p["error_m"] > 120:
            assert p["review"], f"{p['name']} is imprecise and must say so"
    assert "do not share" in terminals()["source"].lower()


def test_stations_are_running_lines_inside_the_map_and_say_what_they_replace():
    from app.config import in_city

    data = json.loads((DATA / "stations.geojson").read_text())
    feats = data["features"]
    assert len(feats) == 11 and len({f["properties"]["id"] for f in feats}) == 11
    assert Counter(f["properties"]["line"] for f in feats) == {"MRT-3": 6, "LRT-1": 5}
    for f in feats:
        lng, lat = f["geometry"]["coordinates"]
        assert in_city(lat, lng), f["properties"]["name"]
        assert f["properties"]["kind"] == "station" and f["properties"]["modes"] in (["mrt3"], ["lrt1"])
    assert "PNR" in data["note"] and "suspended" in data["note"], "why PNR is missing travels with the file"
    terminal_names = {f["properties"]["name"] for f in terminals()["features"]}
    merged = [n for f in feats for n in f["properties"]["merges"]]
    assert set(merged) <= terminal_names and len(merged) == len(set(merged)) == 3, "every merge names a real PDF point, once"
