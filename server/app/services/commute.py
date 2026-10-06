"""Commute options: walk to a hub, ride to another hub that shares the mode, walk to the destination.

Everything here is an estimate. The PUV study has no stop order, route lines, fares or timetables, so a ride is the
straight line between two hubs that serve the same mode, stretched by DETOUR and timed at an assumed speed (ride_modes.json).
No fares: they are not in the data and do not decide the route.
"""
import json
from pathlib import Path

from app.services.transit import distance_m, nearest

WALK_MPS = 1.3  # a steady walking pace
DETOUR = 1.3  # streets are longer than the straight line
MAX_WALK_M = 800  # farther than this to a hub and it is not a commute leg
WALK_ONLY_M = 1500  # a trip this short is also offered as a plain walk
MIN_RIDE_M = 400  # not worth boarding for less
HUBS_PER_END = 4


def load_ride_modes(directory: Path) -> dict:
    return json.loads((directory / "ride_modes.json").read_text())["modes"]


def _line(a, b) -> list[list[float]]:
    return [[a[1], a[0]], [b[1], b[0]]]  # [lng, lat], the order Mapbox takes


def _walk(a, b, label: str) -> dict:
    m = distance_m(*a, *b) * DETOUR
    return {"kind": "walk", "duration_s": m / WALK_MPS, "distance_m": m, "label": label, "geometry": _line(a, b)}


def plan(hubs: list[dict], rides: dict, start: tuple, end: tuple, limit: int = 3) -> list[dict]:
    """Up to `limit` options, quickest first, each {id, total_s, walk_s, tags, legs}.

    The best option of each mode comes first so the list shows different ways to go, then the next quickest fill it.
    ponytail: one ride, no transfers, straight-line ride geometry. Upgrade when the data has stop order and lines.
    """
    pool = []
    if distance_m(*start, *end) <= WALK_ONLY_M:
        pool.append(("walk", [_walk(start, end, "Walk")], "walk"))
    board = [h for h in nearest(hubs, *start, HUBS_PER_END) if h["distance_m"] <= MAX_WALK_M]
    alight = [h for h in nearest(hubs, *end, HUBS_PER_END) if h["distance_m"] <= MAX_WALK_M]
    for a in board:
        for b in alight:
            ride_m = distance_m(a["lat"], a["lng"], b["lat"], b["lng"]) * DETOUR
            if a["id"] == b["id"] or ride_m < MIN_RIDE_M:
                continue
            for mode in set(a["modes"]) & set(b["modes"]):
                f = rides.get(mode)
                if not f:
                    continue
                at, bt = (a["lat"], a["lng"]), (b["lat"], b["lng"])
                ride = {
                    "kind": mode,
                    "duration_s": f["wait_min"] * 60 + ride_m / (f["speed_kmh"] / 3.6),
                    "distance_m": ride_m,
                    "label": f"{a['name']} to {b['name']}",
                    "geometry": _line(at, bt),
                }
                legs = [_walk(start, at, f"Walk to {a['name']}"), ride, _walk(bt, end, f"Walk from {b['name']}")]
                pool.append((mode, legs, f"{mode}:{a['id']}:{b['id']}"))

    options = [
        {
            "id": oid,
            "total_s": sum(leg["duration_s"] for leg in legs),
            "walk_s": sum(leg["duration_s"] for leg in legs if leg["kind"] == "walk"),
            "mode": mode,
            "legs": legs,
        }
        for mode, legs, oid in pool
    ]
    options.sort(key=lambda o: o["total_s"])
    chosen, seen = [], set()
    for o in options:
        if o["mode"] not in seen:
            seen.add(o["mode"])
            chosen.append(o)
    chosen = chosen[:limit]
    chosen += [o for o in options if o not in chosen][: limit - len(chosen)]
    chosen.sort(key=lambda o: o["total_s"])
    for o in chosen:
        o.pop("mode")
        o["tags"] = []
    if chosen:
        chosen[0]["tags"].append("earliest")
        min(chosen, key=lambda o: o["walk_s"])["tags"].append("least_walking")
    return chosen
