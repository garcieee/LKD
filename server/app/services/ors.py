"""OpenRouteService client (https://openrouteservice.org). Place search now; walking directions next.

The key stays on the server: the app only ever talks to our API.
"""
import logging

import httpx

from app.config import CITY_BOUNDS, ORS_API_KEY

log = logging.getLogger(__name__)

BASE = "https://api.openrouteservice.org"
TIMEOUT = 8.0  # seconds; the app waits on this while the user types


class OrsError(Exception):
    """OpenRouteService can't answer. `status` is what our API should reply, `message` is safe to show."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def autocomplete(text: str, near: tuple[float, float] | None = None, client: httpx.Client | None = None) -> list[dict]:
    """Places in Makati matching `text`, best first, as [{label, lat, lng}]. `near` is (lat, lng): results close to it rank higher.

    ponytail: one ORS call per search, no cache. The free tier has a daily cap; add a small TTL cache
    keyed on (text, near rounded to ~100 m) if the demo gets near it.
    """
    if not ORS_API_KEY:
        raise OrsError(503, "Place search isn't set up on the server (ORS_API_KEY).")
    west, south, east, north = CITY_BOUNDS
    params = {
        "text": text,
        "size": 5,
        "boundary.rect.min_lon": west,
        "boundary.rect.min_lat": south,
        "boundary.rect.max_lon": east,
        "boundary.rect.max_lat": north,
    }
    if near:
        params["focus.point.lat"], params["focus.point.lon"] = near
    try:
        # The key goes in a header, not the URL, so it never lands in a log line.
        r = (client or httpx).get(
            f"{BASE}/geocode/autocomplete", params=params, headers={"Authorization": ORS_API_KEY}, timeout=TIMEOUT
        )
    except httpx.HTTPError as e:
        log.warning("ORS unreachable: %s", type(e).__name__)
        raise OrsError(502, "Place search is unavailable. Try again.") from e
    if r.status_code == 429:
        raise OrsError(503, "Place search is busy. Try again in a minute.")
    if r.status_code != 200:
        log.warning("ORS answered %s", r.status_code)  # 401/403 is a bad key: the log says, the app doesn't
        raise OrsError(502, "Place search is unavailable. Try again.")
    return _places(r.json())


def _places(body: dict) -> list[dict]:
    """GeoJSON features -> [{label, lat, lng}], skipping any without a name or a point."""
    out = []
    for f in body.get("features") or []:
        try:
            lng, lat = f["geometry"]["coordinates"][:2]
            label = f["properties"]["label"]
            out.append({"label": str(label), "lat": float(lat), "lng": float(lng)})
        except (KeyError, TypeError, ValueError):
            continue
    return out
