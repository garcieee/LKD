import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")

from models.tickets.eval.common import metrics as m  # noqa: E402


# ---- binary ---------------------------------------------------------------------------------------------------------
def test_prf_matches_a_hand_count():
    r = m.prf([1, 1, 0, 0, 1, 0], [1, 0, 0, 1, 1, 0])  # tp 2, fp 1, fn 1, tn 2
    assert (r["tp"], r["fp"], r["fn"], r["tn"]) == (2, 1, 1, 2)
    assert r["precision"] == pytest.approx(2 / 3) and r["recall"] == pytest.approx(2 / 3) and r["f"] == pytest.approx(2 / 3)


def test_f_beta_weighs_recall_or_precision():
    r1, r2, r05 = (m.prf([1, 1, 1, 0], [1, 1, 1, 1], beta=b) for b in (1, 2, 0.5))  # precision 3/4, recall 1
    assert r1["f"] == pytest.approx(2 * 0.75 / 1.75)
    assert r2["f"] == pytest.approx(0.9375) and r05["f"] == pytest.approx(0.9375 / 1.1875)
    assert r2["f"] > r1["f"] > r05["f"]  # recall is perfect, so weighting recall helps


def test_never_saying_yes_scores_zero_not_nan():
    r = m.prf([1, 1, 0], [0, 0, 0])
    assert r["precision"] == r["recall"] == r["f"] == 0.0


def test_auc_matches_the_scikit_learn_documentation_example():
    y, s = [0, 0, 1, 1], [0.1, 0.4, 0.35, 0.8]
    assert m.roc_auc(y, s) == pytest.approx(0.75) and m.pr_auc(y, s) == pytest.approx(0.8333, abs=1e-3)


def test_a_perfect_ranking_scores_one_and_a_constant_scores_chance():
    y = [0, 0, 0, 1, 1]
    assert m.roc_auc(y, [1, 2, 3, 4, 5]) == 1.0 and m.pr_auc(y, [1, 2, 3, 4, 5]) == 1.0
    assert m.roc_auc(y, [1] * 5) == 0.5 and m.pr_auc(y, [1] * 5) == pytest.approx(0.4)  # chance is the share of positives


Y, S = [0, 0, 1, 1, 1], [0.1, 0.2, 0.6, 0.7, 0.9]


def test_best_threshold_finds_the_clean_cut():
    best = m.best_threshold(Y, S)
    assert best["threshold"] == 0.6 and best["f"] == 1.0 and best["precision"] == 1.0 and best["recall"] == 1.0


def test_best_threshold_moves_with_beta():
    y, s = [1, 1, 1, 0, 0, 1, 0, 0], [0.9, 0.8, 0.55, 0.5, 0.45, 0.4, 0.3, 0.1]
    assert m.best_threshold(y, s, beta=2)["recall"] >= m.best_threshold(y, s, beta=0.5)["recall"]
    assert m.best_threshold(y, s, beta=0.5)["precision"] >= m.best_threshold(y, s, beta=2)["precision"]


def test_operating_points_at_a_target():
    assert m.at_recall(Y, S, 0.5) == {"threshold": 0.6, "precision": 1.0, "recall": 1.0}
    assert m.at_precision(Y, S, 1.0)["recall"] == 1.0
    assert m.at_precision([1, 0], [0.1, 0.9], 0.9) is None  # no threshold is that precise


# ---- several classes ---------------------------------------------------------------------------------------------
def test_multiclass_matches_a_hand_count():
    r = m.multiclass(list("aabbc"), list("abbba"), labels=list("abc"))
    assert r["per_class"]["a"]["precision"] == 0.5 and r["per_class"]["a"]["recall"] == 0.5
    assert r["per_class"]["b"]["f1"] == pytest.approx(0.8) and r["per_class"]["c"]["f1"] == 0.0
    assert r["macro_f1"] == pytest.approx((0.5 + 0.8 + 0.0) / 3) and r["accuracy"] == pytest.approx(0.6)
    assert r["confusion"] == [[1, 1, 0], [0, 2, 0], [1, 0, 0]]


def test_a_label_that_never_occurs_does_not_drag_the_macro_score():
    with_unused = m.multiclass(list("aabbc"), list("abbba"), labels=list("abcd"))
    assert with_unused["macro_f1"] == pytest.approx((0.5 + 0.8 + 0.0) / 3)


def test_one_vs_rest_scores_a_perfect_classifier_one():
    y = ["a", "b", "c", "a", "b", "c"]
    scores = {"a": [1, 0, 0, 1, 0, 0], "b": [0, 1, 0, 0, 1, 0], "c": [0, 0, 1, 0, 0, 1]}
    r = m.one_vs_rest(y, scores)
    assert r["macro_roc_auc"] == 1.0 and r["macro_pr_auc"] == 1.0 and set(r["per_class"]) == {"a", "b", "c"}


# ---- probabilities ----------------------------------------------------------------------------------------------------
def test_brier_by_hand():
    assert m.brier([1, 0], [0.8, 0.3]) == pytest.approx((0.04 + 0.09) / 2)


def test_ece_is_small_when_calibrated_and_large_when_overconfident():
    rng = np.random.default_rng(0)
    p = rng.random(50_000)
    y = rng.random(50_000) < p
    assert m.ece(y, p) < 0.01
    assert m.ece(rng.random(10_000) < 0.5, np.full(10_000, 0.9)) == pytest.approx(0.4, abs=0.02)


def test_reliability_bins_account_for_every_row():
    rng = np.random.default_rng(1)
    p = rng.random(1000)
    rows = m.reliability(rng.random(1000) < p, p)
    assert sum(r["n"] for r in rows) == 1000 and all(r["low"] <= r["mean_p"] <= r["high"] for r in rows)
    assert m.reliability([1, 0], [1.0, 0.0])[-1]["high"] == 1.0  # a probability of exactly 1 lands in the last bin


# ---- ranking ------------------------------------------------------------------------------------------------------------
def test_pairwise_accuracy_counts_ties_as_half():
    assert m.pairwise_accuracy([2, 1, 1], [1, 2, 1], [True, False, True]) == pytest.approx((1 + 1 + 0.5) / 3)


def test_kendall_tau_b_and_spearman():
    assert m.kendall_tau_b([1, 2, 3, 4], [1, 3, 2, 4]) == pytest.approx(4 / 6)  # 5 concordant pairs, 1 discordant
    assert m.kendall_tau_b([1, 2, 3], [3, 2, 1]) == -1.0 and m.spearman([1, 2, 3], [10, 20, 30]) == 1.0


def test_ndcg_perfect_order_is_one_and_reversed_matches_the_hand_value():
    assert m.ndcg_at_k([3, 2, 0], [3, 2, 1]) == pytest.approx(1.0)
    ideal = 3 + 2 / np.log2(3)
    assert m.ndcg_at_k([3, 2, 0], [1, 2, 3]) == pytest.approx((0 + 2 / np.log2(3) + 3 / 2) / ideal)


# ---- clusters -----------------------------------------------------------------------------------------------------------
def test_identical_clusterings_score_one_everywhere():
    t = [0, 0, 1, 1, 2]
    assert m.cluster_pairs(t, ["a", "a", "b", "b", "c"])["f1"] == 1.0
    assert m.bcubed(t, ["a", "a", "b", "b", "c"])["f1"] == 1.0 and m.ari(t, ["a", "a", "b", "b", "c"]) == 1.0


def test_one_big_cluster_has_perfect_recall_and_poor_precision():
    t, p = [0, 0, 1, 1], [9, 9, 9, 9]
    pairs, cubed = m.cluster_pairs(t, p), m.bcubed(t, p)
    assert pairs["recall"] == 1.0 and pairs["precision"] == pytest.approx(2 / 6)  # 2 right pairs out of 6 put together
    assert cubed["recall"] == 1.0 and cubed["precision"] == pytest.approx(0.5) and m.ari(t, p) == 0.0


def test_all_singletons_have_vacuous_precision_and_no_recall():
    t, p = [0, 0, 1, 1], [1, 2, 3, 4]
    pairs, cubed = m.cluster_pairs(t, p), m.bcubed(t, p)
    assert pairs["precision"] == 1.0 and pairs["recall"] == 0.0 and pairs["f1"] == 0.0
    assert cubed["precision"] == 1.0 and cubed["recall"] == pytest.approx(0.5)


# ---- how sure are we ------------------------------------------------------------------------------------------------------
def test_bootstrap_interval_has_the_width_theory_predicts_and_is_repeatable():
    y = (np.random.default_rng(1).random(400) < 0.8).astype(float)
    ci = m.bootstrap_ci(np.mean, y)
    half = (ci.hi - ci.lo) / 2
    assert ci.lo <= ci.point <= ci.hi and half == pytest.approx(1.96 * np.sqrt(y.mean() * (1 - y.mean()) / 400), rel=0.2)
    assert m.bootstrap_ci(np.mean, y) == ci


def test_bootstrap_skips_resamples_the_metric_cannot_score_but_not_forever():
    y = np.array([1] + [0] * 19)
    s = np.random.default_rng(0).random(20)
    ci = m.bootstrap_ci(m.roc_auc, y, s)  # about a third of resamples have no positive and are skipped
    assert 0 <= ci.lo <= ci.hi <= 1
    with pytest.raises(ValueError):
        m.bootstrap_ci(m.roc_auc, np.zeros(20), s)


def test_paired_bootstrap_separates_a_good_scorer_from_a_random_one_and_not_from_itself():
    rng = np.random.default_rng(2)
    y = (rng.random(300) < 0.4).astype(int)
    good, noise = y + rng.normal(0, 0.4, 300), rng.random(300)
    diff = m.paired_bootstrap_diff(m.roc_auc, y, good, noise)
    assert diff.point > 0.2 and diff.lo > 0
    same = m.paired_bootstrap_diff(m.roc_auc, y, good, good)
    assert same.point == same.lo == same.hi == 0
