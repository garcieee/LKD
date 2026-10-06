import numpy as np
import pytest

from models.tickets.eval.matching.chicago import eda, pairs

from . import fixtures as fx


def test_the_eda_counts_match_a_hand_count_of_the_fixture():
    s = eda.category_stats(fx.requests())
    assert (s["rows"], s["located"], s["duplicates"]) == (16, 15, 7)
    assert s["duplicate_rate"] == pytest.approx(7 / 16)
    assert s["duplicate_rate_by_origin"]["Mobile Device"] == {"rows": 7, "duplicate_rate": 1.0}
    assert s["duplicate_rate_by_origin"]["Phone Call"] == {"rows": 7, "duplicate_rate": 0.0}
    assert s["duplicate_rate_by_origin"]["Alderman's Office"] == {"rows": 0, "duplicate_rate": None}
    assert s["duplicates_with_parent_in_file"] == 6 and s["share_of_duplicates_with_parent_in_file"] == pytest.approx(6 / 7)
    assert s["parent_is_itself_a_duplicate"] == 0
    assert s["children_per_parent"] == {"parents_with_children": 3, "one_child": 2, "two_children": 0, "three_or_more": 1, "most": 4}


def test_distance_and_gap_statistics_of_the_duplicate_pairs():
    p = eda.category_stats(fx.requests())["pairs"]  # B-A 10 m 1 d, C-A 20 m 2 d, G-F 5 m 1 d, N-A 8 m 16 d, Q-R 2 m -1 d
    assert p["n"] == 5 and p["distance_m"]["50"] == pytest.approx(8, abs=0.05)
    assert p["share_at_distance_0"] == 0 and p["share_inside_m"]["15"] == pytest.approx(0.8) and p["share_inside_m"]["25"] == 1.0
    assert p["gap_days"]["50"] == pytest.approx(1) and p["share_child_before_parent"] == pytest.approx(0.2)
    assert p["share_abs_gap_at_most_14_days"] == pytest.approx(0.8) and p["share_abs_gap_at_most_30_days"] == 1.0
    assert p["share_inside_shipped_radius"]["no accuracy"] == 1.0


def test_pairs_can_be_split_by_the_origin_of_the_child_and_the_address_buffer_is_counted():
    s = eda.category_stats(fx.requests())
    assert s["pairs_by_child_origin"]["Mobile Device"]["n"] == 5 and s["pairs_by_child_origin"]["Phone Call"] == {"n": 0}
    assert s["addresses"]["parsed"] == 2 and s["addresses"]["same_street_share"] == 1.0
    assert s["addresses"]["inside_four_numbers_share"] == pytest.approx(0.5)
    assert s["earlier_of_the_pair_open_when_the_later_was_created"] == pytest.approx(0.8)  # N arrived after A had closed


def test_the_picture_is_written(tmp_path):
    everything = {"pothole": fx.requests()}
    eda.plot(everything, eda.eda(everything), tmp_path / "eda.png")
    assert (tmp_path / "eda.png").stat().st_size > 5000


def test_the_address_gap_explains_the_label_better_than_distance_in_a_hand_counted_case():
    req = fx.requests()
    data = pairs.build(req, fx.groups(req))
    data["category"] = np.full(len(data["d"]), "pothole")
    got = eda.label_vs_address({"pothole": req}, data)["pothole"]
    # 13 pairs under 60 m: 4 positives and 9 near negatives. Distance: 31.5 of 36 positive-negative pairs are right (ties count half;
    # C-A and I-D are both 20 m, and which is a hair nearer is float noise, so allow half a pair).
    # Street-number gap: only B-A (2), C-A (8) and the near pair H-I (2) have one; every other pair is "infinitely" far apart: 24.5 of 36.
    assert got["pairs"] == 13 and got["positives"] == 4
    assert got["roc_auc_minus_distance"] == pytest.approx(31.5 / 36, abs=0.5 / 36 + 1e-9)
    assert got["roc_auc_minus_street_number_gap"] == pytest.approx(24.5 / 36)
    assert got["median_distance_m"]["positives"] == pytest.approx(7.5, abs=0.05)
