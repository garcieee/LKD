import numpy as np
import pytest

from models.tickets.eval.matching.chicago import evaluate as ev

# eight pairs: positives at 3, 8, 12, 25 and 70 m, negatives at 20, 30 and 50 m
D = {"d": np.array([3, 8, 12, 20, 25, 30, 50, 70.0]), "label": np.array([1, 1, 1, 0, 1, 0, 0, 1]),
     "dt": np.array([1, 2, 3, 4, 5, 6, 7, 8.0]), "category": np.array(["pothole"] * 4 + ["broken_streetlight"] * 4),
     "origin": np.array(["Mobile Device", "Phone Call"] * 4), "kind": np.array([0, 0, 0, 2, 0, 2, 2, 0]), "group": np.zeros(8, int)}


def test_the_best_radius_is_the_smallest_one_with_the_best_score():
    assert ev.pick_radius(D, 1.0) == 25  # F1 .80 from 25 m (tp 4, fp 1, fn 1) until 29 m; 12 m gives .75
    assert ev.pick_radius(D, 0.5) == 12  # precision 1 at 12 m beats .8 at 25 m
    assert ev.pick_radius(D, cost=3) == 12  # 3 * 0 false merges + 2 missed = 2, the least up to 19 m


def test_cost_one_to_one_matches_the_hand_count():
    cost = lambda r: (D["d"][D["label"] == 0] <= r).sum() + (D["d"][D["label"] == 1] > r).sum()
    assert [cost(r) for r in (11, 12, 19, 25, 29, 30)] == [3, 2, 2, 2, 2, 3]  # a tie from 12 m to 29 m
    assert ev.pick_radius(D, cost=1) == 12  # the smallest radius among the ties


def test_a_class_missing_means_nothing_to_choose():
    only_positive = {**D, "label": np.ones(8, int)}
    assert np.isnan(ev.pick_radius(only_positive))


def test_the_threshold_search_never_counts_a_merge_beyond_the_cap():
    p = np.array([0.9, 0.8, 0.7, 0.2, 0.6, 0.3, 0.1, 0.95])  # the 70 m positive has the highest probability but can never be merged
    t = ev.pick_threshold(D, p)
    assert 0.3 < t <= 0.6 and t == 0.6
    kept = (p >= t) & (D["d"] <= ev.CAP)
    assert list(kept) == [True, True, True, False, True, False, False, False]


def test_every_variant_is_capped_and_the_named_radii_are_what_they_say():
    ch = ev.choose(D | {"label": D["label"]}, D)
    by = {v.name: v for v in ev.variants_for(D, ch)}
    assert all(not v.pred[-1] for v in by.values())  # the 70 m pair is never merged, whatever the variant
    assert list(by["fixed 25 m"].pred) == [True, True, True, True, True, False, False, False]
    assert by["shipped no accuracy: 44.5 m"].pred.sum() == 6 and by["shipped accuracy 20 m: 58.2 m"].pred.sum() == 7
    assert list(by["shipped radius + dt <= 14 d"].pred) == list(by["shipped no accuracy: 44.5 m"].pred)  # every dt here is <= 8
    assert by["best F1 radius"].family == "best on validation" and len(by) == len(set(by))
    assert np.array_equal(by["fixed 10 m"].score, -D["d"]) and by["fixed 10 m"].key == by["fixed 60 m"].key == "distance"


def test_the_time_window_turns_a_distant_in_time_pair_into_a_no():
    far_in_time = D | {"dt": np.array([1, 2, 40, 4, 5, 6, 7, 8.0])}
    by = {v.name: v for v in ev.variants_for(far_in_time, ev.choose(D, D))}
    assert not by["shipped radius + dt <= 14 d"].pred[2] and not by["shipped radius + dt <= 30 d"].pred[2]
    assert by["shipped radius + dt <= 14 d"].score[2] < by["shipped radius + dt <= 14 d"].score[0]


def test_the_logistic_features_line_up_with_their_names():
    for flags in ev.LR_VARIANTS.values():
        assert ev.features(D, **flags).shape == (8, len(ev.names(**flags)))


def test_the_table_has_every_metric_with_an_interval_around_the_point():
    ch = ev.choose(D, D)
    rows = ev.evaluate_set(D, ev.variants_for(D, ch), boot=30)
    assert len(rows) == len(ev.variants_for(D, ch))
    row = rows[0]
    for m in ("precision", "recall", "f1", "f05", "pr_auc", "roc_auc"):
        assert row[m]["lo"] <= row[m]["hi"] and 0 <= row[m]["point"] <= 1
    assert (row["tp"], row["fp"], row["fn"], row["tn"]) == (2, 0, 3, 3)  # fixed 10 m: pairs at 3 and 8 m


def paired_data(wards=None):
    rng = np.random.default_rng(0)
    n = 600
    y = rng.random(n) < 0.4
    base = rng.normal(size=n) + y  # the distance score: a weak signal
    helpful, noise = base + 2 * y, rng.normal(size=n)
    mk = lambda name, score, family: ev.Variant(name, family, name, score, score > np.median(score))
    D = {"label": y.astype(int)} | ({} if wards is None else {"ward": wards})
    best = mk("best F1 radius", base, "best on validation")._replace(pred=base > 0.5)
    vs = [best, best._replace(name="best F0.5 radius", pred=base > 1.0), mk("logistic helpful", helpful, "logistic"), mk("logistic noise", noise, "logistic")]
    return D, vs


def test_a_helpful_extra_signal_wins_the_paired_comparison_and_noise_does_not():
    D, vs = paired_data()
    rows = {r["name"]: r for r in ev.paired(D, vs, boot=200)}
    assert set(rows) == {"logistic helpful", "logistic noise"}
    assert rows["logistic helpful"]["pr_auc"]["verdict"] == "better" and rows["logistic helpful"]["pr_auc"]["pairs"]["lo"] > 0
    assert rows["logistic noise"]["pr_auc"]["verdict"] == "worse"  # pure noise ranks far worse than a weak real signal
    assert rows["logistic helpful"]["f1"]["pairs"]["point"] > 0 and rows["logistic helpful"]["pr_auc"]["wards"] is None


def test_resampling_wards_equals_resampling_pairs_when_every_pair_is_its_own_ward():
    D, vs = paired_data(wards=np.arange(600))
    row = {r["name"]: r for r in ev.paired(D, vs, boot=60)}["logistic helpful"]
    for key in ("pr_auc", "f1", "f05"):
        assert row[key]["wards"]["lo"] == pytest.approx(row[key]["pairs"]["lo"]) and row[key]["wards"]["hi"] == pytest.approx(row[key]["pairs"]["hi"])


def test_resampling_wards_widens_the_interval_when_the_pairs_of_a_ward_are_copies_of_each_other():
    rng = np.random.default_rng(1)
    y, a, b = (np.repeat(x, 20) for x in (rng.random(30) < 0.5, rng.normal(size=30), rng.normal(size=30)))  # 30 wards, 20 copies each
    ward = np.repeat(np.arange(30), 20)
    f = lambda yy, s: ((s > 0) == yy).mean()
    pairs_ci = ev.metrics.paired_bootstrap_diff(f, y, a, b, n=300)
    wards_ci = ev.ward_diff(f, y, a, b, ward, 300)
    assert wards_ci.point == pytest.approx(pairs_ci.point)
    assert wards_ci.hi - wards_ci.lo > 2 * (pairs_ci.hi - pairs_ci.lo)  # about sqrt(20) times wider


def test_the_verdict_needs_both_intervals_clear_of_zero():
    CI = ev.metrics.CI
    assert ev.verdict(CI(0.1, 0.05, 0.2), CI(0.1, 0.02, 0.2)) == "better"
    assert ev.verdict(CI(0.1, 0.05, 0.2), CI(0.1, -0.02, 0.2)) == "no clear difference"
    assert ev.verdict(CI(-0.1, -0.2, -0.05), None) == "worse" and ev.verdict(CI(0.0, -0.1, 0.1), None) == "no clear difference"


def test_markdown_shows_each_cell_with_its_interval():
    cell = {"point": 0.5, "lo": 0.25, "hi": 0.75}
    row = {"name": "x", **{m: cell for m in ("precision", "recall", "f1", "f05", "pr_auc", "roc_auc")}}
    table = ev.markdown({"hard": {"test": {"table": [row]}}}, "hard", "test")
    assert table.splitlines()[2] == "| x | " + " | ".join(["0.500 (0.250-0.750)"] * 6) + " |"


def synthetic_pairs(n=400, seed=0):
    rng = np.random.default_rng(seed)
    d = rng.uniform(0, 80, n)
    label = (rng.random(n) < 1 / (1 + np.exp((d - 30) / 8))).astype(int)  # closer pairs are more often duplicates
    return {"d": d, "label": label, "dt": rng.exponential(10, n), "category": rng.choice(ev.CATEGORIES, n), "origin": rng.choice(ev.eda.ORIGINS, n),
            "kind": np.where(label == 1, 0, 2), "group": np.zeros(n, int), "ward": rng.integers(0, 20, n).astype(str)}


def test_windows_and_accuracy_radii_are_also_compared_with_the_shipped_default():
    D = synthetic_pairs()
    vs = ev.variants_for(D, ev.choose(D, D))
    rows = {r["name"]: r for r in ev.paired(D, vs, boot=30)}
    assert set(rows) == {*ev.COMPARED, *[f"logistic {n}" for n in ev.LR_VARIANTS]}
    with_baseline = {n for n, r in rows.items() if "f1_vs_shipped" in r}
    assert with_baseline == {"shipped accuracy 5 m: 19.1 m", "shipped accuracy 10 m: 31.2 m", "shipped accuracy 20 m: 58.2 m",
                             "shipped radius + dt <= 14 d", "shipped radius + dt <= 30 d"}
    row = rows["shipped radius + dt <= 14 d"]
    assert {"f1_vs_shipped", "f05_vs_shipped"} <= set(row) and row["f1_vs_shipped"]["wards"]["lo"] <= row["f1_vs_shipped"]["wards"]["hi"]


def test_the_comparisons_inside_a_category_use_only_the_three_named_variants():
    D = synthetic_pairs()
    vs = ev.variants_for(D, ev.choose(D, D))
    got = ev.within_category(D, vs, boot=20)
    assert set(got) == set(ev.CATEGORIES)
    assert all({r["name"] for r in rows} == set(ev.WITHIN) for rows in got.values())


def three_splits(seed=0, n=900):
    """Synthetic pairs in the three splits, with the columns the real pair data has."""
    D = synthetic_pairs(n, seed)
    D["group"] = np.random.default_rng(seed).integers(0, 3, n)
    return D


def test_the_whole_set_runs_end_to_end_with_and_without_the_extras():
    D = three_splits()
    for detail, light in ((True, False), (False, False), (True, True)):
        out, keep = ev.run_set(D, (0, 1, 2), boot=5, detail=detail, light=light)
        assert set(out) >= {"chosen", "counts", "validation", "test", "validation_f_by_radius"}
        assert ("paired_against_best_fixed_radius" in out["test"]) == (not light)
        assert ("by_category" in out["test"]) == (detail and not light) and ("paired_within_category" in out["test"]) == (detail and not light)
        assert ("by_category" in out["validation"]) == (detail and not light) and "paired_within_category" not in out["validation"]
        assert len(out["test"]["table"]) == len(ev.variants_for(keep["test"][0], ev.choose(*[ev.select(D, g, (0, 1, 2)) for g in (0, 1)])))


def test_the_pictures_and_the_result_file_are_written(tmp_path, monkeypatch):
    from models.tickets.eval.common import results

    monkeypatch.setattr(results, "RESULTS", tmp_path)
    D = three_splits()
    D["kind"] = np.where(D["label"] == 1, 0, np.where(D["d"] >= 50, 1, 2))  # duplicates, far negatives (50 m and more here) and near ones
    monkeypatch.setattr(ev.pairs, "load", lambda kind, everything=None, near_any=False: D)
    out = ev.run("time", boot=5)
    assert {"clean", "hard"} <= set(out)
    written = {p.name for p in tmp_path.iterdir()}
    assert written == {"matching_chicago_evaluate_time.json", "matching_chicago_evaluate_time_radius.png", "matching_chicago_evaluate_time_curves.png"}
    assert all((tmp_path / n).stat().st_size > 2000 for n in written)
    ev.run("time", boot=5, near_any=True)  # the sensitivity run writes tables only
    assert (tmp_path / "matching_chicago_evaluate_time_anyother.json").exists() and not (tmp_path / "matching_chicago_evaluate_time_anyother_radius.png").exists()
