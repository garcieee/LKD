"""Evaluate the same-place matcher (models/tickets/matching) on simulated hazards with exact ground truth.

Read REPORT.md for the findings and the assumptions. The pieces, in the order of the task:
  build_pairs   candidate pairs (earlier report, same reported category, within 150 m), labelled same hazard or not
  rules         fixed radii, the shipped accuracy-aware radius, the same rule with z tuned, a logistic regression
  replay        reports arrive in order and go through matching.find_match; tickets are scored against the hazards
  cutoff, cost  the reported accuracy above which auto-merge should switch off; the price of wrong merges and splits
  run           everything for the 3 GPS profiles x 3 densities, tune on train, choose on validation, test once

Resampling for every interval is by district (a map block), never by pair: pairs share reports and hazards, so
resampling them one by one would make the intervals too narrow. Run:  python -m models.tickets.eval.matching.synthetic.evaluate
"""
import argparse
import time
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from models.tickets import settings as s
from models.tickets.eval.common import metrics as m, plots, results, splits
from models.tickets.eval.matching.synthetic import figures, simulator as sim
from models.tickets.matching import geo
from models.tickets.matching.match import anchor_after, find_match
from models.tickets.types import Sighting, TicketSpot

SPLITS = ("train", "val", "test")
FRACTIONS = (0.6, 0.2, 0.2)
DISTRICT_DEG = 0.005  # about 550 m: the unit of the 60/20/20 split and of every bootstrap
CANDIDATE_M = 150.0  # a pair is a candidate when the two reports are this close
FIXED = (10, 15, 25, 40, 60)  # the fixed radii of the comparison, in metres
FIXED_GRID = (5, 10, 15, 20, 25, 30, 40, 50, 60, 80)  # the radii the cost search may pick from
Z_GRID = tuple(float(z) for z in np.round(np.arange(1.5, 4.0001, 0.1), 1))  # z tried for the accuracy-aware rule
GRID_CELL_DEG = 0.001  # the replay's grid index: about 110 m
DENSITIES = (20, 60, 150)  # hazards per km2
HAZARDS_PER_CELL = 64_800  # per (profile, density): that many hazards in total, over as many independent 3 km patches as it takes
RATIOS = (1, 3, 5)  # a wrong merge costs this many wrong splits (3 is the pre-registered assumption)
CUT_EDGES = (5, 10, 15, 20, 30, 40)  # reported accuracy bins for the auto-merge cutoff, metres
CUT_PRECISION = 0.85  # auto-merge is switched off where validation precision is below this
N_BOOT = 1000
SEEDS = {"dev": 1000, "final": 2024}  # dev numbers steer the code, the final run is made once on seeds nobody has looked at


# ---- districts: the 60/20/20 split and the resampling unit ---------------------------------------------------------
def assign(world: sim.World, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """(split, unit) of every report. A hazard and all its reports share a district, districts are split 60/20/20."""
    parts = splits.block_split(world.hlat, world.hlng, FRACTIONS, DISTRICT_DEG, seed)
    hazard_split = np.empty(world.n_hazards, np.int8)
    for k, index in enumerate(parts):
        hazard_split[index] = k
    hazard_unit = np.unique(splits.block_ids(world.hlat, world.hlng, DISTRICT_DEG), return_inverse=True)[1]
    return hazard_split[world.hazard], hazard_unit[world.hazard]


# ---- pairs ---------------------------------------------------------------------------------------------------------
def build_pairs(lat, lng, acc, category, hazard, group=None, max_m: float = CANDIDATE_M) -> dict:
    """Every (earlier, later) pair of reports with the same reported category within max_m, and inside one group
    (a split) when given. Reports must be in arrival order. Nothing here may use the truth except the label y."""
    lat, lng, acc = np.asarray(lat, float), np.asarray(lng, float), np.asarray(acc, float)
    x, y = sim.to_xy(lat, lng)
    ij = cKDTree(np.column_stack([x, y])).query_pairs(max_m, output_type="ndarray")
    i, j = ij[:, 0], ij[:, 1]  # i < j, so i arrived first
    keep = np.asarray(category)[i] == np.asarray(category)[j]
    if group is not None:
        keep &= np.asarray(group)[i] == np.asarray(group)[j]
    i, j = i[keep], j[keep]
    order = np.lexsort((i, j))
    i, j = i[order], j[order]
    la, ln, ac = lat.tolist(), lng.tolist(), acc.tolist()
    d = np.array([geo.distance_m(la[a], ln[a], la[b], ln[b]) for a, b in zip(i, j)])
    ratio = np.array([geo.match_ratio(la[a], ln[a], ac[a], la[b], ln[b], ac[b]) for a, b in zip(i, j)])
    sigma = np.array([geo.sigma_m(a) for a in ac])
    spread = np.sqrt(sigma[i] ** 2 + sigma[j] ** 2 + 2 * s.STAND_OFF_SIGMA_M**2)  # the matcher's radius is z * spread, clamped
    assert np.allclose(d / np.clip(s.MATCH_Z * spread, s.MATCH_MIN_M, s.MATCH_MAX_M), ratio), "spread disagrees with geo.match_ratio"
    return {"i": i, "j": j, "y": np.asarray(hazard)[i] == np.asarray(hazard)[j], "d": d, "spread": spread, "ratio": ratio,
            "acc_old": acc[i], "acc_new": acc[j]}


def take(rows: dict, mask) -> dict:
    return {k: v[mask] for k, v in rows.items()}


def join(parts: list[dict]) -> dict:
    return {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}


# ---- replay --------------------------------------------------------------------------------------------------------
@contextmanager
def patched(overrides: dict):
    """Run the real matcher with other settings: the matcher reads settings.py at call time. Restored on exit."""
    old = {k: getattr(s, k) for k in overrides}
    try:
        for k, v in overrides.items():
            setattr(s, k, v)
        yield
    finally:
        for k, v in old.items():
            setattr(s, k, v)


def replay(lat, lng, acc, category, t, overrides: dict | None = None) -> np.ndarray:
    """Feed the reports, in the given order, through matching.find_match. Open tickets sit in a grid index so only
    the ones near the report are offered to find_match. A joined ticket moves to its most accurate report
    (match.anchor_after), as the shipped rule does. Returns, per report, the position of the first report of its ticket."""
    out = np.empty(len(lat), np.int64)
    tickets: dict[int, TicketSpot] = {}
    grid: dict[tuple[int, int], set[int]] = {}
    cell = lambda la, ln: (int(np.floor(la / GRID_CELL_DEG)), int(np.floor(ln / GRID_CELL_DEG)))
    with patched(overrides or {}):
        for k in range(len(lat)):
            report = Sighting(str(k), category[k], float(lat[k]), float(lng[k]), accuracy_m=float(acc[k]), created_at=float(t[k]))
            south, west, north, east = geo.box(report.lat, report.lng, s.MATCH_MAX_M)
            (c0, r0), (c1, r1) = cell(south, west), cell(north, east)
            near = [tickets[q] for cx in range(c0, c1 + 1) for cy in range(r0, r1 + 1) for q in grid.get((cx, cy), ())]
            hit = find_match(report, near, report.created_at)
            if hit is None:
                tickets[k] = TicketSpot(str(k), report.category, report.lat, report.lng, report.accuracy_m, "open", report.created_at)
                grid.setdefault(cell(report.lat, report.lng), set()).add(k)
                out[k] = k
                continue
            q = int(hit.ticket_id)
            old = tickets[q]
            lat_q, lng_q, acc_q = anchor_after(old, report)
            tickets[q] = replace(old, lat=lat_q, lng=lng_q, accuracy_m=acc_q, last_activity_at=report.created_at)
            if cell(lat_q, lng_q) != cell(old.lat, old.lng):
                grid[cell(old.lat, old.lng)].discard(q)
                grid.setdefault(cell(lat_q, lng_q), set()).add(q)
            out[k] = q
    return out


def merge_split_events(hazard, ticket) -> np.ndarray:
    """(n, 2) int8, reports in arrival order. Column 0 is 1 when the report made its ticket hold a second hazard (a
    wrong merge: two hazards joined), column 1 when it put its hazard into a second ticket (a wrong split: one hazard
    in two tickets). Their sums are the merges and splits of the final partition, so a cost is a mean over reports."""
    hazard, ticket = np.asarray(hazard, np.int64), np.asarray(ticket, np.int64)

    def first(a):
        mask = np.zeros(len(a), bool)
        mask[np.unique(a, return_index=True)[1]] = True
        return mask

    new_cell = first(hazard * (ticket.max() + 1) + ticket)  # a (hazard, ticket) combination not seen before
    return np.column_stack([new_cell & ~first(ticket), new_cell & ~first(hazard)]).astype(np.int8)


# ---- intervals: resample districts, not pairs --------------------------------------------------------------------
class Units:
    """Rows grouped by unit (a district). rows(sel) lists the rows of the units in sel, repeats included, and which
    copy of its unit each row belongs to."""

    def __init__(self, unit):
        unit = np.asarray(unit)
        self.order = np.argsort(unit, kind="stable")
        _, self.start, self.count = np.unique(unit[self.order], return_index=True, return_counts=True)

    def __len__(self):
        return len(self.start)

    def rows(self, sel):
        count = self.count[sel]
        first = np.repeat(self.start[sel] - (np.cumsum(count) - count), count)
        return self.order[first + np.arange(count.sum())], np.repeat(np.arange(len(sel)), count)


def ci(units: Units, metric, *rows, **kw) -> dict:
    """common.metrics.bootstrap_ci with whole districts as the resampling unit: metric(*rows) on the drawn districts."""

    def over(sel):
        index, _ = units.rows(sel)
        return metric(*[r[index] for r in rows])

    return m.bootstrap_ci(over, np.arange(len(units)), **{"n": N_BOOT, **kw}).as_dict()


def ci_clusters(units: Units, metric, true, pred, **kw) -> dict:
    """The same for cluster metrics: a district drawn twice counts as two districts, each with its own clusters."""

    def over(sel):
        index, copy = units.rows(sel)
        return metric((true[index] * (len(sel) + 1) + copy).tolist(), (pred[index] * (len(sel) + 1) + copy).tolist())

    return m.bootstrap_ci(over, np.arange(len(units)), **{"n": N_BOOT, **kw}).as_dict()


def ci_clusters_all(units: Units, fns: dict, true, pred, **kw) -> dict:
    """ci_clusters for several metrics at once. Every metric is computed once per resample (the resamples are the same
    for all of them), so this gives exactly what separate ci_clusters calls give, in a third of the time.
    fns: name -> metric(true, pred) returning a number or a dict of numbers; the result keys are name or name_key."""
    memo: dict = {}

    def values(sel):
        key = sel.tobytes()
        if key not in memo:
            index, copy = units.rows(sel)
            t, p = (true[index] * (len(sel) + 1) + copy).tolist(), (pred[index] * (len(sel) + 1) + copy).tolist()
            memo[key] = {name: fn(t, p) for name, fn in fns.items()}
        return memo[key]

    pick = lambda name, key: (lambda sel: values(sel)[name] if key is None else values(sel)[name][key])
    probe = {name: fn([0, 1], [0, 1]) for name, fn in fns.items()}
    out = {}
    for name, v in probe.items():
        for key in ([None] if not isinstance(v, dict) else list(v)):
            out[name if key is None else f"{name}_{key}"] = m.bootstrap_ci(pick(name, key), np.arange(len(units)), **{"n": N_BOOT, **kw}).as_dict()
    return out


def ci_diff(units: Units, metric, y, a, b, **kw) -> dict:
    """Interval for metric(y, a) - metric(y, b) on the same drawn districts (common.metrics.paired_bootstrap_diff)."""
    arms, n = (a, b), len(units)

    def over(sel, which):
        index, _ = units.rows(sel)
        return metric(y[index], arms[int(which[0])][index])

    return m.paired_bootstrap_diff(over, np.arange(n), np.zeros(n, int), np.ones(n, int), **{"n": N_BOOT, **kw}).as_dict()


def _unit_sums(units: Units, rows):
    return np.add.reduceat(np.asarray(rows, float)[units.order], units.start, axis=0)


def ci_sums(units: Units, rows, f, **kw) -> dict:
    """Interval for f(column sums of rows). Counts add up over districts, so this is exact and fast."""
    sums = _unit_sums(units, rows)
    return m.bootstrap_ci(lambda sel: f(sums[sel].sum(axis=0)), np.arange(len(units)), **{"n": N_BOOT, **kw}).as_dict()


def ci_sums_diff(units: Units, rows_a, rows_b, f, **kw) -> dict:
    sums, n = [_unit_sums(units, r) for r in (rows_a, rows_b)], len(units)
    over = lambda sel, which: f(sums[int(which[0])][sel].sum(axis=0))
    return m.paired_bootstrap_diff(over, np.arange(n), np.zeros(n, int), np.ones(n, int), **{"n": N_BOOT, **kw}).as_dict()


def _prf(beta, key):
    return lambda y, p: m.prf(y, p, beta)[key]


prec, rec, f1, f05 = _prf(1, "precision"), _prf(1, "recall"), _prf(1, "f"), _prf(0.5, "f")


def share(top, bottom) -> float:
    """sum(top) / sum(bottom); nan when there is nothing to divide by."""
    total = np.sum(bottom)
    return float(np.sum(top) / total) if total else float("nan")


# ---- the rules being compared --------------------------------------------------------------------------------------
def features(P: dict) -> np.ndarray:
    """What a learned rule may see: the distance, both reported accuracies (smaller first: a pair has no order) and
    their ratio. Never anything about the truth."""
    lo, hi = np.minimum(P["acc_old"], P["acc_new"]), np.maximum(P["acc_old"], P["acc_new"])
    return np.column_stack([P["d"], lo, hi, hi / lo])


def radius(P: dict, z: float) -> np.ndarray:
    """The shipped rule with another z: z * sqrt(sa^2 + sb^2 + 2 * stand_off^2), inside the shipped 15 to 60 m clamp."""
    return np.clip(z * P["spread"], s.MATCH_MIN_M, s.MATCH_MAX_M)


def fit_variants(train: dict, val: dict) -> dict:
    """Fit on train, choose on validation. z: the F0.5 curve on both splits, the pick is the validation maximum (the
    train maximum is kept for comparison). The logistic regression and the boosted trees are fitted on train and
    their merge threshold is the validation F0.5 optimum. fixed: the best fixed radius, for the question whether
    listening to the phone's accuracy beats a plain radius."""
    f05_at = lambda P, z: m.prf(P["y"], P["d"] <= radius(P, z), 0.5)["f"]
    curve = {"train": [f05_at(train, z) for z in Z_GRID], "val": [f05_at(val, z) for z in Z_GRID]}
    fixed = max(FIXED, key=lambda r: m.prf(val["y"], val["d"] <= r, 0.5)["f"])  # the best of the five fixed radii on validation
    lr = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)).fit(features(train), train["y"])
    trees = HistGradientBoostingClassifier(max_depth=4, max_iter=150, random_state=0).fit(features(train), train["y"])
    threshold = lambda model: m.best_threshold(val["y"], model.predict_proba(features(val))[:, 1], beta=0.5)["threshold"]
    return {"z": Z_GRID[int(np.argmax(curve["val"]))], "z_train": Z_GRID[int(np.argmax(curve["train"]))], "curve": curve, "fixed": fixed,
            "lr": lr, "lr_threshold": threshold(lr), "trees": trees, "trees_threshold": threshold(trees)}


def variants(P: dict, fit: dict) -> dict:
    """name -> (merge decision, score where higher means more likely the same hazard) for every pair in P."""
    out = {f"fixed {r} m": (P["d"] <= r, -P["d"] / r) for r in FIXED}
    out["shipped"] = (P["ratio"] <= 1.0, -P["ratio"])  # the matcher's own number: geo.match_ratio
    rad = radius(P, fit["z"])
    out["z tuned"] = (P["d"] <= rad, -P["d"] / rad)
    for name, key in (("logistic", "lr"), ("boosted trees (ceiling)", "trees")):
        p = fit[key].predict_proba(features(P))[:, 1]
        out[name] = (p >= fit[key + "_threshold"], p)
    return out


def variant_table(P: dict, fit: dict, auc_diffs: bool = True) -> dict:
    """Every variant on the same pairs: precision, recall, F0.5 and PR-AUC with intervals, and the paired difference
    from the shipped rule (variant minus shipped) in F0.5 and, for the scored variants, PR-AUC (auc_diffs)."""
    units, y, table = Units(P["unit"]), P["y"], {}
    arms = variants(P, fit)
    ship_decision, ship_score = arms["shipped"]
    distance_auc = None
    for name, (decision, score) in arms.items():
        row = {"precision": ci(units, prec, y, decision), "recall": ci(units, rec, y, decision), "f05": ci(units, f05, y, decision)}
        if name.startswith("fixed"):  # every fixed radius ranks the pairs by distance alone: one PR-AUC for all of them
            distance_auc = distance_auc or ci(units, m.pr_auc, y, score)
            row["pr_auc"] = distance_auc
        else:
            row["pr_auc"] = ci(units, m.pr_auc, y, score)
        if name != "shipped":
            row["f05_vs_shipped"] = ci_diff(units, f05, y, decision, ship_decision)
            if auc_diffs and name != "z tuned" and not name.startswith("fixed"):  # z tuned ranks the pairs as the shipped rule does, bar the clamp
                row["pr_auc_vs_shipped"] = ci_diff(units, m.pr_auc, y, score, ship_score)
        table[name] = row
    # does listening to the accuracy pay? the shipped rule and the tuned z against the best fixed radius (picked on validation)
    best_fixed = arms[f"fixed {fit['fixed']} m"][0]
    for name in ("shipped", "z tuned"):
        table[name]["f05_vs_best_fixed"] = ci_diff(units, f05, y, arms[name][0], best_fixed)
        table[name]["best_fixed_m"] = fit["fixed"]
    return table


def fit_summary(fit: dict) -> dict:
    return {"z": fit["z"], "z_train": fit["z_train"], "best_fixed_m": fit["fixed"], "f05_curve": {"z": list(Z_GRID), **fit["curve"]},
            "lr_threshold": fit["lr_threshold"], "trees_threshold": fit["trees_threshold"],
            "lr_coefficients_on_standardised_distance_acc_lo_acc_hi_ratio": fit["lr"][-1].coef_[0].tolist()}


# ---- the shipped rule at pair level ----------------------------------------------------------------------------------
def pair_table(P: dict) -> dict:
    """The shipped rule on one set of pairs: merge when geo.match_ratio <= 1. Threshold-free scores use -match_ratio."""
    units, y = Units(P["unit"]), P["y"]
    merged, score = P["ratio"] <= 1.0, -P["ratio"]
    table = {"pairs": len(y), "positives": int(y.sum()), "prevalence": float(y.mean()),
             "precision": ci(units, prec, y, merged), "recall": ci(units, rec, y, merged), "f1": ci(units, f1, y, merged),
             "f05": ci(units, f05, y, merged), "pr_auc": ci(units, m.pr_auc, y, score), "roc_auc": ci(units, m.roc_auc, y, score)}
    plain = {k: m.bootstrap_ci(fn, y, merged, n=N_BOOT) for k, fn in (("precision", prec), ("recall", rec))}  # what resampling pairs one by one would say
    table["interval_width_district_vs_pair"] = {k: [table[k]["hi"] - table[k]["lo"], plain[k].hi - plain[k].lo] for k in plain}
    return table


def replay_table(hazard, ticket, unit) -> dict:
    """The online replay of the shipped rule against the truth: pairwise, B-cubed and adjusted Rand."""
    rows = {"reports": len(hazard), "hazards": int(len(np.unique(hazard))), "tickets": int(len(np.unique(ticket)))}
    rows |= ci_clusters_all(Units(unit), {"bcubed": m.bcubed, "pairwise": m.cluster_pairs, "ari": m.ari}, hazard, ticket)
    return rows


# ---- the auto-merge cutoff -----------------------------------------------------------------------------------------
def precision_by_bin(P: dict, key: str = "acc_new", with_ci: bool = False, z: float | None = None) -> list[dict]:
    """Precision of the shipped rule's merges, by the reported accuracy of the new report (or the worse of the two).
    Bins: up to 5 m, 5 to 10, ... 30 to 40, above 40. With z, the merges of the same rule with that z instead."""
    merged, y = (P["ratio"] <= 1.0) if z is None else (P["d"] <= radius(P, z)), P["y"]
    bin_of = np.searchsorted(CUT_EDGES, P[key] if key != "acc_worst" else np.maximum(P["acc_old"], P["acc_new"]), side="left")
    units = Units(P["unit"]) if with_ci else None
    rows = []
    for k in range(len(CUT_EDGES) + 1):
        here = merged & (bin_of == k)
        row = {"low_m": CUT_EDGES[k - 1] if k else 0, "high_m": CUT_EDGES[k] if k < len(CUT_EDGES) else None,
               "merges": int(here.sum()), "precision": share(y & here, here)}
        if with_ci and row["merges"]:
            row["precision_ci"] = ci_sums(units, np.column_stack([y & here, here]), lambda t: t[0] / t[1])
        rows.append(row)
    return rows


def cutoff_edge(rows: list[dict]) -> int | None:
    """The largest bin edge E such that every bin up to E has precision >= CUT_PRECISION. 0 means even the best bin
    fails; None means no bin fails, so no cutoff is needed."""
    for k, row in enumerate(rows):
        if not row["precision"] >= CUT_PRECISION:  # a bin without merges (nan) also stops the scan
            return CUT_EDGES[k - 1] if k else 0
    return None


def accuracy_of(P: dict, key: str) -> np.ndarray:
    """The reported accuracy a cutoff looks at: the new report's, or the worse of the report and the ticket it meets."""
    return P["acc_new"] if key == "acc_new" else np.maximum(P["acc_old"], P["acc_new"])


def policy_table(P: dict, cutoff: int | None, key: str = "acc_new") -> dict:
    """What the app does with the cutoff: auto-merge when the rule merges AND the accuracy is within the cutoff,
    otherwise only suggest. Precision and recall of the auto-merges, and what is left to the suggestions."""
    units, y = Units(P["unit"]), P["y"]
    merged = P["ratio"] <= 1.0
    above = np.zeros(len(y), bool) if cutoff is None else ~(accuracy_of(P, key) <= cutoff)
    auto = merged & ~above
    withheld = merged & above  # merges the shipped rule would make that the app now only suggests
    share_of = lambda top, bottom: ci_sums(units, np.column_stack([top, bottom]), lambda t: t[0] / t[1]) if bottom.any() else dict.fromkeys(("point", "lo", "hi"), float("nan"))
    return {"auto_merge_precision": share_of(y & auto, auto), "auto_merge_recall": share_of(y & auto, y),
            "shipped_precision_without_cutoff": share_of(y & merged, merged), "shipped_recall_without_cutoff": share_of(y & merged, y),
            "true_pairs_left_to_suggestions": share_of(y & above, y),
            "withheld_share_of_merges": share_of(withheld, merged), "withheld_merges_that_were_right": share_of(y & withheld, withheld)}


# ---- cost: a wrong merge against a wrong split ------------------------------------------------------------------------
def rule_book() -> dict[str, dict]:
    """Every radius rule the replay runs, as the settings it runs the real matcher with."""
    rules = {"shipped": {}}
    rules.update({f"fixed {r} m": {"MATCH_MIN_M": float(r), "MATCH_MAX_M": float(r)} for r in FIXED_GRID})
    rules.update({f"z {z:.1f}": {"MATCH_Z": z} for z in Z_GRID})
    return rules


def cost_per_1000(events: np.ndarray, ratio: float) -> float:
    """Expected cost per 1,000 reports in units of one wrong split: ratio * wrong merges + wrong splits."""
    return 1000.0 * float((ratio * events[:, 0] + events[:, 1]).mean())


def cost_f(ratio):
    return lambda t: 1000.0 * (ratio * t[1] + t[2]) / t[0]


def count_rows(events):
    return np.column_stack([np.ones(len(events)), events])  # reports, wrong merges, wrong splits


# ---- one simulated patch: truth, pairs, replays ---------------------------------------------------------------------------
def seed_of(base: int, density: float, rep: int) -> int:
    """The same (density, rep) gets the same seed for every profile and setting: common random numbers."""
    return base * 1_000_000 + int(density) * 1_000 + rep


def run_replicate(task: tuple) -> dict:
    """Simulate one patch and return the arrays the analyses need. Ids are made unique per replicate (hazards and
    tickets) and per (density, replicate, district) for the resampling unit, which profiles share."""
    cfg, rep, seed, rules, replay_splits = task
    world = sim.simulate(cfg, seed)
    split, unit = assign(world, seed)
    unit = int(cfg.density) * 10**6 + rep * 10**3 + unit
    P = build_pairs(world.lat, world.lng, world.accuracy, world.category, world.hazard, group=split)
    pairs = {k: v for k, v in P.items() if k not in ("i", "j")} | {"split": split[P["j"]], "unit": unit[P["j"]]}
    names = np.array(sim.REAL_CATEGORIES)[world.category]
    n = world.n_reports
    tickets = {r: np.full(n, -1, np.int64) for r in rules}
    events = {r: np.zeros((n, 2), np.int8) for r in [*rules, "floor"]}
    best_possible = world.hazard * len(sim.REAL_CATEGORIES) + world.category  # one ticket per hazard and reported category
    for name in replay_splits:
        index = np.flatnonzero(split == SPLITS.index(name))
        events["floor"][index] = merge_split_events(world.hazard[index], best_possible[index])  # wrong categories alone force these splits
        for rule, overrides in rules.items():
            first = replay(world.lat[index], world.lng[index], world.accuracy[index], names[index], world.t[index], overrides)
            tickets[rule][index] = rep * 10**5 + index[first]
            events[rule][index] = merge_split_events(world.hazard[index], first)
    return {"hazard": rep * 10**5 + world.hazard, "split": split, "unit": unit, "pairs": pairs, "tickets": tickets, "events": events}


def _stack(parts: list[dict]) -> dict:
    cell = {k: np.concatenate([p[k] for p in parts]) for k in ("hazard", "split", "unit")}
    cell["pairs"] = join([p["pairs"] for p in parts])
    for k in ("tickets", "events"):
        cell[k] = {r: np.concatenate([p[k][r] for p in parts]) for r in parts[0][k]}
    return cell


def gather(specs: dict, base: int, rules: dict, replay_splits: tuple, workers: int | None = None) -> dict:
    """specs: key -> (Config, number of patches). Returns key -> cell. workers=1 runs in this process."""
    tasks = [(key, (cfg, r, seed_of(base, cfg.density, r), rules, replay_splits)) for key, (cfg, n) in specs.items() for r in range(n)]
    if workers == 1:
        done = [run_replicate(t) for _, t in tasks]
    else:
        with ProcessPoolExecutor(workers) as pool:
            done = list(pool.map(run_replicate, [t for _, t in tasks], chunksize=2))
    parts: dict = {}
    for (key, _), result in zip(tasks, done):
        parts.setdefault(key, []).append(result)
    return {key: _stack(p) for key, p in parts.items()}


def patches(density: float) -> int:
    return max(1, round(HAZARDS_PER_CELL / (density * 9)))  # a patch is 9 km2


# ---- the analyses ----------------------------------------------------------------------------------------------------------
KEYS = [(d, p) for d in DENSITIES for p in sim.PROFILES]  # a cell is one (density, profile)
cell_name = lambda key: f"{key[1]}@{key[0]}"
TARGETS = [  # EVALUATION.md, simulation rows (canyon has no target: its deliverable is the cutoff). (profile, source, metric, minimum)
    ("open_sky", "pairs", "precision", 0.95), ("open_sky", "pairs", "recall", 0.90),
    ("city", "pairs", "precision", 0.90), ("city", "pairs", "recall", 0.85), ("city", "pairs", "pr_auc", 0.92),
    ("city", "replay", "bcubed_f1", 0.90)]


def pairs_of(cell: dict, *names: str) -> dict:
    return take(cell["pairs"], np.isin(cell["pairs"]["split"], [SPLITS.index(n) for n in names]))


def reports_of(cell: dict, name: str) -> np.ndarray:
    return cell["split"] == SPLITS.index(name)


def _job(task):
    fn, args = task
    return fn(*args)


def tune_and_test(cells: dict, report: str, pool) -> dict:
    """The pair-level analyses, tuned on train, chosen on validation, scored once on the report split.
    A: every cell tunes on its own districts. B: one z and one model for all nine cells (what the app could ship).
    C: tuned on open sky and city only, tested on the canyon profile (the profile-shift test)."""
    train = {k: pairs_of(cells[k], "train") for k in KEYS}
    val = {k: pairs_of(cells[k], "val") for k in KEYS}
    test = {k: pairs_of(cells[k], report) for k in KEYS}
    easy = [k for k in KEYS if k[1] != "canyon"]
    fit_jobs = {("A", k): (fit_variants, (train[k], val[k])) for k in KEYS}
    fit_jobs["B"] = (fit_variants, (join(list(train.values())), join(list(val.values()))))
    fit_jobs["C"] = (fit_variants, (join([train[k] for k in easy]), join([val[k] for k in easy])))
    fitted = dict(zip(fit_jobs, pool.map(_job, fit_jobs.values()))) if pool else {k: _job(v) for k, v in fit_jobs.items()}
    fits = {"A": {k: fitted[("A", k)] for k in KEYS}, "B": fitted["B"], "C": fitted["C"]}
    jobs = {("pairs", k): (pair_table, (test[k],)) for k in KEYS}
    jobs |= {("replay", k): (replay_table, (cells[k]["hazard"][reports_of(cells[k], report)], cells[k]["tickets"]["shipped"][reports_of(cells[k], report)],
                                            cells[k]["unit"][reports_of(cells[k], report)])) for k in KEYS}
    jobs |= {("A", k): (variant_table, (test[k], fits["A"][k])) for k in KEYS}
    jobs |= {("B", k): (variant_table, (test[k], fits["B"])) for k in KEYS}
    jobs |= {("C", k): (variant_table, (test[k], fits["C"])) for k in KEYS if k[1] == "canyon"}
    mixed = {(d, "mixed"): join([test[(d, p)] for p in sim.PROFILES]) for d in DENSITIES}  # the phones of all three profiles together
    jobs |= {("pairs", k): (pair_table, (P,)) for k, P in mixed.items()}
    jobs |= {("B", k): (variant_table, (P, fits["B"], False)) for k, P in mixed.items()}  # three times the pairs: skip the slow AUC differences
    done = dict(zip(jobs, pool.map(_job, jobs.values()))) if pool else {k: _job(v) for k, v in jobs.items()}
    out = {"pairs": {}, "replay": {}, "variants": {"A": {}, "B": {}, "C": {}}}
    for (kind, key), table in done.items():
        (out["variants"][kind] if kind in "ABC" else out[kind])[cell_name(key)] = table
    out["fits"] = {"A": {cell_name(k): fit_summary(f) for k, f in fits["A"].items()}, "B": fit_summary(fits["B"]), "C": fit_summary(fits["C"])}
    out["tuned_z_for_cost"] = fits["B"]["z"]
    return out


def verdicts(out: dict) -> dict:
    """The pre-registered targets, met or missed, with the interval; and whether any variant beats the shipped rule."""
    targets = []
    for profile, source, metric, minimum in TARGETS:
        for d in DENSITIES:
            r = out[source][cell_name((d, profile))][metric]
            status = "met" if r["point"] >= minimum else "missed"
            sure = r["lo"] >= minimum if status == "met" else r["hi"] < minimum
            targets.append({"profile": profile, "density": d, "metric": metric, "minimum": minimum, "value": r, "status": status,
                            "interval_clear_of_target": bool(sure)})
    wins = []
    for protocol, tables in out["variants"].items():
        for cell, table in tables.items():
            for name, row in table.items():
                diff = row.get("f05_vs_shipped")
                if diff and (diff["lo"] > 0 or diff["hi"] < 0):
                    wins.append({"protocol": protocol, "cell": cell, "variant": name, "f05_vs_shipped": diff, "beats_shipped": diff["lo"] > 0})
    return {"targets": targets, "variants_clear_of_zero": wins}


def cutoff_analysis(cells: dict, report: str, tuned_z: float) -> dict:
    """The reported accuracy above which auto-merge should switch off: validation precision of the shipped rule by
    accuracy bin, the largest edge before the first bin under 0.85, and what that policy does on the report split.
    Also where the cutoff would sit if z were the tuned one (tuning B), to see how the two changes interact."""
    scopes = {f"density {d}": [(d, p) for p in sim.PROFILES] for d in DENSITIES} | {"all densities": KEYS}
    out = {}
    for scope, keys in scopes.items():
        val, test = (join([pairs_of(cells[k], name) for k in keys]) for name in ("val", report))
        entry = {}
        for key in ("acc_new", "acc_worst"):
            rows = precision_by_bin(val, key, with_ci=True)
            cutoff = cutoff_edge(rows)
            entry[key] = {"validation_bins": rows, "cutoff_m": cutoff, "policy": policy_table(test, cutoff, key)}
        tuned_rows = precision_by_bin(val, "acc_new", with_ci=True, z=tuned_z)
        entry["tuned_z"] = {"z": tuned_z, "validation_bins": tuned_rows, "cutoff_m": cutoff_edge(tuned_rows)}
        entry["by_profile"] = {p: precision_by_bin(join([pairs_of(cells[k], "val") for k in keys if k[1] == p])) for p in sim.PROFILES}
        out[scope] = entry
    return out


def cost_analysis(cells: dict, report: str, tuned_z: float) -> dict:
    """Expected cost per 1,000 reports of every radius rule at 1:1, 3:1 and 5:1, from the online replays. The rule
    that minimises validation cost is chosen per ratio, pooled over all cells (the app cannot know the profile or the density), per profile and per density."""
    rules = list(rule_book())
    scopes = {"all": KEYS} | {p: [k for k in KEYS if k[1] == p] for p in sim.PROFILES} | {f"density {d}": [k for k in KEYS if k[0] == d] for d in DENSITIES}
    gather_events = lambda keys, rule, name: np.concatenate([cells[k]["events"][rule][reports_of(cells[k], name)] for k in keys])
    named = ["shipped", *(f"fixed {r} m" for r in FIXED), f"z {tuned_z:.1f}"]
    out = {"tuned_z": tuned_z, "validation": {}, "chosen": {}, "report": {}, "per_cell": {}}
    for scope, keys in scopes.items():
        val = {rule: gather_events(keys, rule, "val") for rule in rules}
        out["validation"][scope] = {rule: {r: cost_per_1000(e, r) for r in RATIOS} for rule, e in val.items()}
        out["chosen"][scope] = {}
        for r in RATIOS:
            pick = lambda names: min(names, key=lambda rule: out["validation"][scope][rule][r])
            out["chosen"][scope][r] = {"any": pick(rules), "fixed": pick([x for x in rules if x.startswith("fixed")]),
                                       "z": pick([x for x in rules if x.startswith("z ")])}
        units = Units(np.concatenate([cells[k]["unit"][reports_of(cells[k], report)] for k in keys]))
        wanted = list(dict.fromkeys(named + ["floor"] + [v for r in RATIOS for v in out["chosen"][scope][r].values()]))
        rows = {rule: count_rows(gather_events(keys, rule, report)) for rule in wanted}
        table = {}
        for rule in wanted:
            table[rule] = {"merges_per_1000": ci_sums(units, rows[rule], lambda t: 1000 * t[1] / t[0]),
                           "splits_per_1000": ci_sums(units, rows[rule], lambda t: 1000 * t[2] / t[0])}
            for r in RATIOS:
                table[rule][f"cost_{r}_to_1"] = ci_sums(units, rows[rule], cost_f(r))
                if rule not in ("shipped", "floor"):  # positive: this rule is cheaper than the shipped one
                    table[rule][f"saving_vs_shipped_{r}_to_1"] = ci_sums_diff(units, rows["shipped"], rows[rule], cost_f(r))
        # does listening to the phone's accuracy pay? the cheapest accuracy-aware z against the cheapest fixed radius, both picked on validation
        table["adaptive_saving_vs_fixed"] = {str(r): ci_sums_diff(units, rows[out["chosen"][scope][r]["fixed"]], rows[out["chosen"][scope][r]["z"]], cost_f(r))
                                             for r in RATIOS}
        out["report"][scope] = table
    for k in KEYS:
        units = Units(cells[k]["unit"][reports_of(cells[k], report)])
        rows = {rule: count_rows(cells[k]["events"][rule][reports_of(cells[k], report)]) for rule in [*named, "floor"]}
        out["per_cell"][cell_name(k)] = {rule: {f"cost_{r}_to_1": ci_sums(units, rows[rule], cost_f(r)) for r in RATIOS} for rule in rows}
    return out


def sizes(cells: dict) -> dict:
    out = {}
    for k, c in cells.items():
        out[cell_name(k)] = {name: {"reports": int(reports_of(c, name).sum()), "pairs": int((c["pairs"]["split"] == i).sum()),
                                    "positive_pairs": int(c["pairs"]["y"][c["pairs"]["split"] == i].sum()),
                                    "districts": int(len(np.unique(c["unit"][reports_of(c, name)])))} for i, name in enumerate(SPLITS)}
    return out


def rounded(x, digits: int = 4):
    """Keep the committed JSON small: floats to 4 decimals, which is finer than any interval here."""
    if isinstance(x, dict):
        return {k: rounded(v, digits) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [rounded(v, digits) for v in x]
    return round(x, digits) if isinstance(x, float) else x


# ---- the run -------------------------------------------------------------------------------------------------------------
CACHE = Path(__file__).resolve().parents[2] / "data" / "cache"  # git-ignored


def main(final: bool = False, workers: int | None = None, scale: float = 1.0, folder: Path | None = None) -> dict:
    """final=False is the development run: dev seeds, validation split only, written to the git-ignored cache.
    final=True is the run the report quotes: fresh seeds, every split, written to eval/results/. Make it once."""
    base, report = SEEDS["final" if final else "dev"], "test" if final else "val"
    folder = Path(folder) if folder else (results.RESULTS if final else CACHE / "matching_synthetic_dev")
    if final and (folder / "matching_synthetic_main.json").exists():
        raise SystemExit(f"the final run is already in {folder}: it is made once. Delete matching_synthetic_*.json there to make it again.")
    specs = {k: (sim.Config(profile=k[1], density=k[0]), max(1, round(patches(k[0]) * scale))) for k in KEYS}
    started = time.time()
    say = lambda what: print(f"[{time.time() - started:6.0f}s] {what}", flush=True)
    cells = gather(specs, base, rule_book(), ("val", "test") if final else ("val",), workers)
    say(f"simulated and replayed {sum(len(c['hazard']) for c in cells.values()):,} reports in {sum(n for _, n in specs.values())} patches")
    if workers == 1:
        out = tune_and_test(cells, report, None)
    else:
        with ProcessPoolExecutor(workers) as pool:
            out = tune_and_test(cells, report, pool)
    say(f"tuned on train, chosen on validation, scored on {report}")
    tuned_z = out.pop("tuned_z_for_cost")
    cost = cost_analysis(cells, report, tuned_z)
    cutoff = cutoff_analysis(cells, report, tuned_z)
    say("cost and cutoff done")
    config = {"final": final, "report_split": report, "seed_base": base, "patches": {cell_name(k): n for k, (_, n) in specs.items()},
              "hazards_per_cell": HAZARDS_PER_CELL, "district_deg": DISTRICT_DEG, "bootstrap_resamples": N_BOOT,
              "resampling_unit": "district", "simulator": asdict(sim.Config()), "match_z_shipped": s.MATCH_Z, "z_grid": list(Z_GRID),
              "sizes": sizes(cells)}
    results.write_result("matching_synthetic_main", rounded({"config": config, "pairs": out["pairs"], "replay": out["replay"], **verdicts(out)}), folder)
    results.write_result("matching_synthetic_variants", rounded({"config": {"report_split": report}, "variants": out["variants"], "fits": out["fits"]}), folder)
    results.write_result("matching_synthetic_cutoff", rounded({"config": {"report_split": report, "edges_m": CUT_EDGES, "precision_floor": CUT_PRECISION}, "scopes": cutoff}), folder)
    results.write_result("matching_synthetic_cost", rounded({"config": {"report_split": report, "ratios": RATIOS}, **cost}, 2), folder)
    folder.mkdir(parents=True, exist_ok=True)
    figures.curves(folder / "matching_synthetic_curves.png", {p: pairs_of(cells[(60, p)], report) for p in sim.PROFILES},
                   f"shipped rule, {report} split, 60 hazards per km2")
    figures.variants(folder / "matching_synthetic_variants.png", out["variants"], DENSITIES, [v for v in out["variants"]["A"]["city@60"] if v != "shipped"])
    figures.cutoff(folder / "matching_synthetic_cutoff.png", cutoff)
    figures.cost(folder / "matching_synthetic_cost.png", cost["validation"], RATIOS, s.MATCH_Z)
    figures.zcurve(folder / "matching_synthetic_zcurve.png", out["fits"], DENSITIES, s.MATCH_Z)
    say(f"written to {folder}")
    return {"out": out, "cost": cost, "cutoff": cutoff, "cells": cells, "folder": folder}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--final", action="store_true", help="the one run on fresh seeds, with the test split, into eval/results/")
    ap.add_argument("--scale", type=float, default=1.0, help="fraction of the patches (development runs)")
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args()
    main(args.final, args.workers, args.scale)
