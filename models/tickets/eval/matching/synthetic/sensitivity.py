"""How far can what the simulation assumes move before the shipped rule breaks?

The shipped rule has nothing tuned, so every district of every patch is fair game (no train or test here); the seeds
are the sweep's own, apart from the development and the final run. One setting changes at a time around the base
world (60 hazards per km2, geometric reports); the same seeds are used at every point, so neighbouring points differ
only in the setting. Per profile and point: pair-level precision, recall and F0.5 of geo.match_ratio <= 1, the F0.5 a
re-tuned z or the best fixed radius would reach on the same pairs (in sample: ceilings, not results), and from the online replay the B-cubed
F1 and the cost of a wrong merge at 3 wrong splits per 1,000 reports. Run:  python -m models.tickets.eval.matching.synthetic.sensitivity
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from models.tickets.eval.common import metrics as m, results
from models.tickets.eval.matching.synthetic import evaluate as ev, figures, simulator as sim

DENSITY, PATCHES, SEED, BOOT = 60, 30, 7000, 300
BASE = sim.Config(density=DENSITY)
SWEEPS = {  # name: (what it moves, values, how a value changes the config)
    "accuracy_scale": ("the phone reports this many times its true accuracy (1 = right on average, below 1 = over-confident)",
                       [0.5, 0.7, 1.0, 1.4, 2.0, 3.0], lambda c, v: replace(c, accuracy_scale=v)),
    "accuracy_spread": ("sigma of the lognormal noise on the reported accuracy", [0.0, 0.35, 0.7, 1.0], lambda c, v: replace(c, accuracy_spread=v)),
    "standoff_max_m": ("the reporter stands 1 to this many metres from the hazard (the matcher assumes about 4 m)",
                       [3, 5, 10, 15, 20, 30], lambda c, v: replace(c, standoff_m=(1.0, float(v)))),
    "clustering": ("share of hazards that sit in clusters of this mean size (0 = uniform hazards)",
                   [(0.0, 3.0), (0.25, 3.0), (0.5, 3.0), (0.8, 6.0)], lambda c, v: replace(c, cluster_share=v[0], cluster_mean=v[1])),
    "popularity": ("reports per hazard", ["geometric, mean 1.6", "heavy tail, mean 3"], lambda c, v: replace(c, heavy_tail=v.startswith("heavy"))),
    "uniform_density": ("hazards with no clustering at all (Poisson), at this many per km2: the main run's densities without the bunching",
                        [20, 60, 150], lambda c, v: replace(c, density=v, cluster_share=0.0)),
}
GRID = {"accuracy_scale": [0.5, 0.7, 1.0, 1.4, 2.0, 3.0], "standoff_max_m": [3, 5, 10, 20, 30]}  # two settings at once, city only


def row(cell: dict) -> dict:
    """One profile at one point: everything on all splits pooled."""
    P, y = cell["pairs"], cell["pairs"]["y"]
    merged = P["ratio"] <= 1.0
    pair_units, units = ev.Units(P["unit"]), ev.Units(cell["unit"])
    f05_by_z = [m.prf(y, P["d"] <= ev.radius(P, z), 0.5)["f"] for z in ev.Z_GRID]
    f05_by_radius = [m.prf(y, P["d"] <= r, 0.5)["f"] for r in ev.FIXED_GRID]
    return {"pairs": len(y), "positives": int(y.sum()),
            "precision": ev.ci(pair_units, ev.prec, y, merged, n=BOOT), "recall": ev.ci(pair_units, ev.rec, y, merged, n=BOOT),
            "f05": ev.ci(pair_units, ev.f05, y, merged, n=BOOT), "best_z_in_sample": ev.Z_GRID[int(np.argmax(f05_by_z))], "f05_best_z_in_sample": max(f05_by_z),
            "best_fixed_m_in_sample": ev.FIXED_GRID[int(np.argmax(f05_by_radius))], "f05_best_fixed_in_sample": max(f05_by_radius),
            "bcubed_f1": ev.ci_clusters(units, lambda t, p: m.bcubed(t, p)["f1"], cell["hazard"], cell["tickets"]["shipped"], n=BOOT),
            "cost_3_to_1": ev.ci_sums(units, ev.count_rows(cell["events"]["shipped"]), ev.cost_f(3), n=BOOT)}


def run(patches: int = PATCHES, workers: int | None = None, folder: Path | None = None) -> dict:
    folder = Path(folder) if folder else results.RESULTS
    specs = {}
    for name, (_, values, make) in SWEEPS.items():
        for v in values:
            for p in sim.PROFILES:
                cfg = replace(make(BASE, v), profile=p)
                specs[(name, str(v), p)] = (cfg, max(1, round(patches * DENSITY / cfg.density)))  # about the same number of hazards at every density
    for a in GRID["accuracy_scale"]:
        for b in GRID["standoff_max_m"]:
            specs[("grid", f"{a}|{b}", "city")] = (replace(BASE, profile="city", accuracy_scale=a, standoff_m=(1.0, float(b))), patches)
    cells = ev.gather(specs, SEED, {"shipped": {}}, ev.SPLITS, workers)
    keys = list(cells)
    if workers == 1:
        rows = [row(cells[k]) for k in keys]
    else:
        with ProcessPoolExecutor(workers) as pool:
            rows = list(pool.map(row, [cells[k] for k in keys]))
    done = dict(zip(keys, rows))
    out = {"config": {"density": DENSITY, "patches_at_60_per_km2": patches, "seed_base": SEED, "bootstrap_resamples": BOOT, "base": asdict(BASE)}, "sweeps": {}, "grid": {}}
    for name, (meaning, values, _) in SWEEPS.items():
        cutoffs = {v: ev.cutoff_edge(ev.precision_by_bin(ev.join([cells[(name, str(v), p)]["pairs"] for p in sim.PROFILES]))) for v in values}  # all profiles pooled
        out["sweeps"][name] = {"meaning": meaning, "points": [{"value": v, "cutoff_m": cutoffs[v], **{p: done[(name, str(v), p)] for p in sim.PROFILES}} for v in values]}
    for a in GRID["accuracy_scale"]:
        for b in GRID["standoff_max_m"]:
            out["grid"][f"accuracy_scale={a}|standoff_max_m={b}"] = done[("grid", f"{a}|{b}", "city")]
    results.write_result("matching_synthetic_sensitivity", ev.rounded(out), folder)
    figures.sensitivity(folder / "matching_synthetic_sensitivity.png", out["sweeps"])
    figures.grid(folder / "matching_synthetic_sensitivity_grid.png", out["grid"], GRID["accuracy_scale"], GRID["standoff_max_m"])
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--patches", type=int, default=PATCHES)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--folder", default=None, help="default eval/results/")
    args = ap.parse_args()
    run(args.patches, args.workers, args.folder)
