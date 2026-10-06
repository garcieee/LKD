from pathlib import Path

from app.services import commute

TRANSIT = Path(__file__).resolve().parent.parent / "data" / "transit"
RIDES = commute.load_ride_modes(TRANSIT)

START = (14.5500, 121.0200)
END = (14.5700, 121.0200)  # about 2.2 km north: too far to be offered as a plain walk


def hub(hid, lat, modes):
    return {"id": hid, "name": hid.upper(), "kind": "stop", "modes": modes, "lat": lat, "lng": 121.0200, "error_m": 0}


# Boards a few metres from START, alights a few metres from END.
JEEP_A, JEEP_B = hub("ja", 14.5502, ["jeepney"]), hub("jb", 14.5698, ["jeepney"])
BUS_A, BUS_B = hub("ba", 14.5504, ["city_bus"]), hub("bb", 14.5696, ["city_bus"])


# The routes the study lists: a jeepney route joins ja and jb, a city bus route joins ba and bb.
LINKS = {"jeepney": {frozenset(("ja", "jb"))}, "city_bus": {frozenset(("ba", "bb"))}}
TRAIN_A, TRAIN_B = hub("ta", 14.5503, ["mrt3"]), hub("tb", 14.5697, ["mrt3"])


def test_a_road_ride_needs_a_route_that_joins_the_two_hubs():
    assert commute.plan([JEEP_A, BUS_B], RIDES, LINKS, START, END) == [], "no route joins them"
    same_mode_no_route = commute.plan([JEEP_A, JEEP_B], RIDES, {}, START, END)
    assert same_mode_no_route == [], "two jeepney hubs are not a jeepney route"
    assert [o["id"] for o in commute.plan([JEEP_A, JEEP_B], RIDES, LINKS, START, END)] == ["jeepney:ja:jb"]


def test_a_route_runs_both_ways():
    assert [o["id"] for o in commute.plan([JEEP_A, JEEP_B], RIDES, LINKS, END, START)] == ["jeepney:jb:ja"]


def test_a_train_needs_only_two_stations_of_the_same_line():
    assert [o["id"] for o in commute.plan([TRAIN_A, TRAIN_B], RIDES, {}, START, END)] == ["mrt3:ta:tb"]
    assert commute.plan([TRAIN_A, hub("lx", 14.5697, ["lrt1"])], RIDES, {}, START, END) == []


def test_offers_the_best_of_each_mode_walk_ride_walk():
    opts = commute.plan([JEEP_A, JEEP_B, BUS_A, BUS_B], RIDES, LINKS, START, END)
    assert {o["id"].split(":")[0] for o in opts} == {"jeepney", "city_bus"}
    for o in opts:
        assert [leg["kind"] for leg in o["legs"]][0::2] == ["walk", "walk"]
        assert o["total_s"] == sum(leg["duration_s"] for leg in o["legs"])


def test_tags_the_earliest_and_least_walking():
    opts = commute.plan([JEEP_A, JEEP_B, BUS_A, BUS_B], RIDES, LINKS, START, END)
    assert opts == sorted(opts, key=lambda o: o["total_s"])
    assert "earliest" in opts[0]["tags"]
    assert "least_walking" in min(opts, key=lambda o: o["walk_s"])["tags"]


def test_a_short_trip_also_offers_a_walk():
    near = (14.5540, 121.0200)
    opts = commute.plan([], RIDES, {}, START, near)
    assert [o["id"] for o in opts] == ["walk"]
    assert commute.plan([], RIDES, {}, START, END) == []  # nothing near and too far to walk


def test_links_come_from_the_studys_routes_where_both_ends_are_hubs():
    hubs = commute_hubs = [{"id": i} for i in ("one-ayala", "washington-terminal", "ayala-station-mrt-3", "gil-puyat-station-lrt-1")]
    links = commute.load_links(TRANSIT, hubs)
    assert links == {
        "jeepney": {frozenset(("one-ayala", "washington-terminal"))},
        "city_bus": {frozenset(("ayala-station-mrt-3", "gil-puyat-station-lrt-1"))},
    }, "Ayala-Washington, and the Gil Puyat-Ayala bus; routes with an end that is no hub, or only one named end, are left out"
    assert commute.load_links(TRANSIT, []) == {}
    assert commute.load_links(Path("/nonexistent"), commute_hubs) == {}
