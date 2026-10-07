"""Build src/data/barangays.ts: Makati's 23 barangays for the dashboard's Barangays menu and map labels.

  python3 dashboard/scripts/build_barangays.py        (from the repo root; standard library only)

The boundaries and districts are models/tickets/resources/districts.json (OpenStreetMap contributors, ODbL), the same
ones the ticket engine uses to give a ticket its district. This adds what the map needs: an id, a bounding box (to zoom
to), a label point (the spot furthest inside the shape, so a name sits in the middle of an odd outline, not on its edge),
and a size rank (big barangays get their names placed first when labels collide). Coordinates are rounded to 5 decimals,
about a metre.
"""
import heapq
import json
import math
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "models" / "tickets" / "resources" / "districts.json"
OUT = ROOT / "dashboard" / "src" / "data" / "barangays.ts"
PHI = math.cos(math.radians(14.55))  # a degree of longitude is this much of a degree of latitude here


def slug(name: str) -> str:
    plain = unicodedata.normalize("NFD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


def tidy(ring):
    """Rounded to 5 decimals, no repeated points, closed."""
    out = []
    for lng, lat in ring:
        p = (round(lng, 5), round(lat, 5))
        if not out or p != out[-1]:
            out.append(p)
    if out[0] != out[-1]:
        out.append(out[0])
    return out


def area(ring):
    """Square degrees, in the isotropic scale (longitude shrunk by PHI): only for ranking sizes."""
    return abs(sum(a[0] * PHI * b[1] - b[0] * PHI * a[1] for a, b in zip(ring, ring[1:]))) / 2


def dist_to_edges(x, y, rings):
    """Signed distance from (x, y) to the outline: positive inside, in the isotropic scale."""
    inside, best = False, float("inf")
    for ring in rings:
        pts = [(lng * PHI, lat) for lng, lat in ring]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
                inside = not inside
            dx, dy = bx - ax, by - ay
            t = 0 if dx == dy == 0 else max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
            best = min(best, math.hypot(x - (ax + t * dx), y - (ay + t * dy)))
    return best if inside else -best


def label_point(rings, precision=1e-6):
    """The pole of inaccessibility: the point furthest from every edge (the polylabel algorithm, on a quadtree)."""
    pts = [(lng * PHI, lat) for ring in rings for lng, lat in ring]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    minx, miny, maxx, maxy = min(xs), min(ys), max(xs), max(ys)
    size = max(maxx - minx, maxy - miny)
    h = size / 2
    sq2 = math.sqrt(2)
    n = 0

    def cell(x, y, half):
        """A square of the search grid, centred on (x, y) in the scaled plane, ordered by the best point it could hold."""
        nonlocal n
        n += 1
        d = dist_to_edges(x, y, rings)  # takes raw degrees for the rings and scales their longitude itself
        return (-(d + half * sq2), n, x, y, half, d)

    queue = []
    cx, cy = minx + (maxx - minx) / 2, miny + (maxy - miny) / 2
    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            heapq.heappush(queue, cell(x + h, y + h, h))
            y += size
        x += size
    best = cell(cx, cy, 0)
    while queue:
        top = heapq.heappop(queue)
        if top[5] > best[5]:
            best = top
        if -top[0] - best[5] <= precision:
            continue
        half = top[4] / 2
        for dx in (-half, half):
            for dy in (-half, half):
                heapq.heappush(queue, cell(top[2] + dx, top[3] + dy, half))
    return best[2] / PHI, best[3]


def main():
    src = json.loads(SOURCE.read_text())
    rows = []
    for b in src["barangays"]:
        rings = [tidy(r) for r in b["rings"]]
        lngs = [p[0] for r in rings for p in r]
        lats = [p[1] for r in rings for p in r]
        lng, lat = label_point(rings)
        rows.append(
            {
                "id": slug(b["name"]),
                "name": b["name"],
                "district": b["district_id"],
                "center": [round(lng, 5), round(lat, 5)],
                "bbox": [min(lngs), min(lats), max(lngs), max(lats)],
                "area": sum(area(r) for r in rings),
                "rings": rings,
            }
        )
    order = sorted(range(len(rows)), key=lambda i: -rows[i]["area"])
    for rank, i in enumerate(order):
        rows[i]["rank"] = rank
    for r in rows:
        del r["area"]
    rows.sort(key=lambda r: r["name"].lower())
    body = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    # one barangay per line, so a diff of a rebuilt file reads
    body = body.replace('},{"id"', '},\n  {"id"').replace('[{"id"', '[\n  {"id"').replace("}]", "}\n]")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "// GENERATED by dashboard/scripts/build_barangays.py from models/tickets/resources/districts.json. Do not edit.\n"
        f"// {src['source']}, fetched {src['fetched']}. Makati's 23 barangays after the EMBO ruling (the ten EMBO\n"
        "// barangays are Taguig now). center: where the name goes. rank: 0 is the biggest. [lng, lat] everywhere.\n"
        'import type { Barangay } from "../features/barangays/barangays.ts";\n\n'
        f"export const DISTRICTS: Record<number, string> = {json.dumps({int(k): v for k, v in src['districts'].items()}, ensure_ascii=False)};\n\n"
        f"export const BARANGAYS: Barangay[] = {body};\n"
    )
    print(f"wrote {OUT.relative_to(ROOT)}: {len(rows)} barangays, {OUT.stat().st_size / 1024:.0f} KB")


main()
