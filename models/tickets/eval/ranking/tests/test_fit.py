import dataclasses

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression

from models.tickets import settings as S
from models.tickets.eval.ranking import aggregate as ag
from models.tickets.eval.ranking import evaluate as ev
from models.tickets.eval.ranking import fit
from models.tickets.eval.ranking import pairs

A, T = ag.A, ag.TIE


@pytest.fixture(scope="module")
def survey():
    return ag.load()


@pytest.fixture(scope="module")
def labels(survey):
    return ag.label_pairs(survey)


@pytest.fixture(scope="module")
def fitted(survey, labels):
    return fit.fit_weights(survey, labels)


def synthetic(weights, n=600, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.uniform(-1, 1, (n, len(weights)))
    y = np.where(rng.random(n) < 1 / (1 + np.exp(-x @ np.asarray(weights))), 1.0, -1.0)
    return x, y


def flip(choice):
    return np.where(choice == T, T, 1 - choice)


# ---- Bradley-Terry fit -------------------------------------------------------------------------------------------------
def test_bt_fit_matches_scikit_learn_when_the_constraint_does_not_bind():
    x, y = synthetic([1.0, 2.0, 0.5, 1.5])
    for lam in (0.5, 5.0):
        reference = LogisticRegression(C=1 / (2 * lam), fit_intercept=False, tol=1e-10, max_iter=2000).fit(x, y).coef_[0]  # same objective: loss + lam |w|^2
        assert reference.min() > 0
        assert fit.bt_fit(x, y, lam) == pytest.approx(reference, abs=5e-3)


def test_bt_fit_never_returns_a_negative_weight_even_when_the_data_ask_for_one():
    x, y = synthetic([2.0, -3.0, 1.0, -1.0])  # the second and fourth features count against the pair's first ticket
    free = LogisticRegression(C=1e6, fit_intercept=False, max_iter=2000).fit(x, y).coef_[0]
    assert free[1] < -1 and free[3] < -0.3  # an unconstrained fit would use negative weights
    for lam in (0.0, 0.1, 10.0):
        w = fit.bt_fit(x, y, lam)
        assert (w >= 0).all() and w[1] == 0.0 and w[3] == 0.0 and w[0] > 0


def test_a_pair_listed_the_other_way_round_gives_the_same_weights():
    x, y = synthetic([1.0, 2.0, 0.5, 1.5], n=200)
    assert fit.bt_fit(-x, -y, 1.0) == pytest.approx(fit.bt_fit(x, y, 1.0), abs=1e-6)


def test_more_penalty_means_smaller_weights():
    x, y = synthetic([1.0, 2.0, 0.5, 1.5])
    norms = [np.linalg.norm(fit.bt_fit(x, y, lam)) for lam in (0.0, 1.0, 10.0, 100.0)]
    assert norms == sorted(norms, reverse=True) and norms[-1] < 0.2 * norms[0]


def test_normalised_weights_sum_to_one_and_all_zero_has_nothing_to_scale():
    scaled = fit.normalised([2.0, 1.0, 1.0, 0.0])
    assert sum(scaled.values()) == pytest.approx(1.0) and scaled == {"danger": 0.5, "reports": 0.25, "foot_traffic": 0.25, "waiting": 0.0}
    assert fit.normalised([0.0, 0.0, 0.0, 0.0]) is None


# ---- the pre-registered rule --------------------------------------------------------------------------------------------
def test_the_rule_needs_three_points_on_validation_and_non_negative_weights():
    assert fit.rule(0.80, 0.84, [0.3, 0.2, 0.3, 0.2])["replace"]  # +4 points
    assert fit.rule(0.80, 0.83, [0.3, 0.2, 0.3, 0.2])["replace"]  # exactly 3 points is enough
    assert not fit.rule(0.80, 0.829, [0.3, 0.2, 0.3, 0.2])["replace"]  # a hair short
    assert not fit.rule(2 / 3, 2 / 3 + 1 / 48, [0.3, 0.2, 0.3, 0.2])["replace"]  # one pair of 48 is 2.1 points
    assert fit.rule(2 / 3, 2 / 3 + 2 / 48, [0.3, 0.2, 0.3, 0.2])["replace"]  # two pairs of 48 is 4.2 points
    assert not fit.rule(0.80, 0.95, [0.3, -0.01, 0.3, 0.2])["replace"] and not fit.rule(0.80, 0.95, [0.3, -0.01, 0.3, 0.2])["non_negative"]
    assert not fit.rule(0.80, None, [0.3, 0.2, 0.3, 0.2])["replace"]
    assert fit.rule(0.80, 0.84, [0.3, 0.2, 0.3, 0.2])["margin"] == fit.MARGIN == 0.03


def test_fitted_weights_on_the_real_pairs_are_never_negative(fitted):
    assert len(fitted["sweep"]) == len(fit.LAMBDAS)
    for row in fitted["sweep"]:
        assert all(v >= 0 for v in row["weights"].values()) and sum(row["normalised"].values()) == pytest.approx(1.0)
    assert all(v >= 0 for v in fitted["raw_weights"].values()) and fitted["decision"]["non_negative"]
    assert sum(fitted["fitted_weights"].values()) == pytest.approx(1.0) and set(fitted["fitted_weights"]) == set(ev.PARTS)


def test_more_penalty_shrinks_the_real_weights(fitted):
    norms = [np.linalg.norm(list(r["weights"].values())) for r in fitted["sweep"]]
    assert norms == sorted(norms, reverse=True)


def test_the_weights_of_record_are_the_fitted_ones_only_if_the_rule_says_replace(fitted):
    d = fitted["decision"]
    assert d["replace"] == (d["non_negative"] and d["validation_gain"] >= fit.MARGIN - 1e-9)
    assert d["weights_of_record"] == (fitted["fitted_weights"] if d["replace"] else dict(S.WEIGHTS))
    assert d["validation_gain"] == pytest.approx(d["fitted_validation_accuracy"] - d["hand_validation_accuracy"])


def test_lambda_is_the_one_with_the_lowest_validation_log_loss_and_the_larger_one_on_a_tie(fitted):
    losses = [r["validation_log_loss"] for r in fitted["sweep"]]
    best = min(losses)
    tied = [r["lambda"] for r in fitted["sweep"] if round(r["validation_log_loss"], 12) == round(best, 12)]
    assert fitted["chosen_lambda"] == max(tied)
    assert fitted["decision"]["fitted_validation_accuracy"] == next(r for r in fitted["sweep"] if r["lambda"] == fitted["chosen_lambda"])["full_score_accuracy"]["validation"]


# ---- which split each step reads ---------------------------------------------------------------------------------------
def test_each_design_holds_only_the_majority_labelled_pairs_of_its_split(survey, labels):
    parts = ev.parts_array(survey.truth)
    for split, n in (("train", 141), ("validation", 48), ("test", 46)):
        x, y, rows = fit.design(survey, labels, parts, split)
        assert x.shape == (n, 4) and len(y) == n and set(y) <= {-1.0, 1.0}
        assert set(survey.split[rows]) == {split} and (labels.winner[rows] >= 0).all()
        assert np.allclose(x, parts[survey.a[rows]] - parts[survey.b[rows]]) and ((labels.winner[rows] == A) == (y > 0)).all()


def test_the_fit_never_reads_the_test_split(survey, labels, fitted):
    outside = survey.split == "test"
    changed = dataclasses.replace(survey, choice=np.where(outside[:, None], flip(survey.choice), survey.choice),
                                  urgency=np.where((survey.ticket_split == "test")[:, None], 6 - survey.urgency, survey.urgency))
    after = ag.label_pairs(changed)
    assert fit.fit_weights(changed, after) == fitted
    assert fit.nnls_urgency(changed) == fit.nnls_urgency(survey) and fit.nnls_urgency(changed, extended=True) == fit.nnls_urgency(survey, extended=True)
    assert fit.candidates(changed, after, fitted["fitted_weights"], boot=20) == fit.candidates(survey, labels, fitted["fitted_weights"], boot=20)
    assert fit.drain_sweep(changed, after) == fit.drain_sweep(survey, labels)
    assert fit.urgency_by_category(changed) == fit.urgency_by_category(survey)
    assert fit.test_report(changed, after, fitted["fitted_weights"], boot=20) != fit.test_report(survey, labels, fitted["fitted_weights"], boot=20)  # the test split is only read here


def test_the_weights_come_from_train_and_the_penalty_from_validation(survey, labels, fitted):
    train_flipped = np.where((survey.split == "train")[:, None], flip(survey.choice), survey.choice)
    changed = dataclasses.replace(survey, choice=train_flipped)
    other = fit.fit_weights(changed, ag.label_pairs(changed))
    assert other["raw_weights"] != fitted["raw_weights"] and other["sweep"][0]["train_log_loss"] != fitted["sweep"][0]["train_log_loss"]
    validation_flipped = dataclasses.replace(survey, choice=np.where((survey.split == "validation")[:, None], flip(survey.choice), survey.choice))
    moved = fit.fit_weights(validation_flipped, ag.label_pairs(validation_flipped))
    assert [r["weights"] for r in moved["sweep"]] == [r["weights"] for r in fitted["sweep"]]  # the weights are fitted on train: unmoved
    assert [r["validation_log_loss"] for r in moved["sweep"]] != [r["validation_log_loss"] for r in fitted["sweep"]]


# ---- non-negative least squares ---------------------------------------------------------------------------------------------
def test_nnls_weights_are_never_negative_and_come_from_train_tickets(survey):
    for extended in (False, True):
        out = fit.nnls_urgency(survey, extended=extended)
        assert out["split_fitted_on"] == "train" and out["n_tickets"] == 120
        assert all(v >= 0 for v in out["weights"].values()) and out["intercept"] >= 0 and sum(out["normalised"].values()) == pytest.approx(1.0)
        assert 0 <= out["r2_train"] <= 1 and out["r2_validation"] <= 1
    ext = fit.nnls_urgency(survey, extended=True)
    assert ext["note_coefficient"] >= 0 and ext["implied_bonus_points"] >= 0
    assert ext["r2_train"] > fit.nnls_urgency(survey)["r2_train"]  # the gate and the note explain urgency the four parts alone do not


def test_nnls_recovers_known_weights_from_exact_data(survey):
    parts = ev.parts_array(survey.truth)
    y = parts @ np.array([2.0, 1.0, 1.5, 0.3]) + 0.2
    exact = dataclasses.replace(survey, urgency=np.repeat(y[:, None], 5, axis=1))
    out = fit.nnls_urgency(exact)
    assert [out["weights"][p] for p in ev.PARTS] == pytest.approx([2.0, 1.0, 1.5, 0.3], abs=1e-6) and out["intercept"] == pytest.approx(0.2, abs=1e-6)
    assert out["r2_train"] == pytest.approx(1.0) and out["r2_validation"] == pytest.approx(1.0)


def test_nnls_will_not_use_a_negative_weight_for_a_part_that_hurts(survey):
    parts = ev.parts_array(survey.truth)
    y = 3 + 2 * parts[:, 0] - 2 * parts[:, 3]  # waiting lowers urgency
    out = fit.nnls_urgency(dataclasses.replace(survey, urgency=np.repeat(y[:, None], 5, axis=1)))
    assert out["weights"]["waiting"] == 0.0 and out["weights"]["danger"] > 0


def test_urgency_by_category_covers_every_kind_on_train_and_validation_only(survey):
    out = fit.urgency_by_category(survey)
    assert set(out) == set(S.SEVERITY) and sum(r["n"] for r in out.values()) < 120 + 40
    assert out["open_manhole"]["mean_urgency"] == max(r["mean_urgency"] for r in out.values())
    assert out["other"]["mean_urgency"] == min(r["mean_urgency"] for r in out.values())
    only_test = fit.urgency_by_category(survey, splits=("test",))
    assert sum(r["n"] for r in only_test.values()) < sum(r["n"] for r in out.values())


# ---- candidate changes -----------------------------------------------------------------------------------------------------
def test_visible_foot_traffic_gives_every_ticket_of_a_busy_label_the_same_number(survey):
    level = {"a quiet side street": 0, "a moderately busy street": 1, "a very busy area": 2}
    seen = {}
    facts = fit.visible_foot_traffic(survey.truth)
    for t, text in zip(survey.truth, survey.description):
        label = next(v for k, v in level.items() if k in text)
        seen.setdefault(label, set()).add(facts(t).foot_traffic)
    assert all(len(v) == 1 for v in seen.values()) and len(seen) == 3  # one value per label, the label the raters read
    means = [seen[k].pop() for k in (0, 1, 2)]
    assert means == sorted(means) and means[0] < 0.25 and means[2] > 0.65
    t = survey.truth[0]
    assert facts(t).category == t["category"] and facts(t).reporters == t["reporters"] and facts(t).days_open == t["days_open"]  # only foot traffic is replaced


def test_every_candidate_is_one_runnable_change_to_the_settings(survey):
    changes = fit.candidate_changes(survey.truth, ev.renormalised("waiting"))
    before = (dict(S.SEVERITY), dict(S.WEIGHTS), S.DANGER_BONUS, S.WAITING_FULL_DAYS)
    for name, change in changes.items():
        assert len(fit.scored(survey.truth, change)) == 200, name
        for w in (change.get("WEIGHTS"),):
            assert w is None or sum(w.values()) == pytest.approx(1.0), name
    assert (dict(S.SEVERITY), dict(S.WEIGHTS), S.DANGER_BONUS, S.WAITING_FULL_DAYS) == before
    drain = changes["flooded drain severity 0.85 -> 0.65 (the pothole's)"]["SEVERITY"]
    assert {k: v for k, v in drain.items() if S.SEVERITY[k] != v} == {"flooded_drain": 0.65}
    middle = changes["the four middle kinds all at severity 0.60"]["SEVERITY"]
    assert {k for k, v in middle.items() if v == 0.60} == {"flooded_drain", "pothole", "broken_streetlight", "blocked_sidewalk"}
    assert changes["waiting weight halved (weights rescaled to sum to 1)"]["WEIGHTS"]["waiting"] < S.WEIGHTS["waiting"]
    assert not any("Bradley" in n for n in fit.candidate_changes(survey.truth, None))


def test_candidates_are_judged_on_train_and_validation_pairs_only(survey, labels, fitted):
    out = fit.candidates(survey, labels, fitted["fitted_weights"], boot=20)
    assert set(out) == {"train", "validation"}
    assert (out["train"]["n_pairs"], out["train"]["n_tickets"], out["validation"]["n_pairs"], out["validation"]["n_tickets"]) == (141, 120, 48, 40)
    rows = out["validation"]["rows"]
    assert "change_vs_shipped" not in rows[ev.SHIPPED] and all("change_vs_shipped" in r for n, r in rows.items() if n != ev.SHIPPED)
    assert rows["Bradley-Terry fitted weights (the pre-registered fit)"]["accuracy"]["point"] == pytest.approx(fitted["decision"]["fitted_validation_accuracy"])
    assert rows[ev.SHIPPED]["accuracy"]["point"] == pytest.approx(fitted["decision"]["hand_validation_accuracy"])


def test_the_drain_sweep_starts_at_the_shipped_value_and_restores_the_settings(survey, labels):
    before = dict(S.SEVERITY)
    sweep = fit.drain_sweep(survey, labels)
    assert S.SEVERITY == before and list(sweep)[0] == "0.85"
    for split in ("train", "validation"):
        assert sweep["0.85"][split] == pytest.approx(fit.accuracy_with(survey, labels, split))
    assert set(sweep["0.85"]) == {"train", "validation"}


def test_accuracy_with_is_the_pairwise_accuracy_of_the_real_score_on_that_split(survey, labels):
    key = ev.score_array(survey.truth, DANGER_BONUS=0.0)
    mask = ev.pair_mask(survey, labels, "validation")
    expected = ev.accuracy_ci(key, survey, mask, labels.winner[mask] == A, 10).point
    assert fit.accuracy_with(survey, labels, "validation", DANGER_BONUS=0.0) == pytest.approx(expected)


# ---- the one test run --------------------------------------------------------------------------------------------------------
def test_the_test_report_is_on_the_test_split_and_compares_with_the_hand_weights(survey, labels, fitted):
    out = fit.test_report(survey, labels, fitted["fitted_weights"], boot=20)
    assert out["split"] == "test" and set(out["headline"]) == {fit.HAND, "fitted weights"}
    for name in out["headline"]:
        assert [out["headline"][name][s]["n_pairs"] for s in ev.SUBSETS] == [46, 41, 31] and out["tickets"][name]["n_tickets"] == 40
    hand = ev.headline(survey, labels, ev.score_array(survey.truth), "test", boot=20)
    assert out["headline"][fit.HAND]["majority"]["accuracy"] == hand["majority"]["accuracy"]
    rows = out["compare"]["majority"]["rows"]
    assert "this_minus_reference" in rows["fitted weights"] and out["compare"]["majority"]["split"] == "test"
    assert rows["fitted weights"]["this_minus_reference"]["point"] == pytest.approx(rows["fitted weights"]["accuracy"]["point"] - rows[fit.HAND]["accuracy"]["point"])


def test_the_whole_fit_run_reports_one_decision_and_the_test_numbers_of_both_weight_sets(survey, labels):
    out = fit.run(survey, labels, boot=20)
    assert out["decision"] == out["bradley_terry"]["decision"] and out["config"]["label_set"] == "majority"
    assert out["test"]["split"] == "test" and out["config"]["lambda_chosen_on"] == "validation log-loss"
    assert out["decision"]["weights_of_record"] == (out["bradley_terry"]["fitted_weights"] if out["decision"]["replace"] else dict(S.WEIGHTS))
    assert set(out["flooded_drain_severity_sweep"]) >= {"0.85", "0.65"}


def test_the_rule_reads_the_same_numbers_as_the_targets_row(survey, labels, fitted):
    row = ev.target_rows({s: {"n_pairs": 1, "accuracy": {"point": 1, "lo": 1, "hi": 1}, "ratio_to_ceiling": {"point": 1, "lo": 1, "hi": 1},
                              "ratio_to_ceiling_like_for_like": {"point": 1, "lo": 1, "hi": 1}, "ceiling": {"point": 1}} for s in ev.SUBSETS},
                         {"n_tickets": 1, "kendall_tau_b": {"point": 1, "lo": 1, "hi": 1}, "ndcg_at_10": {"point": 1, "lo": 1, "hi": 1}},
                         {s: {"n_pairs": 1, "rows": {n: {"reference_minus_this": {"point": 1, "lo": 1, "hi": 1}} for n in ("severity only", "dashboard order")}} for s in ev.SUBSETS},
                         {"decision": fitted["decision"]})[-1]
    assert row["met"] == fitted["decision"]["replace"] and row["value"] == fitted["decision"]["validation_gain"] and row["threshold"] == fit.MARGIN
    assert pairs.SPLITS == ("train", "validation", "test")


# ---- where the weights gain ------------------------------------------------------------------------------------------------
def test_the_fit_reports_accuracy_by_stratum_for_train_and_validation_only(survey, labels, fitted):
    by = fitted["by_stratum"]
    assert set(by) == {"train", "validation"} and set(by["validation"]) == {fit.HAND, "fitted weights"}
    for split, n in (("train", 141), ("validation", 48)):
        assert sum(c["n"] for c in by[split][fit.HAND].values()) == n and set(by[split][fit.HAND]) == {"clear", "close", "trade_off"}
    validation = ev.accuracy_by_stratum(survey, labels, {fit.HAND: ev.score_array(survey.truth)}, "validation")[fit.HAND]
    assert by["validation"][fit.HAND] == validation


def test_the_test_report_adds_the_by_stratum_and_the_random_pair_view(survey, labels, fitted):
    out = fit.test_report(survey, labels, fitted["fitted_weights"], boot=30)
    assert sum(c["n"] for c in out["by_stratum"][fit.HAND].values()) == 46
    post = out["post_stratified"]
    assert post["split"] == "test" and set(post["rows"]) == {fit.HAND, "fitted weights"} and "minus_reference" in post["rows"]["fitted weights"] and "minus_reference" not in post["rows"][fit.HAND]
    assert sum(post["pairs_by_stratum"].values()) == 46


def test_every_candidate_is_also_scored_by_stratum_on_train_and_validation(survey, labels, fitted):
    out = fit.candidates(survey, labels, fitted["fitted_weights"], boot=20)
    for split, n in (("train", 141), ("validation", 48)):
        assert all(sum(c["n"] for c in cells.values()) == n for cells in out[split]["by_stratum"].values()) and set(out[split]["by_stratum"]) == set(out[split]["rows"])
