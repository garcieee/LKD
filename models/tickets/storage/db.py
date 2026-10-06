"""The memory behind the engine: tickets, their sightings and every status change, in one SQLite file on the Lakad
server (<STORAGE_DIR>/lakad.db, next to reports.json). Standard library sqlite3. Only engine.py uses it.

ponytail: one connection behind one lock serves the loop thread and the request threads, which is plenty for one
server process. Past that, a connection per thread with a busy timeout (WAL already lets readers run beside a writer).
"""
import json
import sqlite3
import threading
from contextlib import contextmanager

# One script per schema version; PRAGMA user_version counts how many have run. Add a script, never edit one.
MIGRATIONS = (
    """
    create table if not exists tickets (
      id text primary key,  -- the id of the hazard's first report, so links to /reports/<id> keep working
      category text not null check (category in
        ('pothole', 'open_manhole', 'flooded_drain', 'broken_streetlight', 'blocked_sidewalk', 'other', 'sos')),
      status text not null default 'open' check (status in ('open', 'verified', 'assigned', 'fixed', 'rejected')),
      district_id integer,  -- resources/districts.json; null outside both districts, seen by citywide analysts only
      lat real not null,
      lng real not null,
      priority real not null default 0 check (priority between 0 and 100),
      band text not null default 'Low' check (band in ('Critical', 'High', 'Medium', 'Low')),
      breakdown text not null default '{}',  -- JSON: why it ranks where it does, and its flags
      reporters integer not null default 1 check (reporters >= 1),
      note text not null default '',
      photo_url text not null default '',
      video_url text,
      created_at text not null,  -- ISO 8601 in UTC, like reports.json
      updated_at text not null,
      fixed_at text
    );
    create index if not exists tickets_district on tickets (district_id);
    create table if not exists sightings (
      id text primary key,  -- the report id
      ticket_id text not null references tickets (id) on delete cascade,
      lat real not null,
      lng real not null,
      accuracy_m real,
      note text not null default '',
      photo_url text not null default '',
      video_url text,
      created_at text not null
    );
    create index if not exists sightings_ticket on sightings (ticket_id);
    create table if not exists ticket_events (
      id integer primary key,
      ticket_id text not null references tickets (id) on delete cascade,
      actor text,  -- the analyst's Supabase user id; null when the server made the change (a reopen)
      from_status text,
      to_status text not null,
      at text not null
    );
    create index if not exists ticket_events_ticket on ticket_events (ticket_id);
    """,
    # 2: the four PWD accessibility barriers. SQLite cannot change a check, so tickets is rebuilt the documented way
    # (sqlite.org/lang_altertable.html, section 7). Foreign keys are off while it runs (Db.__init__), so dropping the
    # old table does not cascade to the sightings and events, which keep pointing at "tickets" by name.
    """
    create table tickets_new (
      id text primary key,
      category text not null check (category in
        ('pothole', 'open_manhole', 'flooded_drain', 'broken_streetlight', 'blocked_sidewalk', 'missing_ramp',
         'blocked_tactile_paving', 'broken_elevator', 'unsafe_sidewalk', 'other', 'sos')),
      status text not null default 'open' check (status in ('open', 'verified', 'assigned', 'fixed', 'rejected')),
      district_id integer,
      lat real not null,
      lng real not null,
      priority real not null default 0 check (priority between 0 and 100),
      band text not null default 'Low' check (band in ('Critical', 'High', 'Medium', 'Low')),
      breakdown text not null default '{}',
      reporters integer not null default 1 check (reporters >= 1),
      note text not null default '',
      photo_url text not null default '',
      video_url text,
      created_at text not null,
      updated_at text not null,
      fixed_at text
    );
    insert into tickets_new select * from tickets;
    drop table tickets;
    alter table tickets_new rename to tickets;
    create index tickets_district on tickets (district_id);
    """,
)


def _upsert(table: str, row: dict) -> str:
    """Insert the row, or for a known id update only the columns it has."""
    sets = ", ".join(f"{c} = excluded.{c}" for c in row if c != "id")
    return f"insert into {table} ({', '.join(row)}) values ({', '.join(':' + c for c in row)}) on conflict (id) do update set {sets}"


def _ticket(row: sqlite3.Row) -> dict:
    return {**dict(row), "breakdown": json.loads(row["breakdown"])}


class Db:
    def __init__(self, path):
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)  # transactions are explicit
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._conn.execute("pragma journal_mode = wal")
        # Migrations run before foreign keys go on: a rebuilt table's drop must not cascade (see migration 2).
        version = self._conn.execute("pragma user_version").fetchone()[0]
        for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
            self._conn.executescript(f"begin; {script} pragma user_version = {number}; commit;")
        self._conn.execute("pragma foreign_keys = on")

    @contextmanager
    def _tx(self):
        """One transaction under the lock: all of it lands, or none of it."""
        with self._lock:
            self._conn.execute("begin immediate")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("rollback")
                raise
            self._conn.execute("commit")

    def _status_changed(self, db, ticket_id: str, old: str, new: str, actor: str | None, at: str) -> None:
        """fixed_at follows the status (set when fixed, cleared when reopened) and the change is logged with who made it."""
        if new in ("fixed", "open"):
            db.execute("update tickets set fixed_at = ? where id = ?", (at if new == "fixed" else None, ticket_id))
        db.execute("insert into ticket_events (ticket_id, actor, from_status, to_status, at) values (?, ?, ?, ?, ?)",
                   (ticket_id, actor, old, new, at))

    def save(self, ticket: dict, sighting: dict, at: str) -> None:
        """Upsert a ticket and one sighting of it, together. Only the ticket's given columns change, so the status an
        analyst set survives unless the row carries one (a new ticket, or a reopen, which is logged with no actor)."""
        row = {**ticket, "breakdown": json.dumps(ticket.get("breakdown", {})), "updated_at": at}
        with self._tx() as db:
            old = db.execute("select status from tickets where id = ?", (row["id"],)).fetchone()
            db.execute(_upsert("tickets", row), row)
            if old and "status" in row and row["status"] != old["status"]:
                self._status_changed(db, row["id"], old["status"], row["status"], None, at)
            db.execute(_upsert("sightings", sighting), sighting)

    def tickets(self) -> list[dict]:
        """Every ticket, newest first."""
        with self._lock:
            rows = self._conn.execute("select * from tickets order by created_at desc, id desc").fetchall()
        return [_ticket(r) for r in rows]

    def set_status(self, ticket_id: str, status: str, actor: str | None, at: str, allowed) -> dict | None:
        """Change a ticket's status when allowed(ticket) says yes, checked in the same transaction as the change.
        None when the ticket is missing or not allowed; nothing changes then."""
        with self._tx() as db:
            row = db.execute("select * from tickets where id = ?", (ticket_id,)).fetchone()
            if row is None or not allowed(_ticket(row)):
                return None
            if status != row["status"]:
                db.execute("update tickets set status = ?, updated_at = ? where id = ?", (status, at, ticket_id))
                self._status_changed(db, ticket_id, row["status"], status, actor, at)
            return _ticket(db.execute("select * from tickets where id = ?", (ticket_id,)).fetchone())

    def closed_before(self, at: str) -> set[str]:
        """Ids of the tickets that were fixed or rejected, and untouched since, before this time."""
        with self._lock:
            rows = self._conn.execute(
                "select id from tickets where status in ('fixed', 'rejected') and updated_at < ?", (at,)).fetchall()
        return {r["id"] for r in rows}
