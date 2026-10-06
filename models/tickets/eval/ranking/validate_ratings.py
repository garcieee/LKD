"""Checks a rater's ratings file against the blind survey, and prints the exact instructions for a rater.

  models/.venv/bin/python -m models.tickets.eval.ranking.validate_ratings ratings_engineer.json [more files] [--blind PATH]
      prints every problem found and exits 1 if any file has one
  models/.venv/bin/python -m models.tickets.eval.ranking.validate_ratings --instructions engineer
      prints RATER_INSTRUCTIONS.md with that persona filled in: the text to give that rater

A ratings file is called ratings_<persona>.json and holds
  {"persona": "engineer",
   "pairs":   [{"id": "p001", "choice": "A" | "B" | "tie", "confidence": 1 | 2 | 3}, ...],   every pair of the blind file, once
   "urgency": [{"id": "t001", "urgency": 1 to 5}, ...]}                                       every ticket of the blind file, once
Standard library only.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
BLIND = HERE / "data" / "blind_survey.json"
CHOICES = ("A", "B", "tie")
PERSONAS = {  # the persona sentence is the first thing in a rater's instructions
    "engineer": "You are a public-works engineer for a city government: you inspect roads, drains and street lights and decide which repair jobs the crews do first.",
    "captain": "You are a barangay captain: you know the people on your streets, hear their complaints every day, and are the one residents come to when something goes wrong.",
    "wheelchair": "You are a wheelchair user who gets around the city every day and depends on sidewalks, ramps and crossings being clear and smooth.",
    "commuter": "You are a daily commuter who walks, rides jeepneys and takes the train to work and back, often early in the morning or after dark.",
    "paramedic": "You are a paramedic on an ambulance crew who treats people hurt in falls, crashes and floods on city streets.",
}


def whole(low: int, high: int):
    """A JSON integer from low to high: not text, not 2.0, not true."""
    return lambda v: type(v) is int and low <= v <= high


FIELDS = {  # per list: field -> (is it valid, what is wanted)
    "pairs": {"choice": (lambda v: v in CHOICES, 'one of "A", "B", "tie"'), "confidence": (whole(1, 3), "a whole number from 1 to 3")},
    "urgency": {"urgency": (whole(1, 5), "a whole number from 1 to 5")},
}


def check_rows(name: str, rows, expected: set[str]) -> list[str]:
    """Problems in one list: every row valid, every expected id present once, no other id."""
    if not isinstance(rows, list):
        return [f"{name} must be a list"]
    problems, seen = [], Counter()
    for n, row in enumerate(rows, 1):
        where = f"{name}[{n}]"
        if not isinstance(row, dict):
            problems.append(f"{where} must be an object")
            continue
        problems += [f"{where}: unexpected key {k!r}" for k in row if k != "id" and k not in FIELDS[name]]
        rid = row.get("id")
        if isinstance(rid, str) and rid in expected:
            seen[rid] += 1
        else:
            problems.append(f"{where}: unknown id {rid!r}")
        problems += [f"{where} ({rid}): {f} must be {wanted}, got {row.get(f)!r}" for f, (ok, wanted) in FIELDS[name].items() if not ok(row.get(f))]
    problems += [f"{name}: {i} appears {c} times" for i, c in sorted(seen.items()) if c > 1]
    missing = sorted(expected - set(seen))
    if missing:
        problems.append(f"{name}: {len(missing)} missing, first {', '.join(missing[:10])}")
    return problems


def validate(ratings, blind: dict, filename: str | None = None) -> list[str]:
    """Every problem found, as a readable line. An empty list means the file is complete and valid."""
    if not isinstance(ratings, dict):
        return ["the file must hold one JSON object"]
    problems = [f"unexpected key {k!r}" for k in ratings if k not in ("persona", "pairs", "urgency")]
    problems += [f"missing key {k!r}" for k in ("persona", "pairs", "urgency") if k not in ratings]
    persona = ratings.get("persona")
    if not isinstance(persona, str) or persona not in PERSONAS:
        problems.append(f"persona must be one of {', '.join(PERSONAS)}, got {persona!r}")
    elif filename is not None and filename != f"ratings_{persona}.json":
        problems.append(f"persona {persona!r} belongs in ratings_{persona}.json, not {filename}")
    expected = {"pairs": {p["id"] for p in blind["pairs"]}, "urgency": {t["id"] for t in blind["tickets"]}}
    for name, ids in expected.items():
        if name in ratings:
            problems += check_rows(name, ratings[name], ids)
    return problems


def validate_file(path: Path, blind: dict) -> list[str]:
    try:
        ratings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [f"cannot read {path.name} as JSON: {error}"]
    return validate(ratings, blind, path.name)


def render_instructions(persona: str) -> str:
    """RATER_INSTRUCTIONS.md without its template comment and with the persona filled in: exactly what that rater reads."""
    text = re.sub(r"<!--.*?-->\n*", "", (HERE / "RATER_INSTRUCTIONS.md").read_text(encoding="utf-8"), flags=re.S)
    return text.replace("{persona_sentence}", PERSONAS[persona]).replace("{persona}", persona)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check ratings_<persona>.json files, or print a rater's instructions.")
    parser.add_argument("files", nargs="*", type=Path, help="ratings files to check")
    parser.add_argument("--blind", type=Path, default=BLIND, help="the blind survey (default: data/blind_survey.json)")
    parser.add_argument("--instructions", choices=sorted(PERSONAS), help="print the instructions for this persona and stop")
    args = parser.parse_args(argv)
    if args.instructions:
        print(render_instructions(args.instructions))
        return 0
    blind = json.loads(args.blind.read_text(encoding="utf-8"))
    bad = 0
    for path in args.files:
        problems = validate_file(path, blind)
        bad += bool(problems)
        print(f"{path}: " + ("ok" if not problems else f"{len(problems)} problem(s)"))
        for problem in problems:
            print(f"  {problem}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
