import json

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")

from models.tickets.eval.common import plots, results, splits  # noqa: E402


# ---- splits -----------------------------------------------------------------------------------------------------------
def test_temporal_split_cuts_at_the_boundaries():
    train, val, test = splits.temporal_split([1, 2, 3, 4, 5], 3, 5)
    assert list(train) == [0, 1] and list(val) == [2, 3] and list(test) == [4]


def test_group_split_keeps_every_group_whole_and_covers_every_row():
    rng = np.random.default_rng(0)
    groups = rng.integers(0, 100, 1000)
    parts = splits.group_split(groups)
    assert sorted(np.concatenate(parts)) == list(range(1000))
    owner = {}
    for k, part in enumerate(parts):
        for g in set(groups[part]):
            assert owner.setdefault(g, k) == k  # a group never appears in two splits
    assert [len(p) / 1000 for p in parts] == pytest.approx([0.6, 0.2, 0.2], abs=0.05)


def test_group_split_is_repeatable_and_the_seed_changes_it():
    groups = np.repeat(np.arange(50), 4)
    a, b = splits.group_split(groups, seed=1), splits.group_split(groups, seed=1)
    assert all(np.array_equal(x, y) for x, y in zip(a, b))
    assert not all(np.array_equal(x, y) for x, y in zip(a, splits.group_split(groups, seed=2)))


def test_block_split_never_puts_one_map_block_in_two_splits():
    rng = np.random.default_rng(3)
    lat, lng = rng.uniform(41.6, 42.0, 2000), rng.uniform(-87.9, -87.5, 2000)
    ids = splits.block_ids(lat, lng)
    owner = {}
    for k, part in enumerate(splits.block_split(lat, lng)):
        for block in set(ids[part]):
            assert owner.setdefault(block, k) == k


# ---- results ----------------------------------------------------------------------------------------------------------
def test_a_result_file_carries_its_provenance_and_is_plain_json(tmp_path):
    path = results.write_result("demo", {"f1": np.float64(0.5), "bad": float("nan"), "counts": np.array([1, 2])}, tmp_path)
    data = json.loads(path.read_text())
    assert data["f1"] == 0.5 and data["bad"] is None and data["counts"] == [1, 2]
    assert {"git_commit", "written", "numpy", "scipy", "scikit_learn"} <= set(data["meta"])


def test_md_table_rounds_floats_and_blanks_missing_cells():
    table = results.md_table([{"a": 0.123456, "b": "x"}, {"a": 1}], ["a", "b"])
    assert table.splitlines() == ["| a | b |", "|---|---|", "| 0.123 | x |", "| 1 |  |"]


# ---- plots (smoke: a real picture comes out) ------------------------------------------------------------------------
def test_the_figures_are_written(tmp_path):
    rng = np.random.default_rng(0)
    y = rng.random(200) < 0.3
    s = y + rng.normal(0, 0.6, 200)
    p = np.clip(s / 2, 0, 1)
    plots.save_curves(tmp_path / "curves.png", {"model": (y, s)}, "demo")
    plots.save_reliability(tmp_path / "rel.png", {"model": (y, p)}, "demo")
    plots.save_bars(tmp_path / "bars.png", ["a", "b"], [0.8, 0.9], [0.7, 0.85], [0.9, 0.95], "demo", "F1", target=0.85)
    assert all((tmp_path / f).stat().st_size > 2000 for f in ("curves.png", "rel.png", "bars.png"))
