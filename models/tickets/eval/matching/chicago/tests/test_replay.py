import numpy as np
import pytest

from models.tickets.eval.common import metrics
from models.tickets.eval.matching.chicago import prepare, replay
from models.tickets.matching import match
from models.tickets.types import Sighting, TicketSpot

from . import fixtures as fx

# By hand, with the radius at 44.47 m (no accuracy) and the fixture's days and metres (see fixtures.py):
#   reopen allowed: A starts a ticket; B, C and D (30 m) join it; E, F start theirs; G joins F; I (50 m from A) starts one;
#   J and H join I; K (5 m from A, which closed on day 10) joins A and REOPENS it; L and N join A; Q starts one and R joins it.
#   reopen off:     the same until K, which cannot join the fixed A and starts a ticket; L and N join K's.
ROW = lambda req: {sr: i for i, sr in enumerate(req.sr)}


def tickets(req, rp):
    row = ROW(req)
    groups = {}
    for sr, i in row.items():
        if rp.founder[i] >= 0:
            groups.setdefault(req.sr[rp.founder[i]], set()).add(sr)
    return {frozenset(v) for v in groups.values()}


def test_with_reopen_allowed_a_fixed_ticket_takes_the_next_report():
    req = fx.requests()
    rp = replay.replay(req, reopen=True)
    assert tickets(req, rp) == {frozenset("ABCDKLN"), frozenset("E"), frozenset("FG"), frozenset("IJH"), frozenset("QR")}
    row = ROW(req)
    assert rp.reopened.sum() == 1 and rp.reopened[row["K"]] and rp.founder[row["M"]] == -1  # M has no location
    assert rp.distance[row["D"]] == pytest.approx(30, abs=0.05) and np.isnan(rp.distance[row["A"]])
    assert rp.since_fix_days[row["K"]] == pytest.approx(4) and np.isnan(rp.since_fix_days).sum() == len(req) - 1  # only K reopened a ticket


def test_with_reopen_off_a_closed_ticket_is_unavailable():
    req = fx.requests()
    rp = replay.replay(req, reopen=False)
    assert tickets(req, rp) == {frozenset("ABCD"), frozenset("E"), frozenset("FG"), frozenset("IJH"), frozenset("KLN"), frozenset("QR")}
    assert not rp.reopened.any()


def test_a_wider_radius_from_a_reported_accuracy_merges_more():
    req = fx.requests()
    row = ROW(req)
    narrow = replay.replay(req, reopen=False)  # 44.5 m: I, 50 m from A, starts a ticket of its own
    wide = replay.replay(req, accuracy_m=20, reopen=False)  # about 58 m: I joins A's ticket
    assert narrow.founder[row["I"]] == row["I"] and wide.founder[row["I"]] == wide.founder[row["A"]] == row["A"]


def test_scorable_leaves_out_duplicates_whose_parent_is_not_in_the_file_and_unlocated_rows():
    req = fx.requests()
    row = ROW(req)
    keep = replay.scorable(req)
    assert not keep[row["L"]] and not keep[row["M"]] and keep[row["A"]] and keep[row["N"]] and keep.sum() == 14


def test_the_scores_match_a_hand_count_for_both_runs():
    req = fx.requests()
    items = np.flatnonzero(replay.scorable(req))
    # reopen allowed: ours T_A = {A B C D K N} (15 pairs) + {F G} + {I J H} (3) + {Q R} = 20 pairs; the city's {A B C N} (6) + {F G} + {Q R} = 8, all inside ours
    s = replay.evaluate(req, replay.replay(req, reopen=True), items, None)["scores"]
    assert s["pairs_precision"]["point"] == pytest.approx(8 / 20) and s["pairs_recall"]["point"] == pytest.approx(1.0)
    # reopen off: ours {A B C D} (6) + {K N} (1) + {F G} + {I J H} (3) + {Q R} = 12 pairs, 5 of them the city's (A-B, A-C, B-C, F-G, Q-R)
    s = replay.evaluate(req, replay.replay(req, reopen=False), items, None)["scores"]
    assert s["pairs_precision"]["point"] == pytest.approx(5 / 12) and s["pairs_recall"]["point"] == pytest.approx(5 / 8)
    assert 0 < s["bcubed_f1"]["point"] < 1 and s["ari"]["point"] < 1


def test_extra_merges_are_the_ones_the_city_did_not_flag_and_the_buffer_is_counted():
    req = fx.requests()
    items = np.flatnonzero(replay.scorable(req))
    rep = replay.merge_report(req, replay.replay(req, reopen=True), items)
    # our merges: B C D G J H K N R (L is not scored). The city also flags B C G N R. Extra: D (other street), J (no address),
    # H (52 vs 50 PINE ST: inside), K (104 vs 100 MAIN ST, and it reopens A: inside)
    assert (rep["our_merges"], rep["merges_the_city_also_flags"], rep["extra_merges_the_city_did_not_flag"]) == (9, 5, 4)
    assert rep["extra_inside_the_city_buffer"] == {"inside": 2, "outside": 1, "no_number": 1}
    assert rep["extra_that_reopen_a_fixed_ticket"] == 1 and rep["of_which_reopening_a_fixed_ticket"] == 1
    assert rep["reopening_merges_days_after_the_fix"]["50"] == pytest.approx(4) and rep["reopening_merges_within_one_day_of_the_fix"] == 0.0
    assert rep["extra_where_the_city_flagged_it_to_another_parent"] == 0
    assert (rep["city_duplicates"], rep["city_duplicates_put_in_their_parents_ticket"]) == (5, 5)  # B C G N Q
    off = replay.merge_report(req, replay.replay(req, reopen=False), items)
    assert off["extra_merges_the_city_did_not_flag"] == 4 and off["extra_that_reopen_a_fixed_ticket"] == 0
    assert off["extra_where_the_city_flagged_it_to_another_parent"] == 1  # N joined K, but the city says N is a duplicate of A
    assert off["extra_inside_the_city_buffer"] == {"inside": 1, "outside": 1, "no_number": 2}
    assert off["city_duplicates_put_in_their_parents_ticket"] == 4  # N is not with A


def test_the_cluster_bootstrap_keeps_a_repeated_group_apart_from_its_copy():
    true = np.array([0, 0, 1, 1, 2])
    pred = np.array([0, 0, 1, 1, 2])
    group = replay.components(true, pred)
    assert len(set(group)) == 3 and group[0] == group[1] != group[2] == group[3] != group[4]
    t, p = np.unique(true, return_inverse=True)[1], np.unique(pred, return_inverse=True)[1]
    labels_t, labels_p = replay.resample(t, p, group, np.array([group[0], group[0], group[4]]))  # group of A,B twice, and E once
    assert len(labels_t) == 5 and len(set(labels_t)) == 3  # {A,B} and its copy are two tickets, E a third
    assert metrics.cluster_pairs(labels_t, labels_p)["f1"] == 1.0


def test_components_can_take_two_partitions_at_once():
    true = np.array([0, 1, 2, 3, 4])
    a = np.array([0, 0, 1, 2, 3])  # ties items 0 and 1
    b = np.array([0, 1, 1, 2, 3])  # ties items 1 and 2
    g = replay.components(true, a, b)
    assert g[0] == g[1] == g[2] and len({g[0], g[3], g[4]}) == 3


def test_a_partition_minus_itself_is_zero_and_a_better_one_is_ahead():
    rng = np.random.default_rng(2)
    true = np.repeat(np.arange(60), 3)
    worse = true.copy()
    worse[::4] = 1000 + np.arange(len(worse[::4]))  # every 4th item split off
    same = replay.paired_scores(true, worse, worse.copy(), boot=30)
    assert all(v == {"point": 0.0, "lo": 0.0, "hi": 0.0} for v in same.values())
    ahead = replay.paired_scores(true, true.copy(), worse, boot=60)
    assert all(v["point"] > 0 and v["lo"] > 0 for v in ahead.values())


def test_components_tie_together_what_either_partition_ties():
    true = np.array([0, 0, 1, 2, 3])
    pred = np.array([0, 1, 1, 2, 3])  # item 1 links the city ticket of items 0, 1 to our ticket of items 1, 2
    g = replay.components(true, pred)
    assert g[0] == g[1] == g[2] and len({g[0], g[3], g[4]}) == 3


def test_interval_scores_are_ordered_and_a_perfect_partition_has_a_degenerate_interval():
    true = np.repeat(np.arange(40), 2)
    s = replay.partition_scores(true, true.copy(), boot=30)
    assert all(v["point"] == v["lo"] == v["hi"] == 1.0 for v in s.values())
    pred = true.copy()
    pred[::7] = 100 + np.arange(len(pred[::7]))
    s = replay.partition_scores(true, pred, boot=40)
    assert all(v["lo"] <= v["point"] <= v["hi"] for v in s.values()) and s["pairs_recall"]["point"] < 1


def test_never_merge_has_no_pairs_recall():
    req = fx.requests()
    items = np.flatnonzero(replay.scorable(req))
    s = replay.never_merge(req, items, None)
    assert s["pairs_recall"]["point"] == 0 and s["pairs_precision"]["point"] == 1.0 and s["ari"]["point"] == 0.0


def random_requests(n=400, seed=0):
    """Random reports in a 700 m square, one every 37 minutes, most fixed within weeks: a few neighbours each, so a miss shows."""
    rng = np.random.default_rng(seed)
    start = np.datetime64("2025-01-01T00:00:00")
    stamp = lambda minutes: str(start + np.timedelta64(int(minutes), "m"))
    rows = []
    for i in range(n):
        made = i * 37
        shut = "" if rng.random() < 0.1 else stamp(made + rng.uniform(300, 60_000))
        rows.append({"sr_number": f"R{i:04d}", "sr_type": "x", "status": "Open", "origin": "Mobile Device", "created_date": stamp(made), "closed_date": shut,
                     "duplicate": "false", "parent_sr_number": "", "latitude": repr(fx.north(rng.uniform(0, 700))),
                     "longitude": repr(fx.LNG + rng.uniform(0, 700) / 82_000), "street_address": "", "community_area": "1", "ward": "1"})
    return prepare.from_rows("pothole", rows)


def brute_force(req, accuracy_m, reopen):
    """The same replay without the grid: every earlier ticket goes to find_match."""
    founder, reopened = np.full(len(req), -1), np.zeros(len(req), bool)
    fixed_at, active, tickets = {}, {}, []
    for i in range(len(req)):
        now = req.created[i]
        spots = []
        for f in tickets:
            fixed = fixed_at[f] <= now
            if not (fixed and not reopen):
                spots.append(TicketSpot(str(f), "pothole", req.lat[f], req.lng[f], accuracy_m, "fixed" if fixed else "open", active[f], fixed_at[f] if fixed else None))
        hit = match.find_match(Sighting(str(i), "pothole", req.lat[i], req.lng[i], accuracy_m, created_at=now), spots, now)
        if hit is None:
            founder[i], fixed_at[i], active[i] = i, req.closed[i], now
            tickets.append(i)
        else:
            f = int(hit.ticket_id)
            founder[i], reopened[i], active[f] = f, hit.reopens, now
            if hit.reopens:
                fixed_at[f] = req.closed[i]
    return founder, reopened


@pytest.mark.parametrize("accuracy_m, reopen", [(None, True), (None, False), (5, True), (20, False)])
def test_the_grid_index_finds_every_neighbour_the_brute_force_replay_finds(accuracy_m, reopen):
    req = random_requests()
    rp = replay.replay(req, accuracy_m, reopen)
    founder, reopened = brute_force(req, accuracy_m, reopen)
    assert np.array_equal(rp.founder, founder) and np.array_equal(rp.reopened, reopened)
    assert 20 < rp.joined.sum() < 380 and (rp.reopened.any() or not reopen)  # a real mix of joins, new tickets and reopenings


def year_of_requests(n=900, seed=3):
    """Requests all through 2025 (one every 9.5 hours), a fifth of them duplicates of a recent request, so all three splits have items."""
    rng = np.random.default_rng(seed)
    start = np.datetime64("2025-01-01T00:00:00")
    stamp = lambda minutes: str(start + np.timedelta64(int(minutes), "m"))
    rows, tickets = [], []
    for i in range(n):
        made = i * 570
        dup = i % 5 == 4 and tickets
        parent = tickets[rng.integers(max(0, len(tickets) - 20), len(tickets))] if dup else ""
        spot = rows[[r["sr_number"] for r in rows].index(parent)] if dup else None
        north = float(spot["_north"]) + rng.uniform(-30, 30) if dup else rng.uniform(0, 800)
        east = float(spot["_east"]) + rng.uniform(-30, 30) if dup else rng.uniform(0, 800)
        rows.append({"sr_number": f"Y{i:04d}", "sr_type": "x", "status": "Completed", "origin": "Mobile Device", "created_date": stamp(made),
                     "closed_date": stamp(made + rng.uniform(600, 40_000)), "duplicate": "true" if dup else "false", "parent_sr_number": parent,
                     "latitude": repr(fx.north(north)), "longitude": repr(fx.LNG + east / 82_000), "street_address": "", "community_area": "1", "ward": str(i % 7),
                     "_north": north, "_east": east})
        if not dup:
            tickets.append(f"Y{i:04d}")
    return prepare.from_rows("pothole", rows)


def test_the_whole_replay_runs_and_writes_its_picture(tmp_path):
    req = year_of_requests()
    out = replay.run(boot=5, everything={"pothole": req})["pothole"]
    assert out["scored_requests"]["validation"] > 100 and out["scored_requests"]["test"] > 100
    assert set(out["final"]) >= {"reopen, accuracy None", "no reopen, accuracy None"} and len(out["validation_sweep"]) == 2 * len(replay.ACCURACIES)
    assert "reopen on minus reopen off (shipped accuracy)" in out["paired_test"] and "reopen off, shipped minus never merge" in out["paired_test"]
    test = out["final"]["no reopen, accuracy None"]["test"]
    assert all(v["lo"] <= v["point"] <= v["hi"] for v in test["scores"].values())
    assert 0 < test["merges"]["our_merges"] < test["merges"]["items"] and out["never_merge"]["test"]["pairs_recall"]["point"] == 0
    replay.plot({"pothole": out}, tmp_path / "replay.png")
    assert (tmp_path / "replay.png").stat().st_size > 5000
