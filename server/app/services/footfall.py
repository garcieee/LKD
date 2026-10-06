"""Modeled foot traffic: a relative 0-100 index per place and hour, from transit hubs and curated districts.

Not a count. Each point's raw demand is
    hub:     sum of its modes' weights, plus its share of its district's route ends (split by mode weight,
             capped at route_end_cap so a lone hub does not swallow a whole district's routes)
    anchor:  a district's non-transit draw (offices, nightlife, markets), anchor * anchor_scale
and the index is raw demand, scaled so the strongest point is 100, times an hourly profile (peak 1.0) for
the district it belongs to. A district's index scales its summed demand so the strongest district is 100. Route ends come from data/transit/routes.json. See data/footfall/hotspots.json.
Measured camera counts replace this per zone when they exist (kind "measured"); until then every value is
kind "estimate".
"""
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services.transit import distance_m

log = logging.getLogger(__name__)

METHOD = "transit_hub_prior_v1"
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
MANILA = timezone(timedelta(hours=8))  # no daylight saving
TIER_1, TIER_2 = 0.6, 0.2  # a district's share of the strongest district's demand


def manila_now() -> datetime:
    return datetime.now(MANILA)


def curve(profile: dict, day: str, hour: float) -> float:
    """Relative activity (0-1, 1 = the profile's busiest moment) at `hour` on `day` (mon..sun)."""
    keys = [day, "weekend" if day in ("sat", "sun") else "weekday"]
    peaks = next((profile[k] for k in keys if k in profile), [])
    total = 0.0
    for p in peaks:
        gap = abs(hour - p["at"])
        gap = min(gap, 24 - gap)  # late-night peaks wrap past midnight
        total += p["w"] * math.exp(-0.5 * (gap / p["sd"]) ** 2)
    return min(1.0, max(profile["floor"], total))


def load_model(footfall_dir: Path, transit_dir: Path, hubs: list[dict]) -> dict | None:
    """The scored points and districts, ready for `estimate`. None, with a warning, if hotspots.json is unreadable."""
    try:
        cfg = json.loads((footfall_dir / "hotspots.json").read_text())
    except (OSError, ValueError):
        log.warning("No foot-traffic model in %s: /footfall will answer 503", footfall_dir)
        return None
    try:
        routes = json.loads((transit_dir / "routes.json").read_text())["routes"]
    except (OSError, ValueError, KeyError):
        log.warning("No routes in %s: route ends will not count toward foot traffic", transit_dir)
        routes = []

    ends: dict[str, int] = {}
    for r in routes:
        for name in r["ends"]:
            ends[name] = ends.get(name, 0) + 1

    districts = cfg["districts"]
    for d in districts:
        d["route_ends"] = sum(ends.get(a, 0) for a in d["route_end_aliases"])

    def district_of(lat: float, lng: float) -> dict | None:
        """The nearest district whose circle holds the point."""
        near = [(distance_m(lat, lng, d["lat"], d["lng"]), d) for d in districts]
        near = [(m, d) for m, d in near if m <= d["radius_m"]]
        return min(near, key=lambda t: t[0])[1] if near else None

    members: dict[str, list[dict]] = {d["id"]: [] for d in districts}
    placed = []
    for h in hubs:
        d = district_of(h["lat"], h["lng"])
        if d:
            members[d["id"]].append(h)
        placed.append((h, d))

    def mode_raw(h: dict) -> float:
        return sum(cfg["mode_weight"].get(m, 0) for m in h["modes"])

    points = []
    for h, d in placed:
        raw = mode_raw(h)
        if d:
            total = sum(mode_raw(m) for m in members[d["id"]])
            raw += min(cfg["route_end_cap"], d["route_ends"] * cfg["route_end_weight"] * raw / total)
        points.append(
            {"id": h["id"], "name": h["name"], "kind": "hub", "lat": h["lat"], "lng": h["lng"], "error_m": h["error_m"],
             "raw": raw, "profile": d["profile"] if d else "transit", "district": d["id"] if d else None}
        )
    for d in districts:
        points.append(
            {"id": f"anchor-{d['id']}", "name": d["name"], "kind": "anchor", "lat": d["lat"], "lng": d["lng"],
             "error_m": d["radius_m"] // 2, "raw": d["anchor"] * cfg["anchor_scale"], "profile": d["profile"], "district": d["id"]}
        )

    peak = max(p["raw"] for p in points)
    district_raw = {d["id"]: sum(p["raw"] for p in points if p["district"] == d["id"]) for d in districts}
    top = max(district_raw.values())
    out_districts = []
    for d in districts:
        share = district_raw[d["id"]] / top
        out_districts.append(
            {"id": d["id"], "name": d["name"], "lat": d["lat"], "lng": d["lng"], "radius_m": d["radius_m"],
             "profile": d["profile"], "tier": 1 if share >= TIER_1 else 2 if share >= TIER_2 else 3,
             "share": round(share, 3), "hubs": len(members[d["id"]]), "route_ends": d["route_ends"],
             "anchor": d["anchor"], "basis": d["basis"]}
        )
    out_districts.sort(key=lambda d: -d["share"])
    return {"points": points, "peak": peak, "districts": out_districts, "profiles": cfg["profiles"], "district_raw": district_raw, "top": top}


def estimate(model: dict, day: str, hour: float) -> dict:
    """Every point and district at (day, hour), each with an `index` 0-100 and a ±25% band."""
    profiles = model["profiles"]

    def score(share: float, profile: str) -> dict:
        v = round(100 * share * curve(profiles[profile], day, hour), 1)
        return {"index": v, "lower": round(v * 0.75, 1), "upper": round(min(100, v * 1.25), 1)}

    points = [
        {**{k: p[k] for k in ("id", "name", "kind", "lat", "lng", "error_m", "profile", "district")}, **score(p["raw"] / model["peak"], p["profile"])}
        for p in model["points"]
    ]
    districts = [{**d, **score(model["district_raw"][d["id"]] / model["top"], d["profile"])} for d in model["districts"]]
    districts.sort(key=lambda d: -d["index"])
    return {"kind": "estimate", "method": METHOD, "day": day, "hour": hour, "points": points, "districts": districts}
