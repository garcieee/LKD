"""Markdown tables for REPORT.md, straight from the result files, so no number is typed by hand.

Run:  python -m models.tickets.eval.matching.synthetic.report_tables [folder]   (default eval/results/)
"""
import json
import sys
from pathlib import Path

from models.tickets.eval.common import results

PROFILES = ("open_sky", "city", "canyon")
DENSITIES = (20, 60, 150)
NAME = {"open_sky": "open sky", "city": "city", "canyon": "canyon", "mixed": "all three together"}


def load(folder: Path, name: str) -> dict:
    return json.loads((folder / f"matching_synthetic_{name}.json").read_text())


def ci(r, digits=3, signed=False) -> str:
    if r is None or r.get("point") is None:
        return "n/a"
    f = f"{{:+.{digits}f}}" if signed else f"{{:.{digits}f}}"
    return f"{f.format(r['point'])} [{f.format(r['lo'])}, {f.format(r['hi'])}]"


def table(rows, columns) -> str:
    return results.md_table(rows, columns)


def sizes(main) -> str:
    rows = []
    for d in DENSITIES:
        for p in PROFILES:
            c = main["config"]["sizes"][f"{p}@{d}"]
            rows.append({"density": d, "profile": NAME[p], "patches": main["config"]["patches"][f"{p}@{d}"],
                         **{f"{s} reports": c[s]["reports"] for s in ("train", "val", "test")},
                         **{f"{s} pairs (positive)": f"{c[s]['pairs']} ({c[s]['positive_pairs']})" for s in ("train", "val", "test")}, "test districts": c["test"]["districts"]})
    return table(rows, ["density", "profile", "patches", "train reports", "val reports", "test reports", "train pairs (positive)", "val pairs (positive)",
                        "test pairs (positive)", "test districts"])


def pairs(main) -> str:
    rows = []
    for d in DENSITIES:
        for p in (*PROFILES, "mixed"):
            t = main["pairs"][f"{p}@{d}"]
            rows.append({"density": d, "profile": NAME[p], "pairs": t["pairs"], "positive": f"{t['prevalence']:.2f}", "precision": ci(t["precision"]),
                         "recall": ci(t["recall"]), "F1": ci(t["f1"]), "F0.5": ci(t["f05"]), "PR-AUC": ci(t["pr_auc"]), "ROC-AUC": ci(t["roc_auc"])})
    return table(rows, ["density", "profile", "pairs", "positive", "precision", "recall", "F1", "F0.5", "PR-AUC", "ROC-AUC"])


def widths(main) -> str:
    rows = []
    for cell, t in main["pairs"].items():
        w = t["interval_width_district_vs_pair"]
        rows.append({"cell": cell, "precision: district / pair": f"{w['precision'][0]:.3f} / {w['precision'][1]:.3f}",
                     "recall: district / pair": f"{w['recall'][0]:.3f} / {w['recall'][1]:.3f}"})
    return table(rows, ["cell", "precision: district / pair", "recall: district / pair"])


def replay(main) -> str:
    rows = []
    for d in DENSITIES:
        for p in PROFILES:
            t = main["replay"][f"{p}@{d}"]
            rows.append({"density": d, "profile": NAME[p], "reports": t["reports"], "tickets / hazards": f"{t['tickets']} / {t['hazards']}",
                         "B-cubed P": ci(t["bcubed_precision"]), "B-cubed R": ci(t["bcubed_recall"]), "B-cubed F1": ci(t["bcubed_f1"]),
                         "pairwise F1": ci(t["pairwise_f1"]), "ARI": ci(t["ari"])})
    return table(rows, ["density", "profile", "reports", "tickets / hazards", "B-cubed P", "B-cubed R", "B-cubed F1", "pairwise F1", "ARI"])


def targets(main) -> str:
    rows = []
    for t in main["targets"]:
        rows.append({"profile": NAME[t["profile"]], "metric": t["metric"].replace("bcubed_f1", "B-cubed F1").replace("pr_auc", "PR-AUC"), "density": t["density"],
                     "target": f">= {t['minimum']:.2f}", "value": ci(t["value"]), "result": t["status"].upper(),
                     "interval": ("clear of the target" if t["interval_clear_of_target"] else "touches the target")})
    return table(rows, ["profile", "metric", "density", "target", "value", "result", "interval"])


def variants(var, protocol, density) -> str:
    out = []
    for p in (*PROFILES, "mixed"):
        t = var["variants"][protocol].get(f"{p}@{density}")
        if not t:
            continue
        rows = [{"rule": n, "precision": ci(r["precision"]), "recall": ci(r["recall"]), "F0.5": ci(r["f05"]), "PR-AUC": ci(r["pr_auc"]),
                 "F0.5 minus shipped": ci(r.get("f05_vs_shipped"), 3, True) if n != "shipped" else "-",
                 "F0.5 minus best fixed": f"{ci(r['f05_vs_best_fixed'], 3, True)} (vs {r['best_fixed_m']} m)" if "f05_vs_best_fixed" in r else "-"} for n, r in t.items()]
        out.append(f"**{NAME[p]}, {density} per km2**\n\n" + table(rows, ["rule", "precision", "recall", "F0.5", "PR-AUC", "F0.5 minus shipped", "F0.5 minus best fixed"]))
    return "\n\n".join(out)


def variant_tally(var) -> str:
    """For each rule and tuning protocol: in how many cells it beats the shipped rule, loses to it, or the interval holds zero."""
    names = [n for n in next(iter(var["variants"]["A"].values())) if n != "shipped"]
    rows = []
    for n in names:
        row = {"rule": n}
        for protocol, label in (("A", "tuned per cell"), ("B", "tuned once"), ("C", "profile shift")):
            cells = var["variants"][protocol]
            diffs = [c[n]["f05_vs_shipped"] for c in cells.values()]
            row[f"{label} ({len(cells)} cells)"] = f"{sum(d['lo'] > 0 for d in diffs)} better / {sum(d['hi'] < 0 for d in diffs)} worse / {sum(d['lo'] <= 0 <= d['hi'] for d in diffs)} unclear"
        rows.append(row)
    return table(rows, list(rows[0]))


def gain(var, protocol, density) -> str:
    """F0.5 minus the shipped rule's, for one density: rules by GPS profile (and all three together where there is a mixed cell)."""
    cells = [p for p in (*PROFILES, "mixed") if f"{p}@{density}" in var["variants"][protocol]]
    t = {p: var["variants"][protocol][f"{p}@{density}"] for p in cells}
    rows = [{"rule": n, **{NAME[p]: ci(t[p][n]["f05_vs_shipped"], 3, True) for p in cells}} for n in t[cells[0]] if n != "shipped"]
    for n in ("shipped", "z tuned"):
        rows.append({"rule": f"{n}, minus best fixed ({t[cells[0]][n]['best_fixed_m']} m)", **{NAME[p]: ci(t[p][n]["f05_vs_best_fixed"], 3, True) for p in cells}})
    return f"**{density} hazards per km2**\n\n" + table(rows, ["rule", *[NAME[p] for p in cells]])


def recommended(rec) -> str:
    rows = []
    for scope, e in rec["scopes"].items():
        for label, name in (("shipped_z", f"shipped z {rec['shipped_z']}"), ("recommended_z", f"z {rec['z']}")):
            x, pol = e[label], e[label]["test_policy"]
            rows.append({"scope": scope, "rule": name, "cutoff": "none" if x["cutoff_m"] is None else f"{x['cutoff_m']} m",
                         "auto-merge precision": ci(pol["auto_merge_precision"], 3), "auto-merge recall": ci(pol["auto_merge_recall"], 3),
                         "precision with no cutoff": ci(pol["shipped_precision_without_cutoff"], 3), "recall with no cutoff": ci(pol["shipped_recall_without_cutoff"], 3),
                         "true pairs left to suggestions": ci(pol["true_pairs_left_to_suggestions"], 2)})
    return table(rows, ["scope", "rule", "cutoff", "auto-merge precision", "auto-merge recall", "precision with no cutoff", "recall with no cutoff", "true pairs left to suggestions"])


def trade_off(rec) -> str:
    e = rec["scopes"]["all densities"]
    rows = []
    for a, b in zip(e["shipped_z"]["validation_trade_off"], e["recommended_z"]["validation_trade_off"]):
        rows.append({"auto-merge only up to": "no cutoff" if a["cutoff_m"] is None else f"{a['cutoff_m']} m",
                     f"shipped z: precision / recall": f"{a['precision']:.3f} / {a['recall']:.3f}", f"z {rec['z']}: precision / recall": f"{b['precision']:.3f} / {b['recall']:.3f}"})
    return table(rows, list(rows[0]))


def interval_check(ic) -> str:
    rows = [{"number": k, "truth": f"{ic['truth'][k]:.3f}", "district intervals hold it": f"{ic['share_of_intervals_holding_the_truth'][k]['district']:.2f}",
             "pair intervals hold it": f"{ic['share_of_intervals_holding_the_truth'][k]['pair']:.2f}",
             "mean width, district / pair": f"{ic['mean_interval_width'][k]['district']:.3f} / {ic['mean_interval_width'][k]['pair']:.3f}"} for k in ic["truth"]]
    return table(rows, list(rows[0]))


def fits(var) -> str:
    rows = [{"tuning": f"A {c}", "z (validation pick)": f"{f['z']:.1f}", "z (train optimum)": f"{f['z_train']:.1f}", "logistic threshold": f"{f['lr_threshold']:.2f}"}
            for c, f in var["fits"]["A"].items()]
    rows += [{"tuning": label, "z (validation pick)": f"{var['fits'][k]['z']:.1f}", "z (train optimum)": f"{var['fits'][k]['z_train']:.1f}",
              "logistic threshold": f"{var['fits'][k]['lr_threshold']:.2f}"} for k, label in (("B", "B: all cells"), ("C", "C: open sky and city"))]
    return table(rows, ["tuning", "z (validation pick)", "z (train optimum)", "logistic threshold"])


def cutoff(cut, key="acc_new") -> str:
    out = []
    for scope, e in cut["scopes"].items():
        bins = e[key]["validation_bins"]
        rows = [{"reported accuracy, m": f"{b['low_m']} to {b['high_m']}" if b["high_m"] else f"above {b['low_m']}", "merges": b["merges"],
                 "precision": ci(b.get("precision_ci"), 2) if b.get("precision_ci") else "n/a"} for b in bins]
        cutoff_m = e[key]["cutoff_m"]
        out.append(f"**{scope}: cutoff {'none needed' if cutoff_m is None else str(cutoff_m) + ' m'}**\n\n" + table(rows, ["reported accuracy, m", "merges", "precision"]))
    return "\n\n".join(out)


def cutoff_tuned(cut) -> str:
    rows = []
    for scope, e in cut["scopes"].items():
        for label, bins, cutoff_m in (("shipped z", e["acc_new"]["validation_bins"], e["acc_new"]["cutoff_m"]),
                                      (f"tuned z {e['tuned_z']['z']:.1f}", e["tuned_z"]["validation_bins"], e["tuned_z"]["cutoff_m"])):
            rows.append({"scope": scope, "rule": label, "cutoff": "none needed" if cutoff_m is None else f"{cutoff_m} m",
                         **{(f"to {b['high_m']} m" if b["high_m"] else "above 40 m"): (f"{b['precision']:.2f}" if b["precision"] is not None else "n/a") for b in bins}})
    return table(rows, list(rows[0]))


def policy(cut, key="acc_new") -> str:
    rows = []
    for scope, e in cut["scopes"].items():
        p, c = e[key]["policy"], e[key]["cutoff_m"]
        rows.append({"scope": scope, "cutoff": "none" if c is None else f"{c} m", "auto-merge precision": ci(p["auto_merge_precision"], 2),
                     "shipped precision": ci(p["shipped_precision_without_cutoff"], 2), "auto-merge recall": ci(p["auto_merge_recall"], 2),
                     "shipped recall": ci(p["shipped_recall_without_cutoff"], 2), "true pairs left to suggestions": ci(p["true_pairs_left_to_suggestions"], 2),
                     "withheld merges that were right": ci(p["withheld_merges_that_were_right"], 2)})
    return table(rows, ["scope", "cutoff", "auto-merge precision", "shipped precision", "auto-merge recall", "shipped recall", "true pairs left to suggestions",
                        "withheld merges that were right"])


def cost_choice(cost) -> str:
    rows = []
    for scope, by_ratio in cost["chosen"].items():
        for r, pick in by_ratio.items():
            val = cost["validation"][scope]
            rows.append({"scope": scope, "wrong merge costs": f"{r} splits", "cheapest rule": pick["any"], "cheapest fixed radius": pick["fixed"], "cheapest z": pick["z"],
                         "shipped (validation)": f"{val['shipped'][r]:.0f}", "cheapest (validation)": f"{val[pick['any']][r]:.0f}"})
    return table(rows, ["scope", "wrong merge costs", "cheapest rule", "cheapest fixed radius", "cheapest z", "shipped (validation)", "cheapest (validation)"])


def cost_report(cost, scope="all") -> str:
    t = {n: r for n, r in cost["report"][scope].items() if n != "adaptive_saving_vs_fixed"}
    rows = [{"rule": n, "wrong merges": ci(r["merges_per_1000"], 1), "wrong splits": ci(r["splits_per_1000"], 1), "cost 1:1": ci(r["cost_1_to_1"], 0),
             "cost 3:1": ci(r["cost_3_to_1"], 0), "cost 5:1": ci(r["cost_5_to_1"], 0),
             "saving at 3:1": ci(r.get("saving_vs_shipped_3_to_1"), 0, True) if "saving_vs_shipped_3_to_1" in r else "-"} for n, r in t.items()]
    adaptive = cost["report"][scope]["adaptive_saving_vs_fixed"]
    note = "Cheapest accuracy-aware z against cheapest fixed radius (both picked on validation), cost saved per 1,000 reports: " + "; ".join(
        f"{r}:1 {ci(v, 0, True)}" for r, v in adaptive.items())
    return f"**{scope}**\n\n" + table(rows, ["rule", "wrong merges", "wrong splits", "cost 1:1", "cost 3:1", "cost 5:1", "saving at 3:1"]) + "\n\n" + note


def cost_cells(cost) -> str:
    rows = []
    for d in DENSITIES:
        for p in PROFILES:
            t = cost["per_cell"][f"{p}@{d}"]
            rows.append({"density": d, "profile": NAME[p], "floor": f"{t['floor']['cost_3_to_1']['point']:.0f}", "shipped": ci(t["shipped"]["cost_3_to_1"], 0),
                         **{k: f"{t[k]['cost_3_to_1']['point']:.0f}" for k in t if k.startswith("fixed") or k.startswith("z ")}})
    cols = ["density", "profile", "floor", "shipped"] + [k for k in rows[0] if k not in ("density", "profile", "floor", "shipped")]
    return table(rows, cols)


def sensitivity(sens) -> str:
    out = []
    for name, sw in sens["sweeps"].items():
        rows = []
        for pt in sw["points"]:
            v = pt["value"] if not isinstance(pt["value"], list) else f"{pt['value'][0]:g} clustered, {pt['value'][1]:g} per cluster"
            row = {name: v}
            for p in PROFILES:
                r = pt[p]
                row[f"{NAME[p]} P / R"] = f"{r['precision']['point']:.2f} / {r['recall']['point']:.2f}"
            for p in PROFILES:
                row[f"{NAME[p]} F0.5 (best z; best fixed m)"] = (f"{pt[p]['f05']['point']:.2f} ({pt[p]['f05_best_z_in_sample']:.2f} at {pt[p]['best_z_in_sample']}; "
                                                                 f"{pt[p]['f05_best_fixed_in_sample']:.2f} at {pt[p]['best_fixed_m_in_sample']})")
            row["B-cubed F1 (city)"] = f"{pt['city']['bcubed_f1']['point']:.3f}"
            row["cost 3:1 (city)"] = f"{pt['city']['cost_3_to_1']['point']:.0f}"
            row["cutoff, m"] = "none" if pt["cutoff_m"] is None else pt["cutoff_m"]
            rows.append(row)
        out.append(f"**{name}**: {sw['meaning']}\n\n" + table(rows, list(rows[0])))
    return "\n\n".join(out)


def main(folder: Path) -> None:
    main_, var, cut, cost_ = (load(folder, n) for n in ("main", "variants", "cutoff", "cost"))
    sections = [("SIZES", sizes(main_)), ("PAIRS", pairs(main_)), ("INTERVAL WIDTHS", widths(main_)), ("REPLAY", replay(main_)), ("TARGETS", targets(main_)),
                ("TALLY", variant_tally(var)), ("FITS", fits(var))]
    sections += [(f"VARIANTS {p} {d}", variants(var, p, d)) for p, d in (("A", 60), ("B", 60), ("C", 60), ("A", 20), ("A", 150), ("B", 20), ("B", 150), ("C", 20), ("C", 150))]
    sections += [("CUTOFF acc_new", cutoff(cut)), ("POLICY acc_new", policy(cut)), ("CUTOFF with tuned z", cutoff_tuned(cut)), ("CUTOFF acc_worst", cutoff(cut, "acc_worst")), ("POLICY acc_worst", policy(cut, "acc_worst")),
                 ("COST CHOICE", cost_choice(cost_)), *[(f"COST REPORT {s}", cost_report(cost_, s)) for s in cost_["report"]], ("COST CELLS", cost_cells(cost_))]
    sections += [(f"GAIN B {d}", gain(var, "B", d)) for d in DENSITIES] + [(f"GAIN A {d}", gain(var, "A", d)) for d in DENSITIES] + [("GAIN C", "\n\n".join(gain(var, "C", d) for d in DENSITIES))]
    for name, fn, title in (("sensitivity", sensitivity, "SENSITIVITY"), ("recommended", None, "RECOMMENDED"), ("interval_check", interval_check, "INTERVAL CHECK")):
        if (folder / f"matching_synthetic_{name}.json").exists():
            loaded = load(folder, name)
            if name == "recommended":
                sections += [("RECOMMENDED", recommended(loaded)), ("TRADE-OFF", trade_off(loaded))]
            else:
                sections.append((title, fn(loaded)))
    for title, body in sections:
        print(f"\n<!-- {title} -->\n{body}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else results.RESULTS)
