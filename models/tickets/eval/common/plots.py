"""Small, consistent figures for the evaluation write-ups. Saved as PNG; matplotlib runs without a screen."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn import metrics as skm

INK, FAINT = "#59534e", "#b8b3ac"


def _finish(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def save_curves(path, curves: dict[str, tuple], title: str = "") -> None:
    """Precision-recall and ROC curves side by side. curves: label -> (y_true, scores)."""
    fig, (pr, roc) = plt.subplots(1, 2, figsize=(9, 3.8))
    for label, (y, s) in curves.items():
        precision, recall, _ = skm.precision_recall_curve(y, s)
        fpr, tpr, _ = skm.roc_curve(y, s)
        pr.plot(recall, precision, label=f"{label} (AP {skm.average_precision_score(y, s):.2f})")
        roc.plot(fpr, tpr, label=f"{label} (AUC {skm.roc_auc_score(y, s):.2f})")
    prevalence = float(np.mean(next(iter(curves.values()))[0]))
    pr.axhline(prevalence, color=FAINT, ls="--", lw=1)
    roc.plot([0, 1], [0, 1], color=FAINT, ls="--", lw=1)
    pr.set(xlabel="recall", ylabel="precision", title="Precision-recall", ylim=(0, 1.02))
    roc.set(xlabel="false positive rate", ylabel="true positive rate", title="ROC")
    for ax in (pr, roc):
        ax.legend(fontsize=7)
    fig.suptitle(title, color=INK)
    _finish(fig, path)


def save_reliability(path, curves: dict[str, tuple], title: str = "", bins: int = 10) -> None:
    """Predicted probability against what happened. curves: label -> (y_true, probabilities)."""
    fig, ax = plt.subplots(figsize=(4.6, 4.2))
    ax.plot([0, 1], [0, 1], color=FAINT, ls="--", lw=1)
    for label, (y, p) in curves.items():
        observed, predicted = _bins(np.asarray(y, float), np.asarray(p, float), bins)
        ax.plot(predicted, observed, marker="o", label=label)
    ax.set(xlabel="predicted probability", ylabel="observed share", title=title, xlim=(0, 1), ylim=(0, 1))
    ax.legend(fontsize=7)
    _finish(fig, path)


def _bins(y, p, bins):
    index = np.minimum((p * bins).astype(int), bins - 1)
    keep = [b for b in range(bins) if (index == b).any()]
    return [y[index == b].mean() for b in keep], [p[index == b].mean() for b in keep]


def save_bars(path, labels: list[str], points: list[float], lows: list[float], highs: list[float], title: str = "",
              ylabel: str = "", target: float | None = None) -> None:
    """One bar per label with its confidence interval, and an optional target line."""
    fig, ax = plt.subplots(figsize=(max(4.2, 0.9 * len(labels) + 1.5), 3.6))
    x = np.arange(len(labels))
    errors = [np.asarray(points) - np.asarray(lows), np.asarray(highs) - np.asarray(points)]
    ax.bar(x, points, yerr=errors, capsize=4, color="#212e4a", alpha=0.85)
    if target is not None:
        ax.axhline(target, color="#a63722", ls="--", lw=1.2, label=f"target {target:g}")
        ax.legend(fontsize=7)
    ax.set(xticks=x, xticklabels=labels, ylabel=ylabel, title=title, ylim=(0, 1.02))
    ax.tick_params(axis="x", labelrotation=20, labelsize=8)
    _finish(fig, path)
