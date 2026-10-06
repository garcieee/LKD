"""The configuration REPORT.md recommends, looked at once on the test split.

The final run found the radius that costs least on validation (z for the accuracy-aware rule) and the validation
precision by reported accuracy for the shipped z. This module asks what the two changes do together: the same pairs,
regenerated from the final seeds (the simulation is deterministic), the rule with that z, the auto-merge cutoff found on
VALIDATION for that rule, and only then the test split. Run after the final run:
    python -m models.tickets.eval.matching.synthetic.recommended
"""
import argparse
import json
from pathlib import Path

import numpy as np

from models.tickets.eval.common import results
from models.tickets.eval.matching.synthetic import evaluate as ev, simulator as sim


def with_z(P: dict, z: float | None) -> dict:
    """The pairs with match_ratio replaced by distance / radius at this z, so every function that reads the shipped rule
    (precision_by_bin, policy_table) reads this rule instead. z=None keeps the shipped rule."""
    return P if z is None else {**P, "ratio": P["d"] / ev.radius(P, z)}


def trade_off(P: dict) -> list[dict]:
    """Auto-merge precision and recall at each cutoff (validation, point estimates), to choose another precision floor."""
    y, merged = P["y"], P["ratio"] <= 1.0
    rows = []
    for edge in (*ev.CUT_EDGES, None):
        auto = merged & (P["acc_new"] <= (np.inf if edge is None else edge))
        rows.append({"cutoff_m": edge, "precision": ev.share(y & auto, auto), "recall": ev.share(y & auto, y)})
    return rows


def run(z: float | None = None, scale: float = 1.0, workers: int | None = None, folder: Path | None = None) -> dict:
    folder = Path(folder) if folder else results.RESULTS
    if z is None:
        cost = json.loads((results.RESULTS / "matching_synthetic_cost.json").read_text())
        z = float(cost["chosen"]["all"]["3"]["z"].split()[1])  # the cheapest accuracy-aware z at 3:1 on validation, pooled over all cells
    specs = {k: (sim.Config(profile=k[1], density=k[0]), max(1, round(ev.patches(k[0]) * scale))) for k in ev.KEYS}
    cells = ev.gather(specs, ev.SEEDS["final"], {}, (), workers)  # pairs only: the final data again
    out = {"z": z, "shipped_z": ev.s.MATCH_Z, "scopes": {}}
    scopes = {f"density {d}": [(d, p) for p in sim.PROFILES] for d in ev.DENSITIES} | {"all densities": ev.KEYS}
    for scope, keys in scopes.items():
        val, test = (ev.join([ev.pairs_of(cells[k], name) for k in keys]) for name in ("val", "test"))
        entry = {}
        for label, rule_z in (("shipped_z", None), ("recommended_z", z)):
            v, t = with_z(val, rule_z), with_z(test, rule_z)
            bins = ev.precision_by_bin(v, "acc_new", with_ci=True)
            cutoff = ev.cutoff_edge(bins)
            entry[label] = {"validation_bins": bins, "cutoff_m": cutoff, "validation_trade_off": trade_off(v), "test_policy": ev.policy_table(t, cutoff)}
        out["scopes"][scope] = entry
    results.write_result("matching_synthetic_recommended", ev.rounded(out), folder)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--z", type=float, default=None, help="default: the cheapest z at 3:1 from matching_synthetic_cost.json")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--folder", default=None, help="default eval/results/")
    args = ap.parse_args()
    run(args.z, 1.0, args.workers, args.folder)
