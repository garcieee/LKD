"""Every metric the evaluations use, one tested implementation each. Needs numpy, scipy and scikit-learn.

Conventions: binary labels are 0/1 or bool; a prediction is positive when its score is >= the threshold;
precision, recall and F with nothing to divide by are 0.0 (sklearn's zero_division=0), so a model that never
says yes scores 0, not NaN.
"""
from collections import Counter
from typing import Callable, NamedTuple, Sequence

import numpy as np
from scipy import stats
from sklearn import metrics as skm


# ---- binary classification -------------------------------------------------------------------------------------
def f_beta(precision: float, recall: float, beta: float = 1.0) -> float:
    denominator = beta**2 * precision + recall
    return (1 + beta**2) * precision * recall / denominator if denominator > 0 else 0.0


def prf(y_true, y_pred, beta: float = 1.0) -> dict:
    """Precision, recall, F-beta and the confusion counts for hard yes/no predictions."""
    t, p = np.asarray(y_true).astype(bool), np.asarray(y_pred).astype(bool)
    tp, fp, fn, tn = int((t & p).sum()), int((~t & p).sum()), int((t & ~p).sum()), int((~t & ~p).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": precision, "recall": recall, "f": f_beta(precision, recall, beta), "beta": beta,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def pr_auc(y_true, scores) -> float:
    """Average precision: the headline AUC when positives are rare."""
    return float(skm.average_precision_score(y_true, scores))


def roc_auc(y_true, scores) -> float:
    return float(skm.roc_auc_score(y_true, scores))


def _curve(y_true, scores):
    precision, recall, thresholds = skm.precision_recall_curve(y_true, scores)
    return precision[:-1], recall[:-1], thresholds  # one row per threshold, rule: score >= threshold


def best_threshold(y_true, scores, beta: float = 1.0) -> dict:
    """The threshold with the best F-beta (the highest one among ties), with its precision and recall."""
    precision, recall, thresholds = _curve(y_true, scores)
    f = np.array([f_beta(p, r, beta) for p, r in zip(precision, recall)])
    best = np.flatnonzero(f == f.max())[-1]
    return {"threshold": float(thresholds[best]), "precision": float(precision[best]), "recall": float(recall[best]), "f": float(f[best])}


def at_recall(y_true, scores, target: float) -> dict | None:
    """The most precise threshold that still reaches the recall target, or None if none does."""
    precision, recall, thresholds = _curve(y_true, scores)
    ok = np.flatnonzero(recall >= target)
    if not len(ok):
        return None
    best = ok[np.argmax(precision[ok])]
    return {"threshold": float(thresholds[best]), "precision": float(precision[best]), "recall": float(recall[best])}


def at_precision(y_true, scores, target: float) -> dict | None:
    """The threshold with the most recall that still reaches the precision target, or None if none does."""
    precision, recall, thresholds = _curve(y_true, scores)
    ok = np.flatnonzero(precision >= target)
    if not len(ok):
        return None
    best = ok[np.argmax(recall[ok])]
    return {"threshold": float(thresholds[best]), "precision": float(precision[best]), "recall": float(recall[best])}


# ---- several classes ---------------------------------------------------------------------------------------------
def multiclass(y_true: Sequence, y_pred: Sequence, labels: Sequence) -> dict:
    """Per-class precision, recall, F1 and support, macro F1 over the classes that occur, and the confusion matrix."""
    p, r, f, support = skm.precision_recall_fscore_support(y_true, y_pred, labels=list(labels), zero_division=0)
    per_class = {lab: {"precision": float(p[i]), "recall": float(r[i]), "f1": float(f[i]), "support": int(support[i])} for i, lab in enumerate(labels)}
    present = [i for i in range(len(labels)) if support[i] > 0]
    return {"per_class": per_class, "macro_f1": float(np.mean([f[i] for i in present])) if present else 0.0,
            "accuracy": float(np.mean(np.asarray(y_true) == np.asarray(y_pred))),
            "labels": list(labels), "confusion": skm.confusion_matrix(y_true, y_pred, labels=list(labels)).tolist()}


def one_vs_rest(y_true: Sequence, scores: dict[str, Sequence[float]]) -> dict:
    """ROC-AUC and PR-AUC for each class against the rest, from one score per class, and their macro means."""
    y = np.asarray(y_true)
    per_class = {}
    for label, s in scores.items():
        positive = y == label
        if positive.any() and not positive.all():
            per_class[label] = {"roc_auc": roc_auc(positive, s), "pr_auc": pr_auc(positive, s)}
    return {"per_class": per_class, "macro_roc_auc": float(np.mean([v["roc_auc"] for v in per_class.values()])),
            "macro_pr_auc": float(np.mean([v["pr_auc"] for v in per_class.values()]))}


# ---- probabilities ------------------------------------------------------------------------------------------------
def brier(y_true, p) -> float:
    return float(np.mean((np.asarray(p, float) - np.asarray(y_true, float)) ** 2))


def reliability(y_true, p, bins: int = 10) -> list[dict]:
    """Equal-width bins on 0..1: how many, the mean predicted probability and the share that really happened."""
    y, p = np.asarray(y_true, float), np.asarray(p, float)
    index = np.minimum((p * bins).astype(int), bins - 1)
    return [{"low": b / bins, "high": (b + 1) / bins, "n": int((index == b).sum()), "mean_p": float(p[index == b].mean()), "observed": float(y[index == b].mean())}
            for b in range(bins) if (index == b).any()]


def ece(y_true, p, bins: int = 10) -> float:
    """Expected calibration error: the bin-weighted gap between predicted probability and what happened."""
    rows = reliability(y_true, p, bins)
    total = sum(r["n"] for r in rows)
    return float(sum(r["n"] / total * abs(r["observed"] - r["mean_p"]) for r in rows))


# ---- ranking ----------------------------------------------------------------------------------------------------------
def pairwise_accuracy(score_a, score_b, a_preferred) -> float:
    """Share of pairs where the higher score is the preferred one (a tie counts half). Equal to AUC over pairs."""
    a, b, wins = np.asarray(score_a, float), np.asarray(score_b, float), np.asarray(a_preferred, bool)
    return float(np.where(a == b, 0.5, ((a > b) == wins).astype(float)).mean())


def kendall_tau_b(a, b) -> float:
    return float(stats.kendalltau(a, b, variant="b").statistic)


def spearman(a, b) -> float:
    return float(stats.spearmanr(a, b).statistic)


def ndcg_at_k(relevance, scores, k: int = 10) -> float:
    """NDCG of ranking items by `scores` when their true graded usefulness is `relevance` (non-negative)."""
    return float(skm.ndcg_score([np.asarray(relevance, float)], [np.asarray(scores, float)], k=k))


# ---- clusters (tickets) -------------------------------------------------------------------------------------------
def _contingency(true, pred):
    true, pred = list(true), list(pred)
    return Counter(zip(true, pred)), Counter(true), Counter(pred), len(true)


def cluster_pairs(true, pred) -> dict:
    """Pairwise precision, recall, F1: of the pairs we put together how many belong together, and the reverse.
    With no pairs on one side the ratio is vacuously 1."""
    cell, true_size, pred_size, _ = _contingency(true, pred)
    pairs = lambda m: m * (m - 1) / 2
    both = sum(pairs(m) for m in cell.values())
    in_pred, in_true = sum(pairs(m) for m in pred_size.values()), sum(pairs(m) for m in true_size.values())
    precision, recall = (both / in_pred if in_pred else 1.0), (both / in_true if in_true else 1.0)
    return {"precision": precision, "recall": recall, "f1": f_beta(precision, recall)}


def bcubed(true, pred) -> dict:
    """B-cubed precision, recall, F1: the pairwise idea per item, so big clusters do not drown small ones."""
    cell, true_size, pred_size, n = _contingency(true, pred)
    precision = sum(m * m / pred_size[j] for (_, j), m in cell.items()) / n
    recall = sum(m * m / true_size[i] for (i, _), m in cell.items()) / n
    return {"precision": precision, "recall": recall, "f1": f_beta(precision, recall)}


def ari(true, pred) -> float:
    return float(skm.adjusted_rand_score(list(true), list(pred)))


# ---- how sure are we of a number ---------------------------------------------------------------------------------------
class CI(NamedTuple):
    point: float
    lo: float
    hi: float

    def as_dict(self) -> dict:
        return {"point": self.point, "lo": self.lo, "hi": self.hi}


def bootstrap_ci(metric: Callable[..., float], *arrays, n: int = 1000, seed: int = 0, alpha: float = 0.05) -> CI:
    """Percentile bootstrap interval for metric(*arrays), resampling rows together. A resample the metric cannot
    score (for example one class only, for AUC) is skipped."""
    arrays = [np.asarray(a) for a in arrays]
    size = len(arrays[0])
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(n):
        index = rng.integers(0, size, size)
        try:
            value = metric(*[a[index] for a in arrays])
        except ValueError:
            continue
        if np.isfinite(value):
            values.append(value)
    if len(values) < n // 2:
        raise ValueError("the metric is undefined on most resamples")
    lo, hi = np.percentile(values, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return CI(float(metric(*arrays)), float(lo), float(hi))


def paired_bootstrap_diff(metric: Callable[..., float], y, scores_a, scores_b, n: int = 1000, seed: int = 0, alpha: float = 0.05) -> CI:
    """Interval for metric(y, a) - metric(y, b) on the same resamples. If it excludes 0, the difference is real."""
    y, a, b = np.asarray(y), np.asarray(scores_a), np.asarray(scores_b)
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n):
        index = rng.integers(0, len(y), len(y))
        try:
            diffs.append(metric(y[index], a[index]) - metric(y[index], b[index]))
        except ValueError:
            continue
    if len(diffs) < n // 2:
        raise ValueError("the metric is undefined on most resamples")
    lo, hi = np.percentile(diffs, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return CI(float(metric(y, a) - metric(y, b)), float(lo), float(hi))
