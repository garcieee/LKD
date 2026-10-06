import itertools
import json
from collections import Counter

import numpy as np
import pytest

from models.tickets.eval.ranking import aggregate as ag
from models.tickets.eval.ranking import pairs
from models.tickets.eval.ranking.tests.helpers import tiny_survey

A, B, T = ag.A, ag.B, ag.TIE


@pytest.fixture(scope="module")
def survey():
    return ag.load()


@pytest.fixture(scope="module")
def labels(survey):
    return ag.label_pairs(survey)


# ---- Fleiss kappa ---------------------------------------------------------------------------------------------------
def test_fleiss_kappa_matches_the_published_example():
    """The worked example of Fleiss (1971) as printed in the Wikipedia article: 10 subjects, 14 raters, 5 categories, kappa 0.210."""
    table = [[0, 0, 0, 0, 14], [0, 2, 6, 4, 2], [0, 0, 3, 5, 6], [0, 3, 9, 2, 0], [2, 2, 8, 1, 1],
             [7, 7, 0, 0, 0], [3, 2, 6, 3, 0], [2, 5, 3, 2, 2], [6, 5, 2, 1, 0], [0, 2, 2, 3, 7]]
    assert ag.fleiss_kappa(table) == pytest.approx(0.210, abs=0.001)


def test_fleiss_kappa_on_a_tiny_hand_made_set():
    """3 pairs, 3 raters, 2 categories. P_i = 1, 1, 1/3 so P = 7/9. Shares 5/9 and 4/9 so chance = 41/81. kappa = 22/40."""
    assert ag.fleiss_kappa([[3, 0], [0, 3], [2, 1]]) == pytest.approx(0.55)
    assert ag.fleiss_kappa([[0, 3], [3, 0], [1, 2]]) == pytest.approx(0.55)  # the names of the categories do not matter


def test_fleiss_kappa_extremes():
    assert ag.fleiss_kappa([[5, 0, 0], [0, 5, 0], [0, 0, 5], [5, 0, 0]]) == pytest.approx(1.0)  # always agree, and use more than one category
    assert np.isnan(ag.fleiss_kappa([[5, 0, 0], [5, 0, 0]]))  # one category only: chance agreement is 1, kappa is undefined
    rng = np.random.default_rng(0)
    votes = rng.integers(0, 2, (4000, 5))  # coin flips agree only by chance
    assert abs(ag.fleiss_kappa(ag.vote_counts(votes, 2))) < 0.03


def test_vote_counts_count_a_b_and_tie():
    assert ag.vote_counts([[A, A, B, T, A], [T, T, T, T, T]]).tolist() == [[3, 1, 1], [0, 0, 5]]


# ---- leave-one-rater-out ceiling -------------------------------------------------------------------------------------
TINY = np.array([[A, A, A, A, A],  # everyone agrees with the other four
                 [A, A, A, B, B],  # A,A,A: the other four split 2-2, skipped. B,B: the other four say A, so they disagree
                 [T, T, T, A, B],  # the clear top of the others is "tie" for everyone: skipped
                 [A, A, A, A, B]])  # the four A raters agree, the B rater does not


def test_loro_reference_on_a_tiny_hand_made_set():
    assert ag.loro_reference(TINY).tolist() == [[A, A, A, A, A], [-1, -1, -1, A, A], [-1, -1, -1, -1, -1], [A, A, A, A, A]]


def test_loro_agreement_and_ceiling_on_a_tiny_hand_made_set():
    per_rater = ag.loro_agreement(TINY)
    assert per_rater == pytest.approx([1.0, 1.0, 1.0, 2 / 3, 1 / 3])  # raters 4 and 5 are 1, 0, 1 and 1, 0, 0 on pairs 1, 2, 4
    assert ag.ceiling(TINY) == pytest.approx(0.8)


def test_a_rater_with_nothing_to_compare_is_nan_and_the_ceiling_ignores_it():
    one = np.array([[A, A, B, B, A]])  # raters 1, 2 and 5 face a 2-2 split of the others; raters 3 and 4 face A, A, B, A and chose B
    per_rater = ag.loro_agreement(one)
    assert np.isnan(per_rater[[0, 1, 4]]).all() and per_rater[2] == 0 and per_rater[3] == 0
    assert ag.ceiling(one) == 0.0
    assert np.isnan(ag.loro_agreement(np.array([[T] * 5]))).all()


def test_loro_reference_for_one_pair_by_hand():
    # votes of raters 1..5: A, A, B, B, T.  Rater 1: others A B B T -> B has 2, clear top -> B.  Rater 3: others A A B T -> A.
    # Rater 5: others A A B B -> split -> none.
    assert ag.loro_reference(np.array([[A, A, B, B, T]])).tolist() == [[B, B, A, A, -1]]


def test_ceiling_is_one_when_everybody_always_agrees_and_unanimous_pairs_are_perfect():
    unanimous = np.array([[A] * 5, [B] * 5, [A] * 5])
    assert ag.ceiling(unanimous) == 1.0


# ---- majority, consensus, unanimous ----------------------------------------------------------------------------------
VOTES = {"unanimous A": [A] * 5, "4-1 for A": [A, A, A, A, B], "3-2 for B": [B, B, B, A, A], "split with a tie": [A, A, B, B, T],
         "tie majority": [T, T, T, A, B], "A 2, tie 2, B 1": [A, A, T, T, B], "3 A with 2 ties": [A, A, A, T, T], "4 ties": [T, T, T, T, A]}


def test_majority_needs_three_of_five_and_says_why_it_has_none():
    m = ag.majority_labels(np.array(list(VOTES.values())))
    assert m["winner"].tolist() == [A, A, B, -1, -1, -1, A, -1]
    assert m["support"].tolist() == [5, 4, 3, 0, 0, 0, 3, 0]
    assert m["reason"].tolist() == ["", "", "", "no majority", "tie majority", "no majority", "", "tie majority"]


def test_consensus_and_unanimous_subsets_are_nested_and_exclude_ties():
    m = ag.majority_labels(np.array(list(VOTES.values())))
    labels = ag.Labels(m["votes"], m["winner"], m["support"], m["reason"])
    assert labels.subset("majority").tolist() == [True, True, True, False, False, False, True, False]
    assert labels.subset("consensus").tolist() == [True, True, False, False, False, False, False, False]
    assert labels.subset("unanimous").tolist() == [True, False, False, False, False, False, False, False]


def test_a_unanimous_tie_is_not_a_unanimous_label():
    m = ag.majority_labels(np.array([[T] * 5]))
    labels = ag.Labels(m["votes"], m["winner"], m["support"], m["reason"])
    assert m["winner"].tolist() == [-1] and not labels.subset("unanimous").any() and not labels.subset("consensus").any()


def test_swap_repeats_are_never_labelled(survey, labels):
    assert (labels.winner[~survey.base] == -1).all() and (labels.reason[~survey.base] == "repeat").all()
    assert (labels.winner[survey.base] >= 0).sum() == 235


# ---- swap consistency --------------------------------------------------------------------------------------------------
def test_swap_table_on_a_hand_made_survey():
    """Pair 0 is shown as (t0, t1); pair 1 is its repeat shown as (t1, t0). Five raters, all five cases appear."""
    first = [A, A, A, T, T]   # what each rater said on the original: t0, t0, t0, tie, tie
    second = [B, A, T, T, B]  # on the repeat: B is t0 (consistent), A is t1 (flip), tie (one tie), tie (both tie), B is t0 (one tie)
    s = tiny_survey([first, second], a=[0, 1], b=[1, 0], repeat_of=[-1, 0])
    table = ag.swap_table(s)
    assert table["r0"] == {"n": 1, "same_ticket": 1, "both_tie": 0, "one_tie": 0, "position_flip": 0, "consistency": 1.0}
    assert table["r1"]["position_flip"] == 1 and table["r1"]["consistency"] == 0.0
    assert table["r2"]["one_tie"] == 1 and table["r2"]["consistency"] == 0.0
    assert table["r3"]["both_tie"] == 1 and table["r3"]["consistency"] == 1.0
    assert table["r4"]["one_tie"] == 1
    assert table["panel_majority"]["same_ticket"] == 0  # A, A, A, T, T on the original and B, A, T, T, B on the repeat: the panel says t0, then no majority
    assert table["panel_majority"]["one_tie"] == 1


def test_the_panel_majority_is_judged_on_the_ticket_not_the_letter():
    s = tiny_survey([[A] * 5, [B] * 5], a=[0, 1], b=[1, 0], repeat_of=[-1, 0])
    assert ag.swap_table(s)["panel_majority"]["same_ticket"] == 1
    s = tiny_survey([[A] * 5, [A] * 5], a=[0, 1], b=[1, 0], repeat_of=[-1, 0])  # the same letter twice is a position effect
    assert ag.swap_table(s)["panel_majority"]["position_flip"] == 1


def test_rater_quality_on_the_real_ratings_matches_a_direct_count(survey):
    quality = ag.rater_quality(survey)
    rows = json.loads((pairs.DATA / "ratings_engineer.json").read_text())["pairs"]
    base = {pid for pid, swap in zip(survey.pair_ids, survey.repeat_of) if swap < 0}
    own = [r for r in rows if r["id"] in base]
    assert quality["engineer"]["share_A_base"] == pytest.approx(sum(r["choice"] == "A" for r in own) / 240)
    assert quality["engineer"]["ties_base"] == sum(r["choice"] == "tie" for r in own)
    assert quality["engineer"]["confidence"]["1"] == sum(r["confidence"] == 1 for r in rows)
    ratings = json.loads((pairs.DATA / "ratings_wheelchair.json").read_text())["urgency"]
    assert quality["wheelchair"]["urgency"]["5"] == sum(r["urgency"] == 5 for r in ratings)
    assert all(q["swap"]["n"] == 40 for q in quality.values())


# ---- urgency agreement ------------------------------------------------------------------------------------------------
def test_krippendorff_alpha_ordinal_by_hand():
    """4 items rated by 2 raters: (1,2) (2,3) (1,3) (3,3). Marginals 2, 2, 4 of 8. delta^2: 4, 9, 25 for (1,2), (2,3), (1,3).
    Observed 2 * (4 + 9 + 25) = 76; expected 2 * (2*2*4 + 2*4*9 + 2*4*25) = 576. alpha = 1 - 7 * 76 / 576 = 11 / 144."""
    assert ag.krippendorff_alpha([[1, 2], [2, 3], [1, 3], [3, 3]], levels=3) == pytest.approx(11 / 144)


def test_krippendorff_alpha_two_levels_equals_the_nominal_value():
    assert ag.krippendorff_alpha([[1, 1], [2, 2], [1, 2]], levels=2) == pytest.approx(4 / 9)


def brute_force_alpha(ratings, levels):
    """Alpha from its definition: mean disagreement inside items over mean disagreement between all pairs of ratings."""
    r = np.asarray(ratings)
    flat = r.ravel()
    n_g = np.array([(flat == g).sum() for g in range(1, levels + 1)], float)
    delta2 = lambda c, k: 0.0 if c == k else (n_g[min(c, k) - 1:max(c, k)].sum() - (n_g[c - 1] + n_g[k - 1]) / 2) ** 2
    within = [delta2(x, y) for row in r for i, x in enumerate(row) for j, y in enumerate(row) if i != j]
    between = [delta2(x, y) for i, x in enumerate(flat) for j, y in enumerate(flat) if i != j]
    return 1 - np.mean(within) / np.mean(between)


def test_krippendorff_alpha_matches_a_brute_force_version_of_its_definition():
    rng = np.random.default_rng(3)
    for items, raters in ((12, 3), (20, 5)):
        ratings = np.clip(rng.integers(1, 6, (items, 1)) + rng.integers(-1, 2, (items, raters)), 1, 5)
        assert ag.krippendorff_alpha(ratings, levels=5) == pytest.approx(brute_force_alpha(ratings, 5))


def test_krippendorff_alpha_is_one_for_agreement_and_near_zero_for_noise():
    same = np.repeat(np.array([[1], [3], [5], [2], [4]]), 4, axis=1)
    assert ag.krippendorff_alpha(same) == pytest.approx(1.0)
    noise = np.random.default_rng(5).integers(1, 6, (3000, 5))
    assert abs(ag.krippendorff_alpha(noise)) < 0.03


def test_icc_matches_shrout_and_fleiss_1979():
    """The six targets by four judges of Shrout and Fleiss (1979), Table 2: ICC(2,1) = 0.29 and ICC(2,k) = 0.62."""
    table = [[9, 2, 5, 8], [6, 1, 3, 2], [8, 4, 6, 8], [7, 1, 2, 6], [10, 5, 6, 9], [6, 2, 4, 7]]
    single, mean_of_k = ag.icc2(table)
    assert single == pytest.approx(0.29, abs=0.005) and mean_of_k == pytest.approx(0.62, abs=0.005)
    assert ag.icc2(np.repeat(np.array([[1.0], [2.0], [4.0], [5.0]]), 3, axis=1)) == pytest.approx((1.0, 1.0))


# ---- the real survey ----------------------------------------------------------------------------------------------------
def test_loaded_survey_has_the_planned_shape_and_splits(survey):
    assert survey.choice.shape == (280, 5) and survey.confidence.shape == (280, 5) and survey.urgency.shape == (200, 5)
    assert survey.raters == ("engineer", "captain", "wheelchair", "commuter", "paramedic")
    assert survey.base.sum() == 240 and (~survey.base).sum() == 40
    assert Counter(survey.ticket_split) == {"train": 120, "validation": 40, "test": 40}
    assert Counter(survey.split[survey.base]) == {"train": 144, "validation": 48, "test": 48}
    assert Counter(survey.stratum[survey.base]) == {"clear": 80, "close": 80, "trade_off": 80}


def test_pairs_stay_inside_their_split_and_repeats_mirror_their_originals(survey):
    assert (survey.ticket_split[survey.a] == survey.split).all() and (survey.ticket_split[survey.b] == survey.split).all()
    for row in np.flatnonzero(~survey.base):
        original = survey.repeat_of[row]
        assert survey.base[original] and (survey.a[row], survey.b[row]) == (survey.b[original], survey.a[original])


def test_votes_agree_with_a_direct_count_of_the_five_files(survey, labels):
    files = {name: {r["id"]: r["choice"] for r in json.loads((pairs.DATA / f"ratings_{name}.json").read_text())["pairs"]} for name in survey.raters}
    for k in range(280):
        direct = Counter(files[name][survey.pair_ids[k]] for name in survey.raters)
        assert labels.votes[k].tolist() == [direct["A"], direct["B"], direct["tie"]]


def test_committed_consensus_file_is_what_the_code_derives_and_is_small(survey, labels):
    path = pairs.DATA / "consensus.json"
    assert path.read_text(encoding="utf-8") == pairs.dumps(ag.consensus_doc(survey, labels))
    assert path.stat().st_size < 60_000
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert len(doc["pairs"]) == 240 and len(doc["tickets"]) == 200
    assert Counter(p["label"] for p in doc["pairs"].values()) == {"A": int((labels.winner == A).sum()), "B": int((labels.winner == B).sum()), None: 5}
    assert all(p["split"] in pairs.SPLITS and p["stratum"] in pairs.STRATA for p in doc["pairs"].values())


def test_mean_urgency_is_the_mean_of_the_five_ratings(survey):
    doc = json.loads((pairs.DATA / "consensus.json").read_text(encoding="utf-8"))
    for i, tid in enumerate(survey.ticket_ids):
        assert doc["tickets"][tid]["urgency"] == pytest.approx(survey.urgency[i].mean(), abs=0.05)
        assert doc["tickets"][tid]["split"] == survey.ticket_split[i]
    assert np.allclose(ag.mean_urgency(survey), survey.urgency.mean(axis=1))


def test_ticket_id_orientation_leaves_observed_agreement_alone(survey):
    block = ag.agreement_block(survey, survey.base, boot=100)
    assert block["kappa_by_ticket_id"] == pytest.approx(block["fleiss_kappa"]["point"], abs=0.01)
    assert block["fleiss_kappa"]["lo"] < block["fleiss_kappa"]["point"] < block["fleiss_kappa"]["hi"]


def test_agreement_blocks_use_the_pairs_they_claim(survey):
    for split in pairs.SPLITS:
        assert ag.agreement_block(survey, survey.base & (survey.split == split), boot=20)["n_pairs"] == {"train": 144, "validation": 48, "test": 48}[split]
    assert ag.agreement_block(survey, survey.base & (survey.stratum == "close"), boot=20)["n_pairs"] == 80


def test_raw_agreement_is_symmetric_with_ones_on_the_diagonal(survey):
    raw = ag.raw_agreement(survey.choice[survey.base])
    assert np.allclose(raw, raw.T) and np.allclose(np.diag(raw), 1.0) and ((raw > 0.5) & (raw <= 1)).all()


def test_all_pairs_of_a_vote_table_are_either_labelled_or_have_a_stated_reason(survey, labels):
    unlabelled = survey.base & (labels.winner < 0)
    assert set(labels.reason[unlabelled]) <= {"tie majority", "no majority"}
    assert Counter(labels.reason[unlabelled]) == {"tie majority": 4, "no majority": 1}


def test_labels_block_counts_every_split(survey, labels):
    block = ag.labels_block(survey, labels)
    assert block["all"]["pairs"] == 240 and block["all"]["majority"] == 235
    assert sum(block[s]["majority"] for s in pairs.SPLITS) == 235 and sum(block[s]["unanimous"] for s in pairs.SPLITS) == block["all"]["unanimous"]
    assert all(block[s]["consensus"] <= block[s]["majority"] <= block[s]["pairs"] for s in pairs.SPLITS)
    assert all(sum(block[s]["excluded"].values()) == block[s]["pairs"] - block[s]["majority"] for s in pairs.SPLITS)


def test_every_orientation_of_a_pair_set_gives_the_same_loro_agreement(survey):
    """The LORO agreement cannot depend on which rater is called first, or on how the pairs are ordered."""
    choice = survey.choice[survey.base]
    base = ag.loro_agreement(choice)
    order = np.random.default_rng(0).permutation(len(choice))
    assert np.allclose(ag.loro_agreement(choice[order]), base)
    for perm in itertools.islice(itertools.permutations(range(5)), 6):
        assert np.allclose(ag.loro_agreement(choice[:, list(perm)])[np.argsort(perm)], base)


def test_load_refuses_a_ratings_file_that_the_validator_rejects(tmp_path):
    for name in ("blind_survey.json", "answer_key.json", *(f"ratings_{r}.json" for r in ag.validate_ratings.PERSONAS)):
        (tmp_path / name).write_text((pairs.DATA / name).read_text(encoding="utf-8"), encoding="utf-8")
    assert ag.load(tmp_path).choice.shape == (280, 5)
    broken = json.loads((tmp_path / "ratings_captain.json").read_text())
    broken["pairs"] = broken["pairs"][1:]  # one pair unanswered
    (tmp_path / "ratings_captain.json").write_text(json.dumps(broken))
    with pytest.raises(ValueError, match="ratings_captain.json"):
        ag.load(tmp_path)
