"""GET /route/walk: a walking route in one of three modes, the pedestrian-layer contract.

fastest     foot-walking, quickest.
walkable    foot-walking, steering around no-go zones drawn on unresolved reports (potholes, open
            manholes, blocked sidewalks). OpenRouteService has no sidewalk data, so crowd reports are
            what makes this route differ.
accessible  the wheelchair profile (no steps, kinder surfaces), steering around the same zones and also
            around accessibility barriers (missing ramps, blocked tactile paving, broken elevators, steep or
            broken sidewalks), which the other two modes ignore.

Every route says which unresolved reports it still passes, so the app can show a mode's hazards.
"""
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.config import in_city
from app.services import hazards, ors

router = APIRouter()

Mode = Literal["fastest", "walkable", "accessible"]
PROFILE = {"fastest": "foot-walking", "walkable": "foot-walking", "accessible": "wheelchair"}
PREFERENCE = {"fastest": "fastest", "walkable": "recommended", "accessible": "recommended"}


class Route(BaseModel):
    mode: Mode
    distance_m: float
    duration_s: float
    geometry: list[list[float]]  # [[lng, lat], ...], the order Mapbox takes
    hazard_ids: list[str]  # unresolved reports within 20 m of the line that are in the way in this mode
    avoids_hazards: bool  # false for Fastest, and for a mode that could not route around them


def walk_leg(mode: str, start: tuple, end: tuple, reports: list, client=None) -> tuple[dict, bool]:
    """One walking route in `mode`: ({distance_m, duration_s, geometry}, whether it steers around hazard zones).

    Raises ors.OrsError. Shared with /route/commute, whose walking legs follow the mode the user picked.
    """
    avoid = hazards.avoid_polygons(hazards.for_mode(reports, mode), [start, end]) if mode != "fastest" else None
    try:
        found = ors.directions(PROFILE[mode], start, end, PREFERENCE[mode], avoid, client)
    except ors.OrsError as e:
        if e.status != 404 or not avoid:
            raise
        # The zones may box the trip in: a route past a hazard beats no route.
        avoid = None
        found = ors.directions(PROFILE[mode], start, end, PREFERENCE[mode], None, client)
    return found, avoid is not None


@router.get("/route/walk", response_model=Route)
def route_walk(
    request: Request,
    from_lat: float = Query(...),
    from_lng: float = Query(...),
    to_lat: float = Query(...),
    to_lng: float = Query(...),
    mode: Mode = Query("walkable"),
):
    if not (in_city(from_lat, from_lng) and in_city(to_lat, to_lng)):
        raise HTTPException(422, "Both ends of the walk must be in Makati.")
    start, end = (from_lat, from_lng), (to_lat, to_lng)
    reports = request.app.state.store.all()
    client = getattr(request.app.state, "ors_client", None)
    try:
        found, avoids = walk_leg(mode, start, end, reports, client)
    except ors.OrsError as e:
        raise HTTPException(e.status, e.message) from e
    return Route(
        mode=mode,
        **found,
        hazard_ids=hazards.near_route(found["geometry"], hazards.for_mode(reports, mode)),
        avoids_hazards=avoids,
    )
