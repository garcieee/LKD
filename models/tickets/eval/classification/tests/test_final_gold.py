import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from models.tickets.eval.classification import evaluate as E
from models.tickets.eval.classification import final_gold as G


class Dummy:
    """Stands in for a model: says nothing useful, which is all the gate tests need."""

    def outputs(self, texts):
        return E.Outputs(np.zeros((len(texts), 7)), list(E.CATEGORIES), np.zeros(len(texts)), "proba")


def write_gold(path: Path, n: int = 3) -> Path:
    rows = [{"id": f"g{i}", "text": f"note {i}", "lang": "en", "category": "pothole", "danger": bool(i % 2), "hard": "slice-a"} for i in range(n)]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def test_a_second_scoring_is_refused_unless_forced_and_every_scoring_is_logged(tmp_path):
    gold, log = write_gold(tmp_path / "gold.jsonl"), tmp_path / "gold_runs.log"
    rows, out = G.score("cfg", Dummy(), gold, log)
    assert len(rows) == 3 and out.cat.shape == (3, 7) and G.logged(log) == ["cfg"]
    with pytest.raises(G.AlreadyScored):
        G.score("cfg", Dummy(), gold, log)
    assert G.logged(log) == ["cfg"]  # the refusal is not a scoring: nothing logged
    G.score("cfg", Dummy(), gold, log, force=True)
    G.score("other", Dummy(), gold, log)
    lines = [line.split("\t") for line in log.read_text().splitlines()]
    assert [line[1] for line in lines] == ["cfg", "cfg", "other"] and lines[1][2] == "forced" and len(lines[0]) == 2 and len(lines[2]) == 2
    assert all(datetime.fromisoformat(line[0]) for line in lines)  # a timestamp first


def test_a_refused_scoring_reads_no_notes_and_logs_nothing(tmp_path):
    log = tmp_path / "gold_runs.log"
    log.write_text("2026-01-01T00:00:00+00:00\tcfg\n")
    before = log.read_text()
    with pytest.raises(G.AlreadyScored):  # the gold path does not exist: a read would raise FileNotFoundError instead
        G.score("cfg", Dummy(), tmp_path / "missing.jsonl", log)
    assert log.read_text() == before


def test_the_line_is_logged_before_the_notes_are_read(tmp_path):
    log = tmp_path / "gold_runs.log"
    with pytest.raises(FileNotFoundError):
        G.score("cfg", Dummy(), tmp_path / "missing.jsonl", log)
    assert G.logged(log) == ["cfg"]  # a crash after the notes were touched still counts as a scoring


def test_the_real_gold_file_can_only_be_scored_against_the_real_log(tmp_path):
    with pytest.raises(G.AlreadyScored):
        G.score("cfg", Dummy(), G.GOLD, tmp_path / "other.log")
    assert not (tmp_path / "other.log").exists()


def test_the_command_refuses_a_logged_name_before_scoring_anything(tmp_path):
    log = tmp_path / "gold_runs.log"
    log.write_text("2026-01-01T00:00:00+00:00\tlexicon_v0\n")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"configs": {"lexicon_v0": {"spec": {"kind": "lexicon", "lexicon": "v0", "variant": None}}, "lexicon_v1": {"spec": {"kind": "lexicon", "lexicon": "v1", "variant": None}}}}))
    with pytest.raises(SystemExit, match="refused"):
        G.main(["--gold", str(write_gold(tmp_path / "gold.jsonl")), "--log", str(log), "--out", str(tmp_path), "--config", str(config)])
    assert G.logged(log) == ["lexicon_v0"] and not (tmp_path / f"{G.PREDICTIONS}.json").exists()


def test_only_final_gold_names_the_gold_file():
    for path in E.HERE.glob("*.py"):
        if path.name not in ("final_gold.py", "schema.py"):  # schema.py only mentions it in a docstring
            assert "notes_gold" not in path.read_text(), f"{path.name} must not touch the gold file"
    assert "notes_gold" in (E.HERE / "final_gold.py").read_text()


def test_slices_are_read_from_the_hard_field_in_either_shape():
    assert G.slices_of({"hard": "negation"}) == ["negation"] and G.slices_of({"hard": ["a", "b"]}) == ["a", "b"]
    assert G.slices_of({}) == ["(no slice)"] and G.slices_of({"hard": None}) == ["(no slice)"]


def test_the_report_comes_from_saved_predictions_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "BOOT", 20)  # speed: the shape is under test, not the width of an interval
    rng = np.random.default_rng(0)
    rows = [{"id": f"g{i}", "text": f"note {i}", "lang": "en", "category": E.CATEGORIES[i % 7], "danger": i % 4 == 0, "hard": f"slice-{i % 3}"} for i in range(70)]
    G.save_predictions(tmp_path, rows, "lexicon_v0", E.Outputs(rng.integers(0, 3, (70, 6)).astype(float), list(E.HAZARDS), rng.integers(0, 3, 70).astype(float), "scores"))
    G.save_predictions(tmp_path, rows, "hybrid", E.Outputs(rng.dirichlet(np.ones(7), 70), list(E.CATEGORIES), rng.random(70), "proba"))
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"configs": {
        "lexicon_v0": {"spec": {}, "hint": {"min_score": 1.0, "min_margin": 0.5}, "danger": {"f1": 1.0, "f2": 1.0, "recall90": None}},
        "hybrid": {"spec": {}, "hint": {"min_conf": 0.3}, "danger": {"f1": 0.5, "f2": 0.3, "recall90": 0.2}}}}))
    payload = G.report(tmp_path, config)
    notes, outputs = G.load_predictions(tmp_path)
    y = np.array([n["category"] for n in notes])
    got = payload["configs"]["lexicon_v0"]["category"]["default"]["macro_f1"]
    assert got["point"] == pytest.approx(E.macro_f1(y, E.default_labels(outputs["lexicon_v0"]))) and got["lo"] <= got["point"] <= got["hi"]
    assert set(payload["paired_differences"]) == {"hybrid - lexicon_v0"} and set(payload["decision_rule"]) == {"hybrid vs lexicon_v0"}
    assert {"danger_pr_auc_at_least_0.85", "category_macro_f1_at_least_0.80"} <= set(payload["target_check"]["hybrid"])
    assert set(payload["configs"]["hybrid"]["slices"]) == {"slice-0", "slice-1", "slice-2"}
    for name in ("classification_gold.json", "classification_gold_errors.json", "classification_gold_macro_f1.png", "classification_gold_slices.png"):
        assert (tmp_path / name).exists()
