"""What do the city's duplicate pairs look like next to our match radius? Rows, duplicate rates, and the distance and
time gap between each duplicate and its parent. Writes results/matching_chicago_eda.json and .png.

Run:  models/.venv/bin/python -m models.tickets.eval.matching.chicago.eda
"""
import numpy as np

from models.tickets.eval.common import metrics, plots, results
from models.tickets.eval.matching.chicago import pairs, prepare
from models.tickets.matching import geo

import matplotlib.pyplot as plt  # noqa: E402  (after plots, which picks the headless backend)

ORIGINS = ("Mobile Device", "Phone Call", "Internet", "Alderman's Office")
DISTANCE_Q = (50, 75, 90, 95, 99)
GAP_Q = (1, 5, 25, 50, 75, 90, 95, 99)
INSIDE_M = (15, 25, 31, 45, 60)
SHIPPED = {"no accuracy": geo.match_radius_m(None, None), **{f"accuracy {a} m": geo.match_radius_m(a, a) for a in (5, 10, 20)}}


def quantiles(x: np.ndarray, qs) -> dict:
    return {str(q): float(v) for q, v in zip(qs, np.percentile(x, qs))} if len(x) else {}


def duplicate_pairs(req: prepare.Requests) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(child rows, parent rows, distance in metres) for duplicates whose parent is in the file, both located."""
    child = np.flatnonzero(req.dup & (req.parent >= 0))
    parent = req.parent[child]
    both = req.located[child] & req.located[parent]
    child, parent = child[both], parent[both]
    return child, parent, pairs.metres(req, child, parent)


def pair_stats(req: prepare.Requests, child, parent, d, which: np.ndarray | None = None) -> dict:
    """Distance and time-gap statistics for the duplicate pairs `which` selects (all by default)."""
    which = np.ones(len(d), bool) if which is None else which
    d = d[which]
    gap = (req.created[child[which]] - req.created[parent[which]]) / pairs.DAY  # child minus parent, days
    if not len(d):
        return {"n": 0}
    return {"n": int(len(d)), "distance_m": quantiles(d, DISTANCE_Q), "share_at_distance_0": float((d == 0).mean()),
            "share_inside_m": {str(m): float((d <= m).mean()) for m in INSIDE_M},
            "share_inside_shipped_radius": {k: float((d <= r).mean()) for k, r in SHIPPED.items()},
            "gap_days": quantiles(gap, GAP_Q), "share_child_before_parent": float((gap < 0).mean()),
            "share_abs_gap_at_most_14_days": float((np.abs(gap) <= 14).mean()), "share_abs_gap_at_most_30_days": float((np.abs(gap) <= 30).mean())}


def address_stats(req: prepare.Requests, child, parent) -> dict:
    """How far apart in street numbers the city's duplicates are, among those on the same street."""
    pair = [(prepare.street_number(req.address[c]), prepare.street_number(req.address[p])) for c, p in zip(child, parent)]
    same = [abs(a[0] - b[0]) for a, b in pair if a and b and a[1] == b[1]]
    parsed = sum(1 for a, b in pair if a and b)
    return {"parsed": parsed, "same_street_share": len(same) / parsed if parsed else None,
            "numbers_apart_among_same_street": quantiles(np.array(same, float), (50, 75, 90, 95)),
            "inside_four_numbers_share": sum(x <= 4 for x in same) / parsed if parsed else None}


def category_stats(req: prepare.Requests) -> dict:
    child, parent, d = duplicate_pairs(req)
    in_file = int((req.dup & (req.parent >= 0)).sum())
    named = np.isin(req.origin, ORIGINS)
    rate = lambda m: {"rows": int(m.sum()), "duplicate_rate": float(req.dup[m].mean()) if m.any() else None}
    by_origin = {o: rate(req.origin == o) for o in ORIGINS} | {"other origins": rate(~named)}
    earlier = np.where(req.created[child] <= req.created[parent], child, parent)
    later = np.where(req.created[child] <= req.created[parent], parent, child)
    kids = np.bincount(req.parent[req.parent >= 0], minlength=len(req))
    parents = kids[kids > 0]
    return {
        "rows": len(req), "located": int(req.located.sum()), "duplicates": int(req.dup.sum()),
        "duplicate_rate": float(req.dup.mean()), "duplicate_rate_by_origin": by_origin,
        "duplicates_with_parent_in_file": in_file,
        "share_of_duplicates_with_parent_in_file": in_file / max(1, int(req.dup.sum())),
        "parent_is_itself_a_duplicate": int((req.dup[req.parent[req.parent >= 0]]).sum()),
        "earlier_of_the_pair_open_when_the_later_was_created": float((req.closed[earlier] > req.created[later]).mean()),
        "children_per_parent": {"parents_with_children": int(len(parents)), "one_child": int((parents == 1).sum()),
                                "two_children": int((parents == 2).sum()), "three_or_more": int((parents >= 3).sum()), "most": int(parents.max()) if len(parents) else 0},
        "pairs": pair_stats(req, child, parent, d),
        "pairs_by_child_origin": {o: pair_stats(req, child, parent, d, req.origin[child] == o) for o in ORIGINS},
        "addresses": address_stats(req, child, parent),
    }


def eda(everything: dict[str, prepare.Requests]) -> dict:
    return {c: category_stats(r) for c, r in everything.items()}


def label_vs_address(everything: dict[str, prepare.Requests], data: dict[str, np.ndarray]) -> dict:
    """How much of the city's label is an address relation? Among the pairs under 60 m (positives and near negatives), the
    ROC-AUC of minus-distance and of minus-street-number-gap (a huge gap on another street, or when an address has no number)."""
    gap = np.full(len(data["d"]), 1e9)
    for cat, req in everything.items():
        for i in np.flatnonzero(data["category"] == cat):
            g = prepare.number_gap(req.address[data["child"][i]], req.address[data["other"][i]])
            gap[i] = 1e9 if g is None or not np.isfinite(g) else g
    out = {}
    for cat in (*everything, "all"):
        m = (data["kind"] != pairs.KINDS["far"]) & (data["d"] < pairs.NEAR_M) & ((data["category"] == cat) | (cat == "all"))
        y = data["label"][m]
        out[cat] = {"pairs": int(m.sum()), "positives": int(y.sum()), "roc_auc_minus_distance": metrics.roc_auc(y, -data["d"][m]),
                    "roc_auc_minus_street_number_gap": metrics.roc_auc(y, -gap[m]),
                    "median_distance_m": {"positives": float(np.median(data["d"][m][y == 1])), "near_negatives": float(np.median(data["d"][m][y == 0]))}}
    return out


def plot(everything: dict[str, prepare.Requests], stats: dict, path) -> None:
    fig, (a, b, c) = plt.subplots(1, 3, figsize=(13.5, 3.8))
    for cat, req in everything.items():
        child, parent, d = duplicate_pairs(req)
        gap = np.abs(req.created[child] - req.created[parent]) / pairs.DAY
        n = len(d)
        a.plot(np.sort(d), np.arange(1, n + 1) / n, label=f"{cat} (n={n:,})")
        b.plot(np.sort(gap), np.arange(1, n + 1) / n, label=cat)
    for x, name in ((15, "min 15"), (SHIPPED["no accuracy"], "shipped 44.5"), (60, "max 60")):
        a.axvline(x, color=plots.FAINT, ls="--", lw=1)
        a.text(x, 0.02, f" {name}", rotation=90, fontsize=7, color=plots.INK)
    for x in (14, 30):
        b.axvline(x, color=plots.FAINT, ls="--", lw=1)
    a.set(xlim=(0, 150), ylim=(0, 1), xlabel="distance between a duplicate and its parent (m)", ylabel="share of pairs at most this far",
          title="How far apart the city's duplicates are")
    b.set(xscale="symlog", xlim=(0, 400), ylim=(0, 1), xlabel="time gap |child - parent| (days, log scale)", title="How long apart")
    b.set_xticks([0, 1, 7, 14, 30, 100, 300], ["0", "1", "7", "14", "30", "100", "300"])
    width = 0.8 / len(everything)
    for k, cat in enumerate(everything):
        rates = [stats[cat]["duplicate_rate_by_origin"][o]["duplicate_rate"] or 0.0 for o in ORIGINS]
        c.bar(np.arange(len(ORIGINS)) + k * width, rates, width, label=cat)
    c.set(xticks=np.arange(len(ORIGINS)) + 0.4 - width / 2, xticklabels=[o.replace(" ", "\n") for o in ORIGINS], ylabel="duplicate rate",
          title="Duplicate rate by how the request came in")
    c.tick_params(axis="x", labelsize=7)
    a.legend(fontsize=7, loc="lower right")
    fig.suptitle("Chicago 311: the city's duplicate flag against our match radius", color=plots.INK)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    everything = prepare.load_all()
    stats = eda(everything)
    diagnostic = label_vs_address(everything, pairs.load("time", everything))
    out = results.write_result("matching_chicago_eda", prepare.rounded({"shipped_radius_m": SHIPPED, "categories": stats, "label_vs_address_under_60_m": diagnostic}))
    plot(everything, stats, out.with_suffix(".png"))
    print(out)
