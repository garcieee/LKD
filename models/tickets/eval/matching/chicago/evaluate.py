"""The same-place matcher as a pair classifier on the Chicago pair sets: fixed radii, the shipped accuracy-aware radius,
the best radius picked on validation, a logistic regression that may use time gap and type, a time window, a per-type
radius and cost-based radii. Tune on train, choose operating points on validation, read the test split once. Validation numbers
are therefore in-sample for every operating point picked on them; only the test numbers are out-of-sample.

Two evaluation sets per split, ALWAYS shown together:
  clean = positives + far negatives (100-500 m). Easy: a radius anywhere up to 100 m makes no false positive by design.
  hard  = clean + near negatives (under 60 m, open, not the parent). Ambiguous: the city's rule may have missed some.

Every variant is a matcher, so none may merge beyond the product's own maximum radius (settings.MATCH_MAX_M, 60 m). That is also
the range the near negatives cover: the construction leaves 60-100 m without any negative pair, so a radius there would look
free. A city duplicate further than 60 m apart is therefore a miss for every variant.

Run:  models/.venv/bin/python -m models.tickets.eval.matching.chicago.evaluate [--split time|geo|both] [--boot 1000] [--print]
      add --near-any for the sensitivity run in which any open request may be the other of a near negative (tables only)
"""
import argparse
import json
from typing import NamedTuple

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from models.tickets import settings
from models.tickets.eval.common import metrics, plots, results
from models.tickets.eval.matching.chicago import eda, pairs, prepare

import matplotlib.pyplot as plt  # noqa: E402  (after plots, which picks the headless backend)

RADII = (10, 15, 25, 40, 60)
CAP = settings.MATCH_MAX_M  # no variant merges further apart than this
GRID = np.arange(1.0, CAP + 0.5)  # candidate radii for "best fixed radius", metres
WINDOWS = (14, 30)  # days
COST_RATIOS = (1, 3, 5)  # a wrong merge costs this many wrong splits
SETS = {"clean": (pairs.KINDS["positive"], pairs.KINDS["far"]), "hard": tuple(pairs.KINDS.values())}
SPLITS = prepare.SPLITS
CATEGORIES = tuple(prepare.FILES)
SHIPPED = eda.SHIPPED
LR_VARIANTS = {"distance only": dict(time=False, kind=False, origin=False), "+ time": dict(time=True, kind=False, origin=False),
               "+ type": dict(time=False, kind=True, origin=False), "+ time + type": dict(time=True, kind=True, origin=False),
               "+ time + type + origin": dict(time=True, kind=True, origin=True)}
FULL = "+ time + type"
SHOWN = ("shipped no accuracy: 44.5 m", "best F1 radius", "per-type best F1 radius")  # variants broken down by type and origin


class Variant(NamedTuple):
    name: str
    family: str
    key: str  # variants with the same key share one score, so one PR-AUC and ROC-AUC
    score: np.ndarray  # higher = more likely the same place
    pred: np.ndarray  # the hard decision at the variant's operating point


def select(P: dict, group: int, kinds: tuple, mask: np.ndarray | None = None) -> dict:
    keep = (P["group"] == group) & np.isin(P["kind"], kinds)
    keep = keep if mask is None else keep & mask
    return {k: v[keep] for k, v in P.items()}


def features(D: dict, time: bool, kind: bool, origin: bool) -> np.ndarray:
    cols = [D["d"], np.log1p(D["d"])]
    cols += [D["dt"], np.log1p(D["dt"])] if time else []
    cols += [D["category"] == c for c in CATEGORIES] if kind else []
    cols += [D["origin"] == o for o in eda.ORIGINS] if origin else []
    return np.column_stack(cols).astype(float)


def names(time: bool, kind: bool, origin: bool) -> list[str]:
    return ["d", "log1p d"] + (["dt", "log1p dt"] if time else []) + (list(CATEGORIES) if kind else []) + (list(eda.ORIGINS) if origin else [])


def pick_radius(D: dict, beta: float = 1.0, cost: float | None = None) -> float:
    """The radius in GRID with the best F-beta (or, with `cost`, the fewest weighted mistakes: cost per false merge, 1 per
    false split) on D. The smallest radius among ties."""
    if not D["label"].any() or D["label"].all():
        return float("nan")  # nothing to choose between

    def value(r):
        c = metrics.prf(D["label"], D["d"] <= r, beta)
        return -(cost * c["fp"] + c["fn"]) if cost else c["f"]
    scores = np.array([value(r) for r in GRID])
    return float(GRID[np.flatnonzero(scores == scores.max())[0]])


def pick_threshold(D: dict, p: np.ndarray, beta: float = 1.0) -> float:
    """The probability cut with the best F-beta on D when pairs further than CAP are never merged (the highest cut among ties)."""
    cuts = np.unique(p[D["d"] <= CAP])
    f = np.array([metrics.prf(D["label"], (p >= t) & (D["d"] <= CAP), beta)["f"] for t in cuts])
    return float(cuts[np.flatnonzero(f == f.max())[-1]])


def fit(train: dict, **flags) -> tuple:
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)).fit(features(train, **flags), train["label"])
    return model, {n: float(c) for n, c in zip(names(**flags), model[-1].coef_[0])}


def ci(metric, *arrays, boot: int) -> dict:
    return metrics.bootstrap_ci(metric, *arrays, n=boot).as_dict()


PAIR_METRICS = {"precision": lambda y, p: metrics.prf(y, p)["precision"], "recall": lambda y, p: metrics.prf(y, p)["recall"],
                "f1": lambda y, p: metrics.prf(y, p, 1.0)["f"], "f05": lambda y, p: metrics.prf(y, p, 0.5)["f"]}


def evaluate_set(D: dict, variants: list[Variant], boot: int) -> list[dict]:
    """Precision, recall, F1, F0.5 at the operating point and PR-AUC, ROC-AUC of the score, each with a bootstrap 95% interval."""
    y, auc, rows = D["label"], {}, []
    for v in variants:
        if v.key not in auc:
            auc[v.key] = {"pr_auc": ci(metrics.pr_auc, y, v.score, boot=boot), "roc_auc": ci(metrics.roc_auc, y, v.score, boot=boot)}
        counts = metrics.prf(y, v.pred)
        rows.append({"name": v.name, "family": v.family, **{m: ci(f, y, v.pred, boot=boot) for m, f in PAIR_METRICS.items()}, **auc[v.key],
                     **{k: counts[k] for k in ("tp", "fp", "fn", "tn")}})
    return rows


class Chosen(NamedTuple):
    """Everything fitted or picked before the test split is opened."""

    best_f1: float
    best_f05: float
    per_type: dict
    cost: dict
    lr: dict  # name -> (model, threshold)
    coefficients: dict


def choose(train: dict, val: dict) -> Chosen:
    lr, coefficients = {}, {}
    for name, flags in LR_VARIANTS.items():
        model, coefficients[name] = fit(train, **flags)
        p = model.predict_proba(features(val, **flags))[:, 1]
        lr[name] = (model, pick_threshold(val, p))
    per_type = {c: pick_radius(select_rows(val, val["category"] == c)) for c in CATEGORIES}
    return Chosen(pick_radius(val, 1.0), pick_radius(val, 0.5), per_type, {r: pick_radius(val, cost=r) for r in COST_RATIOS}, lr, coefficients)


def select_rows(D: dict, mask: np.ndarray) -> dict:
    return {k: v[mask] for k, v in D.items()}


def variants_for(D: dict, ch: Chosen) -> list[Variant]:
    d, dt, shipped = D["d"], D["dt"], SHIPPED["no accuracy"]
    fixed = lambda name, family, r: Variant(name, family, "distance", -d, d <= min(r, CAP))
    out = [fixed(f"fixed {r} m", "fixed", r) for r in RADII]
    out += [Variant(f"shipped {label}: {r:.1f} m", "shipped", "distance", -d / r, d <= min(r, CAP)) for label, r in SHIPPED.items()]
    out += [fixed("best F1 radius", "best on validation", ch.best_f1), fixed("best F0.5 radius", "best on validation", ch.best_f05)]
    out += [fixed(f"cost {r}:1 radius", "cost on validation", ch.cost[r]) for r in COST_RATIOS]
    per_type = np.array([ch.per_type[c] if np.isfinite(ch.per_type[c]) else ch.best_f1 for c in D["category"]])
    out.append(Variant("per-type best F1 radius", "per type", "per_type", -d / per_type, d <= per_type))
    out += [Variant(f"shipped radius + dt <= {w} d", "time window", f"window{w}", -(d + 1e6 * (dt > w)), (d <= shipped) & (dt <= w)) for w in WINDOWS]
    for name, flags in LR_VARIANTS.items():
        model, threshold = ch.lr[name]
        p = model.predict_proba(features(D, **flags))[:, 1]
        out.append(Variant(f"logistic {name}", "logistic", f"lr {name}", p, (p >= threshold) & (d <= CAP)))
    return out


SHIPPED_NAME = "shipped no accuracy: 44.5 m"
COMPARED = (SHIPPED_NAME, "shipped accuracy 5 m: 19.1 m", "shipped accuracy 10 m: 31.2 m", "shipped accuracy 20 m: 58.2 m", "per-type best F1 radius",
            "shipped radius + dt <= 14 d", "shipped radius + dt <= 30 d")
WITHIN = ("logistic + time", "per-type best F1 radius", SHIPPED_NAME)  # compared inside each category


def ward_diff(metric, y, a, b, ward: np.ndarray, boot: int) -> metrics.CI:
    """Interval for metric(y, a) - metric(y, b) when whole wards are resampled: the pairs of one ward share tickets and days,
    so resampling single pairs makes the interval too narrow."""
    codes = np.unique(ward, return_inverse=True)[1]
    members = [np.flatnonzero(codes == k) for k in range(codes.max() + 1)]

    def diff(sample):
        i = np.concatenate([members[k] for k in sample])
        return metric(y[i], a[i]) - metric(y[i], b[i])

    return metrics.bootstrap_ci(diff, np.arange(len(members)), n=boot)


def verdict(pair: metrics.CI, ward: metrics.CI | None) -> str:
    """'better' or 'worse' only when the interval from resampling pairs AND the one from resampling wards both exclude zero."""
    cis = [pair] + ([ward] if ward else [])
    return "better" if all(c.lo > 0 for c in cis) else "worse" if all(c.hi < 0 for c in cis) else "no clear difference"


def paired(D: dict, variants: list[Variant], boot: int, only: tuple | None = None) -> list[dict]:
    """Each variant that is more than a radius (or is the shipped radius) against the best fixed radius, on the same resamples:
    PR-AUC of its score minus PR-AUC of minus-distance, its F1 minus the F1 of the best-F1 radius, and its F0.5 minus the F0.5
    of the best-F0.5 radius (each score against the radius picked for that score). Rule 2 of EVALUATION.md: the simple one stays
    unless the interval of the difference is clear of zero. Each difference comes with two intervals (resampling pairs, and
    resampling wards); the verdict needs both. A time window is also compared with the shipped radius it is added to, and a
    radius from a reported accuracy with the shipped default (f1_vs_shipped, f05_vs_shipped)."""
    y, by_name = D["label"], {v.name: v for v in variants}
    best1, best05 = by_name["best F1 radius"], by_name["best F0.5 radius"]
    f = lambda beta: lambda yy, p: metrics.prf(yy, p, beta)["f"]
    rows = []
    for v in variants:
        if (v.name not in only) if only else (v.family != "logistic" and v.name not in COMPARED):
            continue
        row = {"name": v.name}
        for key, metric, a, b in (("pr_auc", metrics.pr_auc, v.score, best1.score), ("f1", f(1.0), v.pred, best1.pred), ("f05", f(0.5), v.pred, best05.pred)):
            pair = metrics.paired_bootstrap_diff(metric, y, a, b, n=boot)
            ward = ward_diff(metric, y, a, b, D["ward"], boot) if "ward" in D else None
            row[key] = {"pairs": pair.as_dict(), "wards": ward.as_dict() if ward else None, "verdict": verdict(pair, ward)}
        if v.family == "time window" or v.name.startswith("shipped accuracy"):  # the baseline for these is the shipped default
            shipped = by_name[SHIPPED_NAME]
            for key, beta in (("f1_vs_shipped", 1.0), ("f05_vs_shipped", 0.5)):
                pair = metrics.paired_bootstrap_diff(f(beta), y, v.pred, shipped.pred, n=boot)
                ward = ward_diff(f(beta), y, v.pred, shipped.pred, D["ward"], boot) if "ward" in D else None
                row[key] = {"pairs": pair.as_dict(), "wards": ward.as_dict() if ward else None, "verdict": verdict(pair, ward)}
        rows.append(row)
    return rows


def breakdowns(D: dict, variants: list[Variant], boot: int) -> dict:
    """Precision, recall and F1 of the shown variants within each category, and recall within each child origin."""
    out = {"by_category": {}, "recall_by_origin": {}}
    for v in variants:
        if not v.name.startswith(SHOWN):
            continue
        out["by_category"][v.name] = {}
        for c in CATEGORIES:
            m = D["category"] == c
            if m.sum() > 0 and D["label"][m].any() and not D["label"][m].all():
                out["by_category"][v.name][c] = {"pairs": int(m.sum()), "positives": int(D["label"][m].sum()),
                    **{k: ci(f, D["label"][m], v.pred[m], boot=boot) for k, f in PAIR_METRICS.items() if k in ("precision", "recall", "f1")}}
        out["recall_by_origin"][v.name] = {}
        for o in eda.ORIGINS:
            m = (D["label"] == 1) & (D["origin"] == o)
            if m.sum() > 1:
                out["recall_by_origin"][v.name][o] = {"positives": int(m.sum()), "recall": ci(lambda p: p.mean(), v.pred[m], boot=boot)}
    return out


def within_category(D: dict, variants: list[Variant], boot: int) -> dict:
    """The same paired comparison inside each category, where a type feature cannot change the ranking (it only moves the
    intercept) and only the time gap could."""
    out = {}
    for c in CATEGORIES:
        m = D["category"] == c
        if D["label"][m].any() and not D["label"][m].all():
            out[c] = paired(select_rows(D, m), [v._replace(score=v.score[m], pred=v.pred[m]) for v in variants], boot, only=WITHIN)
    return out


def counts(D: dict) -> dict:
    n, pos = len(D["label"]), int(D["label"].sum())
    return {"pairs": n, "positives": pos, "prevalence": pos / n if n else None,
            "by_kind": {k: int((D["kind"] == v).sum()) for k, v in pairs.KINDS.items()},
            "positives_by_category": {c: int(((D["category"] == c) & (D["label"] == 1)).sum()) for c in CATEGORIES}}


def run_set(P: dict, kinds: tuple, boot: int, detail: bool, light: bool = False) -> tuple[dict, dict]:
    """`detail` adds the breakdowns by category and origin, and (on test) the paired comparisons inside each category.
    `light` leaves out every paired comparison (the sensitivity run only needs the tables)."""
    train, val, test = (select(P, g, kinds) for g in range(3))
    ch = choose(train, val)
    out = {"chosen": {"best_f1_radius_m": ch.best_f1, "best_f05_radius_m": ch.best_f05, "per_type_f1_radius_m": ch.per_type,
                      "cost_radius_m": {f"{r}:1": v for r, v in ch.cost.items()},
                      "logistic_f1_threshold": {k: v[1] for k, v in ch.lr.items()}},
           "logistic_coefficients_standardised": ch.coefficients, "counts": {s: counts(D) for s, D in zip(SPLITS, (train, val, test))}}
    curve = [(r, metrics.prf(val["label"], val["d"] <= r, 1.0)["f"], metrics.prf(val["label"], val["d"] <= r, 0.5)["f"]) for r in GRID]
    out["validation_f_by_radius"] = {"radius_m": [c[0] for c in curve], "f1": [c[1] for c in curve], "f05": [c[2] for c in curve]}
    keep = {}
    for split, D in (("validation", val), ("test", test)):
        vs = variants_for(D, ch)
        out[split] = {"table": evaluate_set(D, vs, boot)}
        if not light:
            out[split]["paired_against_best_fixed_radius"] = paired(D, vs, boot)
        if detail and not light:
            out[split] |= breakdowns(D, vs, boot)
        if detail and not light and split == "test":
            out[split]["paired_within_category"] = within_category(D, vs, boot)
        keep[split] = (D, vs)
    return out, keep


def plot_radius(path, out: dict) -> None:
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    for name, style in (("clean", "--"), ("hard", "-")):
        c = out[name]["validation_f_by_radius"]
        ax.plot(c["radius_m"], c["f1"], style, color="#212e4a", label=f"{name} F1")
        ax.plot(c["radius_m"], c["f05"], style, color="#a63722", label=f"{name} F0.5")
    ax.axvline(SHIPPED["no accuracy"], color=plots.FAINT, ls=":", lw=1.2)
    ax.text(SHIPPED["no accuracy"], 0.02, " shipped, no accuracy", fontsize=7, rotation=90, color=plots.INK)
    ax.set(xlabel="fixed match radius (m)", ylabel="score on validation pairs", title="Which fixed radius? Clean is easy: no negative is nearer than 100 m", ylim=(0, 1))
    ax.legend(fontsize=7, loc="lower right")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def fmt(c: dict) -> str:
    return f"{c['point']:.3f} ({c['lo']:.3f}-{c['hi']:.3f})"


def markdown(out: dict, which: str, split: str) -> str:
    cols = ["precision", "recall", "f1", "f05", "pr_auc", "roc_auc"]
    head = "| variant | precision | recall | F1 | F0.5 | PR-AUC | ROC-AUC |\n|---|---|---|---|---|---|---|\n"
    return head + "\n".join(f"| {r['name']} | " + " | ".join(fmt(r[c]) for c in cols) + " |" for r in out[which][split]["table"])


def run(kind: str, boot: int, everything=None, near_any: bool = False) -> dict:
    P = pairs.load(kind, everything, near_any)
    out, keep = {}, {}
    for which, kinds in SETS.items():
        out[which], keep[which] = run_set(P, kinds, boot, detail=which == "hard", light=near_any)
    config = {"split": kind, "bootstrap_resamples": boot, "bootstrap_seed": 0, "pair_seed": pairs.SEED, "radii_m": RADII, "grid_m": [GRID[0], GRID[-1]],
              "windows_days": WINDOWS, "cost_ratios": COST_RATIOS, "logistic": "StandardScaler + LogisticRegression(C=1, lbfgs), trained on train only",
              "validation_start": prepare.VALIDATION_START, "test_start": prepare.TEST_START, "geo_fractions": prepare.GEO_FRACTIONS,
              "shipped_radius_m": SHIPPED, "near_m": pairs.NEAR_M, "far_m": pairs.FAR_M}
    config["near_negatives_any_open_request"] = near_any
    path = results.write_result(f"matching_chicago_evaluate_{kind}{'_anyother' if near_any else ''}", prepare.rounded({"config": config, **out}))
    if near_any:
        print(path)
        return out
    plot_radius(path.with_name(path.stem + "_radius.png"), out)
    D, vs = keep["hard"]["test"]
    pick = {"minus distance": "best F1 radius", "per-type radius": "per-type best F1 radius", "logistic": f"logistic {FULL}"}
    curves = {label: (D["label"], v.score) for label, name in pick.items() for v in vs if v.name == name}
    plots.save_curves(path.with_name(path.stem + "_curves.png"), curves, f"Hard test pairs, {kind} split")
    print(path)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="both", choices=["time", "geo", "both"])
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--near-any", action="store_true", help="sensitivity: any open request may be the other of a near negative")
    ap.add_argument("--print", action="store_true", help="print the markdown tables of the saved results instead of running")
    a = ap.parse_args()
    for kind in ("time", "geo") if a.split == "both" else (a.split,):
        if a.print:
            saved = json.loads((results.RESULTS / f"matching_chicago_evaluate_{kind}.json").read_text())
            for which in SETS:
                for split in ("validation", "test"):
                    print(f"\n### {kind} split, {which} set, {split}\n\n" + markdown(saved, which, split))
        else:
            run(kind, a.boot, near_any=a.near_any)
