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
