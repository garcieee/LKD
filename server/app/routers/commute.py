"""GET /route/commute: up to three ways to get there by walking and riding one PUV or train, quickest first.

The ride and the options come from services/commute.py and are estimates. The walking legs are then re-routed along
real streets by OpenRouteService in the walking mode the user picked (fastest, walkable, accessible), and the road
rides (jeepney, UV Express, buses) are drawn along the streets a car would take between the two stops. A leg ORS cannot
answer keeps its straight-line estimate, so the list still comes back. Trains stay a straight line: they run on rails.
"""
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.config import in_city
from app.routers.routes import Mode, Step, walk_leg
from app.services import commute, hazards, ors

router = APIRouter()

Kind = Literal["walk", "jeepney", "uv_express", "city_bus", "p2p_bus", "mrt3", "lrt1"]
Tag = Literal["earliest", "least_walking"]


class Leg(BaseModel):
    kind: Kind
    duration_s: float
    distance_m: float
    label: str
    geometry: list[list[float]]  # [[lng, lat], ...], the order Mapbox takes
    steps: list[Step] = []  # a street-routed walking leg only; rides and straight-line estimates have none
    connection_estimated: bool = False  # short sidewalk-to-boarding/drop-off link


class Option(BaseModel):
    id: str
    total_s: float
    walk_s: float
    tags: list[Tag]
    legs: list[Leg]


def _ends(leg: dict) -> tuple:
    (a, b), (c, d) = leg["geometry"][0], leg["geometry"][-1]
    return (b, a), (d, c)  # (lat, lng) pairs


def _connect_transfers(legs: list[dict]) -> None:
    """Join nearby walking/vehicle snaps with an explicitly estimated walking connection.

    ORS's walking and driving profiles can snap one stop to different sides of a
    road. Preserve both routes and their turn indices; account for the short link
    in walking distance/time. Never invent a long path across unmapped terrain.
    """
    for left, right in zip(legs, legs[1:]):
        if (left["kind"] == "walk") == (right["kind"] == "walk"):
            continue
        a, b = left["geometry"][-1], right["geometry"][0]
        gap = commute.distance_m(a[1], a[0], b[1], b[0])
        if gap == 0 or gap > 40:
            continue
        boarding = left["kind"] == "walk"
        walk = left if boarding else right
        line = walk["geometry"]
        steps = [dict(s) for s in walk.get("steps", [])]
        if boarding:
            walk["geometry"] = [*line, list(b)]
            steps = [s for s in steps if s["type"] != 10]
            at = len(line) - 1
        else:
            walk["geometry"] = [list(a), *line]
            steps = [{**s, "at": s["at"] + 1} for s in steps]
            at = 0
        step = {"type": 6, "text": "Walk to the boarding point (connection estimated)" if boarding else
                "Walk from the drop-off point to the footpath (connection estimated)",
                "name": "", "distance_m": gap, "at": at}
        walk["steps"] = [*steps, step] if boarding else [step, *steps]
        walk["distance_m"] += gap
        walk["duration_s"] += gap / commute.WALK_MPS
        walk["connection_estimated"] = True


def _refine(options: list[dict], mode: str, reports: list, client, rides: dict) -> None:
    """Swaps each walk leg's estimate for an ORS street route and each road ride's for the streets between its stops,
    in place. One call per distinct leg, in parallel.

    A ride keeps its modelled time (wait + distance at the mode's assumed speed), now over the road distance: ORS knows
    nothing of jeepney stops or traffic. Its turn steps are dropped, they are a car's, not a rider's.
    ponytail: a car route stands in for the PUV route, which the study data does not have. Upgrade: real route lines.
    """
    legs = [leg for o in options for leg in o["legs"]]
    jobs = list({(leg["kind"] == "walk", _ends(leg)) for leg in legs if leg["kind"] == "walk" or leg["kind"] in commute.ROAD_KINDS})

    def fetch(job):
        walk, ends = job
        try:
            return walk_leg(mode, *ends, reports, client)[0] if walk else ors.directions("driving-car", *ends, client=client)
        except ors.OrsError:
            return None  # keep the estimate

    with ThreadPoolExecutor(max_workers=6) as pool:
        found = dict(zip(jobs, pool.map(fetch, jobs)))
    for o in options:
        for leg in o["legs"]:
            walk = leg["kind"] == "walk"
            route = found.get((walk, _ends(leg))) if walk or leg["kind"] in commute.ROAD_KINDS else None  # a train on a road's stops stays a line
            if not route:
                continue
            if walk:
                leg.update(route)
            else:
                f = rides[leg["kind"]]
                leg.update(
                    geometry=route["geometry"],
                    distance_m=route["distance_m"],
                    duration_s=f["wait_min"] * 60 + route["distance_m"] / (f["speed_kmh"] / 3.6),
                    steps=[],
                )
        _connect_transfers(o["legs"])
        o["total_s"] = sum(leg["duration_s"] for leg in o["legs"])
        o["walk_s"] = sum(leg["duration_s"] for leg in o["legs"] if leg["kind"] == "walk")


@router.get("/route/commute", response_model=list[Option])
def route_commute(
    request: Request,
    from_lat: float = Query(...),
    from_lng: float = Query(...),
    to_lat: float = Query(...),
    to_lng: float = Query(...),
    mode: Mode = Query("walkable"),
):
    if not (in_city(from_lat, from_lng) and in_city(to_lat, to_lng)):
        raise HTTPException(422, "Both ends of the trip must be in Makati.")
    state, reports = request.app.state, request.app.state.store.all()
    hubs = state.hubs
    if mode == "accessible":  # a missing ramp or a broken elevator at a station closes it to a wheelchair
        hubs = [h for h in hubs if not hazards.barred((h["lat"], h["lng"]), reports)]
    options = commute.plan(hubs, state.rides, state.links, (from_lat, from_lng), (to_lat, to_lng))
    _refine(options, mode, reports, getattr(state, "ors_client", None), state.rides)
    return commute.rank(options)  # street distances can reorder them
