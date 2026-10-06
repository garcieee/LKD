"""Fill db/reports.json with ~60 fake reports so the dashboard queue and Insights have something to show.

Run from server/: python scripts/seed_demo.py          (add --clear to just remove them)
Demo ids start with "demo-", so re-running replaces them and never touches real reports.
"""
import random
import struct
import sys
import zlib
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")
from app.config import STORAGE_DIR
from app.db.store import ReportStore

random.seed(7)
PREFIX = "demo-"
NOTES = ["", "", "Near the corner", "Been like this for weeks", "Kids walk here to school", "Hard to see at night", "Water pooling after rain"]
# category: relative weight. Statuses and ages are mixed below so every Insights card has data.
CATEGORIES = {
    "pothole": 20, "blocked_sidewalk": 16, "broken_streetlight": 10, "flooded_drain": 8, "open_manhole": 4, "other": 4,
    "missing_ramp": 5, "unsafe_sidewalk": 3, "blocked_tactile_paving": 2, "broken_elevator": 2,
}
# Clusters (lat, lng) so Hotspots finds piles, plus scatter across the city.
CLUSTERS = [(14.5547, 121.0244), (14.5656, 121.0150), (14.5509, 121.0176)]


def png(path):  # 1x1 grey PNG, so every demo photo_url resolves
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    raw = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    path.write_bytes(raw + chunk(b"IDAT", zlib.compress(b"\x00\x99\x99\x99")) + chunk(b"IEND", b""))


def main():
    store = ReportStore(STORAGE_DIR / "reports.json")
    real = [r for r in store.all() if not r["id"].startswith(PREFIX)]
    if "--clear" in sys.argv:
        store._write(real)
        return print(f"Removed demo reports, {len(real)} real kept.")

    (STORAGE_DIR / "photos").mkdir(parents=True, exist_ok=True)
    png(STORAGE_DIR / "photos" / "demo.png")
    now = datetime.now(timezone.utc)
    iso = lambda t: t.isoformat(timespec="seconds")
    cats = [c for c, w in CATEGORIES.items() for _ in range(w)]
    demo = []
    for i in range(60):
        created = now - timedelta(hours=random.uniform(0.2, 9 * 24))
        age_h = (now - created).total_seconds() / 3600
        status = random.choices(["open", "verified", "assigned", "fixed"], [3, 2, 2, 4 if age_h > 6 else 0])[0]
        # Fixed within 3 h .. 4 d of reporting, but never in the future.
        updated = min(now, created + timedelta(hours=random.uniform(3, 96))) if status != "open" else created
        if random.random() < 0.55:
            lat, lng = random.choice(CLUSTERS)
            lat, lng = lat + random.gauss(0, 0.0006), lng + random.gauss(0, 0.0006)
        else:
            lat, lng = random.uniform(14.535, 14.575), random.uniform(121.005, 121.045)
        demo.append({
            "id": f"{PREFIX}{i:03d}", "category": random.choice(cats), "lat": lat, "lng": lng,
            "heading": random.choice([None, round(random.uniform(0, 360))]), "note": random.choice(NOTES),
            "photo_url": "/photos/demo.png", "status": status, "created_at": iso(created), "updated_at": iso(updated),
        })
    demo.sort(key=lambda r: r["created_at"])  # the store keeps arrival order
    store._write(sorted(real + demo, key=lambda r: r["created_at"]))
    print(f"Wrote {len(demo)} demo reports ({len(real)} real kept).")


main()
