"""Build resources/places.json: schools, clinics, stations, malls and markets inside Makati, from OpenStreetMap.

  python3 models/tickets/resources/build_places.py                      ask the Overpass API (about 230 KB back)
  python3 models/tickets/resources/build_places.py --from saved.json    reuse a saved Overpass answer

Data: (c) OpenStreetMap contributors, ODbL. The kinds match EXPOSURE_WEIGHTS in settings.py.
"""
import argparse
import json
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

BBOX = (14.5296, 120.9987, 14.5796, 121.0501)  # south, west, north, east: the city extent in settings.py
MIRRORS = ("https://lz4.overpass-api.de/api/interpreter", "https://overpass-api.de/api/interpreter")
OUT = Path(__file__).with_name("places.json")


def query() -> str:
    b = f"({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]})"
    return f"""[out:json][timeout:90];
(nwr["amenity"~"^(school|kindergarten|college|university)$"]{b};
 nwr["amenity"~"^(hospital|clinic|doctors)$"]{b};
 nwr["railway"~"^(station|stop|halt)$"]{b};
 nwr["highway"="bus_stop"]{b};
 nwr["shop"~"^(mall|supermarket)$"]{b};
 nwr["amenity"="marketplace"]{b};);
out center tags;"""


def kind_of(tags: dict) -> str | None:
    amenity, shop = tags.get("amenity"), tags.get("shop")
    if amenity in ("school", "kindergarten", "college", "university"):
        return "school"
    if amenity in ("hospital", "clinic"):
        return "health"
    if amenity == "doctors":
        return "doctor"
    if tags.get("railway"):
        return "rail"
    if tags.get("highway") == "bus_stop":
        return "bus"
    if amenity == "marketplace":
        return "market"
    if shop in ("mall", "supermarket"):
        return "mall"
    return None


def fetch() -> list[dict]:
    data = urllib.parse.urlencode({"data": query()}).encode()
    for url in MIRRORS:
        try:
            request = urllib.request.Request(url, data=data, headers={"User-Agent": "lakad-hackathon"})
            return json.load(urllib.request.urlopen(request, timeout=150))["elements"]
        except Exception as error:
            print("failed", url, error)
    raise SystemExit("no Overpass mirror answered")


def build(elements: list[dict]) -> dict:
    places = []
    for e in elements:
        lat = e.get("lat") or e.get("center", {}).get("lat")
        lng = e.get("lon") or e.get("center", {}).get("lon")
        kind = kind_of(e.get("tags", {}))
        if lat is not None and kind:
            places.append([round(lat, 5), round(lng, 5), kind, e["tags"].get("name", "")])
    places.sort()
    return {"source": "OpenStreetMap contributors (ODbL)", "fetched": str(date.today()), "bbox": list(BBOX), "places": places}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="saved", help="a saved Overpass JSON answer to use instead of asking the API")
    args = parser.parse_args()
    elements = json.loads(Path(args.saved).read_text())  if args.saved else fetch()
    elements = elements["elements"] if isinstance(elements, dict) else elements
    result = build(elements)
    OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(result['places'])} places -> {OUT.name} ({OUT.stat().st_size / 1024:.0f} KB)")
