"""Text normalisation that classify.py lacks, tried on top of a word list and measured on validation.

    models/.venv/bin/python -m models.tickets.eval.classification.variants

classify.py is not touched. A variant is a text -> text step in front of the unchanged classify functions, so punctuation
(which ends a negator's reach) survives, plus a rewritten copy of the word list when the step also changes list words:

  repeats    "lubaaak" -> lubak: runs of one letter squeezed to one, in the note and in the list's words alike
  typo1      one edit away (insert, delete, swap, change) from a list word of 6+ letters, only when exactly one fits
  typo1_strict  the same, but 7+ letters and the same first letter (typos rarely change the first letter, look-alikes often do)
  prefix     a leading mag- / nag- / na- is stripped when what is left is a list word ("nagbaha" -> baha)
  suffix_ng  a trailing -ng is stripped the same way ("asong" -> aso)

A word the list already has is never rewritten. Stripping needs the rest to be a list word, which is why these cannot
turn "bahay" (house) into "baha" (flood). typo1_naive drops the 6-letter floor and is kept only as the control that shows why
the floor is there. Which variant is carried to the gold run: the one with the largest rise in category macro-F1 plus danger PR-AUC
on validation, if that rise is above zero.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

from models.tickets.classification import classify
from models.tickets.eval.classification import evaluate as E
from models.tickets.eval.common import metrics as M
from models.tickets.eval.common import results

PREFIXES = ("mag", "nag", "na")
MIN_REST = 3  # a stripped word shorter than this is not a word
VARIANTS = {
    "repeats": {"squeeze": True},
    "typo1": {"typo": True},
    "typo1_strict": {"typo": True, "typo_min_len": 7, "typo_same_first": True},
    "typo1_naive": {"typo": True, "typo_min_len": 4},
    "prefix": {"prefix": True},
    "suffix_ng": {"suffix": True},
    "repeats+prefix+suffix": {"squeeze": True, "prefix": True, "suffix": True},
    "repeats+prefix+suffix+typo1": {"squeeze": True, "prefix": True, "suffix": True, "typo": True},
    "repeats+prefix+suffix+typo1_strict": {"squeeze": True, "prefix": True, "suffix": True, "typo": True, "typo_min_len": 7, "typo_same_first": True},
}


def squeeze_word(word: str) -> str:
    return re.sub(r"([a-z])\1+", r"\1", word)


def within_one_edit(a: str, b: str) -> bool:
    """True when a and b differ by exactly one insertion, deletion, change or swap of two neighbours."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        wrong = [i for i in range(len(a)) if a[i] != b[i]]
        return len(wrong) == 1 or (len(wrong) == 2 and wrong[1] == wrong[0] + 1 and a[wrong[0]] == b[wrong[1]] and a[wrong[1]] == b[wrong[0]])
    short, long = sorted((a, b), key=len)
    return any(long[:i] + long[i + 1 :] == short for i in range(len(long)))


class Normaliser:
    """A text normaliser and the matching word list. norm(text) is the rewritten text; norm.lexicon is a classify.Lexicon."""

    def __init__(self, data: dict, squeeze=False, typo=False, prefix=False, suffix=False, typo_min_len=6, typo_same_first=False):
        self.squeeze, self.typo, self.prefix, self.suffix = squeeze, typo, prefix, suffix
        self.typo_min_len, self.typo_same_first = typo_min_len, typo_same_first
        shrink = lambda term: " ".join(squeeze_word(w) if squeeze else w for w in classify.tokens(term))
        self.lexicon = classify.Lexicon({
            "categories": {c: [shrink(t) for t in terms] for c, terms in data["categories"].items()},
            "danger": [shrink(t) for t in data["danger"]], "negators": [shrink(t) for t in data["negators"]],
            "boundaries": [shrink(t) for t in data.get("boundaries", [])]})
        lex = self.lexicon
        self.vocab = {w for terms in lex.categories.values() for t in terms for w in t} | {w for t in lex.danger for w in t} | lex.negators | lex.boundaries
        self._cache: dict[str, str] = {}

    def word(self, word: str) -> str:
        if word not in self._cache:
            self._cache[word] = self._rewrite(squeeze_word(word) if self.squeeze else word)
        return self._cache[word]

    def _rewrite(self, word: str) -> str:
        if word in self.vocab or word.isdigit():
            return word
        stems = [word]
        if self.suffix and word.endswith("ng"):
            stems.append(word[:-2])
        for stem in list(stems):
            stems += [stem[len(p):] for p in PREFIXES if self.prefix and stem.startswith(p)]
        for stem in stems[1:]:
            if len(stem) >= MIN_REST and stem in self.vocab:
                return stem
        if self.typo:
            near = [v for v in self.vocab if len(v) >= self.typo_min_len and (v[0] == word[0] or not self.typo_same_first) and within_one_edit(word, v)]
            if len(near) == 1:
                return near[0]
        return word

    def __call__(self, text: str) -> str:
        """The text with every word rewritten and everything between the words (punctuation, spaces) left alone."""
        text = unicodedata.normalize("NFKD", text.lower())
        text = "".join(c for c in text if not unicodedata.combining(c)).replace("'", "").replace("’", "")
        return re.sub(r"[a-z0-9]+", lambda m: self.word(m.group()), text)

    def rewrites(self, texts) -> Counter:
        """How often each (word, replacement) pair happened: what the step really does to a set of notes."""
        seen: Counter = Counter()
        for text in texts:
            for w in classify.tokens(text):
                new = self.word(w)
                if new != w:
                    seen[(w, new)] += 1
        return seen


def measure(data: dict, flags: dict | None, texts, y, d) -> dict:
    """One word list with one variant on one labelled set, at the shipped thresholds (so lists compare like for like)."""
    norm = Normaliser(data, **flags) if flags else None
    out = E.lexicon_outputs(texts, norm.lexicon if norm else classify.Lexicon(data), norm)
    cat = E.category_report(y, E.default_labels(out))
    flagged = E.danger_at(d, out.danger, E.s.DANGER_MIN_SCORE)
    row = {"macro_f1": cat["macro_f1"], "accuracy": cat["accuracy"], "coverage": cat["coverage"], "hint_precision": cat["precision"],
           "danger_pr_auc": M.pr_auc(d, out.danger), "danger_roc_auc": M.roc_auc(d, out.danger),
           "danger_precision": flagged["precision"], "danger_recall": flagged["recall"], "danger_f2": flagged["f2"]}
    if norm:
        rewrites = norm.rewrites(texts)
        row.update({"rewritten_words": sum(rewrites.values()), "top_rewrites": [[a, b, n] for (a, b), n in rewrites.most_common(8)]})
    return row


def pick_best(table: list[dict]) -> dict | None:
    """The variant on v1 with the largest rise in category macro-F1 plus danger PR-AUC, if that rise is above zero (a tie: fewer steps)."""
    helping = [r for r in table if r["base"] == "v1" and r["variant"] != "(none)" and r["d_macro_f1"] + r["d_danger_pr_auc"] > 0]
    if not helping:
        return None
    top = max(helping, key=lambda r: (r["d_macro_f1"] + r["d_danger_pr_auc"], -len(VARIANTS[r["variant"]])))
    return {"name": top["variant"], "flags": VARIANTS[top["variant"]], "base": "v1"}


def run(validation: list[dict], write: bool = False) -> dict:
    """Every variant on the shipped list (v0) and the improved one (v1), validation only. `best` is the variant to carry
    forward on v1, or None when none helps."""
    texts, (y, d) = [r["text"] for r in validation], E.targets_of(validation)
    table = []
    for base in ("v0", "v1"):
        data = E.lexicon_data(base)
        reference = measure(data, None, texts, y, d)
        table.append({"base": base, "variant": "(none)", **reference})
        for name, flags in VARIANTS.items():
            row = measure(data, flags, texts, y, d)
            table.append({"base": base, "variant": name, **row, "d_macro_f1": row["macro_f1"] - reference["macro_f1"],
                          "d_danger_pr_auc": row["danger_pr_auc"] - reference["danger_pr_auc"]})
    best = pick_best(table)
    if write:
        results.write_result("classification_variants", {"rule": "carry forward the variant (on v1) with the largest rise in category macro-F1 + danger PR-AUC, if above zero",
                                                          "table": table, "best": best})
    return {"table": table, "best": best}


if __name__ == "__main__":
    rows = E.load_train()
    outcome = run(E.split_rows(rows)[1], write=True)
    cols = ["base", "variant", "macro_f1", "d_macro_f1", "coverage", "hint_precision", "danger_pr_auc", "d_danger_pr_auc", "danger_f2", "rewritten_words"]
    print(results.md_table(outcome["table"], cols, digits=4))
    print("best:", outcome["best"])
