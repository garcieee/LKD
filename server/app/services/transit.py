"""Transit hubs: PUV terminals and stops from the 2025 Makati PUV study (data/transit/terminals.geojson) and the
running MRT-3 and LRT-1 stations from OpenStreetMap (data/transit/stations.geojson)."""
import json
import logging
import math
from pathlib import Path

log = logging.getLogger(__name__)


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle metres between two points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


def _read(path: Path) -> list[dict]:
    """The hubs in one GeoJSON file as flat dicts (id, name, kind, modes, lat, lng, error_m, merges)."""
    out = []
    for f in json.loads(path.read_text())["features"]:
        lng, lat = f["geometry"]["coordinates"]
        p = f["properties"]
        out.append({"id": p["id"], "name": p["name"], "kind": p["kind"], "modes": p["modes"], "lat": lat, "lng": lng, "error_m": p["error_m"], "merges": p.get("merges", [])})
    return out


def load_hubs(directory: Path) -> list[dict]:
    """Every hub, terminals and stations first, then bus stops. Empty, with a warning, if terminals.geojson is missing.

    A station's `merges` names PUV terminals that stand at it: those are dropped, and the station keeps its own
    (better) position and takes on their modes, so one dot serves the train and the buses.
    """
    try:
        pois = _read(directory / "terminals.geojson")
    except (OSError, ValueError, KeyError):
        log.warning("No transit hubs in %s: /transit/hubs will be empty", directory)
        return []
    try:
        stations = _read(directory / "stations.geojson")
    except (OSError, ValueError, KeyError):
        log.warning("No stations in %s: rail stations will be missing", directory)
        stations = []
    by_name = {h["name"]: h for h in pois}
    for s in stations:
        for name in s["merges"]:
            merged = by_name.pop(name, None)
            if merged:
                s["modes"] = s["modes"] + [m for m in merged["modes"] if m not in s["modes"]]
    pois = list(by_name.values())
    hubs = [h for h in pois if h["kind"] == "terminal"] + stations + [h for h in pois if h["kind"] != "terminal"]
    for h in hubs:
        h.pop("merges", None)
    return hubs


def nearest(hubs: list[dict], lat: float, lng: float, limit: int) -> list[dict]:
    """The `limit` hubs closest to (lat, lng), nearest first, each with its `distance_m` (rounded to a metre)."""
    with_distance = [{**h, "distance_m": round(distance_m(lat, lng, h["lat"], h["lng"]))} for h in hubs]
    return sorted(with_distance, key=lambda h: h["distance_m"])[:limit]
