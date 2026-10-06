"""Transit hubs: the terminals and stops from the 2025 Makati PUV study (data/transit/terminals.geojson)."""
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


def load_hubs(directory: Path) -> list[dict]:
    """The hubs as flat dicts (id, name, kind, modes, lat, lng, error_m). Empty, with a warning, if the file is missing."""
    try:
        features = json.loads((directory / "terminals.geojson").read_text())["features"]
    except (OSError, ValueError, KeyError):
        log.warning("No transit hubs in %s: /transit/hubs will be empty", directory)
        return []
    hubs = []
    for f in features:
        lng, lat = f["geometry"]["coordinates"]
        p = f["properties"]
        hubs.append({"id": p["id"], "name": p["name"], "kind": p["kind"], "modes": p["modes"], "lat": lat, "lng": lng, "error_m": p["error_m"]})
    return hubs


def nearest(hubs: list[dict], lat: float, lng: float, limit: int) -> list[dict]:
    """The `limit` hubs closest to (lat, lng), nearest first, each with its `distance_m` (rounded to a metre)."""
    with_distance = [{**h, "distance_m": round(distance_m(lat, lng, h["lat"], h["lng"]))} for h in hubs]
    return sorted(with_distance, key=lambda h: h["distance_m"])[:limit]
