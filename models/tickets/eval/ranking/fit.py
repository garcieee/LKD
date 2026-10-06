"""Fit the weights of the priority score to the panel's judgments, and try the changes the disagreements point to. What it found: REPORT.md.

    models/.venv/bin/python -m models.tickets.eval.ranking.fit        (from the repo root; run it before evaluate, whose targets read its result)

Bradley-Terry: P(A is first) = 1 / (1 + exp(-w . (parts(A) - parts(B)))) on the four parts of the score, w >= 0, no intercept (a swapped
pair must give the same answer), fitted with L-BFGS-B bounds on the TRAIN pairs (label = the majority winner) plus an L2 penalty
lam * |w|^2. lam is chosen on VALIDATION by log-loss, the model's own objective, so that picking it does not also pick the accuracy
the rule below is judged on. The pre-registered rule (EVALUATION.md): the fitted weights, scaled to sum to 1 so that the floors, the
bonus and the bands keep their meaning, replace the hand weights only if the full score with them beats the full score with the hand
weights by at least 3 points of pairwise accuracy on VALIDATION and every weight is non-negative. Hand and fitted weights are then
reported on TEST once. Non-negative least squares of the mean urgency on the parts shows what the raters seem to care about.

Nothing here reads the test split until that last step: tests/test_fit.py flips every test rating and checks nothing fitted moves.
Candidate changes (a different severity, bonus, cap) are scored on train and validation only; the maintainer decides.
"""
import numpy as np
from scipy import optimize, special

from models.tickets import settings as S
from models.tickets.eval.common import metrics as M
from models.tickets.eval.common import plots, results
from models.tickets.eval.ranking import aggregate as ag
from models.tickets.eval.ranking import evaluate as ev

import matplotlib.pyplot as plt  # noqa: E402  (after common.plots, which selects the Agg backend)

BOOT, SEED = ev.BOOT, ev.SEED
LAMBDAS = (0.0, 0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0)
MARGIN = 0.03  # EVALUATION.md: the fitted weights must win on validation by this much pairwise accuracy
HAND = "hand weights"
BUSY_EDGES = (0.25, 0.65)  # the busy label a rater read: a quiet side street under 0.25, a moderately busy street up to 0.65, else a very busy area


# ---- Bradley-Terry ---------------------------------------------------------------------------------------------------
def bt_fit(x, y, lam: float) -> np.ndarray:
    """Non-negative w minimising the sum of log(1 + exp(-y * (x @ w))) + lam * |w|^2. y is +1 where A is first, -1 where B is."""
    x, y = np.asarray(x, float), np.asarray(y, float)

    def loss(w):
        z = y * (x @ w)
        return np.logaddexp(0, -z).sum() + lam * w @ w, -(x.T @ (y * special.expit(-z))) + 2 * lam * w

    return optimize.minimize(loss, np.full(x.shape[1], 0.1), jac=True, method="L-BFGS-B", bounds=[(0, None)] * x.shape[1]).x


def log_loss(x, y, w) -> float:
    return float(np.logaddexp(0, -np.asarray(y) * (np.asarray(x) @ w)).mean())


def design(survey, labels, parts: np.ndarray, split: str):
    """Feature differences (A minus B), labels (+1 A first, -1 B first) and pair rows for the majority-labelled pairs of ONE split."""
    mask = ev.pair_mask(survey, labels, split, "majority")
    return parts[survey.a[mask]] - parts[survey.b[mask]], np.where(labels.winner[mask] == ag.A, 1.0, -1.0), np.flatnonzero(mask)


def normalised(w) -> dict | None:
    """The weights as a settings table summing to 1, or None if they are all zero (nothing to scale)."""
    w = np.asarray(w, float)
    return {p: float(v / w.sum()) for p, v in zip(ev.PARTS, w)} if w.sum() > 0 else None


def accuracy_with(survey, labels, split: str, **settings) -> float:
    """Pairwise accuracy of the real score under settings overrides on the majority-labelled pairs of a split."""
    key = ev.score_array(survey.truth, **settings)
    mask = ev.pair_mask(survey, labels, split)
    return M.pairwise_accuracy(key[survey.a[mask]], key[survey.b[mask]], labels.winner[mask] == ag.A)


def rule(hand_accuracy: float, fitted_accuracy: float | None, weights, margin: float = MARGIN) -> dict:
    """The pre-registered rule: replace the hand weights only if the fitted ones win on validation by `margin` and none is negative."""
    gain = None if fitted_accuracy is None else fitted_accuracy - hand_accuracy
    non_negative = bool(all(v >= 0 for v in weights))
    return {"margin": margin, "hand_validation_accuracy": hand_accuracy, "fitted_validation_accuracy": fitted_accuracy, "validation_gain": gain,
            "non_negative": non_negative, "replace": bool(gain is not None and non_negative and gain >= margin - 1e-9)}


def fit_weights(survey, labels, lambdas=LAMBDAS) -> dict:
    """Fit on TRAIN for every lam, score each on VALIDATION, choose lam by validation log-loss (the larger lam on a tie), and apply the
    pre-registered rule. Returns everything, including the sweep. The test split is not read."""
    parts = ev.parts_array(survey.truth)
    xt, yt, _ = design(survey, labels, parts, "train")
    xv, yv, _ = design(survey, labels, parts, "validation")
    hand_validation = accuracy_with(survey, labels, "validation")
    sweep = []
    for lam in lambdas:
        w = bt_fit(xt, yt, lam)
        scaled = normalised(w)
        sweep.append({"lambda": lam, "weights": dict(zip(ev.PARTS, map(float, w))), "normalised": scaled, "validation_log_loss": log_loss(xv, yv, w),
                      "train_log_loss": log_loss(xt, yt, w),
                      "linear_accuracy": {"train": M.pairwise_accuracy(xt @ w, np.zeros(len(yt)), yt > 0), "validation": M.pairwise_accuracy(xv @ w, np.zeros(len(yv)), yv > 0)},
                      "full_score_accuracy": {s: accuracy_with(survey, labels, s, WEIGHTS=scaled) for s in ("train", "validation")} if scaled else None})
    best = min(range(len(sweep)), key=lambda i: (round(sweep[i]["validation_log_loss"], 12), -sweep[i]["lambda"]))
    chosen = sweep[best]
    decision = rule(hand_validation, chosen["full_score_accuracy"]["validation"] if chosen["normalised"] else None, chosen["weights"].values())
    decision["weights_of_record"] = chosen["normalised"] if decision["replace"] else dict(S.WEIGHTS)
    keys = {HAND: ev.score_array(survey.truth), "fitted weights": ev.score_array(survey.truth, WEIGHTS=chosen["normalised"])} if chosen["normalised"] else {}
    return {"sweep": sweep, "chosen_lambda": chosen["lambda"], "fitted_weights": chosen["normalised"], "raw_weights": chosen["weights"],
            "train_pairs": len(yt), "validation_pairs": len(yv), "hand_weights": dict(S.WEIGHTS), "decision": decision,
            "by_stratum": {s: ev.accuracy_by_stratum(survey, labels, keys, s) for s in ("train", "validation")} if keys else None}


# ---- what the raters seem to care about -------------------------------------------------------------------------------
def nnls_urgency(survey, extended: bool = False) -> dict:
    """Non-negative least squares of the panel's mean urgency on the four parts (and an intercept), on TRAIN tickets, with the
    weights scaled to sum to 1. extended: the parts times the gate, plus a 0/1 danger-note column, which mirrors how the score is built;
    its note coefficient, in the same units, is the bonus (in points of 100) the raters seem to give a note."""
    truth = survey.truth
    parts, gate = ev.parts_array(truth), np.array([b.gate for b in ev.shipped(truth)])
    note = np.array([float(t["danger"]) for t in truth])
    columns = [parts * gate[:, None], note[:, None]] if extended else [parts]
    x = np.hstack([*columns, np.ones((len(truth), 1))])
    urgency = ag.mean_urgency(survey)
    train, validation = survey.ticket_split == "train", survey.ticket_split == "validation"
    w, _ = optimize.nnls(x[train], urgency[train])
    fitted = x @ w
    r2 = lambda m: float(1 - ((urgency[m] - fitted[m]) ** 2).sum() / ((urgency[m] - urgency[m].mean()) ** 2).sum())
    weights = w[:4]
    out = {"split_fitted_on": "train", "n_tickets": int(train.sum()), "weights": dict(zip(ev.PARTS, map(float, weights))), "normalised": normalised(weights),
           "intercept": float(w[-1]), "r2_train": r2(train), "r2_validation": r2(validation),
           "spearman_validation": M.spearman(fitted[validation], urgency[validation])}
    if extended:
        out["note_coefficient"] = float(w[4])
        out["implied_bonus_points"] = float(100 * w[4] / weights.sum())
    return out


def urgency_by_category(survey, splits=("train", "validation")) -> dict:
    """Mean urgency of the tickets with no note and no 'gone' votes, by kind of hazard, next to the score's danger value: the raters' own scale."""
    mask = np.isin(survey.ticket_split, splits) & np.array([not t["danger"] and t["gone_votes"] == 0 for t in survey.truth])
    urgency = ag.mean_urgency(survey)
    return {c: {"n": int((mask & np.array([t["category"] == c for t in survey.truth])).sum()),
                "mean_urgency": float(urgency[mask & np.array([t["category"] == c for t in survey.truth])].mean()), "table_severity": S.SEVERITY[c]} for c in S.SEVERITY if c in ev.CATEGORIES}


# ---- candidate changes ----------------------------------------------------------------------------------------------
def visible_foot_traffic(truth):
    """A facts function that gives each ticket the foot traffic of the busy label the raters read (the mean of its three levels),
    not the number: what the score would see if it knew only what the raters knew."""
    level = lambda ft: int(ft >= BUSY_EDGES[0]) + int(ft > BUSY_EDGES[1])
    mean = {k: float(np.mean([t["foot_traffic"] for t in truth if level(t["foot_traffic"]) == k])) for k in range(3)}
    return lambda t: ev.facts_of({**t, "foot_traffic": mean[level(t["foot_traffic"])]})


def candidate_changes(truth, fitted: dict | None) -> dict[str, dict]:
    """name -> keyword arguments of ev.shipped. Each is one change to the shipped score."""
    middle = ("flooded_drain", "pothole", "broken_streetlight", "blocked_sidewalk")
    out = {"flooded drain severity 0.85 -> 0.65 (the pothole's)": {"SEVERITY": {**S.SEVERITY, "flooded_drain": 0.65}},
           "the four middle kinds all at severity 0.60": {"SEVERITY": {**S.SEVERITY, **{c: 0.60 for c in middle}}},
           "danger bonus 10 -> 20": {"DANGER_BONUS": 20.0},
           "waiting counted up to 30 days, not 14": {"WAITING_FULL_DAYS": 30},
           "foot traffic as the raters saw it (3 levels)": {"facts": visible_foot_traffic(truth)},
           "waiting weight halved (weights rescaled to sum to 1)": {"WEIGHTS": normalised([S.WEIGHTS[p] / (2 if p == "waiting" else 1) for p in ev.PARTS])}}
    if fitted:
        out["Bradley-Terry fitted weights (the pre-registered fit)"] = {"WEIGHTS": fitted}
    out["flooded drain 0.65 and bonus 20 together"] = {"SEVERITY": {**S.SEVERITY, "flooded_drain": 0.65}, "DANGER_BONUS": 20.0}
    return out


def scored(truth, change: dict) -> np.ndarray:
    return np.array([b.score for b in ev.shipped(truth, **change)])


def candidates(survey, labels, fitted: dict | None, boot: int = BOOT) -> dict:
    """Each candidate change on TRAIN and VALIDATION pairs: accuracy, and the change from the shipped score (a paired interval on validation).
    The test split is not read. Validation is 48 pairs: one pair is 2 points, so read these as direction, not proof."""
    truth = survey.truth
    keys = {ev.SHIPPED: ev.score_array(truth), **{name: scored(truth, change) for name, change in candidate_changes(truth, fitted).items()}}
    urgency = ag.mean_urgency(survey)
    out = {}
    for split in ("train", "validation"):
        mask = ev.pair_mask(survey, labels, split)
        wins, tickets = labels.winner[mask] == ag.A, ev.ticket_mask(survey, split)
        rows = {}
        for name, key in keys.items():
            row = {"accuracy": ev.accuracy_ci(key, survey, mask, wins, boot).as_dict(), "kendall_tau_b_with_urgency": M.kendall_tau_b(key[tickets], urgency[tickets])}
            if name != ev.SHIPPED:
                row["change_vs_shipped"] = ev.difference_ci(key, keys[ev.SHIPPED], survey, mask, wins, boot).as_dict()
            rows[name] = row
        out[split] = {"split": split, "n_pairs": int(mask.sum()), "n_tickets": int(tickets.sum()), "rows": rows, "by_stratum": ev.accuracy_by_stratum(survey, labels, keys, split)}
    return out


def drain_sweep(survey, labels, values=(0.85, 0.80, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50)) -> dict:
    """Pairwise accuracy on train and validation as the flooded drain's severity goes down from the shipped 0.85. Shows whether the gain
    is a curve or a single lucky value. The test split is not read."""
    return {str(v): {s: accuracy_with(survey, labels, s, SEVERITY={**S.SEVERITY, "flooded_drain": v}) for s in ("train", "validation")} for v in values}


# ---- the one test run --------------------------------------------------------------------------------------------------
def test_report(survey, labels, fitted: dict, boot: int = BOOT) -> dict:
    """The hand weights and the fitted weights on the TEST split, once: accuracy against the three label sets, the ceiling ratio, the paired
    difference, and the ticket metrics. Run after the weights and lam are fixed on train and validation."""
    keys = {HAND: ev.score_array(survey.truth), "fitted weights": ev.score_array(survey.truth, WEIGHTS=fitted)}
    return {"split": "test", "headline": {name: ev.headline(survey, labels, key, "test", boot) for name, key in keys.items()},
            "tickets": {name: ev.ticket_metrics(survey, key, "test", boot) for name, key in keys.items()},
            "compare": ev.compare_block(survey, labels, "test", keys, reference=HAND, reference_first=False, boot=boot),
            "by_stratum": ev.accuracy_by_stratum(survey, labels, keys, "test"), "post_stratified": ev.post_stratified(survey, labels, keys, "test", reference=HAND, boot=boot)}


def figure(path, payload: dict) -> None:
    """The hand weights next to the fitted ones and what the urgency ratings imply."""
    fit, nnls, ext = payload["bradley_terry"], payload["nnls"], payload["nnls_extended"]
    rows = {"hand": S.WEIGHTS, "Bradley-Terry (pairs)": fit["fitted_weights"], "NNLS (urgency)": nnls["normalised"], "NNLS with gate and note": ext["normalised"]}
    fig, ax = plt.subplots(figsize=(8, 3.6))
    for i, (name, w) in enumerate(rows.items()):
        ax.bar(np.arange(4) + (i - 1.5) * 0.2, [w[p] for p in ev.PARTS], 0.2, label=name)
    ax.set(xticks=range(4), xticklabels=[p.replace("_", " ") for p in ev.PARTS], ylabel="weight (sums to 1)")
    ax.set_title("What the raters seem to weigh, next to the hand weights", color=plots.INK)
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def run(survey, labels, boot: int = BOOT) -> dict:
    fit = fit_weights(survey, labels)
    fitted = fit["fitted_weights"]
    return {"config": {"bootstrap": boot, "seed": SEED, "lambdas": list(LAMBDAS), "margin": MARGIN, "label_set": "majority",
                       "fitted_on": "train pairs", "lambda_chosen_on": "validation log-loss", "decision_on": "validation pairwise accuracy of the full score"},
            "bradley_terry": fit, "decision": fit["decision"], "nnls": nnls_urgency(survey), "nnls_extended": nnls_urgency(survey, extended=True),
            "urgency_by_category": urgency_by_category(survey), "candidates": candidates(survey, labels, fitted, boot), "flooded_drain_severity_sweep": drain_sweep(survey, labels),
            "test": test_report(survey, labels, fitted, boot) if fitted else None}


def main() -> None:
    done = ag.run()
    payload = run(done["survey"], done["labels"])
    path = results.write_result("ranking_fit", payload)
    figure(path.with_suffix(".png"), payload)
    d = payload["decision"]
    print(f"wrote {path}\nchosen lambda {payload['bradley_terry']['chosen_lambda']}  fitted weights {payload['bradley_terry']['fitted_weights']}")
    print(f"validation: hand {d['hand_validation_accuracy']:.3f}  fitted {d['fitted_validation_accuracy']:.3f}  gain {d['validation_gain']:+.3f}  margin {d['margin']}  non-negative {d['non_negative']}  replace: {d['replace']}")
    for name, head in payload["test"]["headline"].items():
        a = head["majority"]["accuracy"]
        print(f"test {name}: accuracy {a['point']:.3f} [{a['lo']:.3f}, {a['hi']:.3f}]")


if __name__ == "__main__":
    main()
