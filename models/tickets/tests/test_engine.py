"""The engine: attach (pure), one turn of the loop on a fake cache and a real SQLite file, and the district scope."""
import math
import sqlite3
from datetime import datetime, timezone

import pytest

from models.tickets import engine, settings as s

WORLD = engine.load_world()
NOW = datetime(2026, 10, 7, 12, tzinfo=timezone.utc).timestamp()
DAY = 86_400.0
AYALA = (14.5547, 121.0244)  # Urdaneta, District 1
BEL_AIR = (14.55831, 121.03872)  # District 1, 24 m from the next point, across the line between the districts
PINAGKAISAHAN = (14.55814, 121.03887)  # District 2
BGC = (14.5508, 121.0509)  # Taguig: no district


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds")


def north(metres: float, lat: float = AYALA[0]) -> float:
    return lat + math.degrees(metres / 6_371_008.8)


def report(rid, category="pothole", where=AYALA, ago_s=600.0, note="", status="open", **extra) -> dict:
    """A cached report as POST /reports writes it."""
    at = iso(NOW - ago_s)
    return {"id": rid, "category": category, "lat": where[0], "lng": where[1], "heading": None, "note": note,
            "photo_url": f"/photos/{rid}.jpg", "status": status, "created_at": at, "updated_at": at, **extra}


def joined(r: dict, cached: list[dict]) -> tuple[dict, engine.Attachment]:
    """The report as the cache holds it once attached, and the attachment."""
    a = engine.attach(r, cached, WORLD, NOW)
    return {**r, **a.cache}, a


class FakeCache:
    """ReportStore's methods over a list (all() hands out copies, like the JSON file does)."""

    def __init__(self, reports=()):
        self.reports = [dict(r) for r in reports]

    def all(self):
        return [dict(r) for r in self.reports]

    def update(self, report_id, **fields):
        for r in self.reports:
            if r["id"] == report_id:
                r.update(fields)
                return dict(r)
        return None

    def remove(self, report_ids):
        before = len(self.reports)
        self.reports = [r for r in self.reports if r["id"] not in set(report_ids)]
        return before - len(self.reports)

    def get(self, report_id):
        return next(r for r in self.reports if r["id"] == report_id)


@pytest.fixture
def db(tmp_path):
    return engine.database(tmp_path / "lakad.db")


# ---- attach -----------------------------------------------------------------------------------------------------

def test_two_reports_metres_apart_share_one_ticket():
    first, a1 = joined(report("a"), [])
    second, a2 = joined(report("b", where=(north(5), AYALA[1]), ago_s=60), [first])
    assert a1.ticket["id"] == a2.ticket["id"] == second["ticket_id"] == "a"  # a ticket is named after its first report
    assert a2.ticket["reporters"] == 2 and a2.sighting["ticket_id"] == "a" and a2.sighting["id"] == "b"
    assert a2.ticket["priority"] > a1.ticket["priority"]  # a second person makes it more urgent
    assert a2.ticket["photo_url"] == "/photos/a.jpg"  # the ticket shows its first report


def test_reports_far_apart_open_two_tickets():
    first, _ = joined(report("a"), [])
    _, a2 = joined(report("b", where=(north(200), AYALA[1])), [first])
    assert a2.ticket["id"] == "b" and a2.ticket["status"] == "open" and a2.ticket["reporters"] == 1


def test_a_different_category_at_the_same_spot_opens_its_own_ticket():
    first, _ = joined(report("a"), [])
    assert joined(report("b", category="open_manhole"), [first])[1].ticket["id"] == "b"


def test_an_sos_never_merges_and_tops_the_queue():
    first, a1 = joined(report("s1", category="sos"), [])
    _, a2 = joined(report("s2", category="sos"), [first])
    _, a3 = joined(report("p", category="pothole"), [first])
    assert (a1.ticket["id"], a2.ticket["id"], a3.ticket["id"]) == ("s1", "s2", "p")
    assert (a2.ticket["priority"], a2.ticket["band"]) == (100.0, "Critical") and a2.ticket["breakdown"]["sos"]


def test_other_never_merges():
    first, _ = joined(report("a", category="other"), [])
    assert joined(report("b", category="other"), [first])[1].ticket["id"] == "b"


def test_a_rejected_ticket_is_not_joined():
    first, _ = joined(report("a"), [])
    assert joined(report("b"), [{**first, "status": "rejected"}])[1].ticket["id"] == "b"


def test_a_report_soon_after_a_fix_reopens_the_ticket():
    first, _ = joined(report("a", ago_s=10 * DAY), [])
    fixed = {**first, "status": "fixed", "updated_at": iso(NOW - 2 * DAY)}
    _, a = joined(report("b"), [fixed])
    assert a.ticket["id"] == "a" and a.ticket["status"] == "open"


def test_a_report_long_after_a_fix_opens_a_new_ticket():
    first, _ = joined(report("a", ago_s=60 * DAY), [])
    fixed = {**first, "status": "fixed", "updated_at": iso(NOW - (s.REOPEN_WINDOW_DAYS + 5) * DAY)}
    assert joined(report("b"), [fixed])[1].ticket["id"] == "b"


def test_a_report_made_before_the_fix_does_not_reopen_it():
    first, _ = joined(report("a", ago_s=10 * DAY), [])
    fixed = {**first, "status": "fixed", "updated_at": iso(NOW - 2 * DAY)}
    assert joined(report("b", ago_s=3 * DAY), [fixed])[1].ticket["id"] == "b"  # e.g. reports from before the loop


def test_a_report_an_analyst_already_judged_keeps_its_status_and_its_own_ticket():
    first, _ = joined(report("a"), [])
    for status in ("verified", "assigned", "fixed", "rejected"):
        _, a = joined(report("b", status=status), [first])
        assert a.ticket["id"] == "b" and a.ticket["status"] == status


def test_joining_an_assigned_ticket_sends_no_status_so_the_analysts_one_stays():
    first, _ = joined(report("a"), [])
    _, a = joined(report("b"), [{**first, "status": "assigned", "updated_at": iso(NOW - 300)}])
    assert a.ticket["id"] == "a" and "status" not in a.ticket and "status" not in a.cache


def test_the_district_comes_from_the_anchor_the_most_accurate_sighting():
    first, a1 = joined(report("a", where=BEL_AIR, accuracy_m=30.0), [])
    _, a2 = joined(report("b", where=PINAGKAISAHAN, accuracy_m=5.0), [first])
    assert a1.ticket["district_id"] == 1
    assert a2.ticket["id"] == "a" and (a2.ticket["lat"], a2.ticket["lng"]) == PINAGKAISAHAN
    assert a2.ticket["district_id"] == a2.cache["district_id"] == 2
    # A vaguer report does not move it back.
    _, a3 = joined(report("c", where=BEL_AIR, accuracy_m=20.0), [first, {**first, "id": "b", "lat": PINAGKAISAHAN[0],
                                                                         "lng": PINAGKAISAHAN[1], "accuracy_m": 5.0}])
    assert a3.ticket["district_id"] == 2


def test_outside_both_districts_there_is_no_district():
    assert joined(report("a", where=BGC), [])[1].ticket["district_id"] is None


def test_a_pwd_barrier_is_not_danger_for_naming_who_it_stops():
    worded = [joined(report(n, category="missing_ramp", note=note), [])[1] for n, note in
              [("a", "the wheelchair ramp at the crossing is missing"), ("b", "no wheelchair ramp at the crossing"),
               ("c", "walang rampa para sa pwd dito")]]
    assert {a.ticket["priority"] for a in worded} == {joined(report("d", category="missing_ramp"), [])[1].ticket["priority"]}
    assert not any(a.ticket["breakdown"]["danger"] for a in worded), "the wording no longer moves the score"
    _, fell = joined(report("e", category="missing_ramp", note="a man in a wheelchair fell off the curb here"), [])
    assert fell.ticket["breakdown"]["danger"], "a real danger word still counts"
    _, hole = joined(report("f", note="a wheelchair user almost went into this hole"), [])
    assert hole.ticket["breakdown"]["danger"], "on a hazard, who is at risk is still danger"


def test_a_dangerous_note_anywhere_on_the_ticket_adds_the_bonus():
    first, a1 = joined(report("a"), [])
    _, a2 = joined(report("b", note="maraming bata dito"), [first])
    assert not a1.ticket["breakdown"]["danger"]
    assert a2.ticket["breakdown"]["danger"] and a2.ticket["breakdown"]["bonus"] == s.DANGER_BONUS


def test_rows_use_the_table_columns_and_leave_the_clock_columns_alone():
    _, a = joined(report("a", note="lubak", accuracy_m=80.0), [])
    assert set(a.ticket) <= set(engine.TICKET_COLUMNS) and not {"updated_at", "fixed_at"} & set(a.ticket)
    assert set(a.sighting) == set(engine.SIGHTING_COLUMNS)
    assert set(a.cache) == {"ticket_id", "district_id", "priority", "band"}
    assert set(a.ticket["breakdown"]) == {"parts", "belief", "gate", "floor_applied", "bonus", "danger", "hint",
                                          "review", "office"}
    assert a.ticket["breakdown"]["hint"] == "pothole" and a.ticket["breakdown"]["review"] == ["gps_accuracy_poor"]


# ---- one turn of the loop ---------------------------------------------------------------------------------------

def test_a_turn_attaches_saves_and_marks_every_new_report(db):
    cache = FakeCache([report("a", ago_s=120), report("b", where=(north(5), AYALA[1]), ago_s=60),
                       report("far", where=(north(500), AYALA[1]))])
    stats = engine.sync_once(cache, WORLD, db, NOW)
    assert (stats.attached, stats.failed, stats.pruned) == (3, [], 0)
    assert cache.get("a")["ticket_id"] == cache.get("b")["ticket_id"] == "a" and cache.get("far")["ticket_id"] == "far"
    assert cache.get("a")["priority"] == cache.get("b")["priority"]  # the first report is re-ranked with its ticket
    rows = {t["id"]: t for t in db.tickets()}
    assert set(rows) == {"a", "far"} and rows["a"]["reporters"] == 2 and rows["a"]["district_id"] == 1
    again = engine.sync_once(cache, WORLD, db, NOW)
    assert again.attached == 0 and len(db.tickets()) == 2  # nothing left to do


def test_the_first_turn_over_an_old_reports_json_changes_no_status(db):
    # Reports from before the loop: an analyst already set these statuses one report at a time.
    old = [report("a", ago_s=9 * DAY), report("b", ago_s=8 * DAY, status="fixed"),
           report("c", ago_s=7 * DAY, status="assigned"), report("d", ago_s=6 * DAY, status="rejected"),
           report("e", ago_s=5 * DAY)]
    old[1]["updated_at"] = iso(NOW - 4 * DAY)
    cache = FakeCache(old)
    assert engine.sync_once(cache, WORLD, db, NOW).attached == 5
    assert [r["status"] for r in cache.reports] == ["open", "fixed", "assigned", "rejected", "open"]
    # e joins one of the two tickets still in play, the more recently active: never the fixed or the rejected one.
    assert [r["ticket_id"] for r in cache.reports] == ["a", "b", "c", "d", "c"]
    assert {t["id"]: t["status"] for t in db.tickets()} == {"a": "open", "b": "fixed", "c": "assigned", "d": "rejected"}


def test_a_report_that_keeps_failing_is_skipped_and_does_not_block_the_queue(db, monkeypatch):
    cache = FakeCache([report("bad", ago_s=120) | {"created_at": "not a date"}, report("good")])
    stats = engine.sync_once(cache, WORLD, db, NOW)
    assert stats.failed == ["bad"] and stats.attached == 1 and cache.get("good")["ticket_id"] == "good"
    assert cache.get("bad")["sync_tries"] == 1 and "ValueError" in cache.get("bad")["sync_error"]
    for _ in range(s.SYNC_MAX_TRIES):
        engine.sync_once(cache, WORLD, db, NOW)
    assert cache.get("bad")["sync_tries"] == s.SYNC_MAX_TRIES and "ticket_id" not in cache.get("bad")
    assert engine.backlog(cache) == {"pending": 0, "failed": 1}


def test_a_failed_save_leaves_the_report_without_a_ticket_and_a_later_turn_finishes_it(db, monkeypatch):
    cache = FakeCache([report("a")])

    def broken(*args):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(db, "save", broken)
    assert engine.sync_once(cache, WORLD, db, NOW).failed == ["a"] and "ticket_id" not in cache.get("a")
    monkeypatch.undo()
    assert engine.sync_once(cache, WORLD, db, NOW).attached == 1
    assert cache.get("a")["ticket_id"] == "a" and cache.get("a")["sync_error"] is None and db.tickets()[0]["id"] == "a"


def test_a_reopen_opens_every_report_of_the_ticket_and_logs_it(db):
    cache = FakeCache([report("a", ago_s=5 * DAY)])
    engine.sync_once(cache, WORLD, db, NOW - 4 * DAY)
    engine.set_status(db, cache, "a", "fixed", "all", "analyst-1", now=NOW - 2 * DAY)
    cache.reports.append(report("b"))
    engine.sync_once(cache, WORLD, db, NOW)
    assert cache.get("a")["status"] == cache.get("b")["status"] == "open" and cache.get("b")["ticket_id"] == "a"
    ticket = db.tickets()[0]
    assert ticket["status"] == "open" and ticket["fixed_at"] is None and ticket["reporters"] == 2
    assert events(db, "a") == [("analyst-1", "open", "fixed"), (None, "fixed", "open")]


def test_reports_of_tickets_closed_long_ago_leave_the_cache_and_stay_in_the_database(db):
    cache = FakeCache([report("old", ago_s=90 * DAY), report("recent", where=BGC, ago_s=20 * DAY),
                       report("waiting", where=(north(300), AYALA[1]), sync_tries=s.SYNC_MAX_TRIES)])
    engine.sync_once(cache, WORLD, db, NOW - 80 * DAY)
    engine.set_status(db, cache, "old", "fixed", "all", "analyst-1", now=NOW - (s.CACHE_KEEP_DAYS + 1) * DAY)
    engine.set_status(db, cache, "recent", "rejected", "all", "analyst-1", now=NOW - (s.CACHE_KEEP_DAYS - 1) * DAY)
    assert engine.sync_once(cache, WORLD, db, NOW).pruned == 1
    assert [r["id"] for r in cache.reports] == ["recent", "waiting"]  # never-attached reports are never dropped
    assert {t["id"] for t in db.tickets()} == {"old", "recent"}


# ---- the district scope: what an analyst may see and change ------------------------------------------------------

def events(db, ticket_id):
    with db._lock:
        rows = db._conn.execute("select actor, from_status, to_status from ticket_events where ticket_id = ? order by id",
                                (ticket_id,)).fetchall()
    return [tuple(r) for r in rows]


@pytest.fixture
def three(db):
    """A ticket in District 1, one in District 2 and one in neither, each with two cached reports."""
    cache = FakeCache([report("d1", ago_s=300), report("d1b", where=(north(4), AYALA[1]), ago_s=290),
                       report("d2", where=PINAGKAISAHAN, ago_s=200), report("d2b", where=PINAGKAISAHAN, ago_s=190),
                       report("none", where=BGC, ago_s=100), report("noneb", where=BGC, ago_s=90)])
    engine.sync_once(cache, WORLD, db, NOW)
    assert {t["id"]: t["district_id"] for t in db.tickets()} == {"d1": 1, "d2": 2, "none": None}
    return cache


def ids(db, scope):
    return [t["id"] for t in engine.tickets_for(db, scope)]


def test_each_scope_sees_exactly_its_tickets_newest_first(db, three):
    assert ids(db, frozenset({1})) == ["d1"]
    assert ids(db, frozenset({2})) == ["d2"]
    assert ids(db, {1, 2}) == ["d2", "d1"]
    assert ids(db, "all") == ["none", "d2", "d1"]  # citywide sees the ticket with no district too


@pytest.mark.parametrize("scope", [frozenset(), frozenset({None}), {3}, None, "ALL", "all ", "1", [1, 2], (1, 2), 1, True])
def test_any_other_scope_sees_nothing(db, three, scope):
    assert ids(db, scope) == []
    assert engine.set_status(db, three, "d1", "fixed", scope, "x", now=NOW) is None


def test_a_change_outside_the_scope_is_refused_exactly_like_a_missing_ticket_and_changes_nothing(db, three):
    before = db.tickets()
    assert engine.set_status(db, three, "d2", "fixed", frozenset({1}), "analyst-1", now=NOW) is None
    assert engine.set_status(db, three, "none", "fixed", frozenset({1, 2}), "analyst-1", now=NOW) is None
    assert engine.set_status(db, three, "nope", "fixed", "all", "analyst-1", now=NOW) is None
    assert db.tickets() == before and events(db, "d2") == events(db, "none") == []
    assert {r["status"] for r in three.reports} == {"open"}


def test_a_change_inside_the_scope_lands_everywhere_and_names_who_made_it(db, three):
    ticket = engine.set_status(db, three, "d1", "assigned", frozenset({1}), "analyst-1", now=NOW + 60)
    assert ticket["status"] == "assigned" and ticket["updated_at"] == iso(NOW + 60)
    assert events(db, "d1") == [("analyst-1", "open", "assigned")]
    assert [(r["id"], r["status"]) for r in three.reports if r["status"] != "open"] == [("d1", "assigned"), ("d1b", "assigned")]
    fixed = engine.set_status(db, three, "none", "fixed", "all", "city-1", now=NOW + 120)  # citywide reaches no district
    assert fixed["fixed_at"] == iso(NOW + 120) and events(db, "none") == [("city-1", "open", "fixed")]
    assert engine.set_status(db, three, "none", "open", "all", "city-1", now=NOW + 180)["fixed_at"] is None
