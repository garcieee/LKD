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


def test_a_ride_needs_two_hubs_sharing_a_mode():
    assert commute.plan([JEEP_A, BUS_B], RIDES, START, END) == []


def test_offers_the_best_of_each_mode_walk_ride_walk():
    opts = commute.plan([JEEP_A, JEEP_B, BUS_A, BUS_B], RIDES, START, END)
    assert {o["id"].split(":")[0] for o in opts} == {"jeepney", "city_bus"}
    for o in opts:
        assert [leg["kind"] for leg in o["legs"]][0::2] == ["walk", "walk"]
        assert o["total_s"] == sum(leg["duration_s"] for leg in o["legs"])


def test_tags_the_earliest_and_least_walking():
    opts = commute.plan([JEEP_A, JEEP_B, BUS_A, BUS_B], RIDES, START, END)
    assert opts == sorted(opts, key=lambda o: o["total_s"])
    assert "earliest" in opts[0]["tags"]
    assert "least_walking" in min(opts, key=lambda o: o["walk_s"])["tags"]


def test_a_short_trip_also_offers_a_walk():
    near = (14.5540, 121.0200)
    opts = commute.plan([], RIDES, START, near)
    assert [o["id"] for o in opts] == ["walk"]
    assert commute.plan([], RIDES, START, END) == []  # nothing near and too far to walk
