import numpy as np

from models.tickets.eval.matching.chicago import prepare

from . import fixtures as fx


def test_requests_come_out_in_time_order_with_open_requests_never_closed():
    req = fx.requests()
    assert list(req.sr) == [t[0] for t in fx.TABLE]  # the fixture rows were shuffled; the table is in time order
    assert np.all(np.diff(req.created) > 0)
    assert np.isinf(req.closed[list(req.sr).index("E")]) and req.closed[0] > req.created[0]
    assert req.located.sum() == len(req) - 1  # M has no location


def test_the_city_cluster_is_the_parent_for_a_duplicate_and_itself_otherwise():
    req = fx.requests()
    row = {sr: i for i, sr in enumerate(req.sr)}
    assert req.cluster[row["B"]] == req.cluster[row["A"]] == req.cluster[row["C"]] == req.cluster[row["M"]] == req.cluster[row["N"]]
    assert req.cluster[row["G"]] == req.cluster[row["F"]] and req.cluster[row["Q"]] == req.cluster[row["R"]]
    assert len({req.cluster[row[s]] for s in "A D E F I J H K".split()}) == 8  # tickets are alone
    assert req.cluster[row["L"]] not in {req.cluster[i] for i in range(len(req)) if i != row["L"]}  # X is not in the file


def test_the_parent_row_is_found_only_when_the_parent_is_in_the_file():
    req = fx.requests()
    row = {sr: i for i, sr in enumerate(req.sr)}
    assert req.parent[row["B"]] == row["A"] and req.parent[row["Q"]] == row["R"]
    assert req.parent[row["L"]] == -1 and req.parent[row["A"]] == -1 and req.dup[row["L"]]


def test_a_duplicate_that_names_no_parent_is_not_a_duplicate_here():
    rows = fx.rows()
    rows[0]["duplicate"], rows[0]["parent_sr_number"] = "true", ""
    req = prepare.from_rows("pothole", rows)
    assert req.dup.sum() == 6  # the fixture has 6 duplicates, and the one we spoiled does not count as a 7th


def test_time_split_cuts_on_month_boundaries():
    rows = [dict(fx.rows()[0], sr_number=f"s{k}", created_date=day) for k, day in enumerate(
        ["2024-01-01T00:00:00.000", "2025-06-30T23:59:59.000", "2025-07-01T00:00:00.000", "2025-09-30T23:59:59.000",
         "2025-10-01T00:00:00.000", "2025-12-31T23:59:00.000"])]
    req = prepare.from_rows("pothole", rows)
    assert list(prepare.time_split(req)) == [0, 0, 1, 1, 2, 2]


def test_geo_split_gives_a_map_block_one_split_across_categories_and_skips_unlocated_rows():
    req = fx.requests()
    other = prepare.from_rows("broken_streetlight", fx.rows())  # the same places, another category
    ids = prepare.geo_split({"pothole": req, "broken_streetlight": other})
    assert (ids["pothole"][~req.located] == -1).all() and (ids["pothole"][req.located] >= 0).all()
    assert (ids["pothole"] == ids["broken_streetlight"]).all()  # same block, same split, whatever the type
    assert len(set(ids["pothole"][req.located])) == 1  # one block holds all 15 located fixture points


def test_the_address_buffer_is_same_street_and_at_most_four_numbers_apart():
    assert prepare.street_number("2218 S STEWART AVE") == (2218, "S STEWART AVE")
    assert prepare.street_number("  14 w  Armitage ave ") == (14, "W ARMITAGE AVE")
    assert prepare.street_number("STATE ST") is None and prepare.street_number("") is None
    assert prepare.within_buffer("100 N MAIN ST", "104 N MAIN ST") is True
    assert prepare.within_buffer("100 N MAIN ST", "105 N MAIN ST") is False
    assert prepare.within_buffer("100 N MAIN ST", "100 S MAIN ST") is False
    assert prepare.within_buffer("100 N MAIN ST", "100 N OAK AVE") is False
    assert prepare.within_buffer("100 N MAIN ST", "MAIN ST") is None


def test_results_are_rounded_all_the_way_down():
    out = prepare.rounded({"a": 0.123456789, "b": [np.float64(1 / 3), 2, "x"], "c": {"d": float("nan")}, "e": np.int64(3)}, 3)
    assert out["a"] == 0.123 and out["b"] == [0.333, 2, "x"] and out["e"] == 3 and np.isnan(out["c"]["d"])


def test_every_pair_carries_the_ward_of_its_child():
    from models.tickets.eval.matching.chicago import pairs

    req = fx.requests()
    data = pairs.build(req, fx.groups(req))
    assert set(data["ward"]) == {"1"} and len(data["ward"]) == len(data["d"])
