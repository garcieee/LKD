"""Build resources/districts.json: the boundaries of Makati's 23 barangays and the district each is in, from
OpenStreetMap. A ticket gets the district of the barangay its spot is in (classification/routing.py district_of).

  python3 -m models.tickets.resources.build_districts                     ask the Overpass API
  python3 -m models.tickets.resources.build_districts --from saved.json   reuse a saved Overpass answer

Run from the repo root. Data: (c) OpenStreetMap contributors, ODbL. The lists are Makati after the Supreme Court's
EMBO ruling (ATTACH.md): the ten EMBO barangays are Taguig now, so they get no district.
"""
import argparse
import json
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from ..classification.classify import tokens
from ..classification.routing import district_of
from .build_places import MIRRORS

OUT = Path(__file__).with_name("districts.json")
DISTRICTS = {
    1: ("District 1 (Western Makati)", ("Bangkal", "Bel-Air", "Carmona", "Dasmariñas", "Forbes Park", "Kasilawan",
                                        "La Paz", "Magallanes", "Olympia", "Palanan", "Pio del Pilar", "Poblacion",
                                        "San Antonio", "San Isidro", "San Lorenzo", "Santa Cruz", "Singkamas",
                                        "Tejeros", "Urdaneta", "Valenzuela")),
    2: ("District 2 (Eastern Makati)", ("Guadalupe Nuevo", "Guadalupe Viejo", "Pinagkaisahan")),
}
# Makati itself, and every barangay with a member inside it: that includes neighbours that share a border street.
QUERY = """[out:json][timeout:120];
area["boundary"="administrative"]["admin_level"="6"]["name"~"Makati"]->.city;
(rel(pivot.city); rel(area.city)["boundary"="administrative"]["admin_level"="10"];);
out geom;"""


def key(name: str) -> str:
    """One spelling per barangay: case, accents, punctuation and a "Barangay" prefix ignored, "Sta." read as Santa."""
    words = tokens(name)
    words = words[1:] if words[:1] in (["barangay"], ["brgy"]) else words
    return " ".join("santa" if w == "sta" else w for w in words)


def rings(relation: dict) -> list[list[list[float]]]:
    """The relation's outer ways joined end to end into closed [lng, lat] rings, rounded to 5 decimals (about 1 m).

    ponytail: inner rings (holes) are dropped, so a point in a hole counts as inside. Subtract them if a barangay
    ever gets one."""
    ways = [[(p["lon"], p["lat"]) for p in m["geometry"]] for m in relation["members"]
            if m["type"] == "way" and m["role"] in ("outer", "") and m.get("geometry")]
    out = []
    while ways:
        ring = ways.pop(0)
        while ring[0] != ring[-1]:
            for i, way in enumerate(ways):
                if way[0] == ring[-1]:
                    ring += way[1:]
                elif way[-1] == ring[-1]:
                    ring += way[-2::-1]
                else:
                    continue
                del ways[i]
                break
            else:
                raise SystemExit(f"{relation['tags'].get('name')} (relation {relation['id']}): the outer ways do not close")
        points = [[round(x, 5), round(y, 5)] for x, y in ring]
        out.append([p for i, p in enumerate(points) if i == 0 or p != points[i - 1]])
    return out


def inside_point(ring: list[list[float]]) -> tuple[float, float]:
    """(lng, lat) of a point inside the ring: the middle of the widest span across its middle latitude."""
    lats = [y for _, y in ring]
    y = (min(lats) + max(lats)) / 2
    xs = sorted(x1 + (y - y1) * (x2 - x1) / (y2 - y1) for (x1, y1), (x2, y2) in zip(ring, ring[1:]) if (y1 > y) != (y2 > y))
    a, b = max(zip(xs[::2], xs[1::2]), key=lambda span: span[1] - span[0])
    return (a + b) / 2, y


def fetch() -> list[dict]:
    data = urllib.parse.urlencode({"data": QUERY}).encode()
    for url in MIRRORS:
        try:
            request = urllib.request.Request(url, data=data, headers={"User-Agent": "lakad-hackathon"})
            return json.load(urllib.request.urlopen(request, timeout=150))["elements"]
        except Exception as error:
            print("failed", url, error)
    raise SystemExit("no Overpass mirror answered")


def build(elements: list[dict]) -> dict:
    """Fails loudly when one of the 23 is missing or found twice: nothing is guessed."""
    cities = [e for e in elements if e["type"] == "relation" and e.get("tags", {}).get("admin_level") == "6"]
    if len(cities) != 1:
        raise SystemExit(f"expected Makati alone at admin_level 6, got {[c.get('tags', {}).get('name') for c in cities]}")
    makati = [(0, "Makati", (-180.0, -90.0, 180.0, 90.0), rings(cities[0]))]
    wanted = {key(name): (name, d) for d, (_, names) in DISTRICTS.items() for name in names}
    found: dict[str, list] = {}
    for e in elements:
        tags = e.get("tags", {})
        if e["type"] != "relation" or tags.get("admin_level") != "10":
            continue
        if key(tags.get("name", "")) not in wanted:
            print(f"  not on the list: {tags.get('name')!r} (relation {e['id']})")
            continue
        shape = rings(e)
        lng, lat = inside_point(max(shape, key=len))
        if district_of(lat, lng, makati) is None:  # a namesake in a neighbouring city that touches Makati
            print(f"  outside Makati, left out: {tags.get('name')!r} (relation {e['id']})")
            continue
        found.setdefault(key(tags["name"]), []).append((e["id"], tags["name"], shape))
    missing = [name for k, (name, _) in wanted.items() if not found.get(k)]
    twice = [name for k, (name, _) in wanted.items() if len(found.get(k, [])) > 1]
    if missing or twice:
        raise SystemExit(f"missing: {missing}; found more than once: {twice}")
    barangays = []
    for k, (name, d) in wanted.items():
        osm_id, osm_name, shape = found[k][0]
        print(f"  {name:16} district {d}  relation {osm_id}  {len(shape)} ring(s)" + (f"  OSM name {osm_name!r}" if osm_name != name else ""))
        barangays.append({"name": name, "district_id": d, "rings": shape})
    return {"source": "OpenStreetMap contributors (ODbL)", "fetched": str(date.today()),
            "districts": {str(d): name for d, (name, _) in DISTRICTS.items()}, "barangays": barangays}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="saved", help="a saved Overpass JSON answer to use instead of asking the API")
    args = parser.parse_args()
    elements = json.loads(Path(args.saved).read_text()) if args.saved else fetch()
    elements = elements["elements"] if isinstance(elements, dict) else elements
    result = build(elements)
    OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(result['barangays'])} barangays -> {OUT.name} ({OUT.stat().st_size / 1024:.0f} KB)")
