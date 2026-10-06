"""Load the Chicago 311 csv files into numpy arrays, one `Requests` per app category, and assign each request to a split.

Rows are sorted by creation time (ties by sr_number), so index order IS time order. Chicago's times are local with no
zone; they are read as if UTC, which is fine because only differences are used (a daylight-saving hour is noise).
Run the scripts from the repo root, for example:  models/.venv/bin/python -m models.tickets.eval.matching.chicago.eda
"""
import csv
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from models.tickets.eval.common import splits

DATA = Path(__file__).resolve().parents[2] / "data"
RAW = DATA / "raw"
CACHE = DATA / "cache"  # git-ignored

# app category -> (csv file, Chicago request type). Matching only happens inside one type, so this is just naming.
FILES = {
    "pothole": ("chicago_311_pothole_2024_2025.csv", "Pothole in Street Complaint"),
    "broken_streetlight": ("chicago_311_streetlight_2025.csv", "Street Light Out Complaint"),
    "blocked_sidewalk": ("chicago_311_sidewalk_2025.csv", "Sidewalk Inspection Request"),
    "flooded_drain": ("chicago_311_waterstreet_2025.csv", "Water On Street Complaint"),
}
SPLITS = ("train", "validation", "test")
VALIDATION_START, TEST_START = "2025-07-01", "2025-10-01"  # train 2024-01..2025-06, validation 07..09, test 10..12
GEO_FRACTIONS = (0.6, 0.2, 0.2)  # share of 0.02-degree map blocks in train, validation, test


@dataclass
class Requests:
    """One category's requests as parallel arrays, in time order."""

    category: str
    sr: np.ndarray  # sr_number
    origin: np.ndarray  # Mobile Device, Phone Call, Internet, ...
    status: np.ndarray
    created: np.ndarray  # seconds
    closed: np.ndarray  # seconds, +inf while the request is still open (so "open at t" is closed > t)
    dup: np.ndarray  # the city flagged it as a duplicate
    parent: np.ndarray  # row of the parent in this file; -1 when not a duplicate or the parent is not in the file
    parent_sr: np.ndarray  # the parent's sr_number as the city wrote it ("" when not a duplicate)
    cluster: np.ndarray  # int label of the city's ticket: the parent's sr_number if duplicate, else its own
    lat: np.ndarray  # NaN when the city has no location
    lng: np.ndarray
    address: np.ndarray
    ward: np.ndarray  # the city's ward, for resampling places together

    def __len__(self) -> int:
        return len(self.sr)

    @property
    def located(self) -> np.ndarray:
        return np.isfinite(self.lat) & np.isfinite(self.lng)


def _seconds(texts: list[str]) -> np.ndarray:
    stamps = np.array([t[:19] if t else "NaT" for t in texts], dtype="datetime64[s]")
    out = stamps.astype("int64").astype(float)
    out[np.isnat(stamps)] = np.nan
    return out


def _floats(texts: list[str]) -> np.ndarray:
    return np.array([float(t) if t else np.nan for t in texts], dtype=float)


def from_rows(category: str, rows: list[dict]) -> Requests:
    """Build Requests from csv rows (dicts with the portal's column names)."""
    rows = sorted(rows, key=lambda r: (r["created_date"], r["sr_number"]))
    col = lambda name: [r[name] for r in rows]
    sr, parent_sr = np.array(col("sr_number")), np.array(col("parent_sr_number"))
    dup = np.array(col("duplicate")) == "true"
    dup &= parent_sr != ""  # a duplicate with no named parent cannot be linked to anything
    row_of = {s: i for i, s in enumerate(sr.tolist())}
    parent = np.array([row_of.get(p, -1) if d else -1 for p, d in zip(parent_sr.tolist(), dup)], dtype=int)
    closed = _seconds(col("closed_date"))
    closed[np.isnan(closed)] = np.inf
    _, cluster = np.unique(np.where(dup, parent_sr, sr), return_inverse=True)
    return Requests(
        category=category, sr=sr, origin=np.array(col("origin")), status=np.array(col("status")),
        created=_seconds(col("created_date")), closed=closed, dup=dup, parent=parent,
        parent_sr=np.where(dup, parent_sr, ""), cluster=cluster.astype(int),
        lat=_floats(col("latitude")), lng=_floats(col("longitude")), address=np.array(col("street_address")), ward=np.array(col("ward")),
    )


def load(category: str, raw: Path = RAW) -> Requests:
    with (raw / FILES[category][0]).open(newline="") as f:
        return from_rows(category, list(csv.DictReader(f)))


def load_all(raw: Path = RAW) -> dict[str, Requests]:
    return {category: load(category, raw) for category in FILES}


# ---- which split is a request in? Each request is in exactly one, so no ticket crosses a boundary -----------------
def seconds(day: str) -> float:
    return float(np.datetime64(day, "s").astype("int64"))


def time_split(req: Requests) -> np.ndarray:
    """0 train, 1 validation, 2 test by creation month. The categories with only 2025 use the same boundaries."""
    ids = np.empty(len(req), dtype=int)
    for k, part in enumerate(splits.temporal_split(req.created, seconds(VALIDATION_START), seconds(TEST_START))):
        ids[part] = k
    return ids


def geo_split(everything: dict[str, Requests], fractions=GEO_FRACTIONS, seed: int = 0) -> dict[str, np.ndarray]:
    """0 train, 1 validation, 2 test by 0.02-degree map block, all periods. One block map for all categories pooled,
    so a place is in one split whatever the type. -1 for a request with no location."""
    located = {c: np.flatnonzero(r.located) for c, r in everything.items()}
    lat = np.concatenate([r.lat[located[c]] for c, r in everything.items()])
    lng = np.concatenate([r.lng[located[c]] for c, r in everything.items()])
    which = np.empty(len(lat), dtype=int)
    for k, part in enumerate(splits.block_split(lat, lng, fractions, seed=seed)):
        which[part] = k
    out, start = {}, 0
    for c, r in everything.items():
        ids = np.full(len(r), -1, dtype=int)
        ids[located[c]] = which[start:start + len(located[c])]
        out[c], start = ids, start + len(located[c])
    return out


def rounded(value, digits: int = 4):
    """The same nested numbers with floats rounded, so the committed result files stay small."""
    if isinstance(value, dict):
        return {k: rounded(v, digits) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [rounded(v, digits) for v in value]
    if isinstance(value, (float, np.floating)) and np.isfinite(value):
        return round(float(value), digits)
    return value


# ---- the city's address buffer ---------------------------------------------------------------------------------------
_ADDRESS = re.compile(r"^\s*(\d+)\s+(\S.*?)\s*$")


def street_number(address: str) -> tuple[int, str] | None:
    """('2218 S STEWART AVE') -> (2218, 'S STEWART AVE'), or None when there is no leading number."""
    m = _ADDRESS.match(address or "")
    return (int(m.group(1)), " ".join(m.group(2).upper().split())) if m else None


def number_gap(a: str, b: str) -> float | None:
    """Street numbers apart on the same street; infinity on different streets; None if either address has no number."""
    x, y = street_number(a), street_number(b)
    if x is None or y is None:
        return None
    return abs(x[0] - y[0]) if x[1] == y[1] else float("inf")


def within_buffer(a: str, b: str, numbers: int = 4) -> bool | None:
    """The city's pothole buffer: same street and at most `numbers` street numbers apart. None if either has no number."""
    gap = number_gap(a, b)
    return None if gap is None else gap <= numbers
