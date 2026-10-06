"""Pair datasets for the same-place matcher, built from the city's own duplicate flags.

  positive  (child, parent): a request the city flagged as duplicate whose parent is in the file.
  far       a child paired with an open ticket 100-500 m away, one per positive: the CLEAN negative.
  near      a request paired with every open ticket under 60 m that is not its parent: the HARD negative.
            AMBIGUOUS: the city's address rule may simply have missed it, so a near-negative "error" is not
            always a real error. Always read the clean and the hard results side by side.

A "ticket" is a non-duplicate request, because the matcher compares a new report with tickets, not with reports already
merged into one (a merged report is no separate place; the city's children point at their parent). "Open" means still
open when the child was created, and the ticket is older than the child, like every ticket the matcher sees. For positives
the order is whatever the city says (about 8% of potholes name a LATER request as parent), so the time gap used as a
feature, dt, is absolute (days); the signed child-minus-parent gap is kept as dt_signed.

Every pair lies inside one group (a time split or a map-block split): both requests are in it, so no request sits in two
groups. Pairs that would cross a boundary are dropped, and counted.

Run:  models/.venv/bin/python -m models.tickets.eval.matching.chicago.pairs   (builds both datasets, caches them)
"""
import numpy as np
from scipy.spatial import cKDTree

from models.tickets.eval.common import results, splits
from models.tickets.eval.matching.chicago import prepare
from models.tickets.matching import geo

DAY = 86_400.0
NEAR_M = 60.0  # near negatives: under this
FAR_M = (100.0, 500.0)  # far negatives: between these, inclusive
KINDS = {"positive": 0, "far": 1, "near": 2}
SEED = 0


def _flat(req: prepare.Requests, rows: np.ndarray) -> np.ndarray:
    """Metres on a flat local map. Only for finding neighbours fast: every distance used is geo.distance_m."""
    scale = geo.EARTH_RADIUS_M
    lat0 = np.radians(np.nanmean(req.lat))
    return np.c_[np.radians(req.lng[rows]) * scale * np.cos(lat0), np.radians(req.lat[rows]) * scale]


def _reach(metres: float) -> float:
    return metres * 1.02 + 2.0  # the flat map is off by well under 1%; the margin keeps every true neighbour


def metres(req: prepare.Requests, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """geo.distance_m (the matcher's own haversine) between request rows a[k] and b[k]."""
    args = zip(req.lat[a].tolist(), req.lng[a].tolist(), req.lat[b].tolist(), req.lng[b].tolist())
    return np.array([geo.distance_m(*x) for x in args], dtype=float)


def _open_ticket(req, group, other: np.ndarray, child, tickets_only: bool = True) -> np.ndarray:
    """Which `other` rows could have been matched by `child`: same group, still open when it was created, a different
    city ticket, and (by default) a ticket rather than a merged report. `child` is a row or an array of rows."""
    ok = (group[other] == group[child]) & (req.closed[other] > req.created[child]) & (req.cluster[other] != req.cluster[child])
    return ok & ~req.dup[other] if tickets_only else ok


def positive_pairs(req: prepare.Requests, group: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """(child rows, parent rows, funnel) for the city's duplicates with both ends located and in one group."""
    child = np.flatnonzero(req.dup)
    parent = req.parent[child]
    in_file = parent >= 0
    child, parent = child[in_file], parent[in_file]
    located = req.located[child] & req.located[parent]
    same = (group[child] >= 0) & (group[child] == group[parent])
    keep = located & same
    funnel = {"duplicates": int(req.dup.sum()), "parent_not_in_file": int((~in_file).sum()),
              "no_location": int((~located).sum()), "crosses_a_boundary": int((located & ~same).sum()), "kept": int(keep.sum())}
    return child[keep], parent[keep], funnel


def boundary_loss(req: prepare.Requests, group: np.ndarray) -> dict:
    """Per group of the child: how many duplicates (parent in the file, both located) there are, how many keep their pair inside
    the group, and how the dropped ones differ (they are the long-lived tickets: later and, for potholes, farther apart)."""
    child = np.flatnonzero(req.dup & (req.parent >= 0))
    parent = req.parent[child]
    ok = req.located[child] & req.located[parent]
    child, parent = child[ok], parent[ok]
    d, gap = metres(req, child, parent), np.abs(req.created[child] - req.created[parent]) / DAY
    inside = lambda m: float((d[m] <= geo.match_radius_m(None, None)).mean()) if m.any() else None
    median = lambda m: float(np.median(gap[m])) if m.any() else None
    out = {}
    for k in sorted(set(group[child]) - {-1}):
        mine = group[child] == k
        kept = mine & (group[parent] == k)
        lost = mine & ~kept
        out[prepare.SPLITS[k]] = {"children": int(mine.sum()), "kept": int(kept.sum()), "dropped": int(lost.sum()),
                                  "median_gap_days_kept": median(kept), "median_gap_days_dropped": median(lost),
                                  "share_inside_shipped_radius_kept": inside(kept), "share_inside_shipped_radius_dropped": inside(lost)}
    return out


def near_pairs(req: prepare.Requests, group: np.ndarray, tickets_only: bool = True) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(older, newer, distance) for every pair under NEAR_M that the newer request could have matched."""
    usable = np.flatnonzero(req.located & (group >= 0))
    found = cKDTree(_flat(req, usable)).query_pairs(_reach(NEAR_M), output_type="ndarray")
    old, new = usable[found[:, 0]], usable[found[:, 1]]  # `usable` is in time order, so the first of a pair is older
    d = metres(req, old, new)
    keep = (d < NEAR_M) & _open_ticket(req, group, old, new, tickets_only)
    return old[keep], new[keep], d[keep]


def far_pairs(req: prepare.Requests, group: np.ndarray, pivots: np.ndarray, per_pivot: int = 1, seed: int = SEED):
    """(older, newer, distance): for each pivot request, `per_pivot` random open tickets 100-500 m away."""
    rng = np.random.default_rng(seed)
    usable = np.flatnonzero(req.located & (group >= 0))
    tree = cKDTree(_flat(req, usable))
    out_old, out_new, out_d = [], [], []
    for c, around in zip(pivots, tree.query_ball_point(_flat(req, pivots), _reach(FAR_M[1]))):
        other = usable[np.asarray(around, dtype=int)]
        other = other[(other < c) & _open_ticket(req, group, other, c)]
        d = metres(req, other, np.full(len(other), c))
        ring = (d >= FAR_M[0]) & (d <= FAR_M[1])
        other, d = other[ring], d[ring]
        for k in rng.choice(len(other), min(per_pivot, len(other)), replace=False):
            out_old.append(other[k]), out_new.append(c), out_d.append(d[k])
    return np.array(out_old, dtype=int), np.array(out_new, dtype=int), np.array(out_d, dtype=float)


def build(req: prepare.Requests, group: np.ndarray, far_per_positive: int = 1, seed: int = SEED, near_tickets_only: bool = True) -> dict[str, np.ndarray]:
    """All pairs of one category. `group` gives each request's split (-1: unused); both ends share it. With
    near_tickets_only=False any open request, not only a non-duplicate one, may be the other of a near negative (a sensitivity check).
    Arrays: child, other (rows of req), kind (KINDS), label (1 = city duplicate), d (metres), dt (days, absolute),
    dt_signed (child minus other, days), group, origin and ward (of the child)."""
    child, parent, _ = positive_pairs(req, group)
    d_pos = metres(req, child, parent)
    far_old, far_new, d_far = far_pairs(req, group, child, far_per_positive, seed)
    near_old, near_new, d_near = near_pairs(req, group, near_tickets_only)
    children = [child, far_new, near_new]
    others = [parent, far_old, near_old]
    out = {
        "child": np.concatenate(children), "other": np.concatenate(others),
        "kind": np.concatenate([np.full(len(c), k) for c, k in zip(children, KINDS.values())]),
        "d": np.concatenate([d_pos, d_far, d_near]),
    }
    signed = (req.created[out["child"]] - req.created[out["other"]]) / DAY
    out |= {"label": (out["kind"] == KINDS["positive"]).astype(int), "dt": np.abs(signed), "dt_signed": signed,
            "group": group[out["child"]], "origin": req.origin[out["child"]], "ward": req.ward[out["child"]]}
    return out


def build_all(everything: dict[str, prepare.Requests], groups: dict[str, np.ndarray], **kw) -> dict[str, np.ndarray]:
    """Every category pooled, with a `category` column. child/other index into that category's own rows."""
    parts = {c: build(r, groups[c], **kw) for c, r in everything.items()}
    pooled = {k: np.concatenate([p[k] for p in parts.values()]) for k in next(iter(parts.values()))}
    pooled["category"] = np.concatenate([np.full(len(p["child"]), c) for c, p in parts.items()])
    return pooled


# ---- cached datasets and their summary ----------------------------------------------------------------------------
def groups_for(kind: str, everything: dict[str, prepare.Requests]) -> dict[str, np.ndarray]:
    """Each request's split: 'time' (train, validation, test by month) or 'geo' (by 0.02-degree map block)."""
    return {c: prepare.time_split(r) for c, r in everything.items()} if kind == "time" else prepare.geo_split(everything)


def load(kind: str, everything: dict[str, prepare.Requests] | None = None, near_any: bool = False) -> dict[str, np.ndarray]:
    """The pooled pair dataset for 'time' or 'geo' splits, from the cache when it exists. near_any: the sensitivity set in
    which any open request may be the other of a near negative."""
    path = prepare.CACHE / f"matching_chicago_pairs_{kind}{'_anyother' if near_any else ''}.npz"
    if path.exists():
        with np.load(path) as z:
            return {k: z[k] for k in z.files}
    everything = everything or prepare.load_all()
    data = build_all(everything, groups_for(kind, everything), near_tickets_only=not near_any)
    assert requests_in_two_groups(data) == 0, "a request landed in two splits"
    prepare.CACHE.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **data)
    return data


def requests_in_two_groups(data: dict[str, np.ndarray]) -> int:
    """How many requests appear in more than one group. Must be 0: no ticket may sit in two splits."""
    code = np.unique(data["category"], return_inverse=True)[1].astype(np.int64)
    ids = {g: np.unique(np.concatenate([code[m] * 10_000_000 + data[k][m] for k in ("child", "other")]))
           for g in np.unique(data["group"]) for m in [data["group"] == g]}
    return int(sum(len(np.intersect1d(ids[a], ids[b])) for a in ids for b in ids if a < b))


def buffer_counts(req: prepare.Requests, child: np.ndarray, other: np.ndarray) -> dict:
    """How many of these pairs are inside the city's address buffer (same street, at most 4 numbers apart)."""
    flags = [prepare.within_buffer(req.address[c], req.address[o]) for c, o in zip(child, other)]
    return {"inside": sum(f is True for f in flags), "outside": sum(f is False for f in flags), "no_number": sum(f is None for f in flags)}


def summary(everything: dict[str, prepare.Requests], groups: dict[str, np.ndarray], data: dict[str, np.ndarray]) -> dict:
    """Counts per category, group and kind; the positive funnel; and how noisy the near negatives look."""
    out = {}
    for cat, req in everything.items():
        mine = data["category"] == cat
        near, pos = mine & (data["kind"] == KINDS["near"]), mine & (data["kind"] == KINDS["positive"])
        count = {prepare.SPLITS[g]: {k: int((mine & (data["group"] == g) & (data["kind"] == v)).sum()) for k, v in KINDS.items()}
                 for g in range(3)}
        _, _, d_literal = near_pairs(req, groups[cat], tickets_only=False)
        out[cat] = {
            "pairs": count, "positive_funnel": positive_pairs(req, groups[cat])[2], "boundary_loss": boundary_loss(req, groups[cat]),
            "near_negatives": {"same_geocode_share": float((data["d"][near] == 0).mean()),
                               "city_buffer": buffer_counts(req, data["child"][near], data["other"][near]),
                               "count_if_any_request_could_be_the_other": int(len(d_literal))},
            "positives_city_buffer": buffer_counts(req, data["child"][pos], data["other"][pos]),
        }
    return out


def block_summary(everything: dict[str, prepare.Requests], groups: dict[str, np.ndarray]) -> dict:
    """How many 0.02-degree blocks and located requests each map-block split holds."""
    located = {c: np.flatnonzero(groups[c] >= 0) for c in everything}
    ids = np.concatenate([splits.block_ids(r.lat[located[c]], r.lng[located[c]]) for c, r in everything.items()])
    which = np.concatenate([groups[c][located[c]] for c in everything])
    return {"blocks": int(len(set(ids))), "blocks_per_split": {prepare.SPLITS[k]: int(len(set(ids[which == k]))) for k in range(3)},
            "requests_per_split": {prepare.SPLITS[k]: int((which == k).sum()) for k in range(3)}}


def write_manifest(everything: dict[str, prepare.Requests]) -> Path:
    """Which split every request is in, for both split kinds (-1: no location, not used). Kept in the cache, not committed."""
    time, geo_ids = {c: prepare.time_split(r) for c, r in everything.items()}, prepare.geo_split(everything)
    arrays = {f"{c}_{name}": a for c, r in everything.items() for name, a in (("sr", r.sr), ("time_split", time[c]), ("geo_split", geo_ids[c]))}
    prepare.CACHE.mkdir(parents=True, exist_ok=True)
    path = prepare.CACHE / "matching_chicago_split_manifest.npz"
    np.savez_compressed(path, **arrays)
    return path


if __name__ == "__main__":
    everything = prepare.load_all()
    print(write_manifest(everything))
    for kind in ("time", "geo"):
        data = load(kind, everything)
        path = results.write_result(f"matching_chicago_pairs_{kind}", prepare.rounded({
            "config": {"near_m": NEAR_M, "far_m": FAR_M, "far_per_positive": 1, "seed": SEED, "split": kind,
                       "validation_start": prepare.VALIDATION_START, "test_start": prepare.TEST_START,
                       "geo_fractions": prepare.GEO_FRACTIONS},
            "map_blocks": block_summary(everything, groups_for(kind, everything)) if kind == "geo" else None,
            "summary": summary(everything, groups_for(kind, everything), data)}))
        print(path)
