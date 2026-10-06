"""Cluster-level replay: feed one category's requests, in time order, through the shipped matcher
(models.tickets.matching.match.find_match) and compare the tickets it builds with the city's.

The city's ticket for a request is its parent's sr_number if it is a duplicate, else its own sr_number. Ours is the request that
started the ticket it ended in. Open tickets live in a grid index (geo.box finds the neighbours), a ticket keeps the spot of the
request that started it, and it is fixed when that request was closed. Two runs:
  reopen allowed (as shipped): a ticket fixed in the last 30 days can be joined, which reopens it until the joiner's own closing.
  reopen off: a ticket closed before the report arrives is unavailable, which is all the city does (it flags duplicates of OPEN
              parents only; in this data the parent was open in 100% of the pairs).
The replay runs over the whole history, so tickets open since before a period are there to join. A period is scored on its own
requests, except those whose city ticket cannot be told from the file (duplicates whose parent is not in it). Intervals resample
whole groups of requests that the two partitions tie together, not single requests.

Run:  models/.venv/bin/python -m models.tickets.eval.matching.chicago.replay [--boot 1000]
"""
import argparse
from collections import defaultdict
from dataclasses import dataclass

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from models.tickets import settings
from models.tickets.eval.common import metrics, plots, results
from models.tickets.eval.matching.chicago import eda, pairs, prepare
from models.tickets.matching import geo, match
from models.tickets.types import Sighting, TicketSpot

import matplotlib.pyplot as plt  # noqa: E402  (after plots, which picks the headless backend)

ACCURACIES = (None, 5, 10, 20)  # what every phone reports, as if; None is the shipped default (about 44.5 m)
SCORES = {
    "pairs_precision": lambda t, p: metrics.cluster_pairs(t, p)["precision"], "pairs_recall": lambda t, p: metrics.cluster_pairs(t, p)["recall"],
    "pairs_f1": lambda t, p: metrics.cluster_pairs(t, p)["f1"], "bcubed_precision": lambda t, p: metrics.bcubed(t, p)["precision"],
    "bcubed_recall": lambda t, p: metrics.bcubed(t, p)["recall"], "bcubed_f1": lambda t, p: metrics.bcubed(t, p)["f1"], "ari": metrics.ari}


@dataclass
class Replay:
    founder: np.ndarray  # row of the request that started the ticket this request ended in (-1: not replayed, no location)
    joined: np.ndarray  # it joined a ticket that already existed
    reopened: np.ndarray  # ... a ticket that had been fixed
    distance: np.ndarray  # metres to that ticket's spot (NaN when it started a ticket)
    since_fix_days: np.ndarray  # for a reopening join: days between the ticket's fix and this report (NaN otherwise)


def replay(req: prepare.Requests, accuracy_m: float | None = None, reopen: bool = True) -> Replay:
    """The shipped matcher over one category in time order. With one accuracy for every report a ticket's spot never moves
    (anchor_after keeps it), so the grid index is built once per ticket."""
    n = len(req)
    founder, joined, reopened = np.full(n, -1), np.zeros(n, bool), np.zeros(n, bool)
    distance, since_fix = np.full(n, np.nan), np.full(n, np.nan)
    fixed_at, active = np.full(n, np.inf), np.zeros(n)  # per ticket, by its founder's row
    south, west, north, east = geo.box(float(np.nanmean(req.lat)), float(np.nanmean(req.lng)), settings.MATCH_MAX_M)
    where = lambda la, ln: (int(np.floor(la / (north - south))), int(np.floor(ln / (east - west))))  # grid cells about one radius wide
    grid = defaultdict(list)
    lat, lng, created, closed = req.lat.tolist(), req.lng.tolist(), req.created.tolist(), req.closed.tolist()
    for i in np.flatnonzero(req.located).tolist():
        now = created[i]
        s_, w_, n_, e_ = geo.box(lat[i], lng[i], settings.MATCH_MAX_M)
        (r0, c0), (r1, c1) = where(s_, w_), where(n_, e_)
        spots = []
        for key in ((r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)):
            for f in grid.get(key, ()):
                fixed = fixed_at[f] <= now
                if fixed and not reopen:
                    continue
                spots.append(TicketSpot(str(f), req.category, lat[f], lng[f], accuracy_m, "fixed" if fixed else "open", active[f], fixed_at[f] if fixed else None))
        hit = match.find_match(Sighting(str(i), req.category, lat[i], lng[i], accuracy_m, created_at=now), spots, now)
        if hit is None:
            founder[i], fixed_at[i], active[i] = i, closed[i], now
            grid[where(lat[i], lng[i])].append(i)
            continue
        f = int(hit.ticket_id)
        founder[i], joined[i], reopened[i], distance[i], active[f] = f, True, hit.reopens, hit.distance_m, now
        if hit.reopens:
            since_fix[i] = (now - fixed_at[f]) / pairs.DAY
            fixed_at[f] = closed[i]  # open again until the city closes the report that reopened it
    return Replay(founder, joined, reopened, distance, since_fix)


# ---- scoring -------------------------------------------------------------------------------------------------------------
def scorable(req: prepare.Requests) -> np.ndarray:
    """Located requests whose city ticket can be told from the file: not a duplicate, or a duplicate whose located parent is in it."""
    parent_ok = (req.parent >= 0) & req.located[np.maximum(req.parent, 0)]
    return req.located & (~req.dup | parent_ok)


def components(true: np.ndarray, *preds: np.ndarray) -> np.ndarray:
    """A group id per item: items are tied when they share a city ticket or one of ours (in any of the `preds`), directly or
    through others."""
    t = np.unique(true, return_inverse=True)[1]
    ps = [np.unique(p, return_inverse=True)[1] for p in preds]
    start = np.cumsum([t.max() + 1] + [p.max() + 1 for p in ps])  # node ids: the city's tickets first, then each partition's
    size = start[-1]
    rows = np.concatenate([t] * len(ps))
    cols = np.concatenate([start[k] + p for k, p in enumerate(ps)])
    graph = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(size, size))
    return connected_components(graph, directed=False)[1][t]


def resample(t: np.ndarray, p: np.ndarray, group: np.ndarray, sample: np.ndarray) -> tuple[list, list]:
    """The labels of a bootstrap resample of whole groups. `sample` holds group ids drawn with replacement; a group drawn twice
    gets labels of its own the second time, so its copy does not merge with it."""
    copies = np.bincount(sample, minlength=group.max() + 1)[group]
    rows = np.repeat(np.arange(len(t)), copies)
    copy = np.arange(len(rows)) - np.repeat(np.cumsum(copies) - copies, copies)
    return (t[rows] + copy * (t.max() + 1)).tolist(), (p[rows] + copy * (p.max() + 1)).tolist()


def partition_scores(true: np.ndarray, pred: np.ndarray, boot: int | None = None) -> dict:
    """Pairwise and B-cubed precision, recall, F1 and the adjusted Rand index; with `boot`, each with a 95% interval."""
    if boot is None:
        return {k: {"point": float(f(true.tolist(), pred.tolist()))} for k, f in SCORES.items()}
    t, p = np.unique(true, return_inverse=True)[1], np.unique(pred, return_inverse=True)[1]
    group = components(true, pred)
    return {k: metrics.bootstrap_ci(lambda s, f=f: f(*resample(t, p, group, s)), np.arange(group.max() + 1), n=boot).as_dict() for k, f in SCORES.items()}


def paired_scores(true: np.ndarray, a: np.ndarray, b: np.ndarray, boot: int) -> dict:
    """Pairwise F1, B-cubed F1 and ARI of partition a minus those of partition b against the city's, on the same resamples of
    whole groups (groups tie together everything the city and both partitions tie)."""
    t = np.unique(true, return_inverse=True)[1]
    pa, pb = np.unique(a, return_inverse=True)[1], np.unique(b, return_inverse=True)[1]
    group = components(true, a, b)

    def diff(f):
        def one(s):
            ta, qa = resample(t, pa, group, s)
            _, qb = resample(t, pb, group, s)
            return f(ta, qa) - f(ta, qb)
        return metrics.bootstrap_ci(one, np.arange(group.max() + 1), n=boot).as_dict()

    return {k: diff(SCORES[k]) for k in ("pairs_f1", "bcubed_f1", "ari")}


def merge_report(req: prepare.Requests, rp: Replay, items: np.ndarray) -> dict:
    """Our merges among `items`, the ones the city did not flag, and how many of those sit inside the city's address buffer."""
    mine = items[rp.joined[items]]
    agree = req.cluster[mine] == req.cluster[rp.founder[mine]]
    extra = mine[~agree]
    kids = items[req.dup[items]]  # every scored duplicate has its parent in the file
    return {
        "items": int(len(items)), "our_merges": int(len(mine)), "of_which_reopening_a_fixed_ticket": int(rp.reopened[mine].sum()),
        "merges_the_city_also_flags": int(agree.sum()), "extra_merges_the_city_did_not_flag": int(len(extra)),
        "extra_where_the_city_flagged_it_to_another_parent": int(req.dup[extra].sum()),
        "extra_that_reopen_a_fixed_ticket": int(rp.reopened[extra].sum()),
        "extra_inside_the_city_buffer": pairs.buffer_counts(req, extra, rp.founder[extra]),
        "agreeing_merges_inside_the_city_buffer": pairs.buffer_counts(req, mine[agree], rp.founder[mine[agree]]),
        "reopening_merges_days_after_the_fix": eda.quantiles(rp.since_fix_days[mine][rp.reopened[mine]], (25, 50, 75, 90)),
        "reopening_merges_within_one_day_of_the_fix": float((rp.since_fix_days[mine][rp.reopened[mine]] <= 1).mean()) if rp.reopened[mine].any() else None,
        "extra_distance_m": eda.quantiles(rp.distance[extra], (50, 75, 90)), "extra_at_distance_0_share": float((rp.distance[extra] == 0).mean()) if len(extra) else None,
        "city_duplicates": int(len(kids)), "city_duplicates_put_in_their_parents_ticket": int((rp.founder[kids] == rp.founder[req.parent[kids]]).sum()),
    }


def evaluate(req: prepare.Requests, rp: Replay, items: np.ndarray, boot: int | None) -> dict:
    return {"scores": partition_scores(req.cluster[items], rp.founder[items], boot), "merges": merge_report(req, rp, items)}


def never_merge(req: prepare.Requests, items: np.ndarray, boot: int | None) -> dict:
    """The reference that makes every request its own ticket."""
    return partition_scores(req.cluster[items], items, boot)


def brief(entry: dict) -> dict:
    """Points only, for the numbers that are not on the test period (no intervals needed)."""
    m = entry["merges"]
    return {**{k: v["point"] for k, v in entry["scores"].items()}, "our_merges": m["our_merges"], "extra_merges": m["extra_merges_the_city_did_not_flag"],
            "city_duplicates_put_in_their_parents_ticket": m["city_duplicates_put_in_their_parents_ticket"], "city_duplicates": m["city_duplicates"]}


def run(boot: int, everything=None) -> dict:
    out = {}
    for cat, req in (everything or prepare.load_all()).items():
        group = prepare.time_split(req)
        period = {name: np.flatnonzero(scorable(req) & (group == k)) for name, k in (("validation", 1), ("test", 2))}
        entry = {"requests": len(req), "scored_requests": {k: int(len(v)) for k, v in period.items()},
                 "left_out_duplicates_with_parent_not_in_file": int((req.dup & (req.parent < 0)).sum()), "never_merge": {
                     "validation": {k: v["point"] for k, v in never_merge(req, period["validation"], None).items()}, "test": never_merge(req, period["test"], boot)}}
        sweep, runs = {}, {}
        for reopen in (True, False):
            for acc in ACCURACIES:
                rp = runs[(reopen, acc)] = replay(req, acc, reopen)
                sweep[f"{'reopen' if reopen else 'no reopen'}, accuracy {acc}"] = brief(evaluate(req, rp, period["validation"], None))
        entry["validation_sweep"] = sweep
        # the shipped setting, both ways, plus (if it differs) the accuracy with the best validation ARI in each way
        finals = {}
        for reopen in (True, False):
            best = max(ACCURACIES, key=lambda a: sweep[f"{'reopen' if reopen else 'no reopen'}, accuracy {a}"]["ari"])
            for acc in dict.fromkeys((None, best)):
                label = f"{'reopen' if reopen else 'no reopen'}, accuracy {acc}"
                finals[label] = {"reopen": reopen, "accuracy_m": acc, "best_on_validation": acc == best,
                                 "validation": sweep[label], "test": evaluate(req, runs[(reopen, acc)], period["test"], boot)}
        entry["final"] = finals
        # paired differences on the test period (same resamples for both runs), the ones the write-up leans on
        items, truth = period["test"], req.cluster[period["test"]]
        founder = lambda reopen, acc: runs[(reopen, acc)].founder[items]
        versus = {"reopen on minus reopen off (shipped accuracy)": (founder(True, None), founder(False, None)),
                  "reopen off, shipped minus never merge": (founder(False, None), items), "reopen on, shipped minus never merge": (founder(True, None), items)}
        for reopen in (True, False):
            best = next(v["accuracy_m"] for v in finals.values() if v["reopen"] == reopen and v["best_on_validation"])
            if best is not None:
                versus[f"reopen {'on' if reopen else 'off'}, best accuracy on validation ({best}) minus shipped"] = (founder(reopen, best), founder(reopen, None))
        entry["paired_test"] = {name: paired_scores(truth, a, b, boot) for name, (a, b) in versus.items()}
        out[cat] = entry
        print(cat, "done")
    return out


def plot(out: dict, path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6))
    shown = {"never merge": None, "reopen allowed (shipped)": "reopen, accuracy None", "reopen off": "no reopen, accuracy None"}
    cats = list(out)
    for ax, metric in zip(axes, ("pairs_f1", "bcubed_f1", "ari")):
        for k, (name, key) in enumerate(shown.items()):
            vals = [(out[c]["never_merge"]["test"] if key is None else out[c]["final"][key]["test"]["scores"])[metric] for c in cats]
            pts = np.array([v["point"] for v in vals])
            err = np.array([[v["point"] - v["lo"] for v in vals], [v["hi"] - v["point"] for v in vals]])
            ax.bar(np.arange(len(cats)) + (k - 1) * 0.27, pts, 0.27, yerr=err, capsize=2, label=name)
        ax.set(xticks=np.arange(len(cats)), xticklabels=[c.replace("_", "\n") for c in cats], ylim=(0, 1.02), title=metric.replace("_", " "))
        ax.tick_params(axis="x", labelsize=7)
    axes[0].legend(fontsize=7)
    fig.suptitle("Chicago test period: our tickets against the city's (95% intervals)", color=plots.INK)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=1000)
    a = ap.parse_args()
    out = run(a.boot)
    config = {"bootstrap_resamples": a.boot, "accuracies": ACCURACIES, "reopen_window_days": settings.REOPEN_WINDOW_DAYS,
              "validation_start": prepare.VALIDATION_START, "test_start": prepare.TEST_START}
    path = results.write_result("matching_chicago_replay", prepare.rounded({"config": config, "categories": out}))
    plot(out, path.with_suffix(".png"))
    print(path)
