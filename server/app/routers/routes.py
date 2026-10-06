"""GET /route/walk: a walking route in one of three modes, the pedestrian-layer contract.

fastest     foot-walking, quickest.
walkable    foot-walking, steering around no-go zones drawn on unresolved reports (potholes, open
            manholes, blocked or broken sidewalks). OpenRouteService has no sidewalk data, so crowd reports
            are what makes this route differ.
accessible  the wheelchair profile (no steps, kinder surfaces), steering around the same zones and also
            around missing ramps, blocked tactile paving and broken elevators, which the other two ignore.

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


class Step(BaseModel):
    type: int  # ORS turn code: 0 left, 1 right, 2 sharp left, 3 sharp right, 4 slight left, 5 slight right, 6 straight, 7 roundabout in, 8 out, 9 u-turn, 10 arrive, 11 depart, 12 keep left, 13 keep right
    text: str  # "Turn left onto Ayala Avenue"
    name: str  # the street the step goes along, "" when unnamed
    distance_m: float  # along this step, until the next manoeuvre
    at: int  # index into geometry where the manoeuvre happens


class Route(BaseModel):
    mode: Mode
    distance_m: float
    duration_s: float
    geometry: list[list[float]]  # [[lng, lat], ...], the order Mapbox takes
    steps: list[Step] = []  # turn by turn; empty when the router sent none
    hazard_ids: list[str]  # unresolved reports within 20 m of the line that are in the way in this mode
    avoids_hazards: bool  # false for Fastest, and for a mode that could not route around them


def walk_leg(mode: str, start: tuple, end: tuple, reports: list, client=None) -> tuple[dict, bool]:
    """One walking route in `mode`: ({distance_m, duration_s, geometry}, whether it steers around all the mode's zones).

    Raises ors.OrsError. Shared with /route/commute, whose walking legs follow the mode the user picked.
    """
    tries = [hazards.avoid_polygons(hazards.for_mode(reports, mode), [start, end])] if mode != "fastest" else []
    if mode == "accessible":  # boxed in by barriers: still keep clear of the hazards, a manhole is still a manhole
        tries.append(hazards.avoid_polygons(hazards.for_mode(reports, "walkable"), [start, end]))
    for i, avoid in enumerate(tries):
        if not avoid or avoid in tries[:i]:
            continue
        try:
            return ors.directions(PROFILE[mode], start, end, PREFERENCE[mode], avoid, client), i == 0
        except ors.OrsError as e:
            if e.status != 404:
                raise
    # The zones may box the trip in: a route past a hazard beats no route.
    return ors.directions(PROFILE[mode], start, end, PREFERENCE[mode], None, client), False


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
