"""Unresolved reports as route hazards: no-go zones to steer around, and a count of what a route still passes.

Plain-Python geometry on a flat local plane: over a few hundred metres in Makati that is accurate to
centimetres, and it needs no GIS library.
"""
import math

M_PER_DEG = 111_320.0  # metres per degree of latitude; longitude shrinks with cos(lat)
ZONE_HALF_M = 20.0  # a no-go zone is a square this far to each side of the report (40 m across)

# PWD barriers that stop a wheelchair, a cane or a white cane but not someone walking: only the Accessible route counts
# them. The fourth PWD category, a steep or broken sidewalk, trips anyone, so every hazard-avoiding mode counts it.
ACCESSIBLE_ONLY = {"missing_ramp", "blocked_tactile_paving", "broken_elevator"}


def unresolved(reports: list[dict]) -> list[dict]:
    """Fixed and rejected are no longer in the way: assigned and verified still are. A rejected report was judged not
    real, so it must not close a street to anyone's routes.

    An SOS is a call for help, not an obstacle: it is never a no-go zone, so one unvetted video cannot
    close a street to everyone's routes (and it is not listed to the public app either, see /reports).
    """
    return [r for r in reports if r["status"] not in ("fixed", "rejected") and r.get("category") != "sos"]


def for_mode(reports: list[dict], mode: str) -> list[dict]:
    """The reports that are in the way in this route mode: the ACCESSIBLE_ONLY barriers only for Accessible."""
    return reports if mode == "accessible" else [r for r in reports if r.get("category") not in ACCESSIBLE_ONLY]


def _metres(lat0: float, lat: float, lng0: float, lng: float) -> tuple[float, float]:
    """(east, north) of (lat, lng) from (lat0, lng0)."""
    return (lng - lng0) * M_PER_DEG * math.cos(math.radians(lat0)), (lat - lat0) * M_PER_DEG


def _at(r: dict, point: tuple[float, float]) -> bool:
    """Whether a report is too close to a point (lat, lng) to draw a zone there without boxing the point in."""
    return max(map(abs, _metres(r["lat"], point[0], r["lng"], point[1]))) < 2 * ZONE_HALF_M


def barred(point: tuple[float, float], reports: list[dict]) -> bool:
    """An unresolved ACCESSIBLE_ONLY barrier at this point, a station say. Zones never cover the ends of a walk, so
    the Accessible mode has to leave such a point out itself."""
    return any(r.get("category") in ACCESSIBLE_ONLY and _at(r, point) for r in unresolved(reports))


def avoid_polygons(reports: list[dict], keep_clear: list[tuple[float, float]]) -> dict | None:
    """A GeoJSON MultiPolygon of squares around unresolved reports, for ORS `options.avoid_polygons`.

    A report close to a `keep_clear` point (the trip's start or end, as (lat, lng)) is left out:
    a zone over the start would leave no way out of it. None when there is nothing to avoid.
    """
    polygons = []
    for r in unresolved(reports):
        if any(_at(r, point) for point in keep_clear):
            continue
        lat, lng = r["lat"], r["lng"]
        dlat = ZONE_HALF_M / M_PER_DEG
        dlng = ZONE_HALF_M / (M_PER_DEG * math.cos(math.radians(lat)))
        ring = [[lng - dlng, lat - dlat], [lng + dlng, lat - dlat], [lng + dlng, lat + dlat], [lng - dlng, lat + dlat]]
        polygons.append([ring + [ring[0]]])
    return {"type": "MultiPolygon", "coordinates": polygons} if polygons else None


def _distance_to_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def near_route(geometry: list[list[float]], reports: list[dict], radius_m: float = ZONE_HALF_M) -> list[str]:
    """Ids of unresolved reports within `radius_m` of the route line (`geometry` is [[lng, lat], ...])."""
    ids = []
    for r in unresolved(reports):
        lat, lng = r["lat"], r["lng"]
        pts = [_metres(lat, p[1], lng, p[0]) for p in geometry]  # the route, with this report at (0, 0)
        if len(pts) == 1:
            pts = pts * 2
        if any(_distance_to_segment(0, 0, *a, *b) <= radius_m for a, b in zip(pts, pts[1:])):
            ids.append(r["id"])
    return ids
