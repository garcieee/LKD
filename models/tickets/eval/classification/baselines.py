"""Learned baselines for the two tasks, and the one place that turns a configuration spec into a predictor.

    models/.venv/bin/python -m models.tickets.eval.classification.baselines     # validation only: writes results/classification_learned.json

Features: TF-IDF of word 1-2 grams plus TF-IDF of character 3-5 grams (inside word edges), both on the text as classify.py
normalises it. Three models, each fitted twice, once for the 7-class category and once for the binary danger flag:
  naive_bayes          multinomial or complement Naive Bayes, the variant and smoothing chosen on validation
  logistic_regression  C chosen on validation
  hybrid               logistic regression whose input also holds the shipped word list's scores (v0: six category scores and
                       the danger score), so it starts from the rules and learns where they are wrong. v0, not v1, because v0 was
                       written before any note was seen: v1's terms were picked on these very train notes, which would leak.
Chosen by validation macro-F1 (category) and PR-AUC (danger); ties go to the simpler setting. Probabilities come from
predict_proba. A configuration spec is a plain dict, so the same code builds a model for validation and, refitted on train plus
validation, for the gold run.
"""
from __future__ import annotations

import warnings

import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import ComplementNB, MultinomialNB
from sklearn.pipeline import FeatureUnion

from models.tickets.classification import classify
from models.tickets.eval.classification import evaluate as E
from models.tickets.eval.classification import variants
from models.tickets.eval.common import metrics as M
from models.tickets.eval.common import results

LEX_SCALE = 3.0  # lexicon scores run 0..6; divided so they sit near the tf-idf values, then multiplied by the chosen weight
GRIDS = {  # simplest (most smoothing, least fit) first: a tie on validation keeps the earlier one
    "nb": [{"variant": v, "alpha": a} for v in ("multinomial", "complement") for a in (1.0, 0.3, 0.1, 0.03, 0.01)],
    "lr": [{"C": c} for c in (0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0, 3000.0, 10000.0, 30000.0)],
    "hybrid": [{"C": c, "lex_weight": w} for w in (0.5, 1.0, 2.0, 4.0) for c in (0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0)],
}
NAMES = {"nb": "naive_bayes", "lr": "logistic_regression", "hybrid": "hybrid"}


def clean(text: str) -> str:
    return " ".join(classify.tokens(text))


def make_vectorizer() -> FeatureUnion:
    return FeatureUnion([
        ("word", TfidfVectorizer(preprocessor=clean, analyzer="word", ngram_range=(1, 2), token_pattern=r"[a-z0-9]+", sublinear_tf=True)),
        ("char", TfidfVectorizer(preprocessor=clean, analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=2)),
    ])


class Design:
    """The feature matrix of a list of notes: tf-idf, and optionally the shipped word list's scores beside it."""

    _v0 = None

    def __init__(self, vectorizer: FeatureUnion, texts: list[str]):
        if Design._v0 is None:
            Design._v0 = classify.Lexicon(E.lexicon_data("v0"))
        out = E.lexicon_outputs(texts, Design._v0)
        self.tfidf, self.lexicon = vectorizer.transform(texts), np.column_stack([out.cat, out.danger])

    def matrix(self, lex_weight: float = 0.0):
        if not lex_weight:
            return self.tfidf
        return sparse.hstack([self.tfidf, sparse.csr_matrix(lex_weight / LEX_SCALE * self.lexicon)]).tocsr()


def estimator(kind: str, params: dict):
    if kind == "nb":
        return (ComplementNB if params["variant"] == "complement" else MultinomialNB)(alpha=params["alpha"])
    return LogisticRegression(C=params["C"], max_iter=3000)


def fit_task(kind: str, params: dict, design: Design, y):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return estimator(kind, params).fit(design.matrix(params.get("lex_weight", 0.0)), y)


def category_proba(model, design: Design, params: dict) -> np.ndarray:
    """n x 7 probabilities in E.CATEGORIES order (a class the model never saw gets 0)."""
    p = model.predict_proba(design.matrix(params.get("lex_weight", 0.0)))
    out = np.zeros((p.shape[0], len(E.CATEGORIES)))
    for j, label in enumerate(model.classes_):
        out[:, E.CATEGORIES.index(label)] = p[:, j]
    return out


def danger_proba(model, design: Design, params: dict) -> np.ndarray:
    p = model.predict_proba(design.matrix(params.get("lex_weight", 0.0)))
    return p[:, list(model.classes_).index(True)] if True in model.classes_ else np.zeros(p.shape[0])


class LexiconPredictor:
    """A word list, with or without a normalisation variant in front of it."""

    def __init__(self, lexicon: classify.Lexicon, prep=None):
        self.lexicon, self.prep = lexicon, prep

    def outputs(self, texts) -> E.Outputs:
        return E.lexicon_outputs(texts, self.lexicon, self.prep)


class Learned:
    """A fitted learned configuration: one vectorizer, one category model, one danger model."""

    def __init__(self, spec: dict, rows: list[dict]):
        self.spec, texts = spec, [r["text"] for r in rows]
        self.vectorizer = make_vectorizer().fit(texts)
        design = Design(self.vectorizer, texts)
        self.category = fit_task(spec["kind"], spec["category"], design, [r["category"] for r in rows])
        self.danger = fit_task(spec["kind"], spec["danger"], design, [bool(r["danger"]) for r in rows])

    def outputs(self, texts) -> E.Outputs:
        design = Design(self.vectorizer, list(texts))
        return E.Outputs(category_proba(self.category, design, self.spec["category"]), list(E.CATEGORIES),
                         danger_proba(self.danger, design, self.spec["danger"]), "proba")


def make_predictor(spec: dict, fit_rows: list[dict]):
    """spec: {"kind": "lexicon", "lexicon": "v0"|"v1", "variant": flags or None} or
    {"kind": "nb"|"lr"|"hybrid", "category": params, "danger": params}. fit_rows: the notes a learned model is fitted on."""
    if spec["kind"] != "lexicon":
        return Learned(spec, fit_rows)
    data = E.lexicon_data(spec["lexicon"])
    if spec.get("variant"):
        norm = variants.Normaliser(data, **spec["variant"])
        return LexiconPredictor(norm.lexicon, norm)
    return LexiconPredictor(classify.Lexicon(data))


def run(train: list[dict], validation: list[dict], write: bool = False) -> dict:
    """Every grid point of every model on validation; the best setting per model and task. Validation only."""
    texts_t, texts_v = [r["text"] for r in train], [r["text"] for r in validation]
    vectorizer = make_vectorizer().fit(texts_t)
    dt, dv = Design(vectorizer, texts_t), Design(vectorizer, texts_v)
    y_cat_t, y_d_t = [r["category"] for r in train], [bool(r["danger"]) for r in train]
    y, d = E.targets_of(validation)
    specs, grids = {}, {}
    for kind, grid in GRIDS.items():
        rows = {"category": [], "danger": []}
        for params in grid:
            cat = fit_task(kind, params, dt, y_cat_t)
            pred = np.array(E.CATEGORIES)[category_proba(cat, dv, params).argmax(axis=1)]
            rows["category"].append({"params": params, "macro_f1": E.macro_f1(y, pred), "accuracy": E.accuracy(y, pred)})
            score = danger_proba(fit_task(kind, params, dt, y_d_t), dv, params)
            rows["danger"].append({"params": params, "pr_auc": M.pr_auc(d, score), "roc_auc": M.roc_auc(d, score)})
        best = {task: max(range(len(grid)), key=lambda i: (rows[task][i]["macro_f1" if task == "category" else "pr_auc"], -i)) for task in rows}
        specs[NAMES[kind]] = {"kind": kind, "category": grid[best["category"]], "danger": grid[best["danger"]]}
        grids[NAMES[kind]] = rows
    if write:
        results.write_result("classification_learned", {"features": "tf-idf word 1-2 grams + char_wb 3-5 grams, on classify.tokens text", "chosen": specs, "grids": grids})
    return {"specs": specs, "grids": grids}


if __name__ == "__main__":
    train_rows, validation_rows = E.split_rows(E.load_train())
    outcome = run(train_rows, validation_rows, write=True)
    for name, spec in outcome["specs"].items():
        print(name, "category", spec["category"], "danger", spec["danger"])
        for task, key in (("category", "macro_f1"), ("danger", "pr_auc")):
            print("  ", task, [(tuple(r["params"].values()), round(r[key], 3)) for r in outcome["grids"][name][task]])
