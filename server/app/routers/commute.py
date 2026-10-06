"""GET /route/commute: up to three ways to get there by walking and riding one PUV or train, quickest first.

The ride and the options come from services/commute.py and are estimates. The walking legs are then re-routed along
real streets by OpenRouteService; a leg ORS cannot answer keeps its straight-line estimate, so the list still comes back.
"""
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.config import in_city
from app.services import commute, ors

router = APIRouter()

Kind = Literal["walk", "jeepney", "uv_express", "city_bus", "p2p_bus", "mrt3", "lrt1"]
Tag = Literal["earliest", "least_walking"]


class Leg(BaseModel):
    kind: Kind
    duration_s: float
    distance_m: float
    label: str
    geometry: list[list[float]]  # [[lng, lat], ...], the order Mapbox takes


class Option(BaseModel):
    id: str
    total_s: float
    walk_s: float
    tags: list[Tag]
    legs: list[Leg]


def _ends(leg: dict) -> tuple:
    (a, b), (c, d) = leg["geometry"][0], leg["geometry"][-1]
    return (b, a), (d, c)  # (lat, lng) pairs


def _refine(options: list[dict], client) -> None:
    """Swaps each walk leg's estimate for an ORS street route, in place. One call per distinct leg, in parallel."""
    legs = {_ends(leg): leg for o in options for leg in o["legs"] if leg["kind"] == "walk"}

    def fetch(ends):
        try:
            return ors.directions("foot-walking", *ends, "fastest", None, client)
        except ors.OrsError:
            return None  # keep the estimate

    with ThreadPoolExecutor(max_workers=6) as pool:
        found = dict(zip(legs, pool.map(fetch, legs)))
    for o in options:
        for leg in o["legs"]:
            if leg["kind"] == "walk" and found[_ends(leg)]:
                leg.update(found[_ends(leg)])
        o["total_s"] = sum(leg["duration_s"] for leg in o["legs"])
        o["walk_s"] = sum(leg["duration_s"] for leg in o["legs"] if leg["kind"] == "walk")


@router.get("/route/commute", response_model=list[Option])
def route_commute(
    request: Request,
    from_lat: float = Query(...),
    from_lng: float = Query(...),
    to_lat: float = Query(...),
    to_lng: float = Query(...),
):
    if not (in_city(from_lat, from_lng) and in_city(to_lat, to_lng)):
        raise HTTPException(422, "Both ends of the trip must be in Makati.")
    state = request.app.state
    options = commute.plan(state.hubs, state.rides, (from_lat, from_lng), (to_lat, to_lng))
    _refine(options, getattr(state, "ors_client", None))
    return commute.rank(options)  # street distances can reorder them
