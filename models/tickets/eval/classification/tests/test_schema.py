import json
from pathlib import Path

import pytest

from models.tickets.eval.classification import schema

DATA = Path(__file__).resolve().parents[1] / "data"
GOOD = {"id": "x1", "text": "lubak sa harap ng school", "lang": "taglish", "category": "pothole", "danger": False, "family": "f1"}


def test_a_good_row_passes():
    assert schema.check([GOOD], need_family=True) == []


@pytest.mark.parametrize(
    "change, expect",
    [
        ({"category": "sinkhole"}, "category must be"),
        ({"lang": "fr"}, "lang must be"),
        ({"danger": "yes"}, "danger must be"),
        ({"text": "   "}, "empty text"),
    ],
)
def test_bad_values_are_named(change, expect):
    problems = schema.check([{**GOOD, **change}], need_family=True)
    assert any(expect in p for p in problems)


def test_missing_family_matters_only_for_train():
    row = {k: v for k, v in GOOD.items() if k != "family"}
    assert schema.check([row], need_family=False) == []
    assert any("missing family" in p for p in schema.check([row], need_family=True))


def test_duplicate_ids_and_repeated_text_are_caught():
    problems = schema.check([GOOD, {**GOOD}], need_family=True)
    assert any("duplicate id" in p for p in problems) and any("repeated 2 times" in p for p in problems)


def test_summary_counts():
    s = schema.summary([GOOD, {**GOOD, "id": "x2", "danger": True, "category": "none"}])
    assert s["rows"] == 2 and s["danger_share"] == 0.5 and s["category"] == {"pothole": 1, "none": 1}


@pytest.mark.parametrize("name, need_family", [("notes_train.jsonl", True), ("notes_gold.jsonl", False)])
def test_the_committed_datasets_are_valid(name, need_family):
    path = DATA / name
    if not path.exists():
        pytest.skip(f"{name} has not been written yet")
    assert schema.check(schema.load(path), need_family) == []
