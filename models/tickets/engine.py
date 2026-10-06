"""The only door into models/tickets/. The server calls these and nothing else. Plan: ATTACH.md.

load_world   the static inputs the rules need, read once at start
attach       for one report: the ticket it joins or opens, the ticket's district, priority and flags. Pure, no I/O.
sync_once    one turn of the server's loop: attach every cached report that has no ticket yet, save the rows to
             lakad.db, write the outcome back onto the cached reports, let long-closed reports leave the cache
database     the SQLite file the tickets live in (storage/db.py)
tickets_for  the tickets a district scope may see, and the changes made to them, set_status and set_sos_kind (who
             must respond to an SOS): the one place a scope is checked. The server, with no sign-in, passes "all"
backlog      reports still waiting for a ticket, and those that gave up, for /health
"""
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Protocol

from ..ticket_sos import sos
from . import settings as s
from .classification import classify, routing
from .classification.classify import Lexicon
from .matching import match
from .ranking import exposure, priority
from .resources import load
from .storage.db import Db
from .types import ACCESSIBILITY, Sighting, TicketFacts, TicketSpot

# The columns of the tickets and sightings tables (storage/db.py). tests/test_storage.py keeps them equal.
TICKET_COLUMNS = ("id", "category", "status", "district_id", "lat", "lng", "priority", "band", "breakdown",
                  "reporters", "note", "photo_url", "video_url", "created_at", "updated_at", "fixed_at", "sos_kind")
SIGHTING_COLUMNS = ("id", "ticket_id", "lat", "lng", "accuracy_m", "note", "photo_url", "video_url", "created_at")
DAY = 86_400.0


class Cache(Protocol):
    """The server's report store, db/reports.json (server/app/db/store.py ReportStore has exactly these)."""

    def all(self) -> list[dict]: ...

    def update(self, report_id: str, **fields) -> dict | None: ...

    def remove(self, report_ids) -> int: ...


@dataclass(frozen=True)
class World:
    """Everything static the rules need, loaded once at start from resources/."""

    places: list  # resources/places.json
    lexicon: Lexicon  # resources/lexicon.json
    offices: dict  # resources/offices.json
    districts: list  # resources/districts.json: (district_id, barangay, box, rings) per barangay
    barrier_lexicon: Lexicon  # the same lists, for a PWD barrier's notes: see load_world


@dataclass(frozen=True)
class Attachment:
    """What one report comes to: the rows to save, and the fields to add to the report in the cache."""

    ticket: dict  # keys from TICKET_COLUMNS; "status" only for a new ticket (the report's own) or a reopen ("open"),
    #               "sos_kind" only for an SOS
    sighting: dict  # keys from SIGHTING_COLUMNS
    cache: dict  # ticket_id, district_id, priority, band


@dataclass
class SyncStats:
    attached: int = 0
    failed: list[str] = field(default_factory=list)  # report ids that failed this turn, retried up to SYNC_MAX_TRIES
    pruned: int = 0  # reports that left the cache because their ticket closed long ago


def load_world() -> World:
    data = load.load_lexicon()
    # A PWD barrier's note names who it stops ("walang rampa para sa pwd"): there "pwd" and "wheelchair" describe the
    # category, not a danger, so its notes are read without them. Every other danger word still counts.
    barrier = {**data, "danger": [w for w in data["danger"] if w not in ("pwd", "wheelchair")]}
    return World(load.load_places(), Lexicon(data), load.load_offices(), load.load_districts(), Lexicon(barrier))


def _ts(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp()


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds")


def _sighting(r: dict) -> Sighting:
    return Sighting(r["id"], r["category"], r["lat"], r["lng"], r.get("accuracy_m"), created_at=_ts(r["created_at"]),
                    note=r.get("note", ""))


def _tickets(cached: list[dict]) -> dict[str, list[dict]]:
    """The cached reports that already have a ticket, by ticket, in arrival order."""
    out: dict[str, list[dict]] = {}
    for r in cached:
        if r.get("ticket_id"):
            out.setdefault(r["ticket_id"], []).append(r)
    return out


def _spot(ticket_id: str, reports: list[dict]) -> TicketSpot:
    """What matching knows about a ticket, from its cached reports. The anchor is the most accurate sighting, and the
    status is the one set last (a status change reaches every report of the ticket)."""
    first, latest = reports[0], max(reports, key=lambda r: r["updated_at"])
    spot = TicketSpot(ticket_id, first["category"], first["lat"], first["lng"], first.get("accuracy_m"),
                      latest["status"], last_activity_at=max(_ts(r["created_at"]) for r in reports),
                      fixed_at=_ts(latest["updated_at"]) if latest["status"] == "fixed" else None)
    for r in reports[1:]:
        lat, lng, accuracy = match.anchor_after(spot, _sighting(r))
        spot = replace(spot, lat=lat, lng=lng, accuracy_m=accuracy)
    return spot


def attach(report: dict, cached: list[dict], world: World, now: float) -> Attachment:
    """The ticket this report joins (same category, close enough, not rejected) or opens with its own id, and that
    ticket's district, priority and breakdown once the report is on it.

    An SOS never joins another ticket. Nor does a report an analyst already judged before the loop reached it (one
    from before the loop existed, say): it opens its own ticket and keeps its status, so nothing they set is undone."""
    tickets, found = _tickets(cached), None
    if not sos.is_sos(report) and report["status"] == "open":
        sighting = _sighting(report)
        spots = {tid: _spot(tid, rs) for tid, rs in tickets.items() if rs[0]["category"] == report["category"]}
        # Timed from the report, so only a report made after a fix can reopen it.
        found = match.find_match(sighting, [t for t in spots.values() if t.status != "rejected"], sighting.created_at)
    if found:
        ticket_id, reports = found.ticket_id, [*tickets[found.ticket_id], report]
        lat, lng, accuracy = match.anchor_after(spots[ticket_id], sighting)
    else:
        ticket_id, reports = report["id"], [report]
        lat, lng, accuracy = report["lat"], report["lng"], report.get("accuracy_m")

    notes = [r["note"] for r in reports if r.get("note")]
    review = classify.review_reasons(accuracy_m=accuracy)
    if sos.is_sos(report):
        score, band, breakdown = sos.PRIORITY, sos.BAND, sos.flags(review)
    else:
        lexicon = world.barrier_lexicon if report["category"] in ACCESSIBILITY else world.lexicon
        facts = TicketFacts(
            report["category"],
            # ponytail: counts reports, not people, so one phone reporting twice counts twice. Count distinct
            # device ids once the app sends one.
            reporters=len(reports),
            days_open=max(0.0, now - min(_ts(r["created_at"]) for r in reports)) / DAY,
            foot_traffic=exposure.foot_traffic(lat, lng, world.places),
            danger=any(classify.has_danger(note, 0, lexicon) for note in notes),
        )
        b = priority.score(facts)
        hint = classify.category_hint("\n".join(notes), world.lexicon)
        score, band = b.score, b.band
        breakdown = {"parts": b.parts, "belief": b.belief, "gate": b.gate, "floor_applied": b.floor_applied,
                     "bonus": b.bonus, "danger": facts.danger, "hint": hint.category if hint else None,
                     "review": review, "office": routing.office_for(report["category"], world.offices)}

    district = routing.district_of(lat, lng, world.districts)
    head = next((r for r in reports if r["id"] == ticket_id), reports[0])  # the first report: its photo and note
    ticket = {"id": ticket_id, "category": report["category"], "district_id": district, "lat": lat, "lng": lng,
              "priority": round(score, 1), "band": band, "breakdown": breakdown, "reporters": len(reports),
              "note": head.get("note", ""), "photo_url": head.get("photo_url", ""), "video_url": head.get("video_url"),
              "created_at": head["created_at"]}
    if sos.is_sos(report):
        ticket["sos_kind"] = report.get("sos_kind")  # set on reports.json before the loop got here, or None
    if not found:
        ticket["status"] = report["status"]  # "open", unless an analyst got to the report first
    elif found.reopens:
        ticket["status"] = "open"
    # A join sends no status, so the one an analyst set is never overwritten.
    row = {"id": report["id"], "ticket_id": ticket_id, "lat": report["lat"], "lng": report["lng"],
           "accuracy_m": report.get("accuracy_m"), "note": report.get("note", ""),
           "photo_url": report.get("photo_url", ""), "video_url": report.get("video_url"),
           "created_at": report["created_at"]}
    cache = {"ticket_id": ticket_id, "district_id": district, "priority": ticket["priority"], "band": band}
    return Attachment(ticket, row, cache)


def _write(cache: Cache, report: dict, fields: dict) -> None:
    """Onto the cache, and onto this turn's copy so later reports in the same turn see it."""
    cache.update(report["id"], **fields)
    report.update(fields)


def sync_once(cache: Cache, world: World, db: Db, now: float | None = None) -> SyncStats:
    """One turn of the loop. Every cached report without a ticket, oldest first, is attached and saved to lakad.db,
    then marked in the cache: a crash in between only means the next turn saves the same rows again. A report that
    fails SYNC_MAX_TRIES turns keeps its sync_error and is skipped, so it cannot block the queue. Reports whose ticket
    lakad.db has had closed for CACHE_KEEP_DAYS leave the cache.

    ponytail: a ticket is scored when a report joins it, so its waiting time grows unseen between reports. Re-score
    the open tickets once a day if the queue order drifts."""
    now = time.time() if now is None else now
    at, stats, reports = _iso(now), SyncStats(), cache.all()
    pending = [r for r in reports if not r.get("ticket_id") and r.get("sync_tries", 0) < s.SYNC_MAX_TRIES]
    for report in sorted(pending, key=lambda r: str(r.get("created_at", ""))):
        try:
            a = attach(report, reports, world, now)
            db.save(a.ticket, a.sighting, at)
        except Exception as error:  # this report only: the rest of the queue carries on
            _write(cache, report, {"sync_tries": report.get("sync_tries", 0) + 1,
                                   "sync_error": f"{type(error).__name__}: {error}"[:200]})
            stats.failed.append(report["id"])
            continue
        _write(cache, report, {**a.cache, **({"sync_error": None} if report.get("sync_error") else {})})
        shared = {k: a.cache[k] for k in ("district_id", "priority", "band")}
        if "status" in a.ticket:  # a reopen: every report of the ticket is open again (a new one has no others)
            shared.update(status=a.ticket["status"], updated_at=at)
        for other in reports:
            if other.get("ticket_id") == a.cache["ticket_id"] and other is not report:
                _write(cache, other, shared)
        stats.attached += 1
    closed = db.closed_before(_iso(now - s.CACHE_KEEP_DAYS * DAY))
    gone = [r["id"] for r in reports if r.get("ticket_id") in closed]
    stats.pruned = cache.remove(gone) if gone else 0
    return stats


def database(path) -> Db:
    """The SQLite file the tickets live in, created and migrated on first use."""
    return Db(path)


def _visible(ticket: dict, scope) -> bool:
    """The district check, the only one. scope "all" (citywide) sees every ticket; a set of district ids sees only
    those districts' tickets, never one with no district; anything else sees nothing."""
    if scope == "all":
        return True
    return isinstance(scope, (set, frozenset)) and ticket["district_id"] is not None and ticket["district_id"] in scope


def tickets_for(db: Db, scope) -> list[dict]:
    """The tickets an analyst may see, newest first."""
    return [t for t in db.tickets() if _visible(t, scope)]


def set_status(db: Db, cache: Cache, ticket_id: str, status: str, scope, actor: str | None, now: float | None = None) -> dict | None:
    """A status change: on the ticket, in its history under who made it (None: nobody signed in), and on its cached
    reports so the public map follows. None when the ticket is missing or outside the scope, which look the same."""
    at = _iso(time.time() if now is None else now)
    ticket = db.set_status(ticket_id, status, actor, at, allowed=lambda t: _visible(t, scope))
    if ticket is not None:
        for r in cache.all():
            if r.get("ticket_id") == ticket_id and r["status"] != ticket["status"]:
                cache.update(r["id"], status=ticket["status"], updated_at=at)
    return ticket


def set_sos_kind(db: Db, cache: Cache, ticket_id: str, kind: str, scope, now: float | None = None) -> dict | None:
    """Sorting an SOS by who must respond (sos.KINDS): on the ticket and on its cached reports, so every row agrees.
    ValueError for an unknown kind or a ticket that is not an SOS; None when the ticket is missing or outside the
    scope, like set_status. Not logged in the ticket's history, which holds status changes."""
    sos.check_kind(kind)
    at = _iso(time.time() if now is None else now)
    ticket = db.set_sos_kind(ticket_id, kind, at, allowed=lambda t: _visible(t, scope))
    if ticket is not None:
        for r in cache.all():
            if r.get("ticket_id") == ticket_id:
                cache.update(r["id"], sos_kind=kind, updated_at=at)
    return ticket


def backlog(cache: Cache) -> dict:
    """pending: reports still waiting for a ticket. failed: those that gave up after SYNC_MAX_TRIES (see sync_error)."""
    waiting = [r for r in cache.all() if not r.get("ticket_id")]
    failed = sum(r.get("sync_tries", 0) >= s.SYNC_MAX_TRIES for r in waiting)
    return {"pending": len(waiting) - failed, "failed": failed}
