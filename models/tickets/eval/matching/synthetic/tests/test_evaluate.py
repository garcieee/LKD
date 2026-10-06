import math

import numpy as np
import pytest

from models.tickets import settings as s
from models.tickets.eval.common import metrics as m
from models.tickets.eval.matching.synthetic import evaluate as ev
from models.tickets.eval.matching.synthetic import simulator as sim
from models.tickets.matching import geo

POTHOLE, MANHOLE = "pothole", "open_manhole"


def scene(rows):
    """rows: (x metres east, y metres north, reported category, hazard, reported accuracy), in arrival order."""
    x, y = (np.array([r[i] for r in rows], float) for i in (0, 1))
    lat, lng = sim.to_latlng(x, y)
    return lat, lng, np.array([r[4] for r in rows], float), np.array([r[2] for r in rows]), np.array([r[3] for r in rows])


def world(density=150, profile="canyon", seed=3) -> sim.World:
    return sim.simulate(sim.Config(profile=profile, density=density), seed)


# ---- the pair builder labels a tiny hand-made scene -------------------------------------------------------------
HAND_MADE = [
    (0, 0, POTHOLE, "A", 10),  # 0
    (12, 0, POTHOLE, "A", 10),  # 1: a second person at the same pothole
    (40, 0, POTHOLE, "B", 10),  # 2: another pothole 40 m on
    (5, 0, MANHOLE, "C", 10),  # 3: a different category, right next to 0 and 1
    (400, 0, POTHOLE, "D", 10),  # 4: far from everything
    (-6, 8, POTHOLE, "A", 10),  # 5: a third person at pothole A
    (20, 0, MANHOLE, "C", 30),  # 6: a second person at the manhole, with a worse fix
    (3, 0, MANHOLE, "A", 10),  # 7: someone at pothole A who picked the wrong category
]


def test_the_pair_builder_labels_a_hand_made_scene():
    lat, lng, acc, category, hazard = scene(HAND_MADE)
    p = ev.build_pairs(lat, lng, acc, category, hazard)
    found = list(zip(p["i"].tolist(), p["j"].tolist()))
    # earlier first; same reported category only; within 150 m; sorted by the later report
    assert found == [(0, 1), (0, 2), (1, 2), (0, 5), (1, 5), (2, 5), (3, 6), (3, 7), (6, 7)]
    assert p["y"].tolist() == [True, False, False, True, True, False, True, False, False]
    assert p["d"] == pytest.approx([12, 40, 28, math.hypot(6, 8), math.hypot(18, 8), math.hypot(46, 8), 15, 2, 17], abs=0.05)
    assert p["acc_old"].tolist() == [10, 10, 10, 10, 10, 10, 10, 10, 30] and p["acc_new"].tolist() == [10, 10, 10, 10, 10, 10, 30, 10, 10]
    # the score is the matcher's own match_ratio, and the radius is built from the same spread the matcher uses
    for k, (a, b) in enumerate(found):
        assert p["ratio"][k] == pytest.approx(geo.match_ratio(lat[a], lng[a], acc[a], lat[b], lng[b], acc[b]))
    assert p["spread"][0] == pytest.approx(math.sqrt(2 * (10 / 1.51) ** 2 + 2 * 3.0**2))
    assert p["ratio"][0] == pytest.approx(12 / geo.match_radius_m(10, 10))


def test_pairs_never_cross_a_group_and_the_wrong_category_report_pairs_with_nothing_of_its_hazard():
    lat, lng, acc, category, hazard = scene(HAND_MADE)
    group = np.array([0, 0, 0, 0, 0, 1, 0, 0])  # report 5 is in another split
    p = ev.build_pairs(lat, lng, acc, category, hazard, group=group)
    assert 5 not in set(p["i"]) | set(p["j"])
    assert not any(a == 7 or b == 7 for a, b in zip(p["i"], p["j"]) if hazard[a] == hazard[b] == "A")


def test_the_vectorised_radius_agrees_with_the_matcher_on_a_simulated_world():
    w = world()
    p = ev.build_pairs(w.lat, w.lng, w.accuracy, w.category, w.hazard)
    assert len(p["y"]) > 1000
    assert np.array_equal(p["d"] <= ev.radius(p, s.MATCH_Z), p["ratio"] <= 1.0)
    assert np.allclose(ev.radius(p, s.MATCH_Z), p["d"] / p["ratio"])
    assert p["y"].mean() < 0.9 and p["y"].any()  # both kinds of pair exist


# ---- the replay merges and splits where it should ---------------------------------------------------------------
def tickets_of(rows):
    lat, lng, acc, category, _ = scene(rows)
    return ev.replay(lat, lng, acc, category, np.arange(len(rows), dtype=float)).tolist()


def test_the_replay_merges_the_same_place_and_starts_a_new_ticket_far_away():
    got = tickets_of([(0, 0, POTHOLE, "A", 10), (8, 0, POTHOLE, "A", 10), (100, 0, POTHOLE, "B", 10), (104, 3, POTHOLE, "B", 10)])
    assert got == [0, 0, 2, 2]


def test_the_replay_wrongly_merges_two_hazards_only_when_the_accuracy_makes_the_radius_big():
    assert tickets_of([(0, 0, POTHOLE, "A", 20), (25, 0, POTHOLE, "B", 20)]) == [0, 0]  # radius about 58 m: a wrong merge
    assert tickets_of([(0, 0, POTHOLE, "A", 5), (25, 0, POTHOLE, "B", 5)]) == [0, 1]  # radius about 19 m: kept apart


def test_the_replay_splits_one_hazard_when_the_reports_are_too_far_apart_for_their_accuracy():
    assert tickets_of([(0, 0, POTHOLE, "A", 5), (45, 0, POTHOLE, "A", 5)]) == [0, 1]


def test_the_replay_never_merges_across_categories():
    assert tickets_of([(0, 0, POTHOLE, "A", 10), (1, 0, MANHOLE, "A", 10), (2, 0, POTHOLE, "A", 10)]) == [0, 1, 0]


def test_a_joined_ticket_moves_to_its_most_accurate_report_across_a_grid_cell_edge():
    # cell edges are every 0.001 degrees, about 107 m east-west: the first cell edge east of Ayala is near x = 65 m
    rows = [(50, 0, POTHOLE, "A", 10), (70, 0, POTHOLE, "A", 5), (88, 0, POTHOLE, "A", 5)]
    assert tickets_of(rows) == [0, 0, 0]  # 88 m is 38 m from the first report (radius 26 m) but 18 m from the new anchor (19 m)
    # the ticket now sits in the next cell, and a far, poor-accuracy report still finds it there
    assert tickets_of(rows[:2] + [(129, 0, POTHOLE, "A", 30)]) == [0, 0, 0]


def test_the_grid_index_gives_exactly_what_offering_every_ticket_would():
    w = world(density=150, profile="canyon", seed=5)
    names = np.array(sim.REAL_CATEGORIES)[w.category]
    fast = ev.replay(w.lat, w.lng, w.accuracy, names, w.t)
    from dataclasses import replace
    from models.tickets.matching.match import anchor_after, find_match
    from models.tickets.types import Sighting, TicketSpot

    tickets, slow = {}, []
    for k in range(w.n_reports):
        r = Sighting(str(k), names[k], float(w.lat[k]), float(w.lng[k]), accuracy_m=float(w.accuracy[k]), created_at=float(w.t[k]))
        hit = find_match(r, list(tickets.values()), r.created_at)
        if hit is None:
            tickets[k] = TicketSpot(str(k), r.category, r.lat, r.lng, r.accuracy_m, "open", r.created_at)
            slow.append(k)
        else:
            q = int(hit.ticket_id)
            la, ln, ac = anchor_after(tickets[q], r)
            tickets[q] = replace(tickets[q], lat=la, lng=ln, accuracy_m=ac, last_activity_at=r.created_at)
            slow.append(q)
    assert fast.tolist() == slow
    assert 0.5 * w.n_reports < len(set(slow)) < w.n_reports  # some merged, some not


def test_other_settings_run_the_real_matcher_and_are_put_back():
    lat, lng, acc, category, _ = scene([(0, 0, POTHOLE, "A", 10), (12, 0, POTHOLE, "A", 10)])
    t = np.arange(2.0)
    assert ev.replay(lat, lng, acc, category, t).tolist() == [0, 0]  # shipped radius about 31 m
    assert ev.replay(lat, lng, acc, category, t, {"MATCH_MIN_M": 10.0, "MATCH_MAX_M": 10.0}).tolist() == [0, 1]  # a fixed 10 m
    assert ev.replay(lat, lng, acc, category, t, {"MATCH_Z": 1.5}).tolist() == [0, 0]  # radius 15 m
    assert (s.MATCH_Z, s.MATCH_MIN_M, s.MATCH_MAX_M) == (3.03, 15.0, 60.0)
    with pytest.raises(RuntimeError):
        with ev.patched({"MATCH_Z": 1.0}):
            raise RuntimeError
    assert s.MATCH_Z == 3.03


def test_merges_and_splits_are_counted_from_the_final_partition():
    # hazards 0 0 1 1 in tickets 0 1 0 3: ticket 0 holds both hazards (one wrong merge); hazard 0 is in tickets 0 and 1, hazard 1 in
    # tickets 0 and 3 (two wrong splits)
    events = ev.merge_split_events([0, 0, 1, 1], [0, 1, 0, 3])
    assert events.tolist() == [[0, 0], [0, 1], [1, 0], [0, 1]]
    assert events.sum(axis=0).tolist() == [1, 2]
    perfect = ev.merge_split_events([1, 1, 2, 3], [5, 5, 7, 9])
    assert perfect.sum() == 0
    assert ev.cost_per_1000(events, 3) == pytest.approx(1000 * (3 * 1 + 2) / 4)


# ---- resampling by district ---------------------------------------------------------------------------------------
def test_units_resample_whole_districts_with_repeats():
    units = ev.Units([5, 5, 7, 7, 7, 9])
    index, copy = units.rows(np.array([1, 0, 1]))
    assert index.tolist() == [2, 3, 4, 0, 1, 2, 3, 4] and copy.tolist() == [0, 0, 0, 1, 1, 2, 2, 2]
    assert sorted(units.rows(np.arange(len(units)))[0]) == list(range(6))


def test_the_district_interval_matches_the_plain_metric_at_the_point_and_is_wider_when_districts_differ():
    rng = np.random.default_rng(0)
    unit = np.repeat(np.arange(60), 40)
    base = rng.uniform(0.3, 0.9, 60)[unit]  # districts differ: pairs in one district are not independent
    y = rng.random(len(unit)) < base
    decision = rng.random(len(unit)) < 0.5
    units = ev.Units(unit)
    district = ev.ci(units, ev.prec, y, decision, n=300)
    assert district["point"] == pytest.approx(m.prf(y, decision)["precision"])
    pairs = m.bootstrap_ci(ev.prec, y, decision, n=300)
    assert district["hi"] - district["lo"] > 1.5 * (pairs.hi - pairs.lo)
    # the sums version agrees with the plain metric too
    sums = ev.ci_sums(units, np.column_stack([y & decision, decision]), lambda t: t[0] / t[1], n=300)
    assert sums["point"] == pytest.approx(district["point"]) and sums["lo"] < sums["point"] < sums["hi"]


def test_the_paired_difference_uses_the_same_districts_for_both_rules():
    rng = np.random.default_rng(1)
    unit = np.repeat(np.arange(40), 30)
    y = rng.random(len(unit)) < 0.4
    good = y ^ (rng.random(len(unit)) < 0.1)  # right 90% of the time
    bad = y ^ (rng.random(len(unit)) < 0.3)
    d = ev.ci_diff(ev.Units(unit), ev.f1, y, good, bad, n=300)
    assert d["lo"] > 0 and d["point"] == pytest.approx(m.prf(y, good)["f"] - m.prf(y, bad)["f"])
    same = ev.ci_diff(ev.Units(unit), ev.f1, y, good, good, n=300)
    assert same["point"] == same["lo"] == same["hi"] == 0


def test_cluster_intervals_do_not_mix_up_a_district_drawn_twice():
    true = np.array([0, 0, 1, 1, 2, 2])
    pred = np.array([0, 0, 1, 1, 2, 3])  # the last hazard is split
    units = ev.Units([0, 0, 1, 1, 2, 2])
    r = ev.ci_clusters(units, lambda t, p: m.cluster_pairs(t, p)["recall"], true, pred, n=200)
    assert r["point"] == pytest.approx(2 / 3)
    assert r["hi"] <= 1.0 and r["lo"] >= 0.0


def test_all_cluster_metrics_at_once_equal_one_at_a_time():
    rng = np.random.default_rng(2)
    unit = np.repeat(np.arange(30), 20)
    true = np.repeat(np.arange(300), 2)
    pred = np.where(rng.random(len(true)) < 0.2, rng.integers(0, 300, len(true)), true)  # some reports land in the wrong ticket
    units = ev.Units(unit)
    many = ev.ci_clusters_all(units, {"bcubed": m.bcubed, "pairwise": m.cluster_pairs, "ari": m.ari}, true, pred, n=50)
    assert set(many) == {"bcubed_precision", "bcubed_recall", "bcubed_f1", "pairwise_precision", "pairwise_recall", "pairwise_f1", "ari"}
    assert many["bcubed_recall"] == ev.ci_clusters(units, lambda t, p: m.bcubed(t, p)["recall"], true, pred, n=50)
    assert many["ari"] == ev.ci_clusters(units, m.ari, true, pred, n=50)
    assert many["pairwise_f1"] == ev.ci_clusters(units, lambda t, p: m.cluster_pairs(t, p)["f1"], true, pred, n=50)


# ---- splits ----------------------------------------------------------------------------------------------------------
def test_a_hazard_and_all_its_reports_share_a_district_and_districts_never_cross_splits():
    w = world(density=150, profile="city", seed=9)
    split, unit = ev.assign(w, 9)
    for h in range(w.n_hazards):
        pass
    assert all(len(set(split[w.hazard == h])) == 1 for h in range(0, w.n_hazards, 7))
    owner = {}
    for u, k in zip(unit, split):
        assert owner.setdefault(u, k) == k  # a district is in one split only
    shares = [np.mean(split == k) for k in range(3)]
    assert shares == pytest.approx([0.6, 0.2, 0.2], abs=0.1)
    assert len(np.unique(unit)) > 20
    # the profiles of one seed share the districts, so open-sky training and canyon testing never touch the same ground
    other = ev.assign(world(density=150, profile="open_sky", seed=9), 9)
    assert np.array_equal(split, other[0]) and np.array_equal(unit, other[1])


def test_pairs_are_only_formed_inside_one_split():
    w = world(density=150, profile="city", seed=9)
    split, _ = ev.assign(w, 9)
    p = ev.build_pairs(w.lat, w.lng, w.accuracy, w.category, w.hazard, group=split)
    assert np.array_equal(split[p["i"]], split[p["j"]])
    unrestricted = ev.build_pairs(w.lat, w.lng, w.accuracy, w.category, w.hazard)
    assert len(unrestricted["y"]) > len(p["y"])


# ---- the rules ---------------------------------------------------------------------------------------------------------
def pairs_of_a_world(profile="city", density=150, seed=2):
    w = world(density, profile, seed)
    return ev.build_pairs(w.lat, w.lng, w.accuracy, w.category, w.hazard)


def test_the_logistic_regression_and_trees_only_see_distance_and_the_two_accuracies():
    p = pairs_of_a_world()
    x = ev.features(p)
    assert x.shape == (len(p["y"]), 4)
    assert np.array_equal(x[:, 0], p["d"]) and np.allclose(x[:, 1] * x[:, 3], x[:, 2])
    assert (x[:, 1] <= x[:, 2]).all()  # smaller accuracy first: swapping the two reports changes nothing


def test_the_tuned_rules_are_fitted_on_train_and_chosen_on_validation():
    train, val = pairs_of_a_world(seed=1), pairs_of_a_world(seed=2)
    fit = ev.fit_variants(train, val)
    assert fit["z"] in ev.Z_GRID and fit["z_train"] in ev.Z_GRID and len(fit["curve"]["val"]) == len(ev.Z_GRID)
    assert fit["z"] == ev.Z_GRID[int(np.argmax(fit["curve"]["val"]))]  # the pick is the validation optimum
    arms = ev.variants(val, fit)
    assert list(arms)[:5] == [f"fixed {r} m" for r in ev.FIXED] and {"shipped", "z tuned", "logistic"} <= set(arms)
    decision, score = arms["shipped"]
    assert np.array_equal(decision, val["ratio"] <= 1.0) and np.array_equal(score, -val["ratio"])
    for name, (d, sc) in arms.items():
        assert d.dtype == bool and len(d) == len(sc) == len(val["y"])
    # a fixed radius is a distance threshold
    assert np.array_equal(arms["fixed 25 m"][0], val["d"] <= 25)


def test_a_variant_table_has_an_interval_for_every_number_and_none_against_itself(monkeypatch):
    monkeypatch.setattr(ev, "N_BOOT", 30)
    p = {**pairs_of_a_world(seed=1)}
    p["unit"] = np.arange(len(p["y"])) // 25
    fit = ev.fit_variants(p, p)
    table = ev.variant_table(p, fit)
    assert "f05_vs_shipped" not in table["shipped"]
    for row in table.values():
        assert row["precision"]["lo"] <= row["precision"]["point"] <= row["precision"]["hi"]
    assert table["fixed 10 m"]["pr_auc"] == table["fixed 60 m"]["pr_auc"]  # fixed radii rank by distance alone
    assert table["fixed 10 m"]["recall"]["point"] < table["fixed 60 m"]["recall"]["point"]


# ---- the cutoff and the cost -------------------------------------------------------------------------------------------
def synthetic_bins(precisions, merges=400):
    """Pairs that the rule merges, merges per bin each, with the given precision in each of the 7 accuracy bins."""
    acc, y = [], []
    for k, precision in enumerate(precisions):
        low, high = ([0, *ev.CUT_EDGES][k], [*ev.CUT_EDGES, 60][k])
        acc += [(low + high) / 2] * merges
        y += [True] * round(precision * merges) + [False] * (merges - round(precision * merges))
    n = len(acc)
    return {"acc_new": np.array(acc), "acc_old": np.array(acc), "y": np.array(y), "ratio": np.full(n, 0.5), "unit": np.arange(n) // 20}


def test_the_cutoff_is_the_last_bin_edge_before_precision_first_drops_under_0_85():
    rows = ev.precision_by_bin(synthetic_bins([0.97, 0.9, 0.86, 0.8, 0.9, 0.9, 0.9]))
    assert [r["merges"] for r in rows] == [400] * 7 and rows[2]["precision"] == pytest.approx(0.86)
    assert ev.cutoff_edge(rows) == 15  # bins up to 15 m pass; the 15-20 m bin fails, a later bin passing does not bring it back
    assert ev.cutoff_edge(ev.precision_by_bin(synthetic_bins([0.8, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9]))) == 0
    assert ev.cutoff_edge(ev.precision_by_bin(synthetic_bins([0.9] * 7))) is None
    assert ev.cutoff_edge(ev.precision_by_bin(synthetic_bins([0.9] * 6 + [0.5]))) == 40


def test_the_policy_switches_auto_merge_off_above_the_cutoff(monkeypatch):
    monkeypatch.setattr(ev, "N_BOOT", 30)
    p = synthetic_bins([0.97, 0.9, 0.86, 0.8, 0.7, 0.7, 0.7])
    policy = ev.policy_table(p, 15)
    auto_merges = 3 * 400
    assert policy["auto_merge_precision"]["point"] == pytest.approx((0.97 + 0.9 + 0.86) / 3, abs=0.01)
    assert policy["withheld_share_of_merges"]["point"] == pytest.approx(4 / 7)
    assert policy["shipped_precision_without_cutoff"]["point"] < policy["auto_merge_precision"]["point"]
    assert policy["auto_merge_recall"]["point"] < policy["shipped_recall_without_cutoff"]["point"] == pytest.approx(1.0)
    assert ev.policy_table(p, None)["auto_merge_recall"]["point"] == pytest.approx(1.0) and auto_merges == 1200


def test_the_rule_book_has_every_radius_rule_and_the_shipped_one_is_untouched():
    rules = ev.rule_book()
    assert rules["shipped"] == {} and set(f"fixed {r} m" for r in ev.FIXED) <= set(rules)
    assert rules["fixed 25 m"] == {"MATCH_MIN_M": 25.0, "MATCH_MAX_M": 25.0} and rules["z 2.5"] == {"MATCH_Z": 2.5}
    assert [k for k in rules if k.startswith("z ")][0] == "z 1.5" and [k for k in rules if k.startswith("z ")][-1] == "z 4.0"


# ---- the whole run, tiny ---------------------------------------------------------------------------------------------------
def test_gathering_is_deterministic_and_the_same_with_or_without_workers():
    specs = {(20, "city"): (sim.Config(profile="city", density=20), 3)}
    a = ev.gather(specs, 1, {"shipped": {}}, ("val",), workers=1)
    b = ev.gather(specs, 1, {"shipped": {}}, ("val",), workers=1)
    c = ev.gather(specs, 1, {"shipped": {}}, ("val",), workers=2)
    for other in (b, c):
        assert np.array_equal(a[(20, "city")]["tickets"]["shipped"], other[(20, "city")]["tickets"]["shipped"])
        assert np.array_equal(a[(20, "city")]["pairs"]["ratio"], other[(20, "city")]["pairs"]["ratio"])
    cell = a[(20, "city")]
    assert (cell["tickets"]["shipped"][cell["split"] == 1] >= 0).all() and (cell["tickets"]["shipped"][cell["split"] != 1] == -1).all()
    assert cell["events"]["floor"].sum(axis=0)[0] == 0  # one ticket per hazard and category never wrongly merges


def test_the_development_run_works_end_to_end_and_never_touches_the_test_split(monkeypatch, tmp_path, capsys):
    from sklearn.ensemble import HistGradientBoostingClassifier

    monkeypatch.setattr(ev, "N_BOOT", 20)
    monkeypatch.setattr(ev, "HAZARDS_PER_CELL", 1500)
    monkeypatch.setattr(ev, "HistGradientBoostingClassifier", lambda **kw: HistGradientBoostingClassifier(max_iter=5, random_state=0))  # wiring, not accuracy
    run = ev.main(final=False, workers=1, scale=1.0, folder=tmp_path)
    assert run["out"]["pairs"]["city@60"]["precision"]["lo"] <= run["out"]["pairs"]["city@60"]["precision"]["point"]
    written = {p.name for p in tmp_path.glob("*.json")}
    assert written == {"matching_synthetic_main.json", "matching_synthetic_variants.json", "matching_synthetic_cutoff.json", "matching_synthetic_cost.json"}
    cells = run["cells"]
    assert all((c["tickets"]["shipped"][c["split"] == 2] == -1).all() for c in cells.values())  # no replay was run on test
    import json
    main = json.loads((tmp_path / "matching_synthetic_main.json").read_text())
    assert main["config"]["report_split"] == "val" and main["config"]["final"] is False
    assert len(main["targets"]) == 18
    assert {"mixed@20", "mixed@60", "mixed@150"} <= set(main["pairs"]) and "mixed@60" in run["out"]["variants"]["B"]
    cost = json.loads((tmp_path / "matching_synthetic_cost.json").read_text())
    assert set(cost["report"]["all"]["adaptive_saving_vs_fixed"]) == {"1", "3", "5"} and "floor" in cost["report"]["all"]
    assert {p.name for p in tmp_path.glob("*.png")} == {f"matching_synthetic_{n}.png" for n in ("curves", "variants", "cutoff", "cost", "zcurve")}
    # the table generator reads what was written
    from models.tickets.eval.matching.synthetic import report_tables

    report_tables.main(tmp_path)
    shown = capsys.readouterr().out
    assert "<!-- TARGETS -->" in shown and "<!-- COST CHOICE -->" in shown and "| city | recall |" in shown


def test_the_sensitivity_run_writes_its_results_and_figures(monkeypatch, tmp_path):
    from models.tickets.eval.matching.synthetic import sensitivity as sens

    monkeypatch.setattr(sens, "BOOT", 10)
    monkeypatch.setattr(sens, "SWEEPS", {k: (meaning, values[:2], make) for k, (meaning, values, make) in sens.SWEEPS.items() if k != "popularity"})
    monkeypatch.setattr(sens, "GRID", {"accuracy_scale": [0.5, 1.0], "standoff_max_m": [5, 20]})
    out = sens.run(patches=1, workers=1, folder=tmp_path)
    point = out["sweeps"]["accuracy_scale"]["points"][0]
    assert point["value"] == 0.5 and {"open_sky", "city", "canyon", "cutoff_m"} <= set(point)
    row = point["city"]
    assert row["precision"]["lo"] <= row["precision"]["point"] <= row["precision"]["hi"]
    assert row["f05_best_z_in_sample"] >= row["f05"]["point"] - 1e-9 and row["f05_best_fixed_in_sample"] > 0
    assert len(out["grid"]) == 4
    assert {p.name for p in tmp_path.iterdir()} == {"matching_synthetic_sensitivity.json", "matching_synthetic_sensitivity.png", "matching_synthetic_sensitivity_grid.png"}


def test_the_recommended_configuration_check_reads_the_rule_with_its_own_z(monkeypatch, tmp_path):
    from models.tickets.eval.matching.synthetic import recommended

    monkeypatch.setattr(ev, "N_BOOT", 10)
    monkeypatch.setattr(ev, "HAZARDS_PER_CELL", 1500)
    p = pairs_of_a_world()
    same = recommended.with_z(p, None)
    assert same is p
    at_z = recommended.with_z(p, 2.0)
    assert np.array_equal(at_z["ratio"] <= 1.0, p["d"] <= ev.radius(p, 2.0)) and np.array_equal(at_z["d"], p["d"])
    assert (recommended.with_z(p, 1.5)["ratio"] <= 1).sum() < (p["ratio"] <= 1).sum()  # a smaller z merges less
    out = recommended.run(z=2.0, workers=1, folder=tmp_path)
    assert out["z"] == 2.0 and set(out["scopes"]) == {"density 20", "density 60", "density 150", "all densities"}
    both = out["scopes"]["all densities"]
    assert {"shipped_z", "recommended_z"} == set(both) and both["shipped_z"]["validation_trade_off"][-1]["cutoff_m"] is None
    rows = both["recommended_z"]["validation_trade_off"]
    assert [r["recall"] for r in rows] == sorted(r["recall"] for r in rows)  # a wider cutoff auto-merges more of the true pairs
    assert (tmp_path / "matching_synthetic_recommended.json").exists()


def test_the_interval_check_counts_how_often_each_kind_of_interval_holds_the_truth(tmp_path):
    from models.tickets.eval.matching.synthetic import interval_check

    out = interval_check.run(samples=3, patches=2, truth_patches=6, n=20, folder=tmp_path)
    held = out["share_of_intervals_holding_the_truth"]
    assert set(held) == {"precision", "recall"} and all(0 <= v <= 1 for h in held.values() for v in h.values())
    assert 0 < out["truth"]["precision"] < 1 and out["mean_interval_width"]["precision"]["district"] > 0
    assert (tmp_path / "matching_synthetic_interval_check.json").exists()
