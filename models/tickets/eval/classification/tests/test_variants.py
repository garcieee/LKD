import pytest

from models.tickets.classification import classify
from models.tickets.eval.classification import evaluate as E
from models.tickets.eval.classification import variants as V

DATA = {
    "categories": {"pothole": ["pothole", "lubak"], "open_manhole": ["manhole", "nabaha"], "flooded_drain": ["baha", "flooded"], "broken_streetlight": ["streetlight", "walang ilaw"],
                   "blocked_sidewalk": ["sidewalk"], "other": ["aso", "puno"]},
    "danger": ["delikado", "dangerous"], "negators": ["walang", "hindi"], "boundaries": ["pero"]}


def norm(**flags):
    return V.Normaliser(DATA, **flags)


def test_one_edit_means_exactly_one_insert_delete_change_or_swap():
    assert V.within_one_edit("manhole", "mnhole") and V.within_one_edit("flood", "flod") and V.within_one_edit("abc", "acb") and V.within_one_edit("abc", "xbc")
    assert not V.within_one_edit("manhole", "manhole") and not V.within_one_edit("abc", "xyz") and not V.within_one_edit("abc", "abcde") and not V.within_one_edit("abcd", "badc")


def test_repeats_squeeze_letters_in_the_note_and_in_the_list_alike():
    n = norm(squeeze=True)
    assert n("lubaaak sa kalsada") == "lubak sa kalsada"
    assert classify.category_scores(n("lubaaak"), n.lexicon)["pothole"] == 1.0  # "lubaaak" now matches "lubak"
    assert classify.category_scores("lubaaak", classify.Lexicon(DATA))["pothole"] == 0.0
    assert ("floded",) in n.lexicon.categories["flooded_drain"] and classify.category_scores(n("floooded"), n.lexicon)["flooded_drain"] == 1.0  # real double letters match too


def test_typo_matching_fixes_a_long_list_word_one_edit_away_and_nothing_short():
    n = norm(typo=True)
    assert n.word("mnhole") == "manhole" and n.word("pothle") == "pothole" and n.word("sidewalks") == "sidewalk" and n.word("dangerus") == "dangerous"
    assert n.word("bahay") == "bahay" and n.word("baha") == "baha"  # "baha" has 4 letters, below the floor: a house stays a house
    assert norm(typo=True, typo_min_len=4).word("bahay") == "baha"  # the naive version turns it into a flood
    assert n.word("bahay") != norm(typo=True, typo_min_len=4).word("bahay")


def test_typo_matching_leaves_a_word_alone_when_two_list_words_fit_equally():
    twin = V.Normaliser({**DATA, "categories": {**DATA["categories"], "other": ["lubaks", "lubako"]}}, typo=True)
    assert twin.word("lubaka") == "lubaka"  # one edit from both lubaks and lubako


def test_the_strict_typo_variant_wants_the_same_first_letter():
    assert norm(typo=True).word("treetlight") == "streetlight"
    assert norm(typo=True, typo_min_len=7, typo_same_first=True).word("treetlight") == "treetlight"
    assert norm(typo=True, typo_min_len=7, typo_same_first=True).word("streetlite") == "streetlite"  # two edits away: not a typo of it
    assert norm(typo=True, typo_min_len=7, typo_same_first=True).word("streetlighs") == "streetlight"


def test_stripping_mag_nag_na_needs_the_rest_to_be_a_list_word():
    n = norm(prefix=True)
    assert n.word("nagbaha") == "baha" and n.word("magbaha") == "baha" and n.word("nalubak") == "lubak"
    assert n.word("nagusap") == "nagusap" and n.word("nang") == "nang" and n.word("nag") == "nag"  # nothing left, or not a list word
    assert n.word("nabaha") == "nabaha"  # already a list word: never rewritten
    assert norm().word("nagbaha") == "nagbaha"  # off unless asked for


def test_stripping_a_trailing_ng_needs_the_rest_to_be_a_list_word():
    n = norm(suffix=True)
    assert n.word("asong") == "aso" and n.word("punong") == "puno" and n.word("bang") == "bang" and n.word("aso") == "aso"
    both = norm(prefix=True, suffix=True)
    assert both.word("nagbahang") == "baha"  # prefix and suffix together


def test_a_list_word_and_a_number_are_never_rewritten_whatever_is_switched_on():
    n = norm(squeeze=True, typo=True, prefix=True, suffix=True)
    assert n.word("baha") == "baha" and n.word("nabaha") == "nabaha" and n.word("2024") == "2024" and n.word("kalsada") == "kalsada"


def test_the_text_keeps_its_punctuation_so_a_negators_reach_still_ends_at_the_comma():
    n = norm(squeeze=True, prefix=True)
    assert n("Walang bata, delikaado pa rin!") == "walang bata, delikado pa rin!"
    assert classify.danger_terms(n("Walang bata, delikaado pa rin!"), n.lexicon) == ["delikado"]
    assert classify.danger_terms(n("Walang delikaado"), n.lexicon) == []


def test_rewrites_counts_what_a_step_really_does():
    assert norm(prefix=True).rewrites(["nagbaha dito, nagbaha ulit", "may aso"]) == {("nagbaha", "baha"): 2}


def test_measure_scores_a_list_with_and_without_a_step():
    rows = E.split_rows(E.load_train())[1][:60]
    y, d = E.targets_of(rows)
    texts = [r["text"] for r in rows]
    plain, with_step = V.measure(E.lexicon_data("v0"), None, texts, y, d), V.measure(E.lexicon_data("v0"), {"suffix": True}, texts, y, d)
    assert "rewritten_words" not in plain and with_step["rewritten_words"] >= 0 and 0 <= plain["macro_f1"] <= 1


def test_the_variant_carried_forward_has_the_biggest_gain_and_none_when_nothing_gains():
    rows = lambda *gains: [{"base": "v1", "variant": name, "d_macro_f1": a, "d_danger_pr_auc": b} for name, (a, b) in zip(("repeats", "typo1", "repeats+prefix+suffix"), gains)]
    assert V.pick_best(rows((0.0, 0.0), (0.02, -0.005), (0.004, 0.003)))["name"] == "typo1"
    assert V.pick_best(rows((0.0, 0.0), (-0.01, 0.005), (-0.002, 0.0))) is None
    assert V.pick_best([{"base": "v0", "variant": "typo1", "d_macro_f1": 0.5, "d_danger_pr_auc": 0.5}]) is None  # only variants on v1 compete
    tie = V.pick_best(rows((0.01, 0.0), (0.01, 0.0), (0.0, 0.0)))
    assert tie["name"] == "repeats"  # same gain, fewer steps
