import json

import numpy as np
import pytest

from models.tickets.classification import classify
from models.tickets.eval.classification import evaluate as E
from models.tickets.eval.classification import tune_lexicon as T


# ---- the evidence rule on a tiny set -----------------------------------------------------------------------------------
def test_evidence_is_support_families_and_precision_of_the_notes_a_term_is_in():
    fires = [1, 1, 1, 1, 1, 0, 0]
    hits = [1, 1, 1, 1, 0, 1, 1]  # the last two notes carry the class but do not have the term
    families = ["a", "a", "b", "c", "c", "d", "d"]
    ev = T.evidence(fires, hits, families)
    assert ev == {"support": 5, "families": 3, "precision": pytest.approx(0.8)}
    assert T.judged(ev) and not T.qualifies(ev)  # judged (5 notes, 3 families), but 0.8 < 0.9


@pytest.mark.parametrize(
    "support, families, hits, judged, qualifies",
    [(5, 3, 5, True, True),      # exactly on every bar
     (4, 4, 4, False, False),    # one note short
     (6, 2, 6, False, False),    # one family short
     (10, 5, 9, True, True),     # precision 0.9 is enough
     (10, 5, 8, True, False)],   # precision 0.8 is not
)
def test_the_bars_are_five_notes_three_families_and_precision_point_nine(support, families, hits, judged, qualifies):
    fam = [f"f{i % families}" for i in range(support)]
    ev = T.evidence([True] * support, [True] * hits + [False] * (support - hits), fam)
    assert (T.judged(ev), T.qualifies(ev)) == (judged, qualifies)


def test_a_term_that_never_appears_has_no_evidence():
    assert T.evidence([False, False], [True, True], ["a", "b"]) == {"support": 0, "families": 0, "precision": 0.0}


# ---- firing is what classify.py would do ---------------------------------------------------------------------------------------
LEX = classify.Lexicon({"categories": {c: [] for c in E.HAZARDS}, "danger": ["bata", "delikado", "muntik na"], "negators": ["walang", "hindi"], "boundaries": ["pero"]})


def row(text, category="pothole", danger=False, family="f1"):
    return {"text": text, "category": category, "danger": danger, "family": family}


def test_the_danger_index_fires_where_classify_does():
    notes = ["walang bata dito", "hindi delikado", "walang bata pero delikado pa rin", "walang bata, delikado pa rin", "may bata na muntik na mahulog", "bahay namin"]
    index = T.Corpus([row(n) for n in notes]).danger_index(LEX)
    for term in LEX.danger:
        fired = {i for i, n in enumerate(notes) if term in classify._danger_hits(n, LEX)}
        assert index.get(term, set()) == fired, term


# ---- one pass of the rule -----------------------------------------------------------------------------------------------------
V0 = {"categories": {"pothole": ["lubak"], "open_manhole": [], "flooded_drain": ["baha", "barado"], "broken_streetlight": [], "blocked_sidewalk": [], "other": []},
      "danger": ["delikado", "hurt"], "negators": ["walang"], "boundaries": ["pero"]}


def tiny_notes():
    rows = []
    rows += [row("malaking butas dito", "pothole", family=f"p{i % 3}") for i in range(6)]            # 6 notes, 3 families, all pothole: added
    rows += [row("sirang gutter dito", "flooded_drain", family=f"g{i % 2}") for i in range(5)]       # 5 notes but 2 families: not added
    rows += [row("pozo na naman", "pothole", family=f"z{i}") for i in range(4)]                       # 4 notes: not added
    rows += [row("grieta sa kanto", "pothole" if i < 4 else "other", family=f"r{i % 3}") for i in range(5)]  # precision 0.8: not added
    rows += [row("baha na naman", "pothole", family=f"b{i % 3}") for i in range(6)]                   # v0 "baha": judged, never its class: removed
    rows += [row("barado ang kanal", "flooded_drain" if i < 3 else "pothole", family=f"c{i % 3}") for i in range(6)]  # v0 "barado" at 0.5: weak, kept
    rows += [row("may lubak", "pothole", family="l1") for i in range(2)]                              # v0 "lubak": two notes, not judged, kept
    rows += [row("nahulog ang bata", "pothole", True, family=f"n{i % 3}") for i in range(5)]          # danger word: added
    rows += [row("walang nahulog", "pothole", False, family=f"w{i % 3}") for i in range(5)]           # negated, so it must not count against "nahulog"
    rows += [row("delikado po ito", "pothole", False, family=f"d{i % 3}") for i in range(6)]          # v0 "delikado" on notes that are not danger: removed
    rows += [row("nobody hurt here", "pothole", False, family=f"h{i % 3}") for i in range(5)]         # a new negator for "hurt"
    return rows


def test_the_rule_adds_removes_and_leaves_alone_exactly_as_stated():
    data, changes, weak, summary = T.tune(tiny_notes(), V0)
    cats = data["categories"]
    assert "butas" in cats["pothole"]                                             # qualifies
    assert "gutter" not in cats["flooded_drain"] and "pozo" not in cats["pothole"] and "grieta" not in cats["pothole"]
    assert "baha" not in cats["flooded_drain"]                                    # judged, and at least 0.9 of its notes are not flooded_drain
    assert "barado" in cats["flooded_drain"] and "lubak" in cats["pothole"]       # weak and not judged: kept
    assert {c["term"] for c in weak} >= {"barado"}
    assert "nahulog" in data["danger"] and "delikado" not in data["danger"]
    assert "nobody" in data["negators"] and "walang" in data["negators"]
    assert any(c["change"] == "add" and c["term"] == "butas" and c["support"] == 6 and c["families"] == 3 and c["precision"] == 1.0 for c in changes)
    assert summary["flooded_drain"]["removed"] == 1 and summary["flooded_drain"]["weak_kept"] == 1 and summary["pothole"]["not_judged"] == 1


def test_negators_are_judged_before_danger_words_so_a_new_negator_saves_its_danger_word():
    data, changes, _, _ = T.tune(tiny_notes(), V0)
    assert "hurt" in data["danger"]  # once "nobody" cancels it the notes stop counting against "hurt"
    assert not any(c["change"] == "remove" and c["term"] == "hurt" for c in changes)


def test_a_phrase_with_a_term_the_list_has_or_a_function_word_at_its_edge_is_not_a_candidate():
    assert T.contained(("malaking", "lubak"), {("lubak",)}) and not T.contained(("lubak",), {("lubak",)}) and not T.contained(("ibang", "bagay"), {("lubak",)})
    assert not T.usable(("ilaw", "sa")) and not T.usable(("ang", "ilaw")) and T.usable(("butas", "sa", "kalsada")) and not T.usable(("12", "45"))


def test_a_boundary_word_that_marks_danger_notes_is_added_and_one_that_marks_safe_notes_is_removed():
    v0 = {**V0, "danger": ["delikado"], "boundaries": ["pero"]}
    rows = [row("walang bata kaso delikado", "pothole", True, family=f"k{i % 3}") for i in range(5)]       # a negator, "kaso", a danger word: danger notes
    rows += [row("walang bata pero delikado", "pothole", False, family=f"s{i % 3}") for i in range(6)]    # "pero" here wrongly reopens the danger word
    rows += [row("walang delikado dito", "pothole", False, family=f"n{i % 3}") for i in range(6)]         # where "walang" rightly cancels: it stays a negator
    data, changes, _, _ = T.tune(rows, v0)
    assert "kaso" in data["boundaries"] and "pero" not in data["boundaries"] and "walang" in data["negators"]
    assert {(c["change"], c["term"]) for c in changes if c["list"] == "boundaries"} == {("add", "kaso"), ("remove", "pero")}


# ---- the shipped result -----------------------------------------------------------------------------------------------------------
def test_lexicon_v1_loads_like_the_shipped_one_and_has_no_repeats():
    data = json.loads(E.LEXICON_V1.read_text())
    lex = classify.Lexicon(data)
    assert set(lex.categories) == set(E.HAZARDS) and lex.danger and lex.negators and lex.boundaries
    assert all(tokens for terms in lex.categories.values() for tokens in terms)
    for terms in [*data["categories"].values(), data["danger"]]:
        normal = [" ".join(classify.tokens(t)) for t in terms]
        assert len(normal) == len(set(normal))


def test_lexicon_v1_is_what_the_rule_gives_on_the_train_half_only():
    train, validation = E.split_rows(E.load_train())
    v1, changes, _, _ = T.tune(train, E.lexicon_data("v0"))
    shipped = json.loads(E.LEXICON_V1.read_text())
    assert v1["categories"] == shipped["categories"] and v1["danger"] == shipped["danger"]
    assert v1["negators"] == shipped["negators"] and v1["boundaries"] == shipped["boundaries"]
    for change in changes:  # every change stands on the evidence bars, counted on train notes only
        if change["change"] == "add":
            assert change["support"] >= 5 and change["families"] >= 3 and change["precision"] >= 0.9
        else:
            assert change["support"] >= 5 and change["families"] >= 3 and change["precision"] <= 0.1
    assert not ({r["family"] for r in train} & {r["family"] for r in validation})
