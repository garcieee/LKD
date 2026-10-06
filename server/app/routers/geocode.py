"""GET /geocode: the app's destination search. Looks places up in Makati through OpenRouteService."""
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.services import ors

router = APIRouter()


class Place(BaseModel):
    label: str
    lat: float
    lng: float


@router.get("/geocode", response_model=list[Place])
def geocode(
    request: Request,
    q: str = Query(..., min_length=2, max_length=100),
    lat: float | None = Query(None, ge=-90, le=90),
    lng: float | None = Query(None, ge=-180, le=180),
):
    """`lat` and `lng` together (the user's position) rank nearby places first."""
    if (lat is None) != (lng is None):
        raise HTTPException(422, "Send lat and lng together.")
    near = (lat, lng) if lat is not None and lng is not None else None
    try:
        return ors.autocomplete(q.strip(), near, getattr(request.app.state, "ors_client", None))
    except ors.OrsError as e:
        raise HTTPException(e.status, e.message) from e
