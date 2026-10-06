import dataclasses
import json
import math

import numpy as np
import pytest

from models.tickets import settings as S
from models.tickets.eval.common import metrics as M
from models.tickets.eval.ranking import aggregate as ag
from models.tickets.eval.ranking import evaluate as ev
from models.tickets.eval.ranking import pairs
from models.tickets.eval.ranking.tests.helpers import tiny_survey
from models.tickets.ranking import lifecycle, priority
from models.tickets.types import TicketFacts

A, B, T = ag.A, ag.B, ag.TIE


@pytest.fixture(scope="module")
def survey():
    return ag.load()


@pytest.fixture(scope="module")
def labels(survey):
    return ag.label_pairs(survey)


def ticket(category="pothole", reporters=1, gone_votes=0, days_open=0, foot_traffic=0.5, danger=False, place=None):
    return {"category": category, "reporters": reporters, "gone_votes": gone_votes, "days_open": days_open, "foot_traffic": foot_traffic, "danger": danger, "place": place}


def direct_score(t) -> float:
    """priority.score called by hand, so a test does not lean on the code under test."""
    return priority.score(TicketFacts(t["category"], t["reporters"], t["gone_votes"], t["days_open"], t["foot_traffic"], t["danger"])).score


# four hand-made tickets: dashboard severity 3 / 3 / 2 / 1
HAND = [ticket("open_manhole", 1, 0, 3, 0.2), ticket("flooded_drain", 8, 0, 10, 0.9), ticket("pothole", 2, 0, 20, 0.5), ticket("other", 1, 0, 0, 0.1)]


# ---- running the real score under other settings ----------------------------------------------------------------------
def test_override_puts_settings_back_even_when_the_call_fails():
    before = S.DANGER_BONUS
    with pytest.raises(RuntimeError):
        with ev.override(DANGER_BONUS=99.0):
            assert S.DANGER_BONUS == 99.0
            raise RuntimeError
    assert S.DANGER_BONUS == before
    with ev.override(DANGER_BONUS=1.0):
        with ev.override(DANGER_BONUS=2.0):
            assert S.DANGER_BONUS == 2.0
        assert S.DANGER_BONUS == 1.0
    assert S.DANGER_BONUS == before
    with pytest.raises(AttributeError):
        with ev.override(NO_SUCH_SETTING=1):
            pass


def test_the_score_is_recomputed_from_the_attributes_not_read_from_the_key(survey):
    assert [ev.shipped([t])[0] for t in survey.truth[:20]] == [priority.score(ev.facts_of(t)) for t in survey.truth[:20]]
    assert np.array_equal(ev.score_array(survey.truth), [direct_score(t) for t in survey.truth])
    noted = [k for k, t in enumerate(survey.truth) if t["danger"] and t["score"] < 80]
    changed = ev.score_array(survey.truth, DANGER_BONUS=0.0)
    assert all(changed[k] < ev.score_array(survey.truth)[k] for k in noted)  # a change of setting moves the score, whatever the key says


def test_a_variant_leaves_the_settings_alone():
    before = (dict(S.WEIGHTS), S.GATE_MIN)
    t = ticket("pothole", 1, 3, 0, 0.5)
    assert ev.score_array([t], GATE_MIN=1.0)[0] > ev.score_array([t])[0]
    assert (dict(S.WEIGHTS), S.GATE_MIN) == before


def value_of(t) -> float:
    """The weighted sum of the four parts, before gate, floor and bonus, by hand from the settings."""
    parts = (S.SEVERITY[t["category"]], min(1.0, math.log2(max(t["reporters"], 1)) / math.log2(S.REPORTS_FULL_AT)), t["foot_traffic"], min(1.0, t["days_open"] / S.WAITING_FULL_DAYS))
    return 100 * sum(S.WEIGHTS[p] * v for p, v in zip(ev.PARTS, parts))


def test_each_ablation_switches_off_exactly_one_thing():
    plain = ticket("other", 1, 0, 0, 0.1, danger=True)
    assert ev.score_array([plain])[0] - ev.score_array([plain], **ev.ablation_settings()["drop the danger bonus"])[0] == pytest.approx(S.DANGER_BONUS)
    manhole = ticket("open_manhole", 1, 0, 0, 0.1)  # a fresh single report: gate 1, value below the floor
    assert value_of(manhole) < S.FLOORS["open_manhole"]
    assert ev.score_array([manhole])[0] == pytest.approx(S.FLOORS["open_manhole"])
    assert ev.score_array([manhole], **ev.ablation_settings()["drop the floors"])[0] == pytest.approx(value_of(manhole))
    gone = ticket("pothole", 1, 3, 0, 0.5)
    gate = lifecycle.gate(lifecycle.belief(1, 3))
    assert gate < 1 and ev.score_array([gone])[0] == pytest.approx(gate * value_of(gone))
    assert ev.score_array([gone], **ev.ablation_settings()["drop the gate"])[0] == pytest.approx(value_of(gone))
    assert ev.score_array([gone], **ev.ablation_settings()["drop gate, floors and bonus"])[0] == pytest.approx(value_of(gone))


def test_dropping_a_part_rescales_the_other_weights_to_sum_to_one():
    for part in ev.PARTS:
        w = ev.renormalised(part)
        kept = [p for p in ev.PARTS if p != part]
        assert w[part] == 0.0 and sum(w.values()) == pytest.approx(1.0)
        assert [w[p] / S.WEIGHTS[p] for p in kept] == pytest.approx([w[kept[0]] / S.WEIGHTS[kept[0]]] * 3)  # every kept weight scaled alike
    with ev.override(WEIGHTS={"danger": 0.5, "reports": 0.2, "foot_traffic": 0.18, "waiting": 0.12}):
        assert ev.renormalised("danger") == pytest.approx({"danger": 0.0, "reports": 0.4, "foot_traffic": 0.36, "waiting": 0.24})
    assert set(ev.ablation_settings()) >= {f"drop {p.replace('_', ' ')} part" for p in ev.PARTS}


def test_ablating_a_part_equals_scoring_with_that_weight_at_zero():
    t = ticket("pothole", 4, 0, 9, 0.7)
    zero = {**S.WEIGHTS, "waiting": 0.0}
    total = sum(zero.values())
    assert ev.score_array([t], **ev.ablation_settings()["drop waiting part"])[0] == pytest.approx(ev.score_array([t], WEIGHTS={k: v / total for k, v in zero.items()})[0])


def test_ablation_settings_do_not_touch_the_settings_module():
    before = (dict(S.WEIGHTS), dict(S.FLOORS), S.DANGER_BONUS, S.GATE_MIN)
    ev.ablation_keys(HAND)
    assert (dict(S.WEIGHTS), dict(S.FLOORS), S.DANGER_BONUS, S.GATE_MIN) == before


# ---- the baselines ----------------------------------------------------------------------------------------------------
def test_dashboard_severity_is_the_servers_one_to_three():
    severity = ev.dashboard_severity()
    assert [severity(c) for c in ("open_manhole", "flooded_drain", "pothole", "broken_streetlight", "blocked_sidewalk", "other")] == [3, 3, 2, 2, 2, 1]
    assert severity("something else") == 1


def test_comparators_on_hand_made_tickets():
    keys = ev.comparator_keys(HAND)
    assert list(keys) == [ev.SHIPPED, "severity only", "reports only", "foot traffic only", "waiting only", "dashboard order", "random",
                          "reports only (uncapped count)", "waiting only (uncapped days)"]
    assert keys["severity only"].tolist() == [S.SEVERITY[t["category"]] for t in HAND]
    people, cap = [1, 8, 2, 1], math.log2(S.REPORTS_FULL_AT)
    assert keys["reports only"] == pytest.approx([min(1.0, math.log2(p) / cap) for p in people])  # log scale, at most 1
    assert keys["foot traffic only"].tolist() == [0.2, 0.9, 0.5, 0.1]
    assert keys["waiting only"] == pytest.approx([min(1.0, d / S.WAITING_FULL_DAYS) for d in (3, 10, 20, 0)])  # days over the cap, at most 1
    assert keys["reports only (uncapped count)"].tolist() == [1, 8, 2, 1] and keys["waiting only (uncapped days)"].tolist() == [3, 10, 20, 0]
    assert keys["random"].tolist() == [0, 0, 0, 0]
    assert keys[ev.SHIPPED].tolist() == [direct_score(t) for t in HAND]


def test_dashboard_order_is_severity_then_oldest():
    keys = ev.dashboard_keys(HAND)
    assert keys.tolist() == [2, 3, 1, 0]  # (3, 3 days) < (3, 10 days), and a severity 3 beats a severity 2 that has waited 20 days
    same = ev.dashboard_keys([ticket("pothole", days_open=5), ticket("broken_streetlight", days_open=5), ticket("blocked_sidewalk", days_open=6)])
    assert same[0] == same[1] < same[2]  # the same integer severity and age: no preference. The third is a day older, so it comes first
    two = ev.dashboard_keys([ticket("open_manhole", 12, days_open=1, foot_traffic=0.99, danger=True), ticket("flooded_drain", 1, days_open=2, foot_traffic=0.1)])
    assert two[1] > two[0]  # both severity 3: only age separates them, however many people reported the manhole


def test_each_baseline_is_called_for_the_ticket_with_the_larger_number():
    keys = ev.comparator_keys(HAND)
    first, second = np.array([0, 1, 2]), np.array([1, 2, 3])  # t0 v t1, t1 v t2, t2 v t3
    wins = np.array([True, False, True])  # the panel picked t0, then t2, then t2
    accuracy = {n: M.pairwise_accuracy(k[first], k[second], wins) for n, k in keys.items()}
    assert accuracy["severity only"] == pytest.approx(2 / 3)  # t0 over t1 right, t1 over t2 wrong, t2 over t3 right
    assert accuracy["dashboard order"] == pytest.approx(1 / 3)  # keys 2 v 3: t1, wrong. 3 v 1: t1, wrong. 1 v 0: t2, right
    assert accuracy["foot traffic only"] == pytest.approx(1 / 3)  # 0.2 v 0.9: t1 wrong. 0.9 v 0.5: t1 wrong. 0.5 v 0.1: t2 right
    assert accuracy["random"] == 0.5


def test_a_comparator_that_cannot_tell_two_tickets_apart_gets_half_a_point():
    z = np.zeros(10)
    assert M.pairwise_accuracy(z, z, [True, False] * 5) == 0.5
    assert ev.acc_of_diff([True, True, False, False], [2.0, -1.0, 0.0, -3.0]) == pytest.approx((1 + 0 + 0.5 + 1) / 4)
    assert ev.acc_of_diff([True, False, True, False], [0.0, 0.0, 0.0, 0.0]) == 0.5


def test_paired_differences_have_the_stated_sign_and_orientation(survey, labels):
    keys = {ev.SHIPPED: ev.score_array(survey.truth), "random": np.zeros(len(survey.truth))}
    mask = ev.pair_mask(survey, labels, "all")
    wins = labels.winner[mask] == A
    block = ev.compare_block(survey, labels, "all", keys, boot=100)["majority"]["rows"]["random"]["reference_minus_this"]
    assert block["point"] == pytest.approx(ev.accuracy_ci(keys[ev.SHIPPED], survey, mask, wins, 10).point - 0.5) and block["lo"] > 0
    flipped = ev.compare_block(survey, labels, "all", keys, reference="random", reference_first=False, boot=100)["majority"]["rows"][ev.SHIPPED]["this_minus_reference"]
    assert flipped["point"] == pytest.approx(block["point"])  # shipped minus random either way you ask


# ---- the splits each number is on --------------------------------------------------------------------------------------
def test_pair_masks_hold_only_the_pairs_of_the_split_they_name(survey, labels):
    for split, n in {"train": 141, "validation": 48, "test": 46, "all": 235}.items():
        mask = ev.pair_mask(survey, labels, split)
        assert mask.sum() == n and survey.base[mask].all()
        if split != "all":
            assert set(survey.split[mask]) == {split}
            assert set(survey.ticket_split[survey.a[mask]]) == set(survey.ticket_split[survey.b[mask]]) == {split}
            assert ev.ticket_mask(survey, split).sum() == (120 if split == "train" else 40)
    assert ev.ticket_mask(survey, "all").sum() == 200
    for split in ("test", "validation"):  # the label sets are nested
        sets = [ev.pair_mask(survey, labels, split, s).sum() for s in ev.SUBSETS]
        assert sets[0] >= sets[1] >= sets[2] > 0
    with pytest.raises(ValueError):
        ev.pair_mask(survey, labels, "dev")
    with pytest.raises(ValueError):
        ev.ticket_mask(survey, "everything")


def flip(choice):
    return np.where(choice == T, T, 1 - choice)


def test_test_numbers_do_not_move_when_other_splits_are_rated_differently(survey, labels):
    key = ev.score_array(survey.truth)
    before = ev.headline(survey, labels, key, "test", boot=30)
    outside = survey.split != "test"
    other = dataclasses.replace(survey, choice=np.where(outside[:, None], flip(survey.choice), survey.choice))
    assert ev.headline(other, ag.label_pairs(other), key, "test", boot=30) == before
    inside = dataclasses.replace(survey, choice=np.where(~outside[:, None], flip(survey.choice), survey.choice))
    after = ev.headline(inside, ag.label_pairs(inside), key, "test", boot=30)
    assert after["majority"]["accuracy"]["point"] == pytest.approx(1 - before["majority"]["accuracy"]["point"])  # every test label reversed


def test_ticket_metrics_use_only_the_tickets_of_the_split(survey):
    key = ev.score_array(survey.truth)
    before = ev.ticket_metrics(survey, key, "test", boot=30)
    outside = survey.ticket_split != "test"
    changed = dataclasses.replace(survey, urgency=np.where(outside[:, None], 6 - survey.urgency, survey.urgency))
    assert ev.ticket_metrics(changed, key, "test", boot=30) == before
    assert before["n_tickets"] == 40 and ev.ticket_metrics(survey, key, "all", boot=30)["n_tickets"] == 200


def test_headline_agrees_with_a_direct_count_from_the_derived_files(survey, labels):
    """Pairwise accuracy on the test split counted from consensus.json labels and priority.score called by hand."""
    doc = json.loads((pairs.DATA / "consensus.json").read_text())
    key = json.loads((pairs.DATA / "answer_key.json").read_text())
    hits = total = 0
    for pid, p in doc["pairs"].items():
        if p["split"] != "test" or p["label"] is None:
            continue
        a, b = key["pair_truth"][pid]["a_ticket"], key["pair_truth"][pid]["b_ticket"]
        hits += (direct_score(key["ticket_truth"][a]) > direct_score(key["ticket_truth"][b])) == (p["label"] == "A")
        total += 1
    head = ev.headline(survey, labels, ev.score_array(survey.truth), "test", boot=30)["majority"]
    assert head["n_pairs"] == total == 46 and head["accuracy"]["point"] == pytest.approx(hits / total)
    mask = ev.pair_mask(survey, labels, "test")
    assert head["ceiling"]["point"] == pytest.approx(ag.ceiling(survey.choice[mask]))
    assert head["ratio_to_ceiling"]["point"] == pytest.approx(head["accuracy"]["point"] / head["ceiling"]["point"])


def test_headline_ceilings_rise_with_agreement_and_unanimous_ones_are_perfect(survey, labels):
    head = ev.headline(survey, labels, ev.score_array(survey.truth), "test", boot=30)
    assert head["unanimous"]["ceiling"]["point"] == 1.0
    assert head["majority"]["ceiling"]["point"] < head["consensus"]["ceiling"]["point"] < head["unanimous"]["ceiling"]["point"]
    assert [head[s]["n_pairs"] for s in ev.SUBSETS] == [46, 41, 31]
    assert all(head[s]["split"] == "test" for s in ev.SUBSETS)


def test_like_for_like_ratio_is_above_one_for_a_scorer_that_always_matches_the_panel():
    """The raters are sometimes outvoted by the others; a scorer that always takes the panel's side is never wrong, so it beats them."""
    choice = np.array([[A] * 5, [B] * 5, [A, A, A, A, B], [B, B, B, B, A]] * 5)
    sa = np.where((choice == A).sum(1) > 2, 1.0, 0.0)
    assert ev.vs_loro(sa, 1.0 - sa, choice) > 1.0
    assert ev.vs_loro(np.zeros(len(choice)), np.zeros(len(choice)), choice) == pytest.approx(0.5 / ag.ceiling(choice))  # a scorer that always ties gets half


def test_dyadic_interval_handles_pairs_that_share_a_ticket():
    """Eight pairs that all contain ticket 0: they are far from independent, and the interval is for the mean over them."""
    a, b = np.zeros(8, int), np.arange(1, 9)
    correct = np.array([1, 1, 1, 1, 0, 0, 0, 0], float)
    dyadic = ev.dyadic_ci(correct, a, b, boot=1000)
    assert dyadic.point == 0.5 and dyadic.lo <= 0.5 <= dyadic.hi
    assert ev.dyadic_ci(np.ones(8), a, b, boot=200).lo == ev.dyadic_ci(np.ones(8), a, b, boot=200).hi == 1.0
    assert ev.dyadic_ci(correct, a, b, boot=300) == ev.dyadic_ci(correct, a, b, boot=300)  # repeatable


def test_dyadic_interval_is_wider_than_the_pair_bootstrap_on_the_real_test_pairs(survey, labels):
    key = ev.score_array(survey.truth)
    head = ev.headline(survey, labels, key, "test", boot=400)["majority"]
    plain, dyadic = head["accuracy"], head["accuracy_ticket_resampled"]
    assert dyadic["point"] == plain["point"] and dyadic["hi"] - dyadic["lo"] > plain["hi"] - plain["lo"]


# ---- sensitivity -----------------------------------------------------------------------------------------------------
def test_perturbed_weights_stay_within_the_spread_and_sum_to_one():
    rng = np.random.default_rng(0)
    for _ in range(200):
        w = ev.perturbed(rng, S.WEIGHTS, 0.30)
        assert sum(w.values()) == pytest.approx(1.0) and set(w) == set(S.WEIGHTS)
    assert ev.perturbed(np.random.default_rng(1), {"a": 1.0, "b": 1.0}, 0.0) == {"a": 0.5, "b": 0.5}
    ratios = [(lambda w: w["danger"] / w["reports"] / (S.WEIGHTS["danger"] / S.WEIGHTS["reports"]))(ev.perturbed(np.random.default_rng(s), S.WEIGHTS, 0.30)) for s in range(300)]
    assert max(ratios) <= 1.3 / 0.7 + 1e-9 and min(ratios) >= 0.7 / 1.3 - 1e-9  # a ratio of two weights moves by at most 1.3 / 0.7


def test_sensitivity_is_repeatable_and_zero_spread_changes_nothing(survey, labels):
    first = ev.sensitivity(survey, labels, "test", n=15)
    assert first == ev.sensitivity(survey, labels, "test", n=15)
    assert first["split"] == "test" and first["n_pairs"] == 46 and len(first["accuracy_values"]) == len(first["tau_values"]) == 15
    assert first["accuracy"]["min"] <= first["accuracy"]["median"] <= first["accuracy"]["max"] and -1 <= first["kendall_tau_vs_shipped_ranking"]["min"]
    zero = ev.sensitivity(survey, labels, "test", n=5, spread=0.0)
    assert zero["accuracy"]["min"] == zero["accuracy"]["max"] == pytest.approx(zero["shipped_accuracy"])
    assert zero["kendall_tau_vs_shipped_ranking"]["min"] == pytest.approx(1.0)


# ---- disagreements and patterns ----------------------------------------------------------------------------------------------
def hand_survey():
    truth = [ticket("open_manhole", danger=True), ticket("flooded_drain"), ticket("pothole", place="School"), ticket("other")]
    # p0: t0 v t1, 5-0 for A.  p1: t2 v t3, 3-2 for B.  p2: t0 v t3, 4-1 for A.  p3: t1 v t2, 5-0 for B.
    choice = [[A] * 5, [B, B, B, A, A], [A, A, A, A, B], [B] * 5]
    return tiny_survey(choice, a=[0, 2, 0, 1], b=[1, 3, 3, 2], repeat_of=[-1] * 4, truth=truth)


def test_disagreements_list_the_pairs_where_the_score_picks_the_other_ticket():
    s = hand_survey()
    labels = ag.label_pairs(s)
    key = np.array([1.0, 2.0, 3.0, 4.0])  # score: t1 over t0 (raters t0), t3 over t2 (raters t3), t3 over t0 (raters t0), t2 over t1 (raters t2)
    out = ev.disagreements(s, labels, key, "test")
    assert out["labelled_pairs"] == 4 and out["total"] == 2
    assert [r["pair"] for r in out["pairs"]] == ["p0", "p2"]  # the 5-0 first, then the 4-1
    first = out["pairs"][0]
    assert first["votes_for_raters_pick"] == 5 and first["raters_chose"]["ticket"] == "t0" and first["score_chose"]["ticket"] == "t1"
    assert first["raters_chose"]["score"] == 1.0 and first["score_chose"]["score"] == 2.0 and first["score_gap"] == 1.0
    assert first["raters_chose"]["description"] == "ticket 0" and first["raters_chose"]["danger_note"] is True
    assert ev.disagreements(s, labels, key, "test", limit=1)["listed"] == 1 and ev.disagreements(s, labels, key, "test", limit=0)["pairs"] == []


def test_a_tied_score_counts_as_a_disagreement_and_split_votes_are_not_listed():
    s = hand_survey()
    assert ev.disagreements(s, ag.label_pairs(s), np.zeros(4), "test")["total"] == 4
    even = tiny_survey([[A, A, B, B, T]], a=[0], b=[1], repeat_of=[-1])  # no majority: no label, nothing to disagree with
    assert ev.disagreements(even, ag.label_pairs(even), np.zeros(2), "test")["total"] == 0


def test_pattern_summary_counts_what_each_side_has_in_common():
    s = hand_survey()
    out = ev.disagreements(s, ag.label_pairs(s), np.array([1.0, 2.0, 3.0, 4.0]), "test")["pattern"]
    assert out["n"] == 2 and out["raters_chose_category"]["open_manhole"] == 2
    assert out["score_chose_category"] == {**{c: 0 for c in ev.CATEGORIES}, "flooded_drain": 1, "other": 1}
    assert out["danger_note"] == {"raters_chose": 2, "score_chose": 0} and out["no_named_place"] == {"raters_chose": 2, "score_chose": 2}


def test_lean_by_hand():
    """Four pairs, each with exactly one ticket that has the feature. The labeller picks the ticket that has it in 3, the score in 2."""
    truth = [{"f": True}, {"f": False}, {"f": True}, {"f": False}]
    s = tiny_survey([[A] * 5] * 4, a=[0, 2, 0, 2], b=[1, 3, 3, 1], repeat_of=[-1] * 4, truth=truth)
    out = ev.lean(s, np.array([5.0, 4.0, 3.0, 4.0]), np.arange(4), np.array([A, B, A, A]), lambda t: t["f"], boot=50)
    assert out["n"] == 4 and out["labeller_picks_it"] == 0.75 and out["score_picks_it"] == 0.5 and out["gap"]["point"] == 0.25
    assert ev.lean(s, np.zeros(4), np.arange(4), np.array([A, B, A, A]), lambda t: t["f"], boot=50)["score_picks_it"] == 0.5  # a tied score picks neither
    assert ev.lean(s, np.zeros(4), np.arange(4), np.array([A] * 4), lambda t: True, boot=50) == {"n": 0}  # every ticket has it: no pair differs


def test_lean_ignores_pairs_where_both_or_neither_ticket_has_the_feature():
    truth = [{"f": True}, {"f": True}, {"f": False}, {"f": False}]
    s = tiny_survey([[A] * 5] * 2, a=[0, 2], b=[1, 3], repeat_of=[-1, -1], truth=truth)
    assert ev.lean(s, np.arange(4.0), np.arange(2), np.array([A, A]), lambda t: t["f"], boot=20) == {"n": 0}


def test_features_cover_the_caveats_and_the_kinds_of_hazard():
    five = ("has a danger note", "has 'gone' votes", "has a named place nearby", "open past the waiting cap", "labelled a very busy area")
    assert set(five) <= set(ev.FEATURES) and {f"is a {c}" for c in ev.CATEGORIES} <= set(ev.FEATURES)
    assert all(ev.FEATURES[f](ticket(days_open=S.WAITING_FULL_DAYS + 1, foot_traffic=0.7, gone_votes=1, danger=True, place="Park")) for f in five)
    edge = ticket(days_open=S.WAITING_FULL_DAYS, foot_traffic=0.65)
    assert not ev.FEATURES["open past the waiting cap"](edge) and not ev.FEATURES["labelled a very busy area"](edge)  # up to 0.65 is a moderately busy street


# ---- personas ----------------------------------------------------------------------------------------------------------------
def test_persona_block_uses_the_pairs_of_its_split_where_nobody_tied(survey):
    key = ev.score_array(survey.truth)
    out = ev.persona_block(survey, key, "test", boot=30)
    rows = survey.base & (survey.split == "test") & (survey.choice != T).all(axis=1)
    assert out["split"] == "test" and out["n_pairs"] == rows.sum() and all(out[n]["accuracy"]["point"] > 0.5 for n in survey.raters)
    assert ev.persona_block(survey, key, "all", boot=30)["n_pairs"] == (survey.base & (survey.choice != T).all(axis=1)).sum()


def test_persona_accuracy_is_the_score_against_that_personas_own_choices(survey):
    key = ev.score_array(survey.truth)
    out = ev.by_rater(survey, key, "test", boot=30)
    mask = survey.base & (survey.split == "test") & (survey.choice[:, 2] != T)
    expected = M.pairwise_accuracy(key[survey.a[mask]], key[survey.b[mask]], survey.choice[mask, 2] == A)
    assert out["wheelchair"]["accuracy"]["point"] == pytest.approx(expected) and out["wheelchair"]["n_pairs"] == mask.sum()
    assert all(0.6 < r["accuracy"]["point"] < 0.9 for r in ev.by_rater(survey, key, "all", boot=30).values())


# ---- the targets ----------------------------------------------------------------------------------------------------------------
def ci(point, lo, hi):
    return {"point": point, "lo": lo, "hi": hi}


def test_target_rows_say_met_or_missed_and_whether_the_interval_clears():
    head = {s: {"n_pairs": n, "accuracy": ci(acc, acc - 0.1, acc + 0.1), "ratio_to_ceiling": ci(acc / 0.9, 0.7, 1.2), "ratio_to_ceiling_like_for_like": ci(0.95, 0.9, 1.0),
                "ceiling": ci(0.9, 0.85, 0.95)} for s, n, acc in (("majority", 46, 0.783), ("consensus", 41, 0.805), ("unanimous", 31, 0.95))}
    tickets = {"n_tickets": 40, "kendall_tau_b": ci(0.584, 0.4, 0.7), "ndcg_at_10": ci(0.945, 0.9, 0.98)}
    base = {s: {"n_pairs": 10, "rows": {"severity only": {"reference_minus_this": ci(0.3, 0.1, 0.4)}, "dashboard order": {"reference_minus_this": ci(0.3, -0.05, 0.4)}}} for s in ev.SUBSETS}
    fit = {"decision": {"margin": 0.03, "validation_gain": 0.0417, "replace": True, "non_negative": True}}
    rows = ev.target_rows(head, tickets, base, fit)
    pick = lambda name, labels="majority": next(r for r in rows if r["target"].startswith(name) and r.get("labels", "majority") == labels)
    assert not pick("pairwise accuracy")["met"] and pick("pairwise accuracy")["shortfall"] == pytest.approx(0.017)
    assert pick("pairwise accuracy", "consensus")["met"] and not pick("pairwise accuracy", "consensus")["interval_clears"]  # 0.805 reaches 0.80, its lower end 0.705 does not
    assert pick("pairwise accuracy", "unanimous")["met"] and pick("pairwise accuracy", "unanimous")["interval_clears"]
    assert not pick("accuracy >= 0.90 x leave-one-rater-out")["met"] and pick("accuracy >= 0.90 x leave-one-rater-out", "unanimous")["met"]
    assert not pick("Kendall")["met"] and pick("NDCG")["met"]
    assert pick("beats severity only")["met"] and not pick("beats dashboard order")["met"]  # an interval that includes 0 does not beat it
    assert pick("fitted weights")["met"] and pick("fitted weights")["replace"]
    assert not any(r["target"].startswith("fitted") for r in ev.target_rows(head, tickets, base, None))


# ---- the whole run -----------------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def files(survey, labels):
    return ev.run(survey, labels, None, boot=20, perturbations=20)


def test_every_block_names_the_split_and_pair_count_it_is_on(files):
    score = files["ranking_score"]
    assert [score["headline"][s]["n_pairs"] for s in ev.SUBSETS] == [46, 41, 31] and all(score["headline"][s]["split"] == "test" for s in ev.SUBSETS)
    assert {s: (score["other_splits"][s]["split"], score["other_splits"][s]["n_pairs"]) for s in ("train", "validation", "all")} == {"train": ("train", 141), "validation": ("validation", 48), "all": ("all", 235)}
    assert sum(r["n_pairs"] for r in score["strata"].values()) == 46 and all(r["split"] == "test" for r in score["strata"].values())
    assert all(r["split"] == "test" for r in score["raters"].values()) and all(46 <= r["n_pairs"] <= 48 for r in score["raters"].values())
    assert (score["tickets"]["test"]["split"], score["tickets"]["test"]["n_tickets"], score["tickets"]["all"]["n_tickets"]) == ("test", 40, 200)
    assert score["recomputed_vs_stored_max_abs_difference"] >= 0.0


def test_baselines_ablations_and_sensitivity_name_their_splits(files):
    for kind in ("baselines", "ablations"):
        block = files["ranking_baselines"][kind]
        assert block["test"]["majority"]["split"] == "test" and block["test"]["majority"]["n_pairs"] == 46
        assert block["all"]["majority"]["split"] == "all" and block["all"]["majority"]["n_pairs"] == 235
    sens = files["ranking_sensitivity"]
    assert sens["split"] == "test" and sens["n_pairs"] == 46 and sens["n_perturbations"] == 20
    assert files["ranking_targets"]["split"] == "test" and files["ranking_targets"]["primary_label_set"] == "majority"


def test_disagreement_file_lists_only_test_pairs_and_matches_a_direct_count(files):
    block = files["ranking_disagreements"]["splits"]["test"]
    doc = json.loads((pairs.DATA / "consensus.json").read_text())
    key = json.loads((pairs.DATA / "answer_key.json").read_text())
    score = lambda tid: direct_score(key["ticket_truth"][tid])
    expected = sum(1 for pid, p in doc["pairs"].items() if p["split"] == "test" and p["label"] is not None
                   and (score(key["pair_truth"][pid]["a_ticket"]) > score(key["pair_truth"][pid]["b_ticket"])) != (p["label"] == "A"))
    assert block["total"] == expected and block["listed"] == len(block["pairs"]) == min(15, expected) and block["labelled_pairs"] == 46
    for row in block["pairs"]:
        assert key["pair_truth"][row["pair"]]["split"] == "test" and row["raters_chose"]["score"] < row["score_chose"]["score"]
    assert set(files["ranking_disagreements"]["splits"]) == {"test", "validation", "train"}
    assert files["ranking_disagreements"]["splits"]["train"]["labelled_pairs"] == 141 and files["ranking_disagreements"]["splits"]["validation"]["pairs"] == []
    lean = files["ranking_disagreements"]["lean_panel"]
    assert lean["train_validation"]["has a danger note"]["n"] > lean["test"]["has a danger note"]["n"]


def test_the_evidence_for_recommendations_does_not_read_the_test_split(survey, labels):
    key = ev.score_array(survey.truth)
    outside = survey.split == "test"
    changed = dataclasses.replace(survey, choice=np.where(outside[:, None], flip(survey.choice), survey.choice))
    after = ag.label_pairs(changed)
    assert ev.lean_tables(changed, after, key, ("train", "validation"), boot=20) == ev.lean_tables(survey, labels, key, ("train", "validation"), boot=20)
    assert ev.persona_lean(changed, key, ("train", "validation"), boot=20) == ev.persona_lean(survey, key, ("train", "validation"), boot=20)
    assert ev.cap_check(changed, after, key, ("train", "validation"), boot=20) == ev.cap_check(survey, labels, key, ("train", "validation"), boot=20)
    assert ev.lean_tables(changed, after, key, ("test",), boot=20) != ev.lean_tables(survey, labels, key, ("test",), boot=20)  # and the test rows do move the test lean


def test_the_shipped_score_beats_the_dashboard_and_severity_on_the_larger_sample(files):
    rows = files["ranking_baselines"]["baselines"]["all"]["majority"]["rows"]
    for name in ("severity only", "dashboard order", "random"):
        assert rows[name]["reference_minus_this"]["lo"] > 0, name
    assert math.isclose(rows["random"]["accuracy"]["point"], 0.5)


def test_every_interval_in_every_payload_is_a_finite_ordered_triple(files):
    def walk(node):
        if isinstance(node, dict):
            if {"point", "lo", "hi"} <= set(node):
                yield node
            for v in node.values():
                yield from walk(v)
    seen = 0
    for payload in files.values():
        for c in walk(payload):
            seen += 1
            assert all(np.isfinite(c[k]) for k in ("point", "lo", "hi")) and c["lo"] <= c["hi"]
    assert seen > 300


# ---- the survey's mix of pairs ---------------------------------------------------------------------------------------------------
def strata_survey():
    """Four tickets with build-time scores 0, 3, 10, 30 (gaps: 3 close; 10 and 7 between; 30, 27 and 20 clear) and six pairs, two per stratum,
    all rated unanimously. A key that always picks the lower-numbered ticket is right on the A pairs: half the clear pairs, all the close
    ones, half the trade-offs."""
    truth = [{"score": v} for v in (0.0, 3.0, 10.0, 30.0)]
    choice = [[A] * 5, [B] * 5, [A] * 5, [A] * 5, [A] * 5, [B] * 5]
    return tiny_survey(choice, a=[0, 0, 1, 1, 2, 0], b=[1, 2, 2, 3, 3, 3], repeat_of=[-1] * 6, truth=truth,
                       stratum=["clear", "clear", "close", "close", "trade_off", "trade_off"])


def test_stratum_shares_count_every_pair_of_the_splits_tickets_by_score_gap():
    shares = ev.stratum_shares(strata_survey(), "test")
    assert shares == pytest.approx({"clear": 3 / 6, "close": 1 / 6, "between": 2 / 6}) and sum(shares.values()) == pytest.approx(1.0)


def test_stratum_shares_on_the_real_survey_say_close_pairs_are_rarer_than_the_survey_drew_them(survey):
    for split in ("train", "validation", "test", "all"):
        shares = ev.stratum_shares(survey, split)
        assert sum(shares.values()) == pytest.approx(1.0) and shares["close"] < 0.25 and shares["clear"] > 0.4  # a third each is not what random pairs look like


def test_accuracy_by_stratum_by_hand():
    s = strata_survey()
    labels = ag.label_pairs(s)
    out = ev.accuracy_by_stratum(s, labels, {"lower first": np.array([4.0, 3.0, 2.0, 1.0]), "tie": np.zeros(4)}, "test")
    assert out["lower first"] == {"clear": {"n": 2, "accuracy": 0.5}, "close": {"n": 2, "accuracy": 1.0}, "trade_off": {"n": 2, "accuracy": 0.5}}
    assert all(c["accuracy"] == 0.5 for c in out["tie"].values())


def test_post_stratified_accuracy_reweights_the_strata_by_hand():
    s = strata_survey()
    labels = ag.label_pairs(s)
    keys = {"ref": np.array([4.0, 3.0, 2.0, 1.0]), "flat": np.zeros(4)}
    out = ev.post_stratified(s, labels, keys, "test", reference="ref", boot=60)
    expected = 0.5 * 0.5 + (1 / 6) * 1.0 + (2 / 6) * 0.5  # clear, close, between (treated as trade-off)
    assert out["rows"]["ref"]["accuracy"]["point"] == pytest.approx(expected) and out["ceiling"]["point"] == pytest.approx(1.0)
    assert out["rows"]["ref"]["ratio_to_ceiling"]["point"] == pytest.approx(expected)
    assert out["rows"]["flat"]["accuracy"]["point"] == pytest.approx(0.5) and out["rows"]["flat"]["minus_reference"]["point"] == pytest.approx(0.5 - expected)
    assert "minus_reference" not in out["rows"]["ref"] and out["pairs_by_stratum"] == {"clear": 2, "close": 2, "trade_off": 2} and out["split"] == "test"


def test_post_stratified_on_the_real_survey_moves_toward_the_clear_pairs(survey, labels):
    key = ev.score_array(survey.truth)
    out = ev.post_stratified(survey, labels, {ev.SHIPPED: key}, "all", boot=100)
    plain = ev.accuracy_ci(key, survey, ev.pair_mask(survey, labels, "all"), labels.winner[ev.pair_mask(survey, labels, "all")] == A, 10).point
    assert out["rows"][ev.SHIPPED]["accuracy"]["point"] > plain  # most random pairs are clear ones, which the score gets right
    assert out["pairs_by_stratum"] == {"clear": 80, "close": 75, "trade_off": 80} and sum(out["shares"].values()) == pytest.approx(1.0)


def test_targets_are_also_read_for_the_fitted_weights_when_a_fit_is_given(survey, labels):
    fitted = {"danger": 0.3, "reports": 0.2, "foot_traffic": 0.3, "waiting": 0.2}
    fit_result = {"decision": {"margin": 0.03, "validation_gain": 0.05, "replace": True, "non_negative": True}, "bradley_terry": {"fitted_weights": fitted}}
    out = ev.run(survey, labels, fit_result, boot=20, perturbations=5)["ranking_targets"]
    assert "rows_if_fitted_weights_adopted" in out and len(out["rows_if_fitted_weights_adopted"]) == len(out["rows"]) - 1  # no weights row the second time
    key = ev.score_array(survey.truth, WEIGHTS=fitted)
    mask = ev.pair_mask(survey, labels, "test")
    expected = M.pairwise_accuracy(key[survey.a[mask]], key[survey.b[mask]], labels.winner[mask] == A)
    row = next(r for r in out["rows_if_fitted_weights_adopted"] if r["target"] == "pairwise accuracy >= 0.80" and r["labels"] == "majority")
    assert row["value"] == pytest.approx(expected)
    assert "rows_if_fitted_weights_adopted" not in ev.run(survey, labels, None, boot=20, perturbations=5)["ranking_targets"]
