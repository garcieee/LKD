import math

from app.services import hazards

LAT, LNG = 14.5547, 121.0244
M_LNG = hazards.M_PER_DEG * math.cos(math.radians(LAT))  # metres per degree of longitude here


def report(rid, east_m=0.0, north_m=0.0, status="open"):
    return {"id": rid, "lat": LAT + north_m / hazards.M_PER_DEG, "lng": LNG + east_m / M_LNG, "status": status}


def line(*east_north_m):
    """A route as [[lng, lat], ...] from (east, north) metres off the origin."""
    return [[LNG + e / M_LNG, LAT + n / hazards.M_PER_DEG] for e, n in east_north_m]


def test_only_fixed_reports_are_out_of_the_way():
    rs = [report("a"), report("b", status="verified"), report("c", status="assigned"), report("d", status="fixed")]
    assert [r["id"] for r in hazards.unresolved(rs)] == ["a", "b", "c"]


def test_zones_are_forty_metre_squares_around_unresolved_reports():
    zones = hazards.avoid_polygons([report("a"), report("fixed", status="fixed")], keep_clear=[])
    assert zones["type"] == "MultiPolygon" and len(zones["coordinates"]) == 1
    ring = zones["coordinates"][0][0]
    assert ring[0] == ring[-1] and len(ring) == 5
    lngs, lats = [p[0] for p in ring], [p[1] for p in ring]
    assert math.isclose((max(lngs) - min(lngs)) * M_LNG, 40, rel_tol=1e-6)
    assert math.isclose((max(lats) - min(lats)) * hazards.M_PER_DEG, 40, rel_tol=1e-6)
    assert math.isclose(sum(lngs[:4]) / 4, LNG) and math.isclose(sum(lats[:4]) / 4, LAT)


def test_no_zones_when_nothing_is_unresolved():
    assert hazards.avoid_polygons([], []) is None
    assert hazards.avoid_polygons([report("a", status="fixed")], []) is None


def test_a_report_next_to_the_start_or_end_is_left_out_so_the_trip_can_leave():
    start = (LAT, LNG)
    near_start = report("near", east_m=30)  # inside the 40 m keep-clear
    far = report("far", east_m=60)
    zones = hazards.avoid_polygons([near_start, far], keep_clear=[start])
    assert len(zones["coordinates"]) == 1
    assert hazards.avoid_polygons([near_start], keep_clear=[start]) is None


def test_near_route_measures_to_the_line_not_just_its_points():
    route = line((-100, 0), (100, 0))  # a 200 m street, only two points
    rs = [report("on", 0, 0), report("beside", 0, 15), report("off", 0, 25), report("past-end", 130, 0)]
    assert hazards.near_route(route, rs) == ["on", "beside"]
    assert hazards.near_route(route, rs, radius_m=28) == ["on", "beside", "off"]


def test_near_route_ignores_fixed_and_copes_with_tiny_routes():
    route = line((-100, 0), (100, 0))
    assert hazards.near_route(route, [report("a", status="fixed")]) == []
    assert hazards.near_route([], [report("a")]) == []
    assert hazards.near_route(line((0, 5)), [report("a")]) == ["a"]  # a single point is a route of length zero


def test_accessibility_barriers_are_in_the_way_of_the_accessible_mode_only():
    rs = [{**report("ramp"), "category": "missing_ramp"}, {**report("hole"), "category": "pothole"},
          {**report("slab"), "category": "unsafe_sidewalk"}]  # a broken sidewalk trips anyone
    assert [r["id"] for r in hazards.for_mode(rs, "accessible")] == ["ramp", "hole", "slab"]
    for mode in ("fastest", "walkable"):
        assert [r["id"] for r in hazards.for_mode(rs, mode)] == ["hole", "slab"]


def test_the_accessible_only_barriers_are_pwd_categories_of_the_ticket_rules():
    from app.services import ticket_sync  # noqa: F401  (puts models/ on the import path)
    from models.tickets.types import ACCESSIBILITY

    assert hazards.ACCESSIBLE_ONLY == set(ACCESSIBILITY) - {"unsafe_sidewalk"}


def test_a_barrier_at_a_point_bars_it_and_a_hazard_or_a_fixed_barrier_does_not():
    ramp = {**report("ramp", east_m=10), "category": "missing_ramp"}
    here = (LAT, LNG)
    assert hazards.barred(here, [ramp])
    assert not hazards.barred(here, [{**ramp, "category": "pothole"}])
    assert not hazards.barred(here, [{**ramp, "status": "fixed"}])
    assert not hazards.barred(here, [{**report("far", east_m=50), "category": "missing_ramp"}])
