"""Do the 95% intervals of this evaluation cover the truth 95% of the time?

The shipped rule has nothing tuned, so its pair precision and recall in one huge pool of independent patches (city, 60
hazards per km2) is as close to the truth as the simulation gets. Then many independent samples the size of one test
split are drawn, each gets a district-resampled interval (what every number in REPORT.md uses) and a pair-by-pair
interval (what resampling the rows of the pair table would give), and we count how often each holds the truth.
Own seeds, apart from the development, final and sensitivity runs. Run:
    python -m models.tickets.eval.matching.synthetic.interval_check
"""
import argparse
from dataclasses import asdict
from pathlib import Path

import numpy as np

from models.tickets.eval.common import metrics as m, results
from models.tickets.eval.matching.synthetic import evaluate as ev, simulator as sim

SEED_TRUTH, SEED_SAMPLES = 31000, 32000


def run(samples: int = 60, patches: int = 20, truth_patches: int = 400, n: int = 300, folder: Path | None = None) -> dict:
    cfg = sim.Config(profile="city", density=60)
    pairs = lambda base, count: ev.gather({"cell": (cfg, count)}, base, {}, (), workers=1)["cell"]["pairs"]
    big = pairs(SEED_TRUTH, truth_patches)
    truth = {k: fn(big["y"], big["ratio"] <= 1.0) for k, fn in (("precision", ev.prec), ("recall", ev.rec))}
    held = {k: {"district": 0, "pair": 0} for k in truth}
    width = {k: {"district": [], "pair": []} for k in truth}
    for b in range(samples):
        P = pairs(SEED_SAMPLES + b, patches)
        P = ev.take(P, P["split"] == ev.SPLITS.index("test"))  # the size of one test split
        y, merged, units = P["y"], P["ratio"] <= 1.0, ev.Units(P["unit"])
        for k, fn in (("precision", ev.prec), ("recall", ev.rec)):
            for name, r in (("district", ev.ci(units, fn, y, merged, n=n)), ("pair", m.bootstrap_ci(fn, y, merged, n=n).as_dict())):
                held[k][name] += r["lo"] <= truth[k] <= r["hi"]
                width[k][name].append(r["hi"] - r["lo"])
    out = {"config": {"simulator": asdict(cfg), "samples": samples, "patches_per_sample": patches, "truth_patches": truth_patches, "bootstrap_resamples": n,
                      "districts_in_the_last_sample": len(units), "pairs_in_the_last_sample": len(y)},
           "truth": truth, "share_of_intervals_holding_the_truth": {k: {name: v / samples for name, v in h.items()} for k, h in held.items()},
           "mean_interval_width": {k: {name: float(np.mean(w)) for name, w in ws.items()} for k, ws in width.items()}}
    results.write_result("matching_synthetic_interval_check", ev.rounded(out), Path(folder) if folder else None)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--samples", type=int, default=60)
    ap.add_argument("--folder", default=None, help="default eval/results/")
    args = ap.parse_args()
    run(args.samples, folder=args.folder)
