"""Improve the word list from the TRAINING notes only: lexicon v0 -> lexicon_v1.json, and the audit log LEXICON_CHANGES.md.

    models/.venv/bin/python -m models.tickets.eval.classification.tune_lexicon

The rule, one bar used in both directions. A term (a word or phrase, a negator, a boundary word) is JUDGED when it shows up in at
least 5 train notes across at least 3 families. Its precision is the share of the notes it applies to that carry its class:
  - a category term: the notes it appears in whose category is that category;
  - a danger term: the notes it fires on (not cancelled by a negator, as classify.py does) that are danger;
  - a negator: the notes where it stands just before a danger word that are NOT danger;
  - a boundary word: the notes where it sits between a negator and a danger word that ARE danger.
A new term is ADDED when it is judged and its precision is at least 0.9. A term of the shipped list is REMOVED when it is judged and
at least 0.9 of its notes are NOT of its class (precision at most 0.1). A term that is not judged stays: no evidence is not
evidence against. A judged term between the bars (class share above 0.1 and below 0.9) also stays and is listed as weak, with what
removing it would cost on validation. Why not remove everything below 0.9: a word can be the best cue its class has even at
precision 0.8 ("baha", "manhole"); the literal version of that rule was run once as a check and lost 0.05 macro-F1 on validation
(classification_lexicon.json, "removal_below_0.9"). Only the train split of the family split decides; validation puts a number
on each change afterwards, it never picks one.

Two plain guards on new category and danger terms, which only remove candidates: a phrase may not contain a term the list already
has (it adds no new evidence, only double counting), and may not start or end with a function word ("ilaw sa", "ako sa" are
contexts, not hazards).
"""
from __future__ import annotations

import copy
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from models.tickets import settings as s
from models.tickets.classification import classify
from models.tickets.eval.classification import evaluate as E
from models.tickets.eval.common import metrics as M
from models.tickets.eval.common import results

HERE = Path(__file__).resolve().parent
MIN_SUPPORT, MIN_FAMILIES, MIN_PRECISION = 5, 3, 0.9
MAX_N = 3  # words in a candidate phrase
FUNCTION_WORDS = frozenset(
    "sa ang ng na ay mga yung ung ito iyan iyon dito diyan doon ni nang si kay para at o ako ko ka mo namin natin kami tayo nila siya po opo "
    "pa pag din rin ba kasi kc lang naman may mayroon meron the a an of in on to is are was were be it its this that these those and or for "
    "with by from as i me my we our you your he she they there here so just also than then".split())


# ---- the rule --------------------------------------------------------------------------------------------------------
def evidence(fires, hits, families) -> dict:
    """What the notes say about one term. fires: the term is in the note; hits: the note is a positive for the class."""
    fires, hits, families = np.asarray(fires, bool), np.asarray(hits, bool), np.asarray(families)
    support = int(fires.sum())
    return {"support": support, "families": len(set(families[fires].tolist())), "precision": float(hits[fires].mean()) if support else 0.0}


def judged(ev: dict) -> bool:
    return ev["support"] >= MIN_SUPPORT and ev["families"] >= MIN_FAMILIES


def qualifies(ev: dict) -> bool:
    return judged(ev) and ev["precision"] >= MIN_PRECISION


# ---- the training notes, indexed -------------------------------------------------------------------------------------
class Corpus:
    """Train notes with their words, and the sets of notes where each term, negator or boundary word applies."""

    def __init__(self, rows: list[dict]):
        self.rows, self.n = rows, len(rows)
        self.words = [classify.tokens(r["text"]) for r in rows]
        self.parts = [[classify.tokens(p) for p in re.split(r"[,.;:!?\n]+", r["text"])] for r in rows]  # split at punctuation only
        self.family = np.array([r["family"] for r in rows])
        self.category = np.array([r["category"] for r in rows])
        self.danger = np.array([bool(r["danger"]) for r in rows])

    def mask(self, ids) -> np.ndarray:
        m = np.zeros(self.n, bool)
        m[list(ids)] = True
        return m

    def category_index(self) -> dict[tuple, set]:
        """Every 1..3-word phrase -> the notes it is in (whole note, as classify.category_scores reads it)."""
        index: dict[tuple, set] = defaultdict(set)
        for i, w in enumerate(self.words):
            for n in range(1, MAX_N + 1):
                for j in range(len(w) - n + 1):
                    index[tuple(w[j : j + n])].add(i)
        return index

    def danger_index(self, lex: classify.Lexicon) -> dict[tuple, set]:
        """Every 1..3-word phrase -> the notes where it would fire: in a clause, with no negator in the window before it."""
        index: dict[tuple, set] = defaultdict(set)
        for i, r in enumerate(self.rows):
            for words in classify._clauses(r["text"], lex):
                for n in range(1, MAX_N + 1):
                    for j in range(len(words) - n + 1):
                        if not any(w in lex.negators for w in words[max(0, j - s.NEGATION_WINDOW) : j]):
                            index[tuple(words[j : j + n])].add(i)
        return index

    def negation_events(self, lex: classify.Lexicon) -> dict[str, set]:
        """word -> notes where it stands in the window before a danger word. A current negator counts always; any other word
        only where no current negator already cancels that danger word (it would be new work for it)."""
        events: dict[str, set] = defaultdict(set)
        for i, r in enumerate(self.rows):
            for words in classify._clauses(r["text"], lex):
                for term in lex.danger:
                    for j in classify._find(words, term):
                        before = words[max(0, j - s.NEGATION_WINDOW) : j]
                        cancelled = any(w in lex.negators for w in before)
                        for w in set(before):
                            if w in lex.negators or not cancelled:
                                events[w].add(i)
        return events

    def boundary_events(self, lex: classify.Lexicon) -> dict[str, set]:
        """word -> notes where it sits between a negator and a danger word, inside the window of one stretch of punctuation."""
        events: dict[str, set] = defaultdict(set)
        for i, parts in enumerate(self.parts):
            for part in parts:
                for term in lex.danger:
                    for j in classify._find(part, term):
                        window = part[max(0, j - s.NEGATION_WINDOW) : j]
                        for k, w in enumerate(window):
                            if any(x in lex.negators for x in window[:k]):
                                events[w].add(i)
        return events


def contained(phrase: tuple, have: set) -> bool:
    """Does the phrase contain, as a run of its words, a term that is already in the list?"""
    return any(phrase[i : i + n] in have for n in range(1, len(phrase)) for i in range(len(phrase) - n + 1))


def usable(phrase: tuple) -> bool:
    """The two plain guards on a new category or danger term (see the module docstring)."""
    if phrase[0] in FUNCTION_WORDS or phrase[-1] in FUNCTION_WORDS:
        return False
    return any(len(w) >= 3 and not w.isdigit() for w in phrase)


# ---- one pass for every list --------------------------------------------------------------------------------------------
def phrases(index: dict[tuple, set]):
    """Candidate phrases with enough notes, one word first, then two, then three; the commonest first."""
    found = [(g, ids) for g, ids in index.items() if len(ids) >= MIN_SUPPORT]
    return sorted(found, key=lambda kv: (len(kv[0]), -len(kv[1]), kv[0]))


def tune(rows: list[dict], v0: dict) -> tuple[dict, list[dict], list[dict], dict]:
    """(the new word lists, the changes with their evidence, the weak terms that stayed, counts of what the rule did).
    Train notes only."""
    corpus, data, changes, weak, summary = Corpus(rows), copy.deepcopy(v0), [], [], {}
    key = lambda t: tuple(classify.tokens(t))

    def review(name, existing, fires_of, hits):
        """Judge every term of one list: remove it on strong evidence against, count the rest."""
        stats = {"in_v0": len(existing), "kept_with_evidence": 0, "weak_kept": 0, "not_judged": 0, "removed": 0, "added": 0}
        for term in list(existing):
            fires = fires_of(term)
            ev = evidence(fires, hits, corpus.family)
            if qualifies(evidence(fires, ~hits, corpus.family)):
                existing.remove(term)
                changes.append({"change": "remove", "list": name, "term": term, **ev})
                stats["removed"] += 1
            elif qualifies(ev):
                stats["kept_with_evidence"] += 1
            elif judged(ev):
                weak.append({"change": "would remove", "list": name, "term": term, **ev})
                stats["weak_kept"] += 1
            else:
                stats["not_judged"] += 1
        summary[name] = stats

    def add(name, term, ev):
        changes.append({"change": "add", "list": name, "term": term, **ev})
        summary[name]["added"] += 1

    # 1. negators and boundary words, judged against the shipped danger words (they decide what a danger word is worth)
    for name, events_of, hits in (("negators", corpus.negation_events, ~corpus.danger), ("boundaries", corpus.boundary_events, corpus.danger)):
        events = events_of(classify.Lexicon(data))
        review(name, data[name], lambda t: corpus.mask(events.get(t, ())), hits)
        for term, ids in sorted(events.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            ev = evidence(corpus.mask(ids), hits, corpus.family)
            if term not in data[name] and qualifies(ev):
                data[name].append(term)
                add(name, term, ev)

    # 2. danger words and phrases, with the negators and boundary words that remain
    index = corpus.danger_index(classify.Lexicon(data))
    review("danger", data["danger"], lambda t: corpus.mask(index.get(key(t), ())), corpus.danger)
    have = {key(t) for t in data["danger"]}
    for g, ids in phrases(index):
        ev = evidence(corpus.mask(ids), corpus.danger, corpus.family)
        if qualifies(ev) and g not in have and usable(g) and not contained(g, have):
            data["danger"].append(" ".join(g))
            have.add(g)
            add("danger", " ".join(g), ev)

    # 3. category words and phrases: review every list first, then add, so a word can land in the list it belongs to
    index = corpus.category_index()
    for c in E.HAZARDS:
        review(c, data["categories"][c], lambda t, c=c: corpus.mask(index.get(key(t), ())), corpus.category == c)
    have = {key(t) for c in E.HAZARDS for t in data["categories"][c]}
    for g, ids in phrases(index):
        if g in have or not usable(g) or contained(g, have):
            continue
        for c in E.HAZARDS:
            ev = evidence(corpus.mask(ids), corpus.category == c, corpus.family)
            if qualifies(ev):
                data["categories"][c].append(" ".join(g))
                have.add(g)
                add(c, " ".join(g), ev)
                break
    return data, changes, weak, summary


# ---- what each change did to validation ---------------------------------------------------------------------------------------
def apply_change(data: dict, change: dict) -> dict:
    """The word lists with just this one change (an addition, or the removal of a term)."""
    new = copy.deepcopy(data)
    name = change["list"]
    target = new["categories"][name] if name in new["categories"] else new[name]
    if change["change"] == "add":
        target.append(change["term"])
    else:
        target.remove(change["term"])
    return new


def validation_scores(data: dict, texts, y, d) -> dict:
    out = E.lexicon_outputs(texts, classify.Lexicon(data))
    return {"macro_f1": E.macro_f1(y, E.default_labels(out)), "pr_auc": M.pr_auc(d, out.danger)}


def add_effects(changes: list[dict], weak: list[dict], v0: dict, validation: list[dict]) -> dict:
    """Each change on its own against v0 (for a weak term: what removing it would do): macro-F1 at the shipped thresholds for a category
    list, PR-AUC for the danger list, negators and boundary words. Returns the v0 reference numbers."""
    texts, (y, d) = [r["text"] for r in validation], E.targets_of(validation)
    base = validation_scores(v0, texts, y, d)
    for change in changes + weak:
        metric = "pr_auc" if change["list"] in ("danger", "negators", "boundaries") else "macro_f1"
        change["effect_metric"] = metric
        change["effect"] = validation_scores(apply_change(v0, change), texts, y, d)[metric] - base[metric]
    return base


def without_terms(data: dict, terms: list[dict]) -> dict:
    """The lists with all of these terms removed."""
    new = copy.deepcopy(data)
    for term in terms:
        target = new["categories"][term["list"]] if term["list"] in new["categories"] else new[term["list"]]
        target.remove(term["term"])
    return new


# ---- files -----------------------------------------------------------------------------------------------------------------------
def write_lexicon(path: Path, data: dict) -> None:
    def block(terms, width=112, indent=6):
        items, lines, line = [json.dumps(t, ensure_ascii=False) for t in terms], [], []
        for item in items:  # whole terms only: a line may break between terms, never inside one
            if line and len(", ".join(line + [item])) > width:
                lines.append(", ".join(line) + ",")
                line = []
            line.append(item)
        return "\n".join(" " * indent + x for x in lines + [", ".join(line)])

    parts = [f'    "{c}": [\n{block(t)}\n    ]' for c, t in data["categories"].items()]
    note = ("Version 1: lexicon v0 edited by eval/classification/tune_lexicon.py from the training notes only (a term needs 5 notes, 3 families "
            "and precision 0.9 to be added). See LEXICON_CHANGES.md. Matching is on whole words after lowercasing and removing accents and punctuation.")
    path.write_text(
        "{\n" + f'  "_note": {json.dumps(note)},\n  "categories": {{\n' + ",\n".join(parts) + "\n  },\n"
        + f'  "danger": [\n{block(data["danger"], indent=4)}\n  ],\n  "negators": {json.dumps(data["negators"], ensure_ascii=False)},\n'
        + f'  "boundaries": {json.dumps(data["boundaries"], ensure_ascii=False)}\n' + "}\n")


def write_log(path: Path, changes: list[dict], weak: list[dict], summary: dict, base: dict, final: dict, strict: dict, split: dict) -> None:
    row = lambda c: (f"| {c['change']} | {c['list']} | {c['term']} | {c['support']} | {c['families']} | {c['precision']:.2f} | "
                     f"{c['effect_metric'].replace('_', '-')} {c['effect']:+.4f} |")
    head = "| change | list | term | train notes | families | precision | effect on validation |\n|---|---|---|---|---|---|---|"
    order = {"remove": 0, "would remove": 0, "add": 1}
    ordered = lambda rows: [row(c) for c in sorted(rows, key=lambda c: (order[c["change"]], c["list"], -c["support"], c["term"]))]
    lines = [
        "# Lexicon changes: v0 to v1",
        "",
        "Written by `tune_lexicon.py`; do not edit by hand. Every change below comes from the TRAIN split only "
        f"({split['train_rows']} notes, {split['train_families']} families, seed {split['seed']}). Validation ({split['validation_rows']} notes) was used only to "
        "put a number on each change after it was decided.",
        "",
        "## The rule",
        f"A term is judged when it is in at least {MIN_SUPPORT} train notes across at least {MIN_FAMILIES} families. Its precision is the share of the notes it "
        "applies to that carry its class: the category; danger (a danger word counts only where classify.py would not cancel it); not-danger for a negator; "
        f"danger for a boundary word. **Add** a new term when it is judged and its precision is at least {MIN_PRECISION}. **Remove** a v0 term when it is judged and "
        f"at least {MIN_PRECISION} of its notes are NOT of its class (precision at most {1 - MIN_PRECISION:.1f}). A term that is not judged stays. A judged term in between "
        "stays too and is listed as weak below. Guards on new terms only: a phrase may not contain a term the list already has, and may not start or end "
        "with a function word.",
        "",
        "**Effect** = the change on its own against v0, on validation: macro-F1 of the category hint at the shipped thresholds for a category list, "
        "PR-AUC of the danger score for the danger list, negators and boundary words. For a weak term it is what removing it would do. "
        "Terms interact, so effects do not add up to the totals.",
        "",
        "## Totals on validation",
        f"| | category macro-F1 (shipped thresholds) | danger PR-AUC |\n|---|---|---|\n| v0 | {base['macro_f1']:.4f} | {base['pr_auc']:.4f} |\n"
        f"| v1 (this log) | {final['macro_f1']:.4f} | {final['pr_auc']:.4f} |\n| change | {final['macro_f1'] - base['macro_f1']:+.4f} | {final['pr_auc'] - base['pr_auc']:+.4f} |\n"
        f"| v1 and also removing every weak term (the literal remove-below-0.9 rule, a check only) | {strict['macro_f1']:.4f} | {strict['pr_auc']:.4f} |",
        "",
        "## What the rule did to each list",
        "| list | v0 terms | judged and qualified | judged, weak (kept) | not judged (kept) | removed | added |\n|---|---|---|---|---|---|---|",
        *[f"| {n} | {v['in_v0']} | {v['kept_with_evidence']} | {v['weak_kept']} | {v['not_judged']} | {v['removed']} | {v['added']} |" for n, v in summary.items()],
        "",
        "## Every change",
        head,
        *ordered(changes),
        "",
        "## Weak v0 terms: judged, precision below 0.9, kept",
        "These were not removed because the evidence against them is not strong (precision above 0.1). The effect column is what removing each would have cost.",
        head,
        *ordered(weak),
    ]
    if not any(c["list"] in ("negators", "boundaries") for c in changes):
        lines += ["", "No negator and no boundary word was added or removed: no word before a danger word cancelled it with precision 0.9, and no word between a negator "
                  "and a danger word marked a danger note with precision 0.9 on enough notes."]
    path.write_text("\n".join(lines) + "\n")


def run(write: bool = False) -> dict:
    rows = E.load_train()
    train, validation = E.split_rows(rows)
    v0 = E.lexicon_data("v0")
    v1, changes, weak, summary = tune(train, v0)
    base = add_effects(changes, weak, v0, validation)
    texts, (y, d) = [r["text"] for r in validation], E.targets_of(validation)
    final, strict = validation_scores(v1, texts, y, d), validation_scores(without_terms(v1, weak), texts, y, d)
    split = {"seed": E.SEED, "train_rows": len(train), "train_families": len({r["family"] for r in train}), "validation_rows": len(validation)}
    if write:
        write_lexicon(E.LEXICON_V1, v1)
        write_log(HERE / "LEXICON_CHANGES.md", changes, weak, summary, base, final, strict, split)
        results.write_result("classification_lexicon", {
            "rule": {"min_support": MIN_SUPPORT, "min_families": MIN_FAMILIES, "min_precision": MIN_PRECISION, "max_words": MAX_N,
                     "remove_when": "judged and precision <= 0.1 (at least 0.9 of its notes are not of its class)"},
            "split": split, "summary": summary, "changes": changes, "weak_kept": weak, "validation_v0": base, "validation_v1": final,
            "removal_below_0.9": strict})
    return {"v1": v1, "changes": changes, "weak": weak, "summary": summary, "v0_validation": base, "v1_validation": final, "strict": strict}


if __name__ == "__main__":
    out = run(write=True)
    print(json.dumps(out["summary"]))
    print("v0", out["v0_validation"], "\nv1", out["v1_validation"], "\nstrict", out["strict"])
    print(Counter((c["change"], c["list"]) for c in out["changes"]))
