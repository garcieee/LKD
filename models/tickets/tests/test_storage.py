"""storage/db.py: the SQLite file the tickets live in. Its tables must match the rows the engine writes."""
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from models.tickets import engine
from models.tickets.storage import db as storage
from models.tickets.storage.db import MIGRATIONS, Db

AT = "2026-10-07T12:00:00+00:00"
LATER = "2026-10-07T13:00:00+00:00"


def columns(db: Db, table: str) -> list[str]:
    return [r["name"] for r in db._conn.execute(f"pragma table_info({table})")]


def ticket(tid="t", **fields) -> dict:
    return {"id": tid, "category": "pothole", "district_id": 1, "lat": 14.55, "lng": 121.02, "priority": 40.0,
            "band": "Medium", "breakdown": {"why": "test"}, "reporters": 1, "note": "", "photo_url": "", "video_url": None,
            "created_at": AT, **fields}


def sighting(sid="t", tid="t") -> dict:
    return {"id": sid, "ticket_id": tid, "lat": 14.55, "lng": 121.02, "accuracy_m": None, "note": "", "photo_url": "",
            "video_url": None, "created_at": AT}


def events(db: Db) -> list[tuple]:
    return [tuple(r) for r in db._conn.execute("select ticket_id, actor, from_status, to_status, at from ticket_events order by id")]


@pytest.fixture
def db(tmp_path):
    return Db(tmp_path / "lakad.db")


def test_the_tables_have_exactly_the_columns_the_engine_writes(db):
    assert columns(db, "tickets") == list(engine.TICKET_COLUMNS) and engine.TICKET_COLUMNS[-1] == "sos_kind"
    assert columns(db, "sightings") == list(engine.SIGHTING_COLUMNS)
    assert columns(db, "ticket_events") == ["id", "ticket_id", "actor", "from_status", "to_status", "at"]


def test_opening_again_keeps_the_rows_and_runs_no_migration_twice(tmp_path):
    Db(tmp_path / "lakad.db").save(ticket(status="open"), sighting(), AT)
    again = Db(tmp_path / "lakad.db")
    assert again._conn.execute("pragma user_version").fetchone()[0] == len(MIGRATIONS)
    assert again._conn.execute("pragma journal_mode").fetchone()[0] == "wal"
    assert [t["id"] for t in again.tickets()] == ["t"] and again.tickets()[0]["breakdown"] == {"why": "test"}


@pytest.fixture(params=[False, True], ids=["foreign keys off by default", "on by default"])
def sqlite_build(request, monkeypatch):
    """Some SQLite builds turn foreign keys on for every new connection: the migrations must not depend on either."""
    if request.param:
        connect = sqlite3.connect

        def connect_with_foreign_keys(*args, **kwargs):
            conn = connect(*args, **kwargs)
            conn.execute("pragma foreign_keys = on")
            return conn

        monkeypatch.setattr(sqlite3, "connect", connect_with_foreign_keys)


def test_the_category_migration_keeps_every_row_and_takes_the_pwd_barriers(tmp_path, sqlite_build):
    old = Db(tmp_path / "lakad.db")
    old._conn.executescript("pragma foreign_keys = off; drop table ticket_events; drop table sightings; drop table tickets;"
                            f"{MIGRATIONS[0]} pragma user_version = 1; pragma foreign_keys = on;")  # a file from before
    old.save(ticket(status="open"), sighting(), AT)
    old.set_status("t", "assigned", "analyst-1", AT, allowed=lambda t: True)
    with pytest.raises(sqlite3.IntegrityError):
        old.save(ticket("ramp", category="missing_ramp"), sighting("ramp", "ramp"), AT)

    new = Db(tmp_path / "lakad.db")
    assert new._conn.execute("pragma user_version").fetchone()[0] == len(MIGRATIONS)
    assert [(t["id"], t["status"]) for t in new.tickets()] == [("t", "assigned")]
    assert new._conn.execute("select count(*) from sightings").fetchone()[0] == 1, "the rebuild must not cascade"
    assert events(new) == [("t", "analyst-1", "open", "assigned", AT)]
    new.save(ticket("ramp", category="missing_ramp"), sighting("ramp", "ramp"), LATER)
    assert {t["category"] for t in new.tickets()} == {"pothole", "missing_ramp"}
    assert new._conn.execute("pragma foreign_key_check").fetchall() == []
    assert new._conn.execute("pragma foreign_keys").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):  # the foreign key still holds after the rebuild
        new.save(ticket("x"), sighting("x", tid="nowhere"), LATER)


def test_processes_opening_the_file_at_once_run_each_migration_once(tmp_path, monkeypatch):
    # All four read the same user_version and queue for the write lock; each later one must see the work done and skip
    # it. The added migration is slow (so the others really do wait) and cannot run twice (so a repeat fails).
    Db(tmp_path / "lakad.db")  # the file exists, in WAL mode: four first-ever opens would race on switching to WAL
    slow = "create table slow as with recursive c(x) as (select 1 union all select x + 1 from c where x < 400000) select sum(x) as s from c;"
    monkeypatch.setattr(storage, "MIGRATIONS", (*MIGRATIONS, slow))
    errors = []

    def open_file():
        try:
            Db(tmp_path / "lakad.db")
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=open_file) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert Db(tmp_path / "lakad.db")._conn.execute("pragma user_version").fetchone()[0] == len(MIGRATIONS) + 1


def test_a_failed_migration_changes_nothing_and_lets_go_of_the_file(tmp_path, monkeypatch):
    Db(tmp_path / "lakad.db").save(ticket(), sighting(), AT)
    monkeypatch.setattr(storage, "MIGRATIONS", (*MIGRATIONS, "alter table tickets add column x text; select * from nowhere;"))
    with pytest.raises(sqlite3.OperationalError):
        Db(tmp_path / "lakad.db")
    monkeypatch.setattr(storage, "MIGRATIONS", MIGRATIONS)
    after = Db(tmp_path / "lakad.db")  # opens at once: the failed attempt holds no write lock
    assert after._conn.execute("pragma user_version").fetchone()[0] == len(MIGRATIONS)
    assert columns(after, "tickets") == list(engine.TICKET_COLUMNS), "the half-done change was rolled back"
    after.save(ticket("u"), sighting("u", "u"), LATER)
    assert [t["id"] for t in after.tickets()] == ["u", "t"]


def test_the_sos_kind_migration_keeps_every_row_and_only_an_sos_takes_a_kind(tmp_path):
    old = Db(tmp_path / "lakad.db")
    old._conn.executescript("pragma foreign_keys = off; drop table ticket_events; drop table sightings; drop table tickets;"
                            f"{MIGRATIONS[0]} {MIGRATIONS[1]} pragma user_version = 2; pragma foreign_keys = on;")
    old.save(ticket(status="open"), sighting(), AT)  # a file from before, with a row in every table
    old.save(ticket("s", category="sos", status="open"), sighting("s", "s"), AT)
    old.set_status("t", "assigned", "analyst-1", AT, allowed=lambda t: True)
    assert "sos_kind" not in columns(old, "tickets")

    new = Db(tmp_path / "lakad.db")
    assert new._conn.execute("pragma user_version").fetchone()[0] == len(MIGRATIONS)
    kept = [(t["id"], t["status"], t["sos_kind"]) for t in new.tickets()]
    assert kept == [("t", "assigned", None), ("s", "open", None)]
    assert new._conn.execute("select count(*) from sightings").fetchone()[0] == 2
    assert events(new) == [("t", "analyst-1", "open", "assigned", AT)]
    assert new.set_sos_kind("s", "medical", LATER, allowed=lambda t: True)["sos_kind"] == "medical"
    with pytest.raises(sqlite3.IntegrityError):  # the check came with the column: never on the old hazard
        new.save(ticket(sos_kind="police"), sighting(), LATER)
    assert new._conn.execute("pragma foreign_key_check").fetchall() == []
    assert new._conn.execute("pragma foreign_keys").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):  # the foreign key still holds
        new.save(ticket("x"), sighting("x", tid="nowhere"), LATER)


def test_a_save_without_a_status_keeps_the_one_an_analyst_set(db):
    db.save(ticket(status="open"), sighting(), AT)
    db.set_status("t", "assigned", "analyst-1", AT, allowed=lambda t: True)
    db.save(ticket(reporters=2, priority=55.0, band="High"), sighting("s2"), LATER)
    row = db.tickets()[0]
    assert (row["status"], row["reporters"], row["band"], row["updated_at"]) == ("assigned", 2, "High", LATER)
    assert events(db) == [("t", "analyst-1", "open", "assigned", AT)]


def test_a_save_that_reopens_clears_fixed_at_and_is_logged_without_an_actor(db):
    db.save(ticket(status="open"), sighting(), AT)
    assert db.set_status("t", "fixed", "analyst-1", AT, allowed=lambda t: True)["fixed_at"] == AT
    db.save(ticket(status="open"), sighting("s2"), LATER)
    assert db.tickets()[0]["fixed_at"] is None
    assert events(db)[-1] == ("t", None, "fixed", "open", LATER)


def test_a_change_that_is_not_allowed_changes_nothing(db):
    db.save(ticket(status="open"), sighting(), AT)
    seen = []
    assert db.set_status("t", "fixed", "a", LATER, allowed=lambda t: seen.append(t["district_id"]) or False) is None
    assert seen == [1] and db.tickets()[0]["status"] == "open" and events(db) == []
    assert db.set_status("missing", "fixed", "a", LATER, allowed=lambda t: True) is None


def test_the_same_status_again_is_not_a_change(db):
    db.save(ticket(status="open"), sighting(), AT)
    assert db.set_status("t", "open", "a", LATER, allowed=lambda t: True)["updated_at"] == AT and events(db) == []


def test_sorting_an_sos_sets_its_kind_and_nothing_else_and_is_not_logged(db):
    db.save(ticket("s", category="sos", status="open"), sighting("s", "s"), AT)
    got = db.set_sos_kind("s", "police", LATER, allowed=lambda t: True)
    assert (got["sos_kind"], got["status"], got["updated_at"]) == ("police", "open", LATER) and events(db) == []
    assert db.set_sos_kind("s", "medical", LATER, allowed=lambda t: True)["sos_kind"] == "medical"  # sorted again


def test_a_kind_for_a_missing_ticket_one_not_allowed_or_a_hazard_changes_nothing(db):
    db.save(ticket(status="open"), sighting(), AT)
    db.save(ticket("s", category="sos", status="open"), sighting("s", "s"), AT)
    before = db.tickets()
    assert db.set_sos_kind("missing", "police", LATER, allowed=lambda t: True) is None
    assert db.set_sos_kind("s", "police", LATER, allowed=lambda t: False) is None
    assert db.set_sos_kind("t", "police", LATER, allowed=lambda t: False) is None  # a hazard outside it looks missing
    with pytest.raises(ValueError, match="Only an SOS has a kind."):
        db.set_sos_kind("t", "police", LATER, allowed=lambda t: True)
    assert db.tickets() == before and events(db) == []


def test_bad_values_never_reach_the_table(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.save(ticket(status="done"), sighting(), AT)
    with pytest.raises(sqlite3.IntegrityError):
        db.save(ticket(category="ufo"), sighting(), AT)
    with pytest.raises(sqlite3.IntegrityError):  # only an SOS has a kind
        db.save(ticket(sos_kind="police"), sighting(), AT)
    with pytest.raises(sqlite3.IntegrityError):  # and only one of the three
        db.save(ticket(category="sos", sos_kind="firefighters"), sighting(), AT)
    with pytest.raises(sqlite3.IntegrityError):  # a sighting needs its ticket; the failed save leaves no ticket either
        db.save(ticket(), sighting(tid="nowhere"), AT)
    assert db.tickets() == []


def test_closed_before_finds_long_closed_tickets_only(db):
    for tid in ("open", "fixed", "rejected", "fixed-late"):
        db.save(ticket(tid, status="open"), sighting(tid, tid), AT)
    db.set_status("fixed", "fixed", "a", AT, allowed=lambda t: True)
    db.set_status("rejected", "rejected", "a", AT, allowed=lambda t: True)
    db.set_status("fixed-late", "fixed", "a", LATER, allowed=lambda t: True)
    assert db.closed_before(LATER) == {"fixed", "rejected"}


def test_threads_can_write_at_once(db):
    def write(i):
        db.save(ticket(f"t{i}", status="open"), sighting(f"t{i}", f"t{i}"), AT)
        db.set_status(f"t{i}", "verified", "a", LATER, allowed=lambda t: True)

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(write, range(200)))
    assert len(db.tickets()) == 200 and {t["status"] for t in db.tickets()} == {"verified"} and len(events(db)) == 200
