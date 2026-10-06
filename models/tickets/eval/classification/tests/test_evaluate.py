import numpy as np
import pytest

from models.tickets import settings as s
from models.tickets.classification import classify
from models.tickets.eval.classification import evaluate as E

LEX = classify.Lexicon({
    "categories": {"pothole": ["lubak", "butas sa kalsada"], "open_manhole": ["manhole"], "flooded_drain": ["baha", "barado"],
                   "broken_streetlight": ["streetlight", "walang ilaw"], "blocked_sidewalk": ["bangketa"], "other": ["puno"]},
    "danger": ["bata", "delikado", "muntik na"], "negators": ["walang", "hindi"], "boundaries": ["pero"]})


# ---- the family split -------------------------------------------------------------------------------------------------
def test_the_split_keeps_every_family_whole():
    rows = [{"id": f"{f}-{k}", "family": f"fam-{f}", "category": "pothole", "danger": False} for f in range(20) for k in range(5)]
    train, validation = E.split_rows(rows, seed=1)
    assert len(train) + len(validation) == 100 and not ({r["id"] for r in train} & {r["id"] for r in validation})
    assert not ({r["family"] for r in train} & {r["family"] for r in validation})
    assert all(sum(r["family"] == f for r in train) in (0, 5) for f in {r["family"] for r in rows})  # no family cut in two


def test_on_the_real_notes_no_family_is_in_both_halves_and_the_seed_is_the_first_that_covers_validation():
    rows = E.load_train()
    train, validation = E.split_rows(rows)
    assert not ({r["family"] for r in train} & {r["family"] for r in validation})
    assert len(train) + len(validation) == len(rows) and abs(len(validation) / len(rows) - E.FRACTIONS[1]) < 0.03
    assert E.seed_check(rows, E.SEED)["ok"] and E.first_good_seed(rows) == E.SEED
    assert not any(E.seed_check(rows, seed)["ok"] for seed in range(E.SEED))  # the seeds before it fail the rule


# ---- the hint from scores ----------------------------------------------------------------------------------------------------
NOTES = ["lubak", "lubak at baha", "lubak, butas sa kalsada at baha", "please fix asap", "baha baha", "manhole sa kanto", "bahay namin",
         "walang ilaw sa streetlight", "bangketa at manhole at lubak", ""]


@pytest.mark.parametrize("min_score, min_margin", [(1.0, 0.5), (1.0, 0.0), (1.5, 0.5), (2.0, 1.0), (1.0, 2.5)])
def test_hint_labels_equal_classify_category_hint_at_every_setting(monkeypatch, min_score, min_margin):
    monkeypatch.setattr(s, "HINT_MIN_SCORE", min_score)
    monkeypatch.setattr(s, "HINT_MIN_MARGIN", min_margin)
    expected = [(h.category if (h := classify.category_hint(note, LEX)) else "none") for note in NOTES]
    assert list(E.hint_labels(E.lexicon_outputs(NOTES, LEX).cat, min_score, min_margin)) == expected


def test_a_tie_goes_to_the_category_listed_first_as_in_classify():
    cat = np.array([[0, 0, 1.0, 1.0, 0, 0]])
    assert E.hint_labels(cat, 1.0, 0.0)[0] == "flooded_drain" and E.hint_labels(cat, 1.0, 0.5)[0] == "none"


# ---- selective numbers on a hand-made case ---------------------------------------------------------------------------------------
def test_coverage_and_precision_of_the_hints_shown():
    y = np.array(["pothole", "pothole", "none", "flooded_drain", "other"])
    pred = np.array(["pothole", "none", "pothole", "flooded_drain", "none"])  # a hint on the "none" note is wrong
    got = E.selective(y, pred)
    assert got["coverage"] == pytest.approx(3 / 5) and got["precision"] == pytest.approx(2 / 3)
    assert got["answered"] == 3 and got["correct"] == 2 and got["correct_rate"] == pytest.approx(2 / 5)
    assert E.coverage(y, pred) == pytest.approx(0.6) and E.hint_precision(y, pred) == pytest.approx(2 / 3) and E.correct_rate(y, pred) == pytest.approx(0.4)


def test_no_hint_at_all_has_zero_coverage_and_no_precision_to_speak_of():
    got = E.selective(np.array(["pothole", "none"]), np.array(["none", "none"]))
    assert got["coverage"] == 0 and got["precision"] == 0.0 and np.isnan(E.hint_precision(["pothole", "none"], ["none", "none"]))


SCORES = np.array([[3, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0], [0, 2, 0, 0, 0, 0],
                   [0, 0, 1, 1, 0, 0], [0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 1.5, 0], [0, 0, 0, 0, 0, 1]], float)
TRUTH = np.array(["pothole", "pothole", "flooded_drain", "open_manhole", "other", "none", "blocked_sidewalk", "none"])


@pytest.mark.parametrize("target, expected", [(0.6, (1.0, 0.5)), (0.7, (1.0, 0.5)), (0.8, (1.0, 0.0))])
def test_the_operating_point_is_the_most_precise_setting_that_reaches_the_coverage(target, expected):
    out = E.Outputs(SCORES, list(E.HAZARDS), np.zeros(8), "scores")
    pick = E.choose_hint_point(out, TRUTH, target)
    assert (pick["op"]["min_score"], pick["op"]["min_margin"]) == expected and pick["reached"] and pick["coverage"] >= target


def test_when_no_setting_reaches_the_coverage_the_widest_one_is_returned_and_says_so():
    pick = E.choose_hint_point(E.Outputs(SCORES, list(E.HAZARDS), np.zeros(8), "scores"), TRUTH, 0.99)
    assert not pick["reached"] and pick["op"] == {"min_score": 1.0, "min_margin": 0.0}


def test_a_probability_threshold_gives_the_most_precise_cut_that_keeps_enough_notes():
    # confidence order: 0.9 pothole (right), 0.8 flooded (right), 0.7 pothole (wrong), 0.4 none, 0.3 other (wrong)
    p = np.array([[.9, 0, 0, 0, 0, 0, .1], [0, 0, .8, 0, 0, 0, .2], [.7, 0, 0, 0, 0, 0, .3], [.3, 0, 0, 0, 0, 0, .4 + .3], [0, 0, 0, 0, 0, .3, .1]])
    p[3] = [0.3, 0, 0, 0, 0, 0, 0.7]
    p[4] = [0, 0, 0, 0, 0, 0.6, 0.4]
    y = np.array(["pothole", "flooded_drain", "open_manhole", "none", "none"])
    out = E.Outputs(p, list(E.CATEGORIES), np.zeros(5), "proba")
    pick = E.choose_hint_point(out, y, 0.4)  # two hints out of five is the least that counts
    assert pick["op"]["min_conf"] == pytest.approx(0.8) and pick["coverage"] == pytest.approx(0.4) and pick["precision"] == 1.0
    labels = E.operating_labels(out, {"min_conf": 0.8})
    assert list(labels) == ["pothole", "flooded_drain", "none", "none", "none"]  # below 0.8 abstains; an argmax of none stays none


# ---- danger -----------------------------------------------------------------------------------------------------------------------
D = np.array([1, 1, 1, 0, 0, 0, 0, 0], bool)
SCORE = np.array([0.9, 0.8, 0.3, 0.6, 0.2, 0.1, 0.1, 0.0])


def test_danger_thresholds_and_the_numbers_at_a_threshold():
    t = E.danger_thresholds(D, SCORE)
    assert t == {"f1": pytest.approx(0.3), "f2": pytest.approx(0.3), "recall90": pytest.approx(0.3)}
    at = E.danger_at(D, SCORE, 0.3)
    assert at["precision"] == pytest.approx(0.75) and at["recall"] == pytest.approx(1.0) and at["f2"] == pytest.approx(0.9375) and at["flagged"] == 4
    report = E.danger_report(D, SCORE, {"f2": 0.3, "later": None})
    assert set(report["at"]) == {"f2"} and report["prevalence"] == pytest.approx(3 / 8) and 0 < report["pr_auc"] <= 1
    assert report["recall_at_precision_0.60"] == pytest.approx(1.0) and report["precision_at_recall_0.90"] == pytest.approx(0.75)


def test_lexicon_outputs_use_the_scores_classify_draws_its_decisions_from():
    out = E.lexicon_outputs(["lubak at baha", "walang bata", "muntik na mahulog"], LEX)
    assert out.cat.shape == (3, 6) and list(out.cat[0]) == [1, 0, 1, 0, 0, 0]
    assert list(out.danger) == [0.0, 0.0, s.PHRASE_WEIGHT]
