"""The one definition of a labelled note, and a checker both note datasets must pass.

A line of notes_train.jsonl or notes_gold.jsonl:
  {"id": "tr-0001", "text": "...", "lang": "en|tl|taglish", "category": <CATEGORIES>, "danger": true|false,
   "family": "<scenario id>"}                      <- family is required in train, optional in gold

category is the hazard the NOTE describes ("none" when the text does not say, e.g. "please fix asap").
danger is true when the note describes a present risk of physical harm to people (a child, a fall, a crash,
electric shock, drowning). Negated or merely annoying notes are false.
"""
import json
from collections import Counter
from pathlib import Path

CATEGORIES = {"pothole", "open_manhole", "flooded_drain", "broken_streetlight", "blocked_sidewalk", "other", "none"}
LANGS = {"en", "tl", "taglish"}


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def check(rows: list[dict], need_family: bool) -> list[str]:
    """Every problem found, as a readable line. Empty list means the dataset is valid."""
    problems: list[str] = []
    ids: set[str] = set()
    texts: Counter = Counter()
    for n, row in enumerate(rows, 1):
        where = f"line {n} ({row.get('id', '?')})"
        for key in ("id", "text", "lang", "category", "danger") + (("family",) if need_family else ()):
            if key not in row:
                problems.append(f"{where}: missing {key}")
        if row.get("id") in ids:
            problems.append(f"{where}: duplicate id")
        ids.add(row.get("id"))
        text = row.get("text")
        if not isinstance(text, str) or not text.strip():
            problems.append(f"{where}: empty text")
        else:
            texts[" ".join(text.lower().split())] += 1
        if row.get("lang") not in LANGS:
            problems.append(f"{where}: lang must be one of {sorted(LANGS)}")
        if row.get("category") not in CATEGORIES:
            problems.append(f"{where}: category must be one of {sorted(CATEGORIES)}")
        if not isinstance(row.get("danger"), bool):
            problems.append(f"{where}: danger must be true or false")
    problems += [f"text repeated {c} times: {t[:60]!r}" for t, c in texts.items() if c > 1]
    return problems


def summary(rows: list[dict]) -> dict:
    return {
        "rows": len(rows),
        "category": dict(Counter(r["category"] for r in rows)),
        "lang": dict(Counter(r["lang"] for r in rows)),
        "danger_share": round(sum(r["danger"] for r in rows) / max(len(rows), 1), 3),
        "families": len({r.get("family") for r in rows if r.get("family")}),
    }
