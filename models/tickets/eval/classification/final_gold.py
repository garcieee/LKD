"""The final exam: score each final configuration on the gold notes, once. What it found: REPORT.md.

    models/.venv/bin/python -m models.tickets.eval.classification.final_gold                 # every configuration, once
    models/.venv/bin/python -m models.tickets.eval.classification.final_gold --only lexicon_v1 --force   # a deliberate re-run
    models/.venv/bin/python -m models.tickets.eval.classification.final_gold --report        # redo tables and figures from saved predictions

This is the only module that opens the gold notes. Every time a configuration is scored on gold, one line (UTC time, name, "forced" if it
was) is appended to gold_runs.log BEFORE the notes are read, and a name already in the log is refused unless --force. The frozen
configuration (settings, thresholds) comes from results/classification_final_config.json, which evaluate.py wrote from train and
validation alone. Learned models are refitted on train plus validation with those settings; the word lists are fixed files.
--report reads the saved predictions only: it can be re-run, and it opens nothing it should not.

Every number carries a bootstrap 95% interval over notes (1,000 resamples, common.metrics.bootstrap_ci); comparisons use
paired_bootstrap_diff on the same resamples.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from models.tickets import settings as s
from models.tickets.eval.classification import baselines, schema
from models.tickets.eval.classification import evaluate as E
from models.tickets.eval.common import metrics as M
from models.tickets.eval.common import plots, results

GOLD = E.HERE / "data" / "notes_gold.jsonl"  # the one place this package names the file
LOG = E.HERE / "gold_runs.log"
FINAL_CONFIG = results.RESULTS / "classification_final_config.json"
PREDICTIONS = "classification_gold_predictions"
SEED_BOOT = 0
SHARE_WITH_NOTE = 0.30  # EVALUATION.md's practical view: about 30% of real reports carry a note
TARGETS = {"macro_f1": 0.80, "hint_precision": 0.90, "coverage": 0.60, "danger_recall": 0.90, "danger_precision": 0.60, "pr_auc": 0.85}
DECISION_GAP = 0.05  # a learned model must beat the word list's macro-F1 by this much, with the interval clear of zero


# ---- the gate: one scoring per configuration name, every scoring logged -------------------------------------------------
class AlreadyScored(RuntimeError):
    pass


def logged(log: Path) -> list[str]:
    """Configuration names in the log, one per scoring (a forced re-run appears again)."""
    return [line.split("\t")[1] for line in log.read_text().splitlines() if line.strip()] if log.exists() else []


def record(log: Path, name: str, forced: bool) -> None:
    with log.open("a") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}\t{name}" + ("\tforced" if forced else "") + "\n")


def score(name: str, predictor, gold: Path = GOLD, log: Path = LOG, force: bool = False) -> tuple[list[dict], E.Outputs]:
    """Score one configuration on gold. Refuses a name that is already in the log unless forced; logs before it reads the notes."""
    seen = name in logged(log)
    if seen and not force:
        raise AlreadyScored(f"{name} is already in {log.name}: refused. A re-run needs --force and is logged as forced.")
    if gold.resolve() == GOLD.resolve() and log.resolve() != LOG.resolve():
        raise AlreadyScored("the real gold file may only be scored against the real gold_runs.log")
    record(log, name, forced=seen)
    rows = schema.load(gold)
    return rows, predictor.outputs([r["text"] for r in rows])


# ---- saved predictions ---------------------------------------------------------------------------------------------------------
def slices_of(row: dict) -> list[str]:
    hard = row.get("hard")
    if isinstance(hard, (list, tuple)):
        return [str(h) for h in hard] or ["(no slice)"]
    return [str(hard)] if hard else ["(no slice)"]


def save_predictions(out_dir: Path, rows: list[dict], name: str, out: E.Outputs) -> None:
    path = out_dir / f"{PREDICTIONS}.json"
    data = json.loads(path.read_text()) if path.exists() else {"configs": {}}
    data["notes"] = [{"id": r["id"], "text": r["text"], "lang": r.get("lang"), "category": r["category"], "danger": bool(r["danger"]), "slices": slices_of(r)} for r in rows]
    data["configs"][name] = {"kind": out.kind, "columns": out.columns, "cat": np.round(out.cat, 6).tolist(), "danger": np.round(out.danger, 6).tolist()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, separators=(",", ":")) + "\n")


def load_predictions(out_dir: Path) -> tuple[list[dict], dict[str, E.Outputs]]:
    data = json.loads((out_dir / f"{PREDICTIONS}.json").read_text())
    return data["notes"], {n: E.Outputs(np.array(c["cat"]), c["columns"], np.array(c["danger"]), c["kind"]) for n, c in data["configs"].items()}


def short(name: str) -> str:
    """A figure label: the full configuration names are too long to read on an axis."""
    return {"lexicon_v0": "list v0", "lexicon_v1": "list v1", "naive_bayes": "NB", "logistic_regression": "LR"}.get(name, "list v1+norm" if name.startswith("lexicon_v1+") else name)


def ordered(names) -> list[str]:
    names = list(names)
    return [n for n in ("lexicon_v0", "lexicon_v1") if n in names] + sorted(n for n in names if n.startswith("lexicon_v1+")) \
        + [n for n in ("naive_bayes", "logistic_regression", "hybrid") if n in names]


# ---- numbers with intervals ---------------------------------------------------------------------------------------------------------
def ci(metric, *arrays) -> dict:
    try:
        return M.bootstrap_ci(metric, *arrays, n=E.BOOT, seed=SEED_BOOT).as_dict()
    except ValueError:
        return {"point": float(metric(*arrays)), "lo": None, "hi": None}


def diff(metric, y, a, b) -> dict:
    return M.paired_bootstrap_diff(metric, y, a, b, n=E.BOOT, seed=SEED_BOOT).as_dict()


def per_class(c: str, field: str):
    return lambda y, p: M.prf(y == c, p == c)[field]


def flagged(t: float, field: str):
    beta = 2.0 if field == "f2" else 1.0
    return lambda d, sc: M.prf(d, sc >= t, beta)["precision" if field == "precision" else "recall" if field == "recall" else "f"]


def category_numbers(y, default, op_labels) -> dict:
    cm = M.multiclass(y, default, E.CATEGORIES)
    return {
        "default": {"macro_f1": ci(E.macro_f1, y, default), "accuracy": ci(E.accuracy, y, default), "coverage": ci(E.coverage, y, default),
                    "hint_precision": ci(E.hint_precision, y, default), "confusion": cm["confusion"], "labels": cm["labels"],
                    "per_class": {c: {"support": cm["per_class"][c]["support"], **{k: ci(per_class(c, f), y, default) for k, f in (("precision", "precision"), ("recall", "recall"), ("f1", "f"))}} for c in E.CATEGORIES}},
        "operating_point": {"macro_f1": ci(E.macro_f1, y, op_labels), "accuracy": ci(E.accuracy, y, op_labels), "coverage": ci(E.coverage, y, op_labels),
                            "hint_precision": ci(E.hint_precision, y, op_labels), "correct_rate": ci(E.correct_rate, y, op_labels),
                            "of_all_reports": {k: {n: SHARE_WITH_NOTE * v for n, v in ci(f, y, op_labels).items() if v is not None} for k, f in (("correct_hint", E.correct_rate), ("any_hint", E.coverage))}},
    }


def danger_numbers(d, score_, thresholds: dict) -> dict:
    out = {"prevalence": float(np.mean(d)), "pr_auc": ci(M.pr_auc, d, score_), "roc_auc": ci(M.roc_auc, d, score_), "at": {}}
    for name, t in thresholds.items():
        out["at"][name] = {"threshold": t, **{f: ci(flagged(t, f), d, score_) for f in ("precision", "recall", "f1", "f2")},
                           "flagged_share": float(np.mean(score_ >= t))}
    return out


def slice_numbers(notes, y, d, default, op_labels, score_, t_f2) -> dict:
    """Per difficulty slice: category accuracy, hints at the operating point, danger recall and precision at the F2 threshold."""
    rows = {}
    for name in sorted({sl for n in notes for sl in n["slices"]}):
        keep = np.array([name in n["slices"] for n in notes])
        ys, ds, dp, op, sc = y[keep], d[keep], default[keep], op_labels[keep], score_[keep]
        row = {"n": int(keep.sum()), "danger_notes": int(ds.sum()), "accuracy": ci(E.accuracy, ys, dp), "macro_f1": ci(E.macro_f1, ys, dp),
               "coverage": ci(E.coverage, ys, op), "hint_precision": ci(E.hint_precision, ys, op)}
        if ds.sum():  # an interval needs a few danger notes in the slice; below 5 only the point is given
            interval = ci if ds.sum() >= 5 else (lambda metric, *arrays: {"point": float(metric(*arrays)), "lo": None, "hi": None})
            row.update({"danger_recall": interval(flagged(t_f2, "recall"), ds, sc), "danger_precision": interval(flagged(t_f2, "precision"), ds, sc)})
        rows[name] = row
    return rows


def breakdown(groups, y, d, default, op_labels, score_, t_f2) -> dict:
    """The same numbers cut by a note field (true category, language) instead of difficulty: category accuracy, hints at the operating point,
    and danger recall and precision at the F2 threshold. Point estimates: the groups are small."""
    rows = {}
    for name in sorted(set(groups)):
        keep = np.array([g == name for g in groups])
        row = {"n": int(keep.sum()), "danger_notes": int(d[keep].sum()), "accuracy": E.accuracy(y[keep], default[keep]), "coverage": E.coverage(y[keep], op_labels[keep]),
               "hint_precision": E.hint_precision(y[keep], op_labels[keep]), "flagged": int((score_[keep] >= t_f2).sum())}
        if d[keep].sum():
            row.update({"danger_recall": flagged(t_f2, "recall")(d[keep], score_[keep]), "danger_precision": flagged(t_f2, "precision")(d[keep], score_[keep])})
        rows[name] = row
    return rows


# ---- the report ---------------------------------------------------------------------------------------------------------------------------
def met(point: float | None, target: float) -> bool:
    return point is not None and point >= target


def report(out_dir: Path, final_config: Path = FINAL_CONFIG) -> dict:
    """Every table and figure from the saved predictions: no gold file is opened."""
    notes, outputs = load_predictions(out_dir)
    frozen = json.loads(final_config.read_text())["configs"]
    names = ordered(outputs)
    y, d = np.array([n["category"] for n in notes]), np.array([n["danger"] for n in notes])
    default = {n: E.default_labels(outputs[n]) for n in names}
    op = {n: E.operating_labels(outputs[n], frozen[n]["hint"]) for n in names}
    thresholds = {n: {**{k: v for k, v in frozen[n]["danger"].items() if v is not None}, **({"shipped": s.DANGER_MIN_SCORE} if outputs[n].kind == "scores" else {})} for n in names}

    per_config = {}
    for n in names:
        per_config[n] = {"spec": frozen[n]["spec"], "hint_operating_point": frozen[n]["hint"],
                         "category": category_numbers(y, default[n], op[n]), "danger": danger_numbers(d, outputs[n].danger, thresholds[n]),
                         "slices": slice_numbers(notes, y, d, default[n], op[n], outputs[n].danger, thresholds[n]["f2"]),
                         "by_true_category": breakdown(list(y), y, d, default[n], op[n], outputs[n].danger, thresholds[n]["f2"]),
                         "by_language": breakdown([nt["lang"] for nt in notes], y, d, default[n], op[n], outputs[n].danger, thresholds[n]["f2"])}

    pairs = {}
    for i, a in enumerate(names):
        for b in names[:i]:
            pairs[f"{a} - {b}"] = {"macro_f1_default": diff(E.macro_f1, y, default[a], default[b]), "macro_f1_operating_point": diff(E.macro_f1, y, op[a], op[b]),
                                   "danger_pr_auc": diff(M.pr_auc, d, outputs[a].danger, outputs[b].danger)}

    lists = [n for n in names if n.startswith("lexicon")]
    decision = {}
    for learned in (n for n in names if not n.startswith("lexicon")):
        for word_list in lists:
            row = pairs[f"{learned} - {word_list}"]
            decision[f"{learned} vs {word_list}"] = {view: {**row[view], "beats_by_0.05": row[view]["point"] >= DECISION_GAP and row[view]["lo"] > 0} for view in ("macro_f1_default", "macro_f1_operating_point")}

    targets = {}
    for n in names:
        c, dg = per_config[n]["category"], per_config[n]["danger"]
        f2 = dg["at"]["f2"]
        targets[n] = {
            "category_macro_f1_at_least_0.80": {"value": c["default"]["macro_f1"]["point"], "met": met(c["default"]["macro_f1"]["point"], TARGETS["macro_f1"]), "interval_clears_target": met(c["default"]["macro_f1"]["lo"], TARGETS["macro_f1"])},
            "category_precision_at_least_0.90_at_coverage_at_least_0.60": {
                "precision": c["operating_point"]["hint_precision"]["point"], "coverage": c["operating_point"]["coverage"]["point"],
                "met": met(c["operating_point"]["hint_precision"]["point"], TARGETS["hint_precision"]) and met(c["operating_point"]["coverage"]["point"], TARGETS["coverage"]),
                "interval_clears_target": met(c["operating_point"]["hint_precision"]["lo"], TARGETS["hint_precision"]) and met(c["operating_point"]["coverage"]["lo"], TARGETS["coverage"])},
            "danger_recall_at_least_0.90_and_precision_at_least_0.60_at_the_F2_threshold": {
                "recall": f2["recall"]["point"], "precision": f2["precision"]["point"],
                "met": met(f2["recall"]["point"], TARGETS["danger_recall"]) and met(f2["precision"]["point"], TARGETS["danger_precision"]),
                "interval_clears_target": met(f2["recall"]["lo"], TARGETS["danger_recall"]) and met(f2["precision"]["lo"], TARGETS["danger_precision"])},
            "danger_pr_auc_at_least_0.85": {"value": dg["pr_auc"]["point"], "met": met(dg["pr_auc"]["point"], TARGETS["pr_auc"]), "interval_clears_target": met(dg["pr_auc"]["lo"], TARGETS["pr_auc"])}}

    payload = {"notes": len(notes), "danger_notes": int(d.sum()), "category_counts": dict(Counter(y.tolist())), "bootstrap": {"resamples": E.BOOT, "seed": SEED_BOOT},
               "targets": TARGETS, "configs": per_config, "paired_differences": pairs, "decision_rule": decision, "target_check": targets,
               "share_of_reports_with_a_note": SHARE_WITH_NOTE}
    errors = error_analysis(notes, y, d, outputs, default, thresholds, per_config)
    results.write_result("classification_gold", payload, out_dir)
    results.write_result("classification_gold_errors", errors, out_dir)
    figures(out_dir, notes, y, d, outputs, op, per_config, frozen)
    return payload


def error_analysis(notes, y, d, outputs, default, thresholds, per_config) -> dict:
    """After the final run: the top confusions, the slices that break each model, and 15 random mistakes per task for the best
    model (best = highest gold macro-F1 for the category hint, highest gold PR-AUC for danger)."""
    names = list(outputs)
    best_cat = max(names, key=lambda n: per_config[n]["category"]["default"]["macro_f1"]["point"])
    best_danger = max(names, key=lambda n: per_config[n]["danger"]["pr_auc"]["point"])
    rng = np.random.default_rng(0)
    out = {"best_category_model": best_cat, "best_danger_model": best_danger, "configs": {}}
    for n in names:
        c = per_config[n]["category"]["default"]
        cells = [(c["labels"][i], c["labels"][j], count) for i, row in enumerate(c["confusion"]) for j, count in enumerate(row) if i != j and count]
        slices = per_config[n]["slices"]
        out["configs"][n] = {
            "top_confusions": [{"true": a, "predicted": b, "count": k} for a, b, k in sorted(cells, key=lambda x: -x[2])[:8]],
            "lowest_accuracy_slices": [{"slice": k, "n": v["n"], "accuracy": v["accuracy"]["point"]} for k, v in sorted(slices.items(), key=lambda kv: kv[1]["accuracy"]["point"])[:4]],
            "lowest_danger_recall_slices": [{"slice": k, "danger_notes": v["danger_notes"], "recall": v["danger_recall"]["point"]} for k, v in
                                            sorted(((k, v) for k, v in slices.items() if v["danger_notes"] >= 3), key=lambda kv: kv[1]["danger_recall"]["point"])[:4]],
            "danger_false_negatives_by_slice": dict(Counter(sl for i, nt in enumerate(notes) if d[i] and outputs[n].danger[i] < thresholds[n]["f2"] for sl in nt["slices"])),
            "danger_false_positives_by_slice": dict(Counter(sl for i, nt in enumerate(notes) if not d[i] and outputs[n].danger[i] >= thresholds[n]["f2"] for sl in nt["slices"]))}
    pick = lambda pool, k: sorted(rng.choice(pool, size=min(k, len(pool)), replace=False).tolist()) if pool else []
    wrong = [i for i in range(len(notes)) if default[best_cat][i] != y[i]]
    out["category_mistakes"] = [{"id": notes[i]["id"], "text": notes[i]["text"], "slices": notes[i]["slices"], "true": y[i], "predicted": default[best_cat][i]} for i in pick(wrong, 15)]
    t = thresholds[best_danger]["f2"]
    fn = [i for i in range(len(notes)) if d[i] and outputs[best_danger].danger[i] < t]
    fp = [i for i in range(len(notes)) if not d[i] and outputs[best_danger].danger[i] >= t]
    n_fn = min(len(fn), round(15 * len(fn) / max(len(fn) + len(fp), 1)))
    out["danger_mistakes"] = [{"id": notes[i]["id"], "text": notes[i]["text"], "slices": notes[i]["slices"], "true_danger": bool(d[i]), "score": float(outputs[best_danger].danger[i]),
                               "kind": "missed" if d[i] else "false alarm"} for i in pick(fn, n_fn) + pick(fp, 15 - n_fn)]
    return out


def figures(out_dir: Path, notes, y, d, outputs, op, per_config, frozen) -> None:
    names = list(outputs)
    for key, metric, target, title, fname in (("macro_f1", ("category", "default", "macro_f1"), 0.80, "Category hint, gold: 7-class macro-F1", "classification_gold_macro_f1.png"),
                                              ("pr_auc", ("danger", "pr_auc"), 0.85, "Danger flag, gold: PR-AUC", "classification_gold_pr_auc.png")):
        cells = []
        for n in names:
            cell = per_config[n]
            for part in metric:
                cell = cell[part]
            cells.append(cell)
        plots.save_bars(out_dir / fname, [short(n) for n in names], [c["point"] for c in cells], [c["lo"] for c in cells], [c["hi"] for c in cells], title, key.replace("_", "-"), target)
    plots.save_curves(out_dir / "classification_gold_danger.png", {short(n): (d, outputs[n].danger) for n in names}, "Danger flag, gold")
    curves = {short(n): E.selective_curve(outputs[n], y) for n in names}
    points = {short(n): (per_config[n]["category"]["operating_point"]["coverage"]["point"], per_config[n]["category"]["operating_point"]["hint_precision"]["point"]) for n in names}
    E.save_selective(out_dir / "classification_gold_selective.png", curves, points, "Category hint, gold (dots: validation-chosen settings)")
    slice_names = sorted(per_config[names[0]]["slices"])
    grid = np.array([[per_config[n]["slices"][sl]["accuracy"]["point"] for n in names] for sl in slice_names])
    fig, ax = plt.subplots(figsize=(1.0 * len(names) + 3.6, 0.42 * len(slice_names) + 1.6))
    image = ax.imshow(grid, vmin=0, vmax=1, cmap="Blues", aspect="auto")
    ax.set_xticks(range(len(names)), [short(n) for n in names], rotation=25, ha="right", fontsize=7)
    ax.set_yticks(range(len(slice_names)), [f"{sl} ({per_config[names[0]]['slices'][sl]['n']})" for sl in slice_names], fontsize=7)
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            ax.text(j, i, f"{grid[i, j]:.2f}", ha="center", va="center", fontsize=6, color="white" if grid[i, j] > 0.6 else "black")
    ax.set_title("Category accuracy by difficulty slice, gold", fontsize=9)
    fig.colorbar(image, ax=ax, shrink=0.8)
    fig.tight_layout()
    fig.savefig(out_dir / "classification_gold_slices.png", dpi=130)
    plt.close(fig)


# ---- the run ---------------------------------------------------------------------------------------------------------------------------------
def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", nargs="*", help="score just these configurations")
    ap.add_argument("--force", action="store_true", help="score a configuration that is already in the log (logged as forced)")
    ap.add_argument("--report", action="store_true", help="redo tables and figures from the saved predictions; scores nothing")
    ap.add_argument("--gold", type=Path, default=GOLD, help="a stand-in file, for a dry run only")
    ap.add_argument("--log", type=Path, default=LOG)
    ap.add_argument("--out", type=Path, default=results.RESULTS)
    ap.add_argument("--config", type=Path, default=FINAL_CONFIG)
    args = ap.parse_args(argv)
    if not args.report:
        frozen = json.loads(args.config.read_text())["configs"]
        names = args.only or ordered(frozen)
        repeated = [n for n in names if n in logged(args.log)]
        if repeated and not args.force:
            raise SystemExit(f"refused: {repeated} already in {args.log.name}. Nothing was scored.")
        fit_rows = E.load_train()  # train + validation: the learned models are refitted on all 80 families
        for name in names:
            predictor = baselines.make_predictor(frozen[name]["spec"], fit_rows)
            rows, out = score(name, predictor, args.gold, args.log, args.force)
            save_predictions(args.out, rows, name, out)
            print("scored", name)
    payload = report(args.out, args.config)
    for n, t in payload["target_check"].items():
        print(n, {k[:44]: v["met"] for k, v in t.items()})


if __name__ == "__main__":
    main()
