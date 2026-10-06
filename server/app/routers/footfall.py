"""GET /footfall: modeled foot traffic for Makati, a relative 0-100 index per transit hub and district.

An estimate from transit hubs, route ends and curated districts (data/footfall/hotspots.json), not a count.
`kind` says so, and will read "measured" for zones a camera counts. Day and hour default to now in Manila.
"""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.services import footfall, forecast

router = APIRouter()

Day = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class Scored(BaseModel):
    index: float  # 0-100, relative: 100 is the strongest hub (or district) at its busiest hour
    lower: float
    upper: float


class Point(Scored):
    id: str
    name: str
    kind: Literal["hub", "anchor"]  # anchor: a district's draw that the transit data cannot see
    lat: float
    lng: float
    error_m: int
    profile: str
    district: str | None


class District(Scored):
    id: str
    name: str
    lat: float
    lng: float
    radius_m: int
    profile: str
    tier: Literal[1, 2, 3]
    share: float  # demand against the strongest district, any hour
    hubs: int
    route_ends: int
    anchor: float
    basis: str  # where the district's anchor comes from


class Footfall(BaseModel):
    kind: Literal["estimate", "measured"]
    method: str
    day: Day
    hour: float
    points: list[Point]
    districts: list[District]


@router.get("/footfall", response_model=Footfall)
def get_footfall(
    request: Request,
    day: Day | None = None,
    hour: float | None = Query(None, ge=0, lt=24),
):
    model = request.app.state.footfall
    if model is None:
        raise HTTPException(503, "No foot-traffic model loaded.")
    now = footfall.manila_now()
    return footfall.estimate(model, day or footfall.DAYS[now.weekday()], now.hour + now.minute / 60 if hour is None else hour)


class SeriesPoint(BaseModel):
    t: str  # ISO 8601, Manila time (+08:00), on the hour
    index: float
    kind: Literal["history", "forecast"]
    lower: float | None = None  # 80% band, forecast only
    upper: float | None = None


class Series(BaseModel):
    zone: str
    name: str
    method: str
    history_source: Literal["simulated", "measured"]
    now: str
    backtest_smape_pct: float  # error of forecasting the last simulated week from the three before it
    points: list[SeriesPoint]


@router.get("/footfall/series", response_model=Series)
def get_series(
    request: Request,
    zone: str = Query("all", description='"all" or a district id from /footfall'),
    past_days: int = Query(7, ge=1, le=14),
    future_days: int = Query(3, ge=1, le=7),
    at: datetime | None = Query(None, description="Treat this moment as now (ISO 8601). Default: now in Manila."),
):
    """Hourly index for a zone: `past_days` of history, then `future_days` of forecast. The history is simulated."""
    model = request.app.state.footfall
    if model is None:
        raise HTTPException(503, "No foot-traffic model loaded.")
    if forecast.zone_name(model, zone) is None:
        raise HTTPException(404, "No such zone.")
    now = at.replace(tzinfo=footfall.MANILA) if at and at.tzinfo is None else at
    return forecast.series(model, zone, now or footfall.manila_now(), past_days, future_days)
