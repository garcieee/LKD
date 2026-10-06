"""Priority score prototype: calibrate foot-traffic exposure on real OSM places in Makati, then
check the ranking against cases a sensible person would agree on, plus monotonicity invariants."""
import json
import math
import random
import urllib.parse
import urllib.request

S, W, N, E = 14.5296, 120.9987, 14.5796, 121.0501

# ---------- 1. exposure from OpenStreetMap places ----------
b = f"({S},{W},{N},{E})"
q = f"""[out:json][timeout:90];
(nwr["amenity"~"^(school|kindergarten|college|university)$"]{b};
 nwr["amenity"~"^(hospital|clinic|doctors)$"]{b};
 nwr["railway"~"^(station|stop|halt)$"]{b};
 nwr["highway"="bus_stop"]{b};
 nwr["shop"~"^(mall|supermarket)$"]{b};
 nwr["amenity"="marketplace"]{b};);
out center tags;"""
import os

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pois_raw.json")
if os.path.exists(CACHE):
    els = json.load(open(CACHE))
else:
    els = None
    for url in ("https://overpass.kumi.systems/api/interpreter", "https://lz4.overpass-api.de/api/interpreter", "https://overpass-api.de/api/interpreter"):
        try:
            req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(), headers={"User-Agent": "lakad-hackathon-research"})
            els = json.load(urllib.request.urlopen(req, timeout=150))["elements"]
            print("fetched from", url)
            break
        except Exception as ex:
            print("failed", url, ex)
    if els is None:
        raise SystemExit("no Overpass mirror answered")
    json.dump(els, open(CACHE, "w"))


def weight(t):
    a, r, h, s = t.get("amenity"), t.get("railway"), t.get("highway"), t.get("shop")
    if a in ("school", "kindergarten", "college", "university"):
        return 1.0, "school"
    if a in ("hospital", "clinic"):
        return 1.0, "health"
    if a == "doctors":
        return 0.5, "health"
    if r:
        return 0.9, "rail"
    if h == "bus_stop":
        return 0.4, "bus"
    if a == "marketplace":
        return 0.8, "market"
    if s in ("mall", "supermarket"):
        return 0.7, "mall"
    return 0.0, "?"


pois = []
for e in els:
    lat = e.get("lat") or e.get("center", {}).get("lat")
    lon = e.get("lon") or e.get("center", {}).get("lon")
    if lat is None:
        continue
    w, kind = weight(e.get("tags", {}))
    pois.append((lat, lon, w, kind, e["tags"].get("name", "")))
print(f"{len(pois)} places used")
from collections import Counter
print(dict(Counter(p[3] for p in pois)))

M_LAT = 111_320.0
M_LON = 111_320.0 * math.cos(math.radians(14.55))
TAU, REACH = 100.0, 300.0


def raw_exposure(lat, lon):
    t = 0.0
    for plat, plon, w, _, _ in pois:
        d = math.hypot((plat - lat) * M_LAT, (plon - lon) * M_LON)
        if d <= REACH:
            t += w * math.exp(-d / TAU)
    return t


grid = []
lat = S
while lat <= N:
    lon = W
    while lon <= E:
        grid.append(((lat, lon), raw_exposure(lat, lon)))
        lon += 150 / M_LON
    lat += 150 / M_LAT
vals = sorted(v for _, v in grid)
pct = lambda p: vals[int(p * (len(vals) - 1))]
print(f"grid points {len(vals)}; raw exposure percentiles  p10={pct(.1):.2f} p25={pct(.25):.2f} p50={pct(.5):.2f} p75={pct(.75):.2f} p90={pct(.9):.2f} p99={pct(.99):.2f}")
for theta in (2, 3, 4, 6):
    f = lambda v: 1 - math.exp(-v / theta)
    print(f"  theta={theta}: X at p25/p50/p75/p90 = {f(pct(.25)):.2f} {f(pct(.5)):.2f} {f(pct(.75)):.2f} {f(pct(.9)):.2f}")
top = sorted(grid, key=lambda g: -g[1])[:3]
for (la, lo), v in top:
    near = sorted(pois, key=lambda p: math.hypot((p[0] - la) * M_LAT, (p[1] - lo) * M_LON))
    names = [p[4] for p in near[:12] if p[4]][:3]
    print(f"  busiest ~({la:.4f},{lo:.4f}) raw={v:.1f} near: {names}")
THETA = 1.0
expo = lambda lat, lon: max(0.1, 1 - math.exp(-raw_exposure(lat, lon) / THETA))  # floor: nowhere is zero

# ---------- 2. the score ----------
SEV = {"open_manhole": 1.0, "flooded_drain": 0.85, "pothole": 0.65, "broken_streetlight": 0.55, "blocked_sidewalk": 0.5, "other": 0.25}
WT = dict(sev=0.50, conf=0.20, exp=0.18, wait=0.12)
FLOOR = {"open_manhole": 62.0, "flooded_drain": 48.0}  # safety-critical: never below this while believed real


def score(cat, n=1, deny=0, days=0, X=0.5, danger=0.0, w=WT):
    Sv = SEV[cat]
    C = min(1.0, math.log2(max(n, 1)) / 3)  # 1 reporter 0, 2 -> .33, 4 -> .67, 8+ -> 1
    Wt = min(1.0, days / 14)
    B = (3 + n) / (4 + n + deny)  # belief it is real/still there: Beta(3,1) prior, each reporter a yes
    G = min(1.0, max(0.25, (B - 0.3) / 0.5))  # gate: fresh single report -> 1.0
    raw = w["sev"] * Sv + w["conf"] * C + w["exp"] * X + w["wait"] * Wt
    return min(100.0, max(100 * G * raw, G * FLOOR.get(cat, 0)) + 100 * danger), B


cases = [  # (label, A, B): A should outrank B
    ("open manhole beats pothole, both 1 report, busy", dict(cat="open_manhole", X=.9), dict(cat="pothole", X=.9)),
    ("6 reporters beat 1 (same pothole, busy, 5 days)", dict(cat="pothole", n=6, X=.8, days=5), dict(cat="pothole", n=1, X=.8, days=5)),
    ("busy street beats quiet street (same hazard)", dict(cat="pothole", X=.9), dict(cat="pothole", X=.2)),
    ("12 days waiting beats 1 day (same hazard)", dict(cat="pothole", X=.5, days=12), dict(cat="pothole", X=.5, days=1)),
    ("open manhole 1 report quiet beats streetlight 3 reports busy", dict(cat="open_manhole", X=.2), dict(cat="broken_streetlight", n=3, X=.9, days=3)),
    ("no 'gone' votes beats 3 'gone' votes", dict(cat="pothole", n=1, X=.5), dict(cat="pothole", n=1, deny=3, X=.5)),
    ("flooded drain + child danger beats pothole 4 reports", dict(cat="flooded_drain", X=.6, danger=.10), dict(cat="pothole", n=4, X=.6)),
    ("sidewalk blocked 8 reports busy beats pothole 1 report quiet", dict(cat="blocked_sidewalk", n=8, X=.9, days=4), dict(cat="pothole", X=.2)),
    ("pothole 8 reports quiet 10 days vs open manhole 1 report busy (judgement call)", dict(cat="pothole", n=8, X=.3, days=10), dict(cat="open_manhole", X=.9)),
]
print("\nRanking cases (A should outrank B)")
ok = 0
for label, a, bb in cases:
    sa, _ = score(**a)
    sb, _ = score(**bb)
    ok += sa > sb
    print(f"  {'PASS' if sa > sb else 'FAIL'}  {sa:5.1f} vs {sb:5.1f}  {label}")
print(f"{ok}/{len(cases)} agree")

# ---------- 3. invariants over random tickets ----------
random.seed(3)
bad = 0
for _ in range(20000):
    k = dict(cat=random.choice(list(SEV)), n=random.randint(1, 12), deny=random.randint(0, 6), days=random.uniform(0, 30), X=random.random(), danger=random.choice([0, 0, .1]))
    base, _ = score(**k)
    more_n, _ = score(**{**k, "n": k["n"] + 1})
    older, _ = score(**{**k, "days": k["days"] + 1})
    busier, _ = score(**{**k, "X": min(1, k["X"] + .1)})
    gone, _ = score(**{**k, "deny": k["deny"] + 1})
    if not (0 <= base <= 100 and more_n >= base - 1e-9 and older >= base - 1e-9 and busier >= base - 1e-9 and gone <= base + 1e-9):
        bad += 1
print(f"invariants (more reporters / older / busier never lower; more 'gone' never higher; 0..100): {bad} violations in 20000")
