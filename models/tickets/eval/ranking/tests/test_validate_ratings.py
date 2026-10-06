import copy
import json
import re

import pytest

from models.tickets.eval.ranking import pairs, validate_ratings as v


@pytest.fixture(scope="module")
def blind():
    return pairs.build()[0]


def ratings(blind, persona="engineer"):
    """A complete, valid file for the survey."""
    return {"persona": persona,
            "pairs": [{"id": p["id"], "choice": "AB"[n % 2], "confidence": 1 + n % 3} for n, p in enumerate(blind["pairs"])],
            "urgency": [{"id": t["id"], "urgency": 1 + n % 5} for n, t in enumerate(blind["tickets"])]}


def test_a_complete_file_passes_for_every_persona(blind):
    for persona in v.PERSONAS:
        assert v.validate(ratings(blind, persona), blind, f"ratings_{persona}.json") == []
    assert v.validate(ratings(blind), blind) == []  # no file name to check


def test_ties_are_valid(blind):
    good = ratings(blind)
    good["pairs"][0]["choice"] = "tie"
    assert v.validate(good, blind) == []


def test_a_missing_pair_is_caught_by_name(blind):
    bad = ratings(blind)
    gone = bad["pairs"].pop(7)["id"]
    problems = v.validate(bad, blind)
    assert len(problems) == 1 and "missing" in problems[0] and gone in problems[0]


def test_a_missing_ticket_is_caught_by_name(blind):
    bad = ratings(blind)
    gone = bad["urgency"].pop()["id"]
    problems = v.validate(bad, blind)
    assert len(problems) == 1 and "urgency" in problems[0] and "missing" in problems[0] and gone in problems[0]


def test_an_empty_list_reports_everything_missing_in_one_line(blind):
    assert v.validate({**ratings(blind), "pairs": []}, blind) == [f"pairs: {len(blind['pairs'])} missing, first " + ", ".join(sorted(p["id"] for p in blind["pairs"])[:10])]


def test_a_pair_or_ticket_twice_is_caught(blind):
    bad = ratings(blind)
    bad["pairs"].append(copy.deepcopy(bad["pairs"][3]))
    bad["urgency"].append(copy.deepcopy(bad["urgency"][5]))
    problems = v.validate(bad, blind)
    assert sorted(problems) == sorted([f"pairs: {bad['pairs'][3]['id']} appears 2 times", f"urgency: {bad['urgency'][5]['id']} appears 2 times"])


def test_an_id_that_is_not_in_the_survey_is_caught(blind):
    bad = ratings(blind)
    bad["pairs"][0]["id"] = "p999"
    bad["urgency"][0]["id"] = ["t001"]  # not even text
    problems = v.validate(bad, blind)
    assert any("unknown id 'p999'" in p for p in problems) and any("unknown id ['t001']" in p for p in problems)
    assert any("missing" in p for p in problems)


@pytest.mark.parametrize("choice", ["C", "a", "b", "TIE", "Tie", "", None, 1, ["A"], True])
def test_a_bad_choice_is_caught(blind, choice):
    bad = ratings(blind)
    bad["pairs"][2]["choice"] = choice
    problems = v.validate(bad, blind)
    assert len(problems) == 1 and "choice must be" in problems[0] and bad["pairs"][2]["id"] in problems[0]


@pytest.mark.parametrize("confidence", [0, 4, -1, "2", 2.0, 2.5, None, True, [2]])
def test_a_bad_confidence_is_caught(blind, confidence):
    bad = ratings(blind)
    bad["pairs"][2]["confidence"] = confidence
    problems = v.validate(bad, blind)
    assert len(problems) == 1 and "confidence must be" in problems[0]


@pytest.mark.parametrize("urgency", [0, 6, -3, "3", 3.0, 3.5, None, True, False, [3]])
def test_a_bad_urgency_is_caught(blind, urgency):
    bad = ratings(blind)
    bad["urgency"][4]["urgency"] = urgency
    problems = v.validate(bad, blind)
    assert len(problems) == 1 and "urgency must be" in problems[0] and bad["urgency"][4]["id"] in problems[0]


def test_a_missing_value_is_caught(blind):
    bad = ratings(blind)
    del bad["pairs"][1]["confidence"]
    del bad["urgency"][1]["urgency"]
    assert len(v.validate(bad, blind)) == 2


@pytest.mark.parametrize("persona", ["", "Engineer", "bob", None, 7, ["engineer"]])
def test_a_wrong_persona_is_caught(blind, persona):
    bad = {**ratings(blind), "persona": persona}
    problems = v.validate(bad, blind)
    assert len(problems) == 1 and "persona must be one of" in problems[0]


def test_a_missing_persona_is_caught(blind):
    bad = ratings(blind)
    del bad["persona"]
    assert any("missing key 'persona'" in p for p in v.validate(bad, blind))


def test_the_file_name_must_match_the_persona(blind):
    problems = v.validate(ratings(blind, "paramedic"), blind, "ratings_engineer.json")
    assert problems == ["persona 'paramedic' belongs in ratings_paramedic.json, not ratings_engineer.json"]
    assert v.validate(ratings(blind, "paramedic"), blind, "paramedic.json")


def test_the_shape_of_the_file_is_checked(blind):
    assert v.validate([], blind) == ["the file must hold one JSON object"]
    assert any("unexpected key 'notes'" in p for p in v.validate({**ratings(blind), "notes": "x"}, blind))
    only = {"persona": "engineer", "pairs": []}
    assert any("missing key 'urgency'" in p for p in v.validate(only, blind))
    assert v.validate({**ratings(blind), "pairs": {}}, blind) == ["pairs must be a list"]
    bad = ratings(blind)
    bad["pairs"][0] = "p001"
    bad["urgency"][0]["reason"] = "dark"
    problems = v.validate(bad, blind)
    assert any("pairs[1] must be an object" in p for p in problems) and any("unexpected key 'reason'" in p for p in problems)


def test_the_command_line_reads_files_and_sets_the_exit_code(blind, tmp_path, capsys):
    survey = tmp_path / "blind_survey.json"
    survey.write_text(json.dumps(blind))
    good = tmp_path / "ratings_engineer.json"
    good.write_text(json.dumps(ratings(blind)))
    assert v.main([str(good), "--blind", str(survey)]) == 0
    assert "ok" in capsys.readouterr().out
    short = ratings(blind, "captain")
    short["pairs"].pop()
    (tmp_path / "ratings_captain.json").write_text(json.dumps(short))
    (tmp_path / "ratings_commuter.json").write_text("{not json")
    code = v.main([str(good), str(tmp_path / "ratings_captain.json"), str(tmp_path / "ratings_commuter.json"), str(tmp_path / "ratings_paramedic.json"), "--blind", str(survey)])
    out = capsys.readouterr().out
    assert code == 1 and "pairs: 1 missing" in out and out.count("cannot read") == 2


def test_the_committed_blind_file_accepts_a_complete_file():
    committed = json.loads(v.BLIND.read_text(encoding="utf-8"))
    assert v.validate(ratings(committed), committed, "ratings_engineer.json") == []


# ---- the instructions a rater is given -------------------------------------------------------------------------------
@pytest.mark.parametrize("persona", sorted(v.PERSONAS))
def test_a_rater_reads_only_its_own_persona_and_nothing_about_the_key(persona):
    text = v.render_instructions(persona)
    assert text.startswith("# ") and v.PERSONAS[persona] in text and f"ratings_{persona}.json" in text
    assert not any(other in text for name, other in v.PERSONAS.items() if name != persona)
    assert "{persona" not in text and "<!--" not in text and "Template" not in text
    # no hint that a score, an answer key, splits or repeated pairs exist (the persona sentence is free text: a commuter takes the train)
    body = text.replace(v.PERSONAS[persona], "")
    assert not re.search(r"\b(answer key|answer_key|score|scores|scoring|priority|split|swap|swapped|repeat|repeated|repeats|stratum|train|training|validation|test|bias)\b", body, re.I)
    assert "answer_key" not in text


def test_the_instructions_carry_the_tasks_formats_and_rules():
    text = v.render_instructions("engineer")
    for part in ["Which should it fix first", "`\"A\"`, `\"B\"` or `\"tie\"`", "from 1 to 5", "Judge only from the descriptions", "any other file in the repository",
                 "No averaging and no hedging", "`tie` is allowed but rare", "blind_survey.json"]:
        assert part in text, part
    assert text.index(v.PERSONAS["engineer"]) < text.index("## What you have")  # the persona comes first


def test_the_example_in_the_instructions_is_valid_for_the_validator():
    for persona in v.PERSONAS:
        block = re.search(r"```json\n(.*?)```", v.render_instructions(persona), re.S).group(1)
        example = json.loads(block)
        assert set(example) == {"persona", "pairs", "urgency"} and example["persona"] == persona
        assert v.check_rows("pairs", example["pairs"], {"p000", "p999"}) == []
        assert v.check_rows("urgency", example["urgency"], {"t000", "t999"}) == []


def test_the_instructions_command_prints_the_rendered_text(capsys):
    assert v.main(["--instructions", "wheelchair"]) == 0
    assert capsys.readouterr().out.strip() == v.render_instructions("wheelchair").strip()
