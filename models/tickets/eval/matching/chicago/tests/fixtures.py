"""A tiny hand-made Chicago-like fixture that every test in this folder shares: 16 pothole requests along one line.

Positions are metres north of one point, so every distance is checkable by hand. Days are in January 2025, 08:00.
  sr  day  north  note
  A    1     0    ticket, closes day 10
  B    2    10    duplicate of A
  C    3    20    duplicate of A
  D    4    30    ticket, closes day 10
  E    5   300    ticket, stays open
  F    6   400    ticket, stays open
  G    7   405    duplicate of F
  I    8    50    ticket, stays open
  J    9    80    ticket, stays open
  H   12    15    ticket, stays open (A and D are already closed)
  K   14     5    ticket, stays open   (group 1)
  L   15     0    duplicate of X, a parent that is not in the file
  M   16     -    duplicate of A, no location
  N   17     8    duplicate of A       (group 1: its parent A is in group 0)
  Q   19   602    duplicate of R, but created BEFORE its parent
  R   20   600    ticket, stays open
"""
import math

import numpy as np

from models.tickets.eval.matching.chicago import prepare
from models.tickets.matching import geo

LAT, LNG = 41.88, -87.63

#  sr, day, north metres (None: no location), parent sr ("": not a duplicate), closed day (None: open), origin
TABLE = [
    ("A", 1, 0, "", 10, "Phone Call"), ("B", 2, 10, "A", 10, "Mobile Device"), ("C", 3, 20, "A", 10, "Mobile Device"),
    ("D", 4, 30, "", 10, "Phone Call"), ("E", 5, 300, "", None, "Phone Call"), ("F", 6, 400, "", None, "Internet"),
    ("G", 7, 405, "F", None, "Mobile Device"), ("I", 8, 50, "", None, "Phone Call"), ("J", 9, 80, "", None, "Phone Call"),
    ("H", 12, 15, "", None, "Internet"), ("K", 14, 5, "", None, "Phone Call"), ("L", 15, 0, "X", None, "Mobile Device"),
    ("M", 16, None, "A", None, "Mobile Device"), ("N", 17, 8, "A", None, "Mobile Device"),
    ("Q", 19, 602, "R", None, "Mobile Device"), ("R", 20, 600, "", None, "Phone Call"),
]
ADDRESS = {"A": "100 N MAIN ST", "B": "102 N MAIN ST", "C": "108 N MAIN ST", "D": "100 N OAK AVE", "I": "50 N PINE ST",
           "H": "52 N PINE ST", "K": "104 N MAIN ST"}


def north(metres: float) -> float:
    return LAT + math.degrees(metres / geo.EARTH_RADIUS_M)


def rows() -> list[dict]:
    out = []
    for sr, day, at, parent, closed, origin in TABLE:
        out.append({
            "sr_number": sr, "sr_type": "Pothole in Street Complaint", "status": "Open" if closed is None else "Completed",
            "origin": origin, "created_date": f"2025-01-{day:02d}T08:00:00.000",
            "closed_date": "" if closed is None else f"2025-01-{closed:02d}T08:00:00.000",
            "duplicate": "true" if parent else "false", "parent_sr_number": parent,
            "latitude": "" if at is None else repr(north(at)), "longitude": "" if at is None else repr(LNG),
            "street_address": ADDRESS.get(sr, ""), "community_area": "1", "ward": "1"})
    return rows_shuffled(out)


def rows_shuffled(out: list[dict]) -> list[dict]:
    """The csv is not in time order, so from_rows must sort."""
    return [out[i] for i in np.random.default_rng(1).permutation(len(out))]


def requests() -> prepare.Requests:
    return prepare.from_rows("pothole", rows())


def groups(req: prepare.Requests) -> np.ndarray:
    """Everything in group 0 except K and N, which are in group 1."""
    g = np.zeros(len(req), dtype=int)
    for sr in ("K", "N"):
        g[list(req.sr).index(sr)] = 1
    return g
