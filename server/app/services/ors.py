"""OpenRouteService client (https://openrouteservice.org): place search and walking directions.

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


def directions(
    profile: str,
    start: tuple[float, float],
    end: tuple[float, float],
    preference: str = "recommended",
    avoid: dict | None = None,
    client: httpx.Client | None = None,
) -> dict:
    """A walking route between two (lat, lng) points: {distance_m, duration_s, geometry: [[lng, lat], ...], steps}.

    Each step is {type, text, name, distance_m, at}: `type` is ORS's turn code (0 left ... 10 arrive, 11 depart),
    `at` the index into geometry where the manoeuvre happens. No steps (ORS sent none) is an empty list, not an error.

    `profile` is an ORS profile: foot-walking, or wheelchair for the Accessible mode. `avoid` is a GeoJSON
    MultiPolygon of no-go zones. Status 404 means ORS found no route (try again without `avoid`).
    """
    if not ORS_API_KEY:
        raise OrsError(503, "Routing isn't set up on the server (ORS_API_KEY).")
    body = {
        "coordinates": [[start[1], start[0]], [end[1], end[0]]],  # ORS wants [lng, lat]
        "preference": preference,
        "instructions": True,  # the turn steps ride along with the line
    }
    if avoid:
        body["options"] = {"avoid_polygons": avoid}
    try:
        r = (client or httpx).post(
            f"{BASE}/v2/directions/{profile}/geojson", json=body, headers={"Authorization": ORS_API_KEY}, timeout=TIMEOUT
        )
    except httpx.HTTPError as e:
        log.warning("ORS unreachable: %s", type(e).__name__)
        raise OrsError(502, "Routing is unavailable. Try again.") from e
    if r.status_code == 429:
        raise OrsError(503, "Routing is busy. Try again in a minute.")
    if r.status_code in (400, 404):  # 404: no route; 400: e.g. a point it cannot snap to a footpath
        log.info("ORS found no route: %s %s", r.status_code, r.text[:200])
        raise OrsError(404, "No walking route found between those points.")
    if r.status_code != 200:
        log.warning("ORS answered %s", r.status_code)
        raise OrsError(502, "Routing is unavailable. Try again.")
    try:
        feature = r.json()["features"][0]
        summary = feature["properties"]["summary"]
        line = [[round(p[0], 6), round(p[1], 6)] for p in feature["geometry"]["coordinates"]]  # drop elevation
        steps = _steps(feature["properties"].get("segments"), len(line))
        return {
            "distance_m": float(summary["distance"]),
            "duration_s": float(summary["duration"]),
            "geometry": line,
            "steps": steps,
        }
    except (KeyError, IndexError, TypeError, ValueError) as e:
        log.warning("ORS route in an unexpected shape")
        raise OrsError(502, "Routing is unavailable. Try again.") from e


def _steps(segments, points: int) -> list[dict]:
    """ORS segments -> [{type, text, name, distance_m, at}], skipping any step that is not in the shape we expect."""
    out = []
    for seg in segments or []:
        for st in seg.get("steps") or []:
            try:
                at = int(st["way_points"][0])
                if not 0 <= at < points:
                    continue
                name = str(st.get("name") or "")
                out.append(
                    {
                        "type": int(st["type"]),
                        "text": str(st["instruction"]),
                        "name": "" if name == "-" else name,  # ORS writes "-" for an unnamed way
                        "distance_m": float(st["distance"]),
                        "at": at,
                    }
                )
            except (KeyError, IndexError, TypeError, ValueError):
                continue
    return out


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
