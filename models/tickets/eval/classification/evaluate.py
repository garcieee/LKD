"""The shared code of the classification evaluation, and the validation run. What it found: REPORT.md.

    models/.venv/bin/python -m models.tickets.eval.classification.evaluate    # validation only: writes results/classification_validation.*

Two tasks on a short note: the category hint (7 classes, "none" = no hint) and the danger flag (binary). Every metric comes
from eval/common/metrics.py. Nothing here reads the gold file: only final_gold.py does. Tune on train, choose on validation.
"""
from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from models.tickets import settings as s
from models.tickets.classification import classify
from models.tickets.eval.classification import schema
from models.tickets.eval.common import metrics as M
from models.tickets.eval.common import plots, results
import matplotlib.pyplot as plt  # after plots, which selects the screenless backend
from models.tickets.eval.common.splits import group_split
from models.tickets.resources.load import load_lexicon

HERE = Path(__file__).resolve().parent
TRAIN_FILE = HERE / "data" / "notes_train.jsonl"
LEXICON_V1 = HERE / "lexicon_v1.json"

HAZARDS = ["pothole", "open_manhole", "flooded_drain", "broken_streetlight", "blocked_sidewalk", "other"]
CATEGORIES = HAZARDS + ["none"]  # "none": the note does not say, so no hint
SHIPPED_HINT = (s.HINT_MIN_SCORE, s.HINT_MIN_MARGIN)
HINT_GRID = ([1.0 + 0.5 * k for k in range(7)], [0.5 * k for k in range(8)])  # min score 1..4, margin 0..3.5
COVERAGE_TARGET = 0.60  # EVALUATION.md: precision at least 0.90 while answering at least 60% of notes
BOOT = 1000  # bootstrap resamples, the project standard

# ---- the split: whole families, the seed chosen by a rule that never looks at a model ---------------------------------
FRACTIONS = (0.75, 0.25)
MIN_FAMILIES_PER_CATEGORY, MIN_DANGER_FAMILIES = 2, 4  # validation must cover every category, and a few danger families
SEED = 4  # the first seed that passes seed_check (seeds 0-3 leave a category with one family or none in validation)


def load_train() -> list[dict]:
    return schema.load(TRAIN_FILE)


def split_rows(rows: list[dict], seed: int = SEED) -> tuple[list[dict], list[dict]]:
    """(train, validation): every family lands wholly in one of them (common.splits.group_split)."""
    train, validation = group_split([r["family"] for r in rows], FRACTIONS, seed)
    return [rows[i] for i in train], [rows[i] for i in validation]


def seed_check(rows: list[dict], seed: int) -> dict:
    """What the validation half would hold for this seed: families per category and danger families."""
    _, validation = split_rows(rows, seed)
    family = {r["family"]: r for r in validation}  # category and danger are constant inside a family
    by_category = {c: sum(1 for r in family.values() if r["category"] == c) for c in CATEGORIES}
    danger = sum(1 for r in family.values() if r["danger"])
    ok = min(by_category.values()) >= MIN_FAMILIES_PER_CATEGORY and danger >= MIN_DANGER_FAMILIES
    return {"seed": seed, "ok": ok, "families_by_category": by_category, "danger_families": danger, "families": len(family)}


def first_good_seed(rows: list[dict], limit: int = 50) -> int:
    return next(seed for seed in range(limit) if seed_check(rows, seed)["ok"])


def targets_of(rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    return np.array([r["category"] for r in rows]), np.array([bool(r["danger"]) for r in rows])


# ---- what a model hands back -------------------------------------------------------------------------------------------
@dataclass
class Outputs:
    """cat: n x len(columns) matched evidence ("scores", the word list) or probabilities ("proba"); danger: one number a note."""
    cat: np.ndarray
    columns: list[str]
    danger: np.ndarray
    kind: str  # "scores" | "proba"


def lexicon_outputs(texts, lex: classify.Lexicon, prep=None) -> Outputs:
    """The continuous scores classify.py draws its decisions from. prep: optional text -> text normaliser (variants.py)."""
    texts = [prep(t) for t in texts] if prep else list(texts)
    cat = np.array([[classify.category_scores(t, lex).get(c, 0.0) for c in HAZARDS] for t in texts], float).reshape(len(texts), len(HAZARDS))
    return Outputs(cat, list(HAZARDS), np.array([classify.danger_score(t, lex) for t in texts], float), "scores")


def hint_labels(cat: np.ndarray, min_score: float, min_margin: float) -> np.ndarray:
    """classify.category_hint for a whole matrix of scores: the winner when it clears both thresholds, else "none"."""
    order = np.argsort(-cat, axis=1, kind="stable")  # a tie keeps the lexicon's order, as in classify.py
    top = np.take_along_axis(cat, order[:, :1], 1)[:, 0]
    second = np.take_along_axis(cat, order[:, 1:2], 1)[:, 0]
    ok = (top >= min_score) & (top - second >= min_margin)
    return np.where(ok, np.array(HAZARDS)[order[:, 0]], "none")


def default_labels(out: Outputs) -> np.ndarray:
    """The plain 7-class prediction: the word list at the shipped thresholds, a learned model's argmax."""
    if out.kind == "scores":
        return hint_labels(out.cat, *SHIPPED_HINT)
    return np.array(out.columns)[out.cat.argmax(axis=1)]


def operating_labels(out: Outputs, op: dict) -> np.ndarray:
    """The prediction at an operating point; abstaining is "none". op: min_score+min_margin (list) or min_conf (learned)."""
    if out.kind == "scores":
        return hint_labels(out.cat, op["min_score"], op["min_margin"])
    return np.where(out.cat.max(axis=1) >= op["min_conf"], np.array(out.columns)[out.cat.argmax(axis=1)], "none")


# ---- category metrics ----------------------------------------------------------------------------------------------------
def macro_f1(y, pred) -> float:
    return M.multiclass(y, pred, CATEGORIES)["macro_f1"]


def accuracy(y, pred) -> float:
    return float(np.mean(np.asarray(y) == np.asarray(pred)))


def selective(y, pred) -> dict:
    """The hints shown: a note answers when its prediction is not "none". A hint on a "none" note is wrong."""
    y, pred = np.asarray(y), np.asarray(pred)
    answered = pred != "none"
    n, k = int(answered.sum()), int((answered & (pred == y)).sum())
    return {"coverage": n / len(y), "precision": k / n if n else 0.0, "answered": n, "correct": k, "correct_rate": k / len(y)}


def coverage(y, pred) -> float:
    return selective(y, pred)["coverage"]


def hint_precision(y, pred) -> float:
    a = np.asarray(pred) != "none"
    return float(np.mean(np.asarray(pred)[a] == np.asarray(y)[a])) if a.any() else float("nan")


def correct_rate(y, pred) -> float:
    """Share of ALL notes that get a correct hint."""
    return selective(y, pred)["correct_rate"]


def category_report(y, pred) -> dict:
    return {**M.multiclass(y, pred, CATEGORIES), **selective(y, pred)}


def choose_hint_point(out: Outputs, y, target: float = COVERAGE_TARGET) -> dict:
    """The most precise setting that still answers at least `target` of the notes (VALIDATION only). The word list
    searches min score and margin; a learned model searches one maximum-probability threshold. If nothing reaches the
    target, the setting with the most coverage is returned and `reached` says False."""
    if out.kind == "scores":
        settings = [{"min_score": a, "min_margin": b} for a in HINT_GRID[0] for b in HINT_GRID[1]]
    else:
        settings = [{"min_conf": float(t)} for t in np.unique(out.cat.max(axis=1))]
    rows = [{"op": op, **selective(y, operating_labels(out, op))} for op in settings]
    ok = [r for r in rows if r["coverage"] >= target]
    best = max(ok, key=lambda r: (r["precision"], r["coverage"])) if ok else max(rows, key=lambda r: (r["coverage"], r["precision"]))
    return {**best, "reached": bool(ok)}


def selective_curve(out: Outputs, y) -> tuple[list[float], list[float]]:
    """(coverage, precision) along the thresholds: the upper edge of the grid for a word list, the sweep for a model."""
    if out.kind == "scores":
        points = [selective(y, hint_labels(out.cat, a, b)) for a in HINT_GRID[0] for b in HINT_GRID[1]]
    else:
        points = [selective(y, operating_labels(out, {"min_conf": float(t)})) for t in np.unique(out.cat.max(axis=1))]
    points = [p for p in points if p["answered"]]
    keep = sorted({(p["coverage"], p["precision"]) for p in points if not any(q["coverage"] >= p["coverage"] and q["precision"] > p["precision"] for q in points)})
    return [c for c, _ in keep], [p for _, p in keep]


# ---- danger metrics ------------------------------------------------------------------------------------------------------
def danger_at(d, score, threshold: float) -> dict:
    """Precision, recall, F1 and F2 when a note is flagged at score >= threshold."""
    flagged = np.asarray(score) >= threshold
    one, two = M.prf(d, flagged, 1.0), M.prf(d, flagged, 2.0)
    return {"threshold": float(threshold), "precision": one["precision"], "recall": one["recall"], "f1": one["f"], "f2": two["f"],
            "flagged": int(flagged.sum()), "tp": one["tp"], "fp": one["fp"], "fn": one["fn"]}


def danger_thresholds(d, score) -> dict:
    """The operating points, from VALIDATION: F1-best, F2-best (the one the target uses) and the one for recall 0.90."""
    at90 = M.at_recall(d, score, 0.90)
    return {"f1": M.best_threshold(d, score, 1.0)["threshold"], "f2": M.best_threshold(d, score, 2.0)["threshold"],
            "recall90": at90["threshold"] if at90 else None}


def danger_report(d, score, thresholds: dict[str, float | None]) -> dict:
    p60, r90 = M.at_precision(d, score, 0.60), M.at_recall(d, score, 0.90)
    return {"prevalence": float(np.mean(d)), "pr_auc": M.pr_auc(d, score), "roc_auc": M.roc_auc(d, score),
            "recall_at_precision_0.60": p60["recall"] if p60 else None, "precision_at_recall_0.90": r90["precision"] if r90 else None,
            "at": {name: danger_at(d, score, t) for name, t in thresholds.items() if t is not None}}


# ---- figures -----------------------------------------------------------------------------------------------------------------
def save_selective(path, curves: dict[str, tuple], points: dict[str, tuple] | None = None, title: str = "") -> None:
    """Precision of the hints shown against the share of notes answered. curves: label -> (coverage, precision);
    points: label -> (coverage, precision) of the chosen operating point. Dashed lines are the targets."""
    fig, ax = plt.subplots(figsize=(5.4, 4.2))
    for i, (label, (c, p)) in enumerate(curves.items()):
        line, = ax.plot(c, p, label=label, lw=1.4)
        if points and label in points:
            ax.scatter(*points[label], color=line.get_color(), s=40, zorder=3, edgecolor="black")
    ax.axvline(COVERAGE_TARGET, color=plots.FAINT, ls="--", lw=1)
    ax.axhline(0.90, color=plots.FAINT, ls="--", lw=1)
    ax.set(xlabel="coverage (share of notes with a hint)", ylabel="precision of the hints shown", title=title, xlim=(0, 1.02), ylim=(0.3, 1.02))
    ax.legend(fontsize=7, loc="lower left")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


# ---- how wide validation really is: resample whole families --------------------------------------------------------------------------
def family_bootstrap(metric, arrays, families, n: int = BOOT, seed: int = 0, other=None) -> dict:
    """95% interval when whole families are drawn with replacement. The notes of one family are alike, so a note-level interval is
    too narrow for validation. With `other` (a second set of arrays) the interval is for metric(arrays) - metric(other), on the same draws."""
    fam = np.asarray(families)
    members = [np.flatnonzero(fam == f) for f in np.unique(fam)]
    rng, values = np.random.default_rng(seed), []
    for _ in range(n):
        index = np.concatenate([members[i] for i in rng.integers(0, len(members), len(members))])
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error")  # a draw with no danger family cannot score PR-AUC: sklearn warns, so skip it
                value = metric(*[np.asarray(a)[index] for a in arrays]) - (metric(*[np.asarray(a)[index] for a in other]) if other else 0.0)
        except (ValueError, UserWarning):
            continue
        if np.isfinite(value):
            values.append(value)
    lo, hi = np.percentile(values, [2.5, 97.5])
    point = metric(*arrays) - (metric(*other) if other else 0.0)
    return {"point": float(point), "lo": float(lo), "hi": float(hi)}


# ---- the validation run ---------------------------------------------------------------------------------------------------------
def lexicon_data(version: str) -> dict:
    """The word lists: v0 is the shipped resources/lexicon.json, v1 is the one tune_lexicon.py wrote beside this file.
    Only the HAZARDS lists: the PWD barrier lists came later and no labelled note has them."""
    if version != "v0":
        return json.loads(LEXICON_V1.read_text())
    v0 = load_lexicon()
    return {**v0, "categories": {c: v0["categories"][c] for c in HAZARDS}}


def configuration_report(out: Outputs, y, d, op: dict | None = None) -> tuple[dict, dict]:
    """Everything a configuration scores on one labelled set at its validation-chosen operating points.
    Returns (the report, the frozen operating points)."""
    default = category_report(y, default_labels(out))
    op = op or {"hint": choose_hint_point(out, y)["op"], "danger": danger_thresholds(d, out.danger)}
    at_op = operating_labels(out, op["hint"])
    thresholds = dict(op["danger"])
    if out.kind == "scores":
        thresholds["shipped"] = s.DANGER_MIN_SCORE
    report = {"category": {"default": default, "operating_point": {"op": op["hint"], **category_report(y, at_op)}},
              "danger": danger_report(d, out.danger, thresholds)}
    return report, op


def robustness(rows: list[dict], seeds: list[int]) -> dict:
    """The same recipe on other family splits (no seed rule here: a class missing from one validation half is missing for every
    configuration alike): v1 re-derived from each split's train half and the learned models re-chosen on its validation half.
    A look at how far one split moves the answer; it changes nothing that was frozen."""
    from models.tickets.eval.classification import baselines, tune_lexicon

    v0, table = lexicon_data("v0"), {}
    for seed in seeds:
        train, validation = split_rows(rows, seed)
        y, d = targets_of(validation)
        texts = [r["text"] for r in validation]
        outs = {"lexicon_v0": lexicon_outputs(texts, classify.Lexicon(v0)), "lexicon_v1": lexicon_outputs(texts, classify.Lexicon(tune_lexicon.tune(train, v0)[0]))}
        for name, spec in baselines.run(train, validation)["specs"].items():
            outs[name] = baselines.make_predictor(spec, train).outputs(texts)
        table[seed] = {n: {"macro_f1": macro_f1(y, default_labels(o)), "pr_auc": M.pr_auc(d, o.danger)} for n, o in outs.items()}
    names = list(next(iter(table.values())))
    summary = {n: {m: {"mean": float(np.mean([table[s][n][m] for s in seeds])), "sd": float(np.std([table[s][n][m] for s in seeds], ddof=1))} for m in ("macro_f1", "pr_auc")} for n in names}
    wins = {f"{a} beats lexicon_v1": {m: sum(table[s][a][m] > table[s]["lexicon_v1"][m] for s in seeds) for m in ("macro_f1", "pr_auc")} for a in names if a not in ("lexicon_v1",)}
    return {"seeds": seeds, "per_seed": table, "summary": summary, "seeds_where": wins}


def main(argv=None) -> None:
    """Task 1 and 4: the shipped word list, the improved one, the normalisation variants and the learned baselines, all on
    validation, then the operating points frozen for the one gold run. --robustness: the recipe on other splits, a diagnostic."""
    import argparse

    from models.tickets.eval.classification import baselines, variants  # imported here: both import this module

    parser = argparse.ArgumentParser()
    parser.add_argument("--robustness", type=int, metavar="N", help="repeat the recipe on the family splits of seeds 0..N-1, write results/classification_robustness.json")
    args = parser.parse_args(argv)
    rows = load_train()
    if args.robustness:
        outcome = robustness(rows, list(range(args.robustness)))
        results.write_result("classification_robustness", outcome)
        print(json.dumps(outcome["summary"], indent=1), json.dumps(outcome["seeds_where"], indent=1))
        return
    train, validation = split_rows(rows)
    y, d = targets_of(validation)
    check = seed_check(rows, SEED)
    assert check["ok"] and SEED == first_good_seed(rows), "the seed no longer satisfies the split rule"

    best_variant = variants.run(validation, write=True)["best"]
    specs = {"lexicon_v0": {"kind": "lexicon", "lexicon": "v0", "variant": None},
             "lexicon_v1": {"kind": "lexicon", "lexicon": "v1", "variant": None}}
    if best_variant:
        specs[f"lexicon_v1+{best_variant['name']}"] = {"kind": "lexicon", "lexicon": "v1", "variant": best_variant["flags"]}
    specs.update(baselines.run(train, validation, write=True)["specs"])

    report, frozen, outputs = {}, {}, {}
    for name, spec in specs.items():
        outputs[name] = baselines.make_predictor(spec, train).outputs([r["text"] for r in validation])
        report[name], op = configuration_report(outputs[name], y, d)
        frozen[name] = {"spec": spec, **op}
    split = {"seed": SEED, "fractions": FRACTIONS, "train_rows": len(train), "validation_rows": len(validation),
             "train_families": len({r["family"] for r in train}), "validation_families": check["families"],
             "validation_families_by_category": check["families_by_category"], "validation_danger_families": check["danger_families"],
             "validation_danger_share": float(np.mean(d))}
    fam = [r["family"] for r in validation]
    labels = {n: default_labels(outputs[n]) for n in outputs}
    noise = {"note": "95% intervals from resampling whole families, the honest width of a validation number",
             "macro_f1": {n: family_bootstrap(macro_f1, (y, labels[n]), fam) for n in outputs},
             "danger_pr_auc": {n: family_bootstrap(M.pr_auc, (d, outputs[n].danger), fam) for n in outputs}, "paired": {}}
    variant = [n for n in outputs if n.startswith("lexicon_v1+")]
    for a, b in [("lexicon_v1", "lexicon_v0"), *[(v, "lexicon_v1") for v in variant], *[(m, "lexicon_v1") for m in ("naive_bayes", "logistic_regression", "hybrid")]]:
        noise["paired"][f"{a} - {b}"] = {"macro_f1": family_bootstrap(macro_f1, (y, labels[a]), fam, other=(y, labels[b])),
                                         "danger_pr_auc": family_bootstrap(M.pr_auc, (d, outputs[a].danger), fam, other=(d, outputs[b].danger))}
    results.write_result("classification_validation", {"split": split, "configs": report, "family_bootstrap": noise})
    results.write_result("classification_final_config", {"split": split, "refit": "train+validation (learned models only)", "configs": frozen})

    plots.save_curves(results.RESULTS / "classification_validation_danger.png", {n: (d, outputs[n].danger) for n in outputs}, "Danger flag, validation")
    curve = {n: selective_curve(outputs[n], y) for n in outputs}
    points = {n: (report[n]["category"]["operating_point"]["coverage"], report[n]["category"]["operating_point"]["precision"]) for n in outputs}
    save_selective(results.RESULTS / "classification_validation_selective.png", curve, points, "Category hint, validation")
    print(summary_table(report))


def summary_table(report: dict) -> str:
    rows = []
    for name, r in report.items():
        cat, dg = r["category"], r["danger"]
        rows.append({"config": name, "macroF1": cat["default"]["macro_f1"], "acc": cat["default"]["accuracy"], "cov(def)": cat["default"]["coverage"],
                     "prec(def)": cat["default"]["precision"], "cov(op)": cat["operating_point"]["coverage"], "prec(op)": cat["operating_point"]["precision"],
                     "PR-AUC": dg["pr_auc"], "ROC-AUC": dg["roc_auc"], "P(F2)": dg["at"]["f2"]["precision"], "R(F2)": dg["at"]["f2"]["recall"]})
    return results.md_table(rows, list(rows[0]))


if __name__ == "__main__":
    main()
