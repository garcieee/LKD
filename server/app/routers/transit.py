"""GET /transit/hubs: Makati's PUV terminals, bus stops and MRT-3 / LRT-1 stations, nearest first when the caller sends a position.

PUV positions are estimates from the study's maps (data/transit/terminals.geojson): `error_m` says how rough.
Station positions come from OpenStreetMap (data/transit/stations.geojson).
"""
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.services import transit

router = APIRouter()

Kind = Literal["terminal", "stop", "station"]  # station: a train station
Mode = Literal["jeepney", "uv_express", "city_bus", "p2p_bus", "mrt3", "lrt1"]


class Hub(BaseModel):
    id: str
    name: str
    kind: Kind
    modes: list[Mode]  # the kinds of PUV and trains that serve it, trains first
    lat: float
    lng: float
    error_m: int  # rough radius of doubt around the position
    distance_m: int | None = None  # from the caller, when a position was sent


@router.get("/transit/hubs", response_model=list[Hub])
def hubs(
    request: Request,
    lat: float | None = Query(None, ge=-90, le=90),
    lng: float | None = Query(None, ge=-180, le=180),
    kind: Kind | None = None,
    mode: Mode | None = None,
    limit: int = Query(10, ge=1, le=50),
):
    """`lat` and `lng` together sort by distance. `kind` and `mode` narrow the list; `limit` caps it."""
    if (lat is None) != (lng is None):
        raise HTTPException(422, "Send lat and lng together.")
    found = [h for h in request.app.state.hubs if (kind is None or h["kind"] == kind) and (mode is None or mode in h["modes"])]
    if lat is None:
        return found[:limit]
    return transit.nearest(found, lat, lng, limit)
