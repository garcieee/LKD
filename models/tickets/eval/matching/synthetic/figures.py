"""The figures of REPORT.md, drawn from the result dicts (small PNGs, same look as eval/common/plots.py)."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from models.tickets.eval.common import plots

COLOR = {"open_sky": "#2b6f77", "city": "#212e4a", "canyon": "#a63722"}
NAME = {"open_sky": "open sky", "city": "city", "canyon": "canyon"}
PROFILES = tuple(COLOR)


def _save(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def curves(path, pairs_by_profile: dict, title: str) -> None:
    """Precision-recall and ROC of the shipped rule's score (minus match_ratio), one curve per GPS profile."""
    plots.save_curves(path, {NAME[p]: (P["y"], -P["ratio"]) for p, P in pairs_by_profile.items()}, title)


def variants(path, tables: dict, densities, order: list[str]) -> None:
    """F0.5 of every variant minus the shipped rule's, with the 95% interval. Rows of panels: tuned per cell (A), tuned once
    for all cells (B). Columns: GPS profile. Markers: the three densities, light to dark."""
    fig, axes = plt.subplots(2, 3, figsize=(11, 6.4), sharey=True, sharex=True)
    for r, protocol in enumerate(("A", "B")):
        for c, profile in enumerate(PROFILES):
            ax = axes[r, c]
            for i, name in enumerate(order):
                for j, d in enumerate(densities):
                    row = tables[protocol][f"{profile}@{d}"][name]["f05_vs_shipped"]
                    ax.errorbar(row["point"], i + (j - 1) * 0.24, xerr=[[row["point"] - row["lo"]], [row["hi"] - row["point"]]], fmt="o", ms=3,
                                lw=1.2, color=COLOR[profile], alpha=(0.35, 0.65, 1.0)[j], label=f"{d} per km2" if i == 0 and c == 0 and r == 0 else None)
            ax.axvline(0, color=plots.FAINT, lw=1)
            ax.set_title(f"{NAME[profile]}, " + ("tuned per cell" if protocol == "A" else "tuned once for all cells"), fontsize=9, color=plots.INK)
            ax.set_yticks(range(len(order)), order, fontsize=8)
            ax.invert_yaxis()
            if r == 1:
                ax.set_xlabel("F0.5 minus the shipped rule's (test split)", fontsize=8)
    axes[0, 0].legend(fontsize=7, loc="lower left", title="density", title_fontsize=7)
    _save(fig, path)


def cutoff(path, scopes: dict) -> None:
    """Validation precision of the shipped rule's merges by the new report's reported accuracy, with the 0.85 line."""
    fig, ax = plt.subplots(figsize=(6.6, 4.2))
    shades = {"density 20": 0.4, "density 60": 0.7, "density 150": 1.0}
    for scope, alpha in shades.items():
        rows = scopes[scope]["acc_new"]["validation_bins"]
        x = [i for i, b in enumerate(rows) if "precision_ci" in b]
        point = [rows[i]["precision_ci"]["point"] for i in x]
        low = [rows[i]["precision_ci"]["point"] - rows[i]["precision_ci"]["lo"] for i in x]
        high = [rows[i]["precision_ci"]["hi"] - rows[i]["precision_ci"]["point"] for i in x]
        ax.errorbar(np.array(x) + (alpha - 0.7) * 0.2, point, yerr=[low, high], marker="o", ms=4, lw=1.3, capsize=2, color=plots.INK, alpha=alpha,
                    label=f"{scope.split()[1]} hazards per km2: cutoff {scopes[scope]['acc_new']['cutoff_m']} m")
    ax.axhline(0.85, color="#a63722", ls="--", lw=1.2, label="precision 0.85")
    edges = [b["high_m"] for b in scopes["density 60"]["acc_new"]["validation_bins"]]
    ax.set_xticks(range(len(edges)), [f"up to {e}" if e else "above 40" for e in edges], fontsize=8)
    ax.set(xlabel="reported accuracy of the new report, m", ylabel="precision of the merges (validation)", ylim=(0.4, 1.0))
    ax.legend(fontsize=7)
    _save(fig, path)


def cost(path, validation: dict, ratios, shipped_z: float) -> None:
    """Validation cost per 1,000 reports of every radius rule, pooled over all cells. Top row: fixed radius, bottom row:
    the accuracy-aware rule with another z. The dashed line is the shipped rule; the ring is the cheapest rule."""
    fig, axes = plt.subplots(2, len(ratios), figsize=(10.5, 6), sharey="col")
    book = validation["all"]
    families = (("fixed", "fixed radius, m", lambda k: float(k.split()[1])), ("z ", "z of the accuracy-aware rule", lambda k: float(k.split()[1])))
    for c, ratio in enumerate(ratios):
        for r, (prefix, label, value) in enumerate(families):
            ax = axes[r, c]
            rules = sorted((k for k in book if k.startswith(prefix)), key=value)
            x, y = [value(k) for k in rules], [book[k][ratio] for k in rules]
            ax.plot(x, y, marker="o", ms=3, color=plots.INK)
            ax.plot(x[int(np.argmin(y))], min(y), "o", ms=11, mfc="none", mec="#a63722")
            ax.axhline(book["shipped"][ratio], color="#a63722", ls="--", lw=1, label=f"shipped (z={shipped_z})")
            ax.set(xlabel=label, title=f"a wrong merge costs {ratio} wrong split{'s' if ratio > 1 else ''}", ylabel="cost per 1,000 reports" if c == 0 else "")
            ax.title.set_fontsize(9)
            if c == 0 and r == 0:
                ax.legend(fontsize=7)
    _save(fig, path)


def sensitivity(path, sweeps: dict) -> None:
    """Recall and precision of the shipped rule against each setting the simulation fixes, per GPS profile."""
    names = ("accuracy_scale", "standoff_max_m", "clustering")
    fig, axes = plt.subplots(2, len(names), figsize=(11, 5.6), sharey="row")
    for c, name in enumerate(names):
        points = sweeps[name]["points"]
        x = np.arange(len(points))
        for r, metric in enumerate(("recall", "precision")):
            ax = axes[r, c]
            for profile in PROFILES:
                rows = [p[profile][metric] for p in points]
                ax.errorbar(x + (list(COLOR).index(profile) - 1) * 0.08, [q["point"] for q in rows], marker="o", ms=3, lw=1.2, color=COLOR[profile],
                            yerr=[[q["point"] - q["lo"] for q in rows], [q["hi"] - q["point"] for q in rows]], capsize=2, label=NAME[profile])
            ax.axhline(0.85, color=plots.FAINT, ls="--", lw=1)
            ax.set_xticks(x, [str(p["value"]) if name != "clustering" else f"{p['value'][0]:g}, {p['value'][1]:g}" for p in points], fontsize=8)
            ax.set(ylabel=metric if c == 0 else "", ylim=(0.3, 1.02),
                   xlabel={"accuracy_scale": "reported accuracy / true accuracy", "standoff_max_m": "stand-off up to, m",
                           "clustering": "share clustered, hazards per cluster"}[name] if r == 1 else "")
    axes[0, 0].legend(fontsize=7, loc="lower left")
    _save(fig, path)


def grid(path, cells: dict, scales, stands) -> None:
    """City profile: precision and recall of the shipped rule when the phone's accuracy and the stand-off are both off."""
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    for ax, metric in zip(axes, ("precision", "recall")):
        z = np.array([[cells[f"accuracy_scale={a}|standoff_max_m={b}"][metric]["point"] for b in stands] for a in scales])
        image = ax.imshow(z, vmin=0.4, vmax=1.0, cmap="Blues", origin="lower", aspect="auto")
        for i in range(len(scales)):
            for j in range(len(stands)):
                ax.text(j, i, f"{z[i, j]:.2f}", ha="center", va="center", fontsize=8, color="white" if z[i, j] > 0.75 else plots.INK)
        ax.set_xticks(range(len(stands)), [str(b) for b in stands])
        ax.set_yticks(range(len(scales)), [str(a) for a in scales])
        ax.set(xlabel="stand-off up to, m", ylabel="reported accuracy / true accuracy", title=f"{metric}, city", )
        ax.title.set_fontsize(9)
    _save(fig, path)


def zcurve(path, fits: dict, densities, shipped_z: float) -> None:
    """F0.5 of the accuracy-aware rule against z, on the validation districts, for every cell (tuning A) and for all cells
    together (tuning B, dashed). The optimum of each is ringed; the grey line is the shipped z."""
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.6), sharey=True)
    for ax, profile in zip(axes, PROFILES):
        for j, d in enumerate(densities):
            fit = fits["A"][f"{profile}@{d}"]["f05_curve"]
            ax.plot(fit["z"], fit["val"], color=COLOR[profile], alpha=(0.35, 0.65, 1.0)[j], lw=1.4, label=f"{d} per km2")
            best = int(np.argmax(fit["val"]))
            ax.plot(fit["z"][best], fit["val"][best], "o", ms=8, mfc="none", mec=COLOR[profile], alpha=(0.35, 0.65, 1.0)[j])
        pooled = fits["B"]["f05_curve"]
        ax.plot(pooled["z"], pooled["val"], color=plots.INK, ls="--", lw=1.2, label="all cells together")
        ax.axvline(shipped_z, color=plots.FAINT, lw=1.5)
        ax.set(xlabel="z", title=NAME[profile], ylabel="F0.5 on validation" if profile == "open_sky" else "")
        ax.title.set_fontsize(9)
        ax.legend(fontsize=7, loc="lower left")
    _save(fig, path)
