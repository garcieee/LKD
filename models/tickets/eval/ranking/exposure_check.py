"""The foot-traffic check pre-registered in EVALUATION.md: 500 random Makati points must keep their order when EXPOSURE_SCALE is
halved or doubled (Spearman rho at least 0.95), and the busiest spots must be places a person would call busy.

There is no ground truth for foot traffic, so this is a sanity check, not a score. The second half is a judgment: the script
lists the ten busiest spots and the places next to them, and a person reads the list.

    models/.venv/bin/python -m models.tickets.eval.ranking.exposure_check
"""
import json
import math
from unittest import mock

import numpy as np
from scipy.stats import spearmanr

from models.tickets import settings as s
from models.tickets.eval.common import results
from models.tickets.matching.geo import distance_m
from models.tickets.ranking.exposure import foot_traffic
from models.tickets.resources import load

SEED = 2026
N_POINTS = 500
TARGET_RHO = 0.95
GRID_M = 50     # spacing of the grid the busiest spots are picked from
APART_M = 400   # two busiest spots are at least this far apart, so one mall does not fill the list
DEDUPE_M = 30   # what-if only: same-kind places closer than this count once
M_PER_DEGREE = 111_320


def traffic_at(points, places, scale):
    """foot_traffic at each (lat, lng) with EXPOSURE_SCALE set to `scale` for the length of the call."""
    with mock.patch.object(s, "EXPOSURE_SCALE", scale):
        return np.array([foot_traffic(lat, lng, places) for lat, lng in points])


def top_spots(points, values, places, count=10, apart_m=APART_M):
    """The highest points, each at least apart_m from those already taken, with their three nearest places."""
    spots = []
    for i in np.argsort(-values, kind="stable"):
        lat, lng = points[i]
        if any(distance_m(lat, lng, p["lat"], p["lng"]) < apart_m for p in spots):
            continue
        near = sorted((distance_m(lat, lng, p[0], p[1]), p[2], p[3]) for p in places)[:3]
        spots.append({"lat": float(lat), "lng": float(lng), "foot_traffic": float(values[i]),
                      "nearest": [{"m": round(d), "kind": kind, "name": name} for d, kind, name in near]})
        if len(spots) == count:
            break
    return spots


def dedupe(places, within_m=DEDUPE_M):
    """One place per kind within within_m, named ones first, so a station's unnamed platform nodes fold into the station."""
    kept = []
    for p in sorted(places, key=lambda p: (not p[3], p[0], p[1])):
        if not any(q[2] == p[2] and distance_m(p[0], p[1], q[0], q[1]) < within_m for q in kept):
            kept.append(p)
    return kept


def run():
    places = load.load_places()
    south, west, north, east = json.loads((load.HERE / "places.json").read_text())["bbox"]
    rng = np.random.default_rng(SEED)
    points = list(zip(rng.uniform(south, north, N_POINTS), rng.uniform(west, east, N_POINTS)))

    scales = {"x0.5": s.EXPOSURE_SCALE * 0.5, "shipped": s.EXPOSURE_SCALE, "x2": s.EXPOSURE_SCALE * 2}
    values = {name: traffic_at(points, places, scale) for name, scale in scales.items()}
    rho = {"x0.5 vs shipped": spearmanr(values["x0.5"], values["shipped"])[0],
           "x2 vs shipped": spearmanr(values["x2"], values["shipped"])[0],
           "x0.5 vs x2": spearmanr(values["x0.5"], values["x2"])[0]}
    at_floor = {name: float(np.mean(v <= s.EXPOSURE_FLOOR + 1e-12)) for name, v in values.items()}

    lat_step = GRID_M / M_PER_DEGREE
    lng_step = lat_step / math.cos(math.radians((south + north) / 2))
    grid = [(lat, lng) for lat in np.arange(south, north, lat_step) for lng in np.arange(west, east, lng_step)]
    grid_values = traffic_at(grid, places, s.EXPOSURE_SCALE)
    spots = top_spots(grid, grid_values, places)

    # What-if, nothing shipped changes: one OSM station often has several nodes within a few metres, and each pulls on its own.
    deduped = dedupe(places)
    values_dd = traffic_at(points, deduped, s.EXPOSURE_SCALE)
    what_if = {"within_m": DEDUPE_M, "places_before": len(places), "places_after": len(deduped),
               "spearman_rho_vs_shipped": spearmanr(values_dd, values["shipped"])[0],
               "median": float(np.median(values_dd)), "p90": float(np.percentile(values_dd, 90)),
               "busiest_spots": top_spots(grid, traffic_at(grid, deduped, s.EXPOSURE_SCALE), deduped)}

    for name, value in rho.items():
        print(f"Spearman rho, {name}: {value:.4f}")
    print("share of the 500 points at the floor:", {k: round(v, 3) for k, v in at_floor.items()})
    print(f"median and 90th percentile of the 500 points at the shipped scale: {np.median(values['shipped']):.2f}, {np.percentile(values['shipped'], 90):.2f}")
    for label, listed in (("shipped places", spots), (f"what-if, same-kind places within {DEDUPE_M} m counted once", what_if["busiest_spots"])):
        print(f"busiest spots, {label}:")
        for rank, spot in enumerate(listed, 1):
            near = "; ".join(f"{n['kind']} {n['name']} ({n['m']} m)" for n in spot["nearest"])
            print(f"{rank:2d}. {spot['foot_traffic']:.2f} at {spot['lat']:.5f}, {spot['lng']:.5f}: {near}")
    print(f"what-if: {len(places)} -> {len(deduped)} places, rho against shipped {what_if['spearman_rho_vs_shipped']:.4f}, "
          f"median {what_if['median']:.2f}, p90 {what_if['p90']:.2f}")

    results.write_result("ranking_exposure_check", {
        "seed": SEED, "points": N_POINTS, "box": [south, west, north, east], "target_rho": TARGET_RHO,
        "scales": scales, "spearman_rho": rho, "share_at_floor": at_floor,
        "shipped_median": float(np.median(values["shipped"])), "shipped_p90": float(np.percentile(values["shipped"], 90)),
        "grid_m": GRID_M, "grid_points": len(grid), "busiest_spots": spots, "what_if_dedupe": what_if})
    return rho, spots


if __name__ == "__main__":
    run()
