"""Evaluate belief (ranking/lifecycle.py) against the vote simulator. What it found: REPORT.md.

    python -m models.tickets.eval.lifecycle.evaluate                       # validation only: prints, writes nothing
    python -m models.tickets.eval.lifecycle.evaluate --split test --write  # the one test run: results/lifecycle_*

Belief, the gate and the likely-gone flag are always the real functions of lifecycle.py. A different prior or flag
threshold is tried by overriding that one setting for the length of the call. Every metric comes from
eval/common/metrics.py. Each bootstrap resamples tickets, never single votes: the votes of one ticket are not
independent. Tune on train, choose on validation, report on test; the sweeps are descriptive and tune nothing.
"""
import argparse
import dataclasses
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple

import numpy as np
from scipy import optimize

from models.tickets import settings as S
from models.tickets.eval.common import metrics as M
from models.tickets.eval.common import plots, results
from models.tickets.eval.lifecycle.simulator import Sim, SimConfig, concat, simulate
from models.tickets.ranking import lifecycle

TRAIN_SEEDS, VALIDATION_SEEDS, TEST_SEEDS = tuple(range(1000, 1005)), tuple(range(2000, 2005)), tuple(range(3000, 3005))
SEEDS = {"train": TRAIN_SEEDS, "validation": VALIDATION_SEEDS, "test": TEST_SEEDS}
BOOT = 1000  # bootstrap resamples, the project standard
KS = (1, 2, 3, 5, 8)  # the vote counts reported: k votes = k taps after the first report
FRESH = 0.8  # belief of a fresh single report: the "always 0.8" baseline
ECE_MAX, AUC_MIN, AUC_FROM_VOTES = 0.05, 0.75, 3  # the pre-registered targets (EVALUATION.md)
PRIORS = {"(3,1) shipped": (3, 1), "(2,1)": (2, 1), "(1,1)": (1, 1), "(5,2)": (5, 2), "(1,0.5)": (1, 0.5)}
PRIOR_FIT_RANGE = (0.1, 20.0)  # the train fit may not go below a tenth of a vote of prior weight, or above 20
THRESHOLDS = tuple(round(0.30 + 0.025 * i, 3) for i in range(13))  # 0.30 ... 0.60, the range asked for
EXTRA_THRESHOLDS = (0.65, 0.70, 0.75, 0.80)  # beyond it, only to see where the F2 curve goes
SWEEP_KS = (1, 3, 5, 8)
SWEEPS = {  # name -> [(label, SimConfig changes)]
    "voter accuracy (sensitivity = specificity)": [(f"{a:.2f}", dict(sensitivity=a, specificity=a)) for a in (0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95)],
    "share of voters who tap at random": [(f"{x:.2f}", dict(noise=x)) for x in (0.0, 0.05, 0.10, 0.15, 0.20, 0.30)],
    "hazard lifetime (mean days)": [(f"{m:g}", dict(lifetime_means=(m,))) for m in (2.0, 5.0, 15.0, 60.0, 180.0)],
    "share of hazards gone before anyone votes": [(f"{x:.2f}", dict(gone_before_votes=x)) for x in (0.0, 0.1, 0.3, 0.5)],
    "share of 'gone' taps actually cast": [(f"{x:.2f}", dict(gone_tap_rate=x)) for x in (1.0, 0.5, 0.25, 0.1)],
    "vote delay (mean days after the first report)": [(f"{d:g}", dict(vote_delay_days=d)) for d in (3.0, 10.0, 30.0)],
}


# ---- plumbing ------------------------------------------------------------------------------------------------------
@contextmanager
def override(**values):
    """Set settings for the length of a call (a prior, a threshold) and always put them back."""
    old = {name: getattr(S, name) for name in values}  # an unknown name fails here, loudly
    try:
        for name, value in values.items():
            setattr(S, name, value)
        yield
    finally:
        for name, value in old.items():
            setattr(S, name, value)


def ci(metric, *arrays) -> dict:
    return M.bootstrap_ci(metric, *arrays, n=BOOT).as_dict()


def diff(metric, y, a, b) -> dict:
    return M.paired_bootstrap_diff(metric, y, a, b, n=BOOT).as_dict()


def pooled(metric):
    """Run a metric on padded (tickets x votes) arrays, ignoring cells with no vote (NaN in the first array).
    Resampling the rows of such arrays resamples whole tickets: a cluster bootstrap."""
    def run(y, *rest):
        ok = ~np.isnan(y)
        return metric(y[ok], *(r[ok] for r in rest))
    return run


def _div(a, b) -> float:
    return float(a) / float(b) if b else 0.0


def _prf(tp, fp, fn) -> dict:
    """Pooled precision, recall, F1 and F2 from per-ticket confusion counts (same numbers as M.prf on every vote)."""
    tp, fp, fn = tp.sum(), fp.sum(), fn.sum()
    precision, recall = _div(tp, tp + fp), _div(tp, tp + fn)
    return {"precision": precision, "recall": recall, "f1": M.f_beta(precision, recall, 1), "f2": M.f_beta(precision, recall, 2)}


def prf_ci(tp, fp, fn) -> dict:
    return {key: ci(lambda a, b, c, key=key: _prf(a, b, c)[key], tp, fp, fn) for key in ("precision", "recall", "f1", "f2")}


def prf_metric(name: str):
    """(y_gone, flagged) -> one of precision, recall, f1, f2, from M.prf."""
    return lambda y, f: M.prf(y, f, beta=2 if name == "f2" else 1)["f" if name in ("f1", "f2") else name]


def rate_ci(num, den) -> dict:
    """Pooled rate sum(num) / sum(den) from per-ticket counts, with the counts behind it (an interval of [0, 0] means no events)."""
    return {**ci(lambda a, b: _div(a.sum(), b.sum()), num, den), "events": int(num.sum()), "of": int(den.sum())}


def share_ci(hit, among) -> dict:
    """The share of the `among` rows that are `hit` (two boolean arrays), with the counts behind it."""
    return {**ci(lambda h, m: h[m].mean(), hit, among), "events": int((hit & among).sum()), "of": int(among.sum())}


def majority(yes, no):
    """The simple-majority forecast: 1 if more yes than no, 0 if fewer, 0.5 on a tie."""
    return np.where(yes > no, 1.0, np.where(yes < no, 0.0, 0.5))


# ---- belief at every vote ------------------------------------------------------------------------------------------
class Scored(NamedTuple):
    """Per ticket and vote (padded, NaN or False where there is no such vote): the counts, what lifecycle.py says
    and what is true. The first report counts as one yes, as in the engine."""
    valid: np.ndarray
    yes: np.ndarray
    no: np.ndarray
    belief: np.ndarray
    gate: np.ndarray
    flag: np.ndarray
    truth: np.ndarray  # 1.0 still there, 0.0 gone, at the moment of this vote
    next_truth: np.ndarray  # the same at the moment of the next vote (a forecast; NaN after the last vote)

    def at(self, k: int, truth: str = "truth") -> dict[str, np.ndarray]:
        """Everything after exactly k votes, for the tickets that got that many."""
        j = k - 1
        ok = self.valid[:, j] & ~np.isnan(getattr(self, truth)[:, j])
        cols = {f: getattr(self, f)[ok, j] for f in ("yes", "no", "belief", "gate", "flag")}
        return {**cols, "truth": getattr(self, truth)[ok, j]}


def score(world: Sim) -> Scored:
    ok = world.valid
    yes = np.where(ok, 1 + np.cumsum(world.yes & ok, axis=1), 0)
    no = np.where(ok, np.cumsum(~world.yes & ok, axis=1), 0)
    belief, gate = np.full(ok.shape, np.nan), np.full(ok.shape, np.nan)
    flag = np.zeros(ok.shape, bool)
    belief[ok] = [lifecycle.belief(y, n) for y, n in zip(yes[ok].tolist(), no[ok].tolist())]
    gate[ok] = [lifecycle.gate(b) for b in belief[ok].tolist()]
    flag[ok] = [lifecycle.likely_gone(b) for b in belief[ok].tolist()]
    truth = np.where(ok, world.there, np.nan)
    next_truth = np.full(ok.shape, np.nan)
    next_truth[:, :-1] = truth[:, 1:]
    return Scored(ok, yes, no, belief, gate, flag, truth, next_truth)


def world_of(cfg: SimConfig, split: str) -> Sim:
    return concat([simulate(cfg, seed) for seed in SEEDS[split]])


# ---- 1. the pre-registered targets, by vote count -----------------------------------------------------------------
def target_row(col: dict, full: bool = True) -> dict:
    """Belief and the two baselines on one vote count. full=False skips the majority baseline, PR-AUC and the curve."""
    y, b = col["truth"], col["belief"]
    forecasts = {"belief": b, "always_0.8": np.full_like(b, FRESH)}
    metrics = {"brier": M.brier, "ece": M.ece, "roc_auc": M.roc_auc}
    if full:
        forecasts["majority"] = majority(col["yes"], col["no"])
        metrics["pr_auc"] = M.pr_auc
    row = {"n": len(y), "prevalence": ci(np.mean, y)}
    for name, p in forecasts.items():
        row[name] = {metric: ci(fn, y, p) for metric, fn in metrics.items()}
    row["brier_belief_minus_always_0.8"] = diff(M.brier, y, b, forecasts["always_0.8"])
    if full:
        row["brier_belief_minus_majority"] = diff(M.brier, y, b, forecasts["majority"])
        row["roc_auc_belief_minus_majority"] = diff(M.roc_auc, y, b, forecasts["majority"])
        row["reliability"] = M.reliability(y, b)
    return row


def verdict(row: dict, k: int) -> dict:
    """Met only when the whole 95% interval is on the passing side of the target."""
    out = {"ece_at_most_0.05": row["belief"]["ece"]["hi"] <= ECE_MAX, "brier_below_always_0.8": row["brier_belief_minus_always_0.8"]["hi"] < 0}
    if k >= AUC_FROM_VOTES:
        out["roc_auc_at_least_0.75"] = row["belief"]["roc_auc"]["lo"] >= AUC_MIN
    return out


def targets_eval(sc: Scored) -> dict:
    by_votes = {k: target_row(sc.at(k)) for k in KS}
    verdicts = {k: verdict(row, k) for k, row in by_votes.items()}
    overall = {name: all(v[name] for v in verdicts.values() if name in v) for name in ("ece_at_most_0.05", "brier_below_always_0.8", "roc_auc_at_least_0.75")}
    forecast = {k: target_row(sc.at(k, "next_truth"), full=False) for k in KS}  # truth at the NEXT vote: no tap shares a moment with the label
    return {"by_votes": by_votes, "verdicts": verdicts, "overall": overall, "forecast_by_votes": forecast}


def per_seed_eval(cfg: SimConfig, split: str, k: int = 3) -> list[dict]:
    """The same numbers seed by seed: the spread should match what the bootstrap interval says."""
    rows = []
    for seed in SEEDS[split]:
        col = score(simulate(cfg, seed)).at(k)
        y, b = col["truth"], col["belief"]
        rows.append({"seed": seed, "n": len(y), "brier": M.brier(y, b), "ece": M.ece(y, b), "roc_auc": M.roc_auc(y, b)})
    return rows


# ---- 2. priors ----------------------------------------------------------------------------------------------------
def belief_under(world: Sim, prior) -> np.ndarray:
    with override(BELIEF_PRIOR=prior):
        return score(world).belief


def fit_prior(train: Scored) -> tuple[float, float]:
    """The Beta prior with the lowest Brier on the train split (reference only: it is not one of the candidates)."""
    ok = train.valid
    key, inverse = np.unique(train.yes[ok] * 1000 + train.no[ok], return_inverse=True)
    truth = train.truth[ok]

    def loss(theta):
        with override(BELIEF_PRIOR=tuple(np.exp(theta))):
            table = np.array([lifecycle.belief(int(c) // 1000, int(c) % 1000) for c in key])
        return M.brier(truth, table[inverse.ravel()])

    edge = (np.log(PRIOR_FIT_RANGE[0]), np.log(PRIOR_FIT_RANGE[1]))
    best = optimize.minimize(loss, np.log(S.BELIEF_PRIOR), method="Nelder-Mead", bounds=[edge, edge], options={"xatol": 1e-3, "fatol": 1e-8})
    return tuple(float(x) for x in np.exp(best.x))


def priors_eval(train: Sim, validation: Sim, report: Sim) -> dict:
    fitted = fit_prior(score(train))
    candidates = {**PRIORS, f"fitted on train ({fitted[0]:.2f},{fitted[1]:.2f})": fitted}
    val_truth, val_scored = score(validation).truth, {name: belief_under(validation, p) for name, p in candidates.items()}
    val_brier = {name: pooled(M.brier)(val_truth, b) for name, b in val_scored.items()}
    chosen = min(PRIORS, key=val_brier.get)  # the five given priors compete; the fitted one is only a reference
    del val_scored
    shipped = "(3,1) shipped"
    truth, beliefs = score(report).truth, {name: belief_under(report, p) for name, p in candidates.items()}
    rows = {}
    for name, b in beliefs.items():
        row = {"prior": candidates[name], "validation_brier": val_brier[name], "brier": ci(pooled(M.brier), truth, b),
               "ece_by_votes": {k: ci(M.ece, *(a[~np.isnan(truth[:, k - 1]), k - 1] for a in (truth, b))) for k in KS}}
        if name != shipped:
            row["brier_minus_shipped"] = diff(pooled(M.brier), truth, b, beliefs[shipped])
            row["by_votes_brier_minus_shipped"] = {k: diff(M.brier, *(a[~np.isnan(truth[:, k - 1]), k - 1] for a in (truth, b, beliefs[shipped]))) for k in KS}
        rows[name] = row
    beats = {name: bool(r["brier_minus_shipped"]["hi"] < 0) for name, r in rows.items() if name != shipped}
    return {"rows": rows, "chosen_on_validation": chosen, "fitted_on_train": fitted, "beats_shipped": beats,
            "chosen_beats_shipped": bool(beats.get(chosen, False)), "decision": chosen if beats.get(chosen, False) else shipped}


def prior_sweep(cfg: SimConfig, split: str, shares=(0.0, 0.1, 0.3, 0.5)) -> list[dict]:
    """Does a better prior exist? It depends on how many hazards are already gone when the first extra vote comes."""
    out = []
    for share in shares:
        world = world_of(dataclasses.replace(cfg, gone_before_votes=share), split)
        truth = score(world).truth
        beliefs = {name: belief_under(world, p) for name, p in PRIORS.items()}
        rows = {name: {"brier_minus_shipped": diff(pooled(M.brier), truth, b, beliefs["(3,1) shipped"])} for name, b in beliefs.items() if name != "(3,1) shipped"}
        best = min(rows, key=lambda n: rows[n]["brier_minus_shipped"]["point"])
        out.append({"gone_before_votes": share, "prevalence": float(np.nanmean(truth)), "rows": rows,
                    "best_point": best if rows[best]["brier_minus_shipped"]["point"] < 0 else "(3,1) shipped"})
    return out


# ---- 3. the likely-gone flag --------------------------------------------------------------------------------------
def flagged_at(sc: Scored, threshold: float) -> np.ndarray:
    with override(LIKELY_GONE_BELOW=threshold):
        out = np.zeros(sc.valid.shape, bool)
        out[sc.valid] = [lifecycle.likely_gone(b) for b in sc.belief[sc.valid].tolist()]
    return out


def flag_counts(sc: Scored, flagged: np.ndarray):
    """Per ticket: true positives, false positives, false negatives (positive = the hazard is gone)."""
    gone, there = sc.truth == 0, sc.truth == 1
    return (flagged & gone).sum(1), (flagged & there).sum(1), (~flagged & gone).sum(1)


def flag_eval(validation: Scored, report: Scored) -> dict:
    flags_val = {t: _prf(*flag_counts(validation, flagged_at(validation, t))) for t in THRESHOLDS + EXTRA_THRESHOLDS}
    best_f2 = max(flags_val[t]["f2"] for t in THRESHOLDS)
    plateau = [t for t in THRESHOLDS if flags_val[t]["f2"] >= best_f2 - 1e-12]
    best = plateau[len(plateau) // 2]  # the F2 curve is flat between two reachable beliefs: take the middle of the plateau
    table = []
    for t in THRESHOLDS + EXTRA_THRESHOLDS:
        tp, fp, fn = flag_counts(report, flagged_at(report, t))
        table.append({"threshold": t, "in_range_asked": t in THRESHOLDS, "validation": flags_val[t], **prf_ci(tp, fp, fn),
                      "false_flag_rate": rate_ci(fp, (report.truth == 1).sum(1)), "flag_rate": rate_ci(tp + fp, report.valid.sum(1))})
    everything = prf_ci(*flag_counts(report, report.valid))  # flag every vote: what a rule that never looks at belief scores
    y_gone = np.where(np.isnan(report.truth), np.nan, 1.0 - report.truth)
    at80 = M.at_recall(y_gone[~np.isnan(y_gone)], 1 - report.belief[~np.isnan(y_gone)], 0.8)

    def precision_at_80(y, s):
        found = M.at_recall(y, s, 0.8)
        if found is None:
            raise ValueError("recall 0.8 not reachable")
        return found["precision"]

    p80 = ci(pooled(precision_at_80), y_gone, 1 - report.belief)
    shipped_t, best_t = S.LIKELY_GONE_BELOW, best
    best_counts, shipped_counts = (flag_counts(report, flagged_at(report, t)) for t in (best_t, shipped_t))
    f2_gain = ci(lambda a1, a2, a3, b1, b2, b3: _prf(a1, a2, a3)["f2"] - _prf(b1, b2, b3)["f2"], *best_counts, *shipped_counts)
    by_votes = {}
    for k in KS:
        col = report.at(k)
        y = col["truth"] == 0
        by_votes[k] = {}
        for name, t in (("shipped", shipped_t), ("validation_best", best_t)):
            with override(LIKELY_GONE_BELOW=t):
                flagged = np.array([lifecycle.likely_gone(x) for x in col["belief"].tolist()])
            by_votes[k][name] = {m: ci(prf_metric(m), y, flagged) for m in ("precision", "recall", "f1", "f2")}
            by_votes[k][name]["false_flag_rate"] = share_ci(flagged, ~y)
    return {"table": table, "flag_everything": everything, "validation_best_f2_threshold": best, "validation_f2_plateau": plateau,
            "validation_best_f2_threshold_any": max(flags_val, key=lambda t: flags_val[t]["f2"]), "shipped_threshold": shipped_t,
            "f2_best_minus_shipped": f2_gain, "precision_at_recall_0.8": {"precision": p80, "flag_when_belief_at_most": None if at80 is None else 1 - at80["threshold"]},
            "by_votes": by_votes}


# ---- 4. the gate --------------------------------------------------------------------------------------------------
def demotion_levels(flag: np.ndarray, gate: np.ndarray) -> dict[str, np.ndarray]:
    """Three ways to say "the gate demoted this ticket" (NaN gate = no vote = False)."""
    return {"flag: belief under the likely-gone line": flag, "gate at most 0.5: score halved or worse": gate <= 0.5, "gate below 1: any cut": gate < 1.0}


def gate_eval(sc: Scored) -> dict:
    there, gone = sc.truth == 1, sc.truth == 0
    cut = np.where(sc.valid, 1.0 - sc.gate, 0.0)
    pooled_rows = {}
    for name, demoted in demotion_levels(sc.flag, sc.gate).items():
        pooled_rows[name] = {"false_demotion_rate_of_there": rate_ci((demoted & there).sum(1), there.sum(1)),
                             "demotion_rate_of_gone": rate_ci((demoted & gone).sum(1), gone.sum(1))}
    pooled_rows["mean score cut (1 - gate)"] = {"false_demotion_rate_of_there": rate_ci((cut * there).sum(1), there.sum(1)),
                                                 "demotion_rate_of_gone": rate_ci((cut * gone).sum(1), gone.sum(1))}
    by_votes = {}
    for k in KS:
        col = sc.at(k)
        t, g = col["truth"] == 1, col["truth"] == 0
        by_votes[k] = {name: {"false_demotion_rate_of_there": share_ci(d, t), "demotion_rate_of_gone": share_ci(d, g)}
                       for name, d in demotion_levels(col["flag"], col["gate"]).items()}
    return {"gate_parameters": {"GATE_LOW": S.GATE_LOW, "GATE_SPAN": S.GATE_SPAN, "GATE_MIN": S.GATE_MIN, "LIKELY_GONE_BELOW": S.LIKELY_GONE_BELOW},
            "gate_at_the_shipped_flag_line": lifecycle.gate(S.LIKELY_GONE_BELOW), "pooled": pooled_rows, "by_votes": by_votes}


# ---- 5. how many votes before belief says anything ----------------------------------------------------------------
def information_eval(sc: Scored, ks=range(1, 11)) -> list[dict]:
    rows = []
    for k in ks:
        col = sc.at(k)
        y, b, flag = col["truth"], col["belief"], col["flag"]
        skill = lambda yy, bb: 1 - M.brier(yy, bb) / M.brier(yy, np.full_like(bb, FRESH))
        rows.append({"votes": k, "share_of_tickets_reaching_it": float(sc.valid[:, k - 1].mean()), "n": len(y), "prevalence": float(y.mean()),
                     "roc_auc": ci(M.roc_auc, y, b), "brier_skill_vs_always_0.8": ci(skill, y, b),
                     "flag_recall_of_gone": share_ci(flag, y == 0), "false_flag_rate": share_ci(flag, y == 1)})
    return rows


def snapshot_eval(world: Sim, days=(7, 30)) -> dict:
    """What the app would show on day T for every ticket, including those nobody voted on: the realistic lens."""
    out = {}
    for day in days:
        counted = world.valid & (world.time <= day)
        yes, no = 1 + (counted & world.yes).sum(1), (counted & ~world.yes).sum(1)
        beliefs = [lifecycle.belief(y, n) for y, n in zip(yes.tolist(), no.tolist())]
        gate = np.array([lifecycle.gate(b) for b in beliefs])
        flag = np.array([lifecycle.likely_gone(b) for b in beliefs])
        there = day < world.end
        b = np.array(beliefs)
        out[day] = {"share_gone": ci(lambda t: 1 - t.mean(), there), "no_vote_at_all": ci(np.mean, counted.sum(1) == 0),
                    "belief_roc_auc": ci(M.roc_auc, there, b), "brier_belief_minus_always_0.8": diff(M.brier, there, b, np.full_like(b, FRESH)),
                    "flag_recall_of_gone": share_ci(flag, ~there), "false_flag_rate": share_ci(flag, there),
                    "gate_cut_share_of_gone": share_ci(gate < 1, ~there), "gate_cut_share_of_there": share_ci(gate < 1, there),
                    "gone_with_belief_at_least_0.8": share_ci(b >= FRESH, ~there)}
    return out


# ---- 6. sweeps ----------------------------------------------------------------------------------------------------
def sweep_point(cfg: SimConfig, split: str) -> dict:
    sc = score(world_of(cfg, split))
    row = {}
    for k in SWEEP_KS:
        col = sc.at(k)
        y, b = col["truth"], col["belief"]
        r = {"n": len(y), "prevalence": float(y.mean()), "ece": ci(M.ece, y, b), "brier_belief_minus_always_0.8": diff(M.brier, y, b, np.full_like(b, FRESH)),
             "roc_auc": ci(M.roc_auc, y, b)}
        r["met"] = {"ece": r["ece"]["hi"] <= ECE_MAX, "brier": r["brier_belief_minus_always_0.8"]["hi"] < 0}
        if k >= AUC_FROM_VOTES:
            r["met"]["roc_auc"] = r["roc_auc"]["lo"] >= AUC_MIN
        row[k] = r
    return row


def sweeps_eval(cfg: SimConfig, split: str) -> dict:
    return {name: [{"value": label, "changes": changes, "by_votes": sweep_point(dataclasses.replace(cfg, **changes), split)} for label, changes in points]
            for name, points in SWEEPS.items()}


# ---- figures ------------------------------------------------------------------------------------------------------
def _round(x, digits: int = 5):
    """Round every float so the committed JSON stays small and readable."""
    if isinstance(x, dict):
        return {k: _round(v, digits) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_round(v, digits) for v in x]
    return round(float(x), digits) if isinstance(x, (float, np.floating)) else x


def _save(fig, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plots.plt.close(fig)


def plot_priors(path: Path, priors: dict, split: str) -> None:
    rows = {n: r for n, r in priors["rows"].items() if "brier_minus_shipped" in r}
    fig, ax = plots.plt.subplots(figsize=(6.4, 0.55 * len(rows) + 1.6))
    y = np.arange(len(rows))
    point = np.array([r["brier_minus_shipped"]["point"] for r in rows.values()])
    lo = np.array([r["brier_minus_shipped"]["lo"] for r in rows.values()])
    hi = np.array([r["brier_minus_shipped"]["hi"] for r in rows.values()])
    ax.errorbar(point, y, xerr=[point - lo, hi - point], fmt="o", color="#212e4a", capsize=4)
    ax.axvline(0, color="#a63722", ls="--", lw=1.2)
    ax.set(yticks=y, yticklabels=list(rows), xlabel="Brier minus shipped (below 0 = better)", title=f"Each prior against the shipped (3,1), {split}, 95% interval")
    ax.title.set_fontsize(9)
    _save(fig, path)


def plot_flag(path: Path, flag: dict, split: str) -> None:
    fig, ax = plots.plt.subplots(figsize=(6.6, 4.0))
    t = [r["threshold"] for r in flag["table"]]
    for key, color in (("precision", "#212e4a"), ("recall", "#a63722"), ("f1", "#7a8a6a"), ("f2", "#c08a2e")):
        ax.plot(t, [r[key]["point"] for r in flag["table"]], marker="o", ms=3, label=key, color=color)
        ax.fill_between(t, [r[key]["lo"] for r in flag["table"]], [r[key]["hi"] for r in flag["table"]], color=color, alpha=0.12)
    ax.axvline(flag["shipped_threshold"], color=plots.INK, ls="--", lw=1, label="shipped 0.45")
    ax.axvline(flag["validation_best_f2_threshold"], color=plots.FAINT, ls=":", lw=1.5, label="F2-best on validation")
    ax.set(xlabel="flag a ticket when belief is below (0.65 and up: beyond the range asked)", ylabel="score", title=f"Likely-gone flag by threshold, {split}", ylim=(0, 1.02))
    ax.xaxis.label.set_fontsize(8)
    ax.legend(fontsize=7)
    _save(fig, path)


def plot_sweeps(path: Path, sweeps: dict) -> None:
    columns = 3
    rows = -(-len(sweeps) // columns)
    fig, axes = plots.plt.subplots(rows, columns, figsize=(3.5 * columns, 3.0 * rows), squeeze=False)
    for ax, (name, points) in zip(axes.ravel(), sweeps.items()):
        x = np.arange(len(points))
        for k, color in ((3, "#212e4a"), (8, "#a63722")):
            auc = [p["by_votes"][k]["roc_auc"] for p in points]
            ax.plot(x, [a["point"] for a in auc], marker="o", ms=3, color=color, label=f"ROC-AUC, {k} votes")
            ax.fill_between(x, [a["lo"] for a in auc], [a["hi"] for a in auc], color=color, alpha=0.15)
            ax.plot(x, [p["by_votes"][k]["ece"]["point"] for p in points], marker="s", ms=3, ls=":", color=color, label=f"ECE, {k} votes")
        ax.axhline(AUC_MIN, color=plots.FAINT, ls="--", lw=1)
        ax.axhline(ECE_MAX, color=plots.FAINT, ls="--", lw=1)
        ax.set(title=name, ylim=(0, 1.0))
        ax.set_xticks(x, [p["value"] for p in points], fontsize=7)
        ax.title.set_fontsize(8)
    for ax in axes.ravel()[len(sweeps):]:
        ax.axis("off")
    axes[0, 0].legend(fontsize=6, loc="center left")
    _save(fig, path)


def plot_information(path: Path, info: list[dict], split: str) -> None:
    fig, (left, right) = plots.plt.subplots(1, 2, figsize=(9.2, 4.4))
    k = [r["votes"] for r in info]
    left.plot(k, [r["roc_auc"]["point"] for r in info], marker="o", color="#212e4a", label="ROC-AUC")
    left.fill_between(k, [r["roc_auc"]["lo"] for r in info], [r["roc_auc"]["hi"] for r in info], color="#212e4a", alpha=0.15)
    left.plot(k, [r["flag_recall_of_gone"]["point"] for r in info], marker="o", color="#a63722", label="flag recall of gone (0.45)")
    left.plot(k, [r["false_flag_rate"]["point"] for r in info], marker="o", color="#7a8a6a", label="flag false alarms among still there")
    left.plot(k, [r["share_of_tickets_reaching_it"] for r in info], marker="s", ls="--", color=plots.FAINT, label="share of tickets with that many votes")
    left.axhline(AUC_MIN, color=plots.FAINT, ls=":", lw=1)
    left.set(xlabel="votes after the first report", ylim=(0, 1.02), title=f"What belief can do after k votes, {split}")
    left.legend(fontsize=6.5, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=2)
    right.plot(k, [r["brier_skill_vs_always_0.8"]["point"] for r in info], marker="o", color="#212e4a")
    right.fill_between(k, [r["brier_skill_vs_always_0.8"]["lo"] for r in info], [r["brier_skill_vs_always_0.8"]["hi"] for r in info], color="#212e4a", alpha=0.15)
    right.axhline(0, color=plots.FAINT, ls="--", lw=1)
    right.set(xlabel="votes after the first report", title=f"Brier skill against always 0.8 (above 0 = better), {split}")
    right.title.set_fontsize(9)
    _save(fig, path)


# ---- run ----------------------------------------------------------------------------------------------------------
def run(split: str = "validation", write: bool = False, out: Path | None = None, tickets: int = 10_000, boot: int | None = None, sweeps: bool = True) -> dict:
    """Choices (prior, flag threshold) are made on validation and the numbers are reported on `split`."""
    global BOOT
    BOOT = boot or BOOT
    cfg = SimConfig(tickets=tickets)
    train, validation, report = world_of(cfg, "train"), world_of(cfg, "validation"), world_of(cfg, split)
    val_scored, scored = score(validation), score(report)
    payload = {"targets": targets_eval(scored), "priors": priors_eval(train, validation, report), "flag": flag_eval(val_scored, scored),
               "gate": gate_eval(scored), "information": {"by_votes": information_eval(scored), "snapshot": snapshot_eval(report)}}
    payload["targets"]["per_seed"] = per_seed_eval(cfg, split)
    if sweeps:
        payload["sweeps"] = sweeps_eval(cfg, split)
        payload["priors"]["by_share_gone_before_votes"] = prior_sweep(cfg, split)
    if write:
        folder = out or results.RESULTS
        folder.mkdir(parents=True, exist_ok=True)
        header = {"notes": ["k votes = k taps after the first report, which counts as one yes", "truth = the hazard is there at the moment of the vote",
                            "intervals: 95% percentile bootstrap over whole tickets", "a target is met only when the whole interval passes"],
                  "split": split, "seeds": SEEDS[split], "train_seeds": TRAIN_SEEDS, "validation_seeds": VALIDATION_SEEDS, "bootstrap_resamples": BOOT,
                  "sim_config": dataclasses.asdict(cfg), "settings": {"BELIEF_PRIOR": S.BELIEF_PRIOR, "GATE_LOW": S.GATE_LOW, "GATE_SPAN": S.GATE_SPAN,
                                                                      "GATE_MIN": S.GATE_MIN, "LIKELY_GONE_BELOW": S.LIKELY_GONE_BELOW}}
        for name, body in payload.items():
            results.write_result(f"lifecycle_{name}", _round({**header, name: body}), folder)
        k_rel = {f"{k} votes": (scored.at(k)["truth"], scored.at(k)["belief"]) for k in KS}
        plots.save_reliability(folder / "lifecycle_reliability.png", k_rel, f"Belief after k votes, {split}")
        plot_priors(folder / "lifecycle_priors.png", payload["priors"], split)
        plot_flag(folder / "lifecycle_flag.png", payload["flag"], split)
        plot_information(folder / "lifecycle_information.png", payload["information"]["by_votes"], split)
        if sweeps:
            plot_sweeps(folder / "lifecycle_sweeps.png", payload["sweeps"])
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", choices=("validation", "test"), default="validation", help="where the numbers are reported (default validation)")
    parser.add_argument("--write", action="store_true", help="write eval/results/lifecycle_*.json and *.png")
    parser.add_argument("--tickets", type=int, default=10_000, help="tickets per seed")
    parser.add_argument("--boot", type=int, default=None, help="bootstrap resamples (default 1000)")
    parser.add_argument("--no-sweeps", action="store_true")
    args = parser.parse_args()
    if args.split == "test" and not args.write:
        parser.error("a test run is never thrown away: use --write with --split test")
    payload = run(args.split, args.write, None, args.tickets, args.boot, not args.no_sweeps)
    rows = [{"votes": k, "belief_ece": r["belief"]["ece"]["point"], "belief_brier": r["belief"]["brier"]["point"], "always_0.8_brier": r["always_0.8"]["brier"]["point"],
             "belief_auc": r["belief"]["roc_auc"]["point"]} for k, r in payload["targets"]["by_votes"].items()]
    print(results.md_table(rows, ["votes", "belief_ece", "belief_brier", "always_0.8_brier", "belief_auc"]))
    print("verdicts:", payload["targets"]["overall"], "| prior chosen on validation:", payload["priors"]["chosen_on_validation"],
          "| F2-best flag threshold on validation:", payload["flag"]["validation_best_f2_threshold"])


if __name__ == "__main__":
    main()
