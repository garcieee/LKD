import numpy as np
import pytest

from models.tickets.classification import classify
from models.tickets.eval.classification import baselines as B
from models.tickets.eval.classification import evaluate as E

NOTES = [  # (text, category, danger): a few hand-made notes, every category and both danger values
    ("may malaking lubak sa kanto", "pothole", False), ("pothole near the school, a kid almost fell", "pothole", True), ("butas sa kalsada dito", "pothole", False),
    ("walang takip ang manhole", "open_manhole", False), ("open manhole, muntik nang mahulog ang bata", "open_manhole", True), ("manhole cover is missing", "open_manhole", False),
    ("baha sa kanto, barado ang kanal", "flooded_drain", False), ("clogged drain and flooded street", "flooded_drain", False), ("malalim ang baha, delikado sa mga bata", "flooded_drain", True),
    ("patay ang ilaw sa poste", "broken_streetlight", False), ("the streetlight is out, so dark and dangerous", "broken_streetlight", True), ("sira ang streetlight dito", "broken_streetlight", False),
    ("nakaharang ang vendors sa bangketa", "blocked_sidewalk", False), ("cars parked on the sidewalk, wheelchair cannot pass", "blocked_sidewalk", True), ("bangketa puno ng paninda", "blocked_sidewalk", False),
    ("natumba ang puno sa kalsada", "other", False), ("stray dogs bite people here", "other", True), ("exposed wires, someone could be shocked", "other", True),
    ("please fix asap", "none", False), ("see photo", "none", False), ("delikado po dito", "none", True),
]
ROWS = [{"text": t, "category": c, "danger": d} for t, c, d in NOTES]
SPECS = {
    "nb": {"kind": "nb", "category": {"variant": "complement", "alpha": 0.3}, "danger": {"variant": "multinomial", "alpha": 0.1}},
    "lr": {"kind": "lr", "category": {"C": 100.0}, "danger": {"C": 100.0}},
    "hybrid": {"kind": "hybrid", "category": {"C": 100.0, "lex_weight": 2.0}, "danger": {"C": 100.0, "lex_weight": 0.5}},
}


@pytest.mark.parametrize("name", SPECS)
def test_each_learned_model_gives_probabilities_in_the_category_order(name):
    out = B.make_predictor(SPECS[name], ROWS).outputs([r["text"] for r in ROWS])
    assert out.kind == "proba" and out.columns == E.CATEGORIES and out.cat.shape == (len(ROWS), 7)
    assert np.allclose(out.cat.sum(axis=1), 1.0) and ((0 <= out.danger) & (out.danger <= 1)).all()


def test_logistic_regression_learns_its_own_training_notes():
    out = B.make_predictor(SPECS["lr"], ROWS).outputs([r["text"] for r in ROWS])
    assert (np.array(E.CATEGORIES)[out.cat.argmax(axis=1)] == np.array([r["category"] for r in ROWS])).mean() >= 0.9
    assert out.danger[[r["danger"] for r in ROWS]].mean() > out.danger[[not r["danger"] for r in ROWS]].mean()


def test_a_class_the_model_never_saw_gets_probability_zero():
    seen = [r for r in ROWS if r["category"] != "other"]
    out = B.make_predictor(SPECS["lr"], seen).outputs(["natumba ang puno"])
    assert out.cat[0, E.CATEGORIES.index("other")] == 0.0 and out.cat.shape == (1, 7)


def test_the_hybrid_sees_the_shipped_word_lists_scores_beside_the_tf_idf():
    vectorizer = B.make_vectorizer().fit([r["text"] for r in ROWS])
    design = B.Design(vectorizer, ["lubak at baha", "walang bata"])
    assert design.matrix().shape[1] + 7 == design.matrix(2.0).shape[1]  # six category scores and the danger score
    v0 = classify.Lexicon(E.lexicon_data("v0"))
    assert list(design.lexicon[0]) == list(E.lexicon_outputs(["lubak at baha"], v0).cat[0]) + [0.0]
    assert design.lexicon[0, E.HAZARDS.index("pothole")] == 1.0 and design.lexicon[0, E.HAZARDS.index("flooded_drain")] == 1.0


def test_a_spec_builds_a_word_list_predictor_with_or_without_a_step_in_front():
    plain = B.make_predictor({"kind": "lexicon", "lexicon": "v0", "variant": None}, []).outputs(["lubak", "nagbaha"])
    assert plain.kind == "scores" and plain.cat[0, 0] == 1.0 and plain.cat[1, E.HAZARDS.index("flooded_drain")] == 0.0
    step = B.make_predictor({"kind": "lexicon", "lexicon": "v0", "variant": {"prefix": True}}, []).outputs(["nagbaha"])
    assert step.cat[0, E.HAZARDS.index("flooded_drain")] == 1.0  # nag- stripped, "baha" matches
