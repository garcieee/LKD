"""The only door into models/tickets/. The server calls these and nothing else. Plan: ATTACH.md.

attach     for one report: the ticket it joins or opens, the ticket's district, priority and flags. Pure, no I/O.
sync_once  one turn of the server's loop: attach every cached report that has no ticket yet, push the rows to the
           database, write the outcome back onto the cached report, pull status changes analysts made.
database   the Supabase connection for sync_once, or None when SUPABASE_URL is not set (the loop then works on the
           cache alone).

Scaffold: the signatures and the row shapes are fixed by ATTACH.md and tests/test_contract.py. The bodies come on
the tickets-engine branch.
"""
from dataclasses import dataclass, field
from typing import Protocol

# The columns of public.tickets and public.sightings (supabase/migrations/). tests/test_contract.py keeps them equal.
TICKET_COLUMNS = ("id", "category", "status", "district_id", "lat", "lng", "priority", "band", "breakdown",
                  "reporters", "note", "photo_url", "video_url", "created_at", "updated_at", "fixed_at")
SIGHTING_COLUMNS = ("id", "ticket_id", "lat", "lng", "accuracy_m", "note", "photo_url", "video_url", "created_at")


class Cache(Protocol):
    """The server's report store, db/reports.json (server/app/db/store.py ReportStore has exactly these)."""

    def all(self) -> list[dict]: ...

    def update(self, report_id: str, **fields) -> dict | None: ...


@dataclass(frozen=True)
class World:
    """Everything static the rules need, loaded once at start from resources/."""

    places: list  # resources/places.json
    lexicon: object  # classification.classify.Lexicon
    offices: dict  # resources/offices.json
    districts: list  # resources/districts.json: (district_id, polygons) per district


@dataclass(frozen=True)
class Attachment:
    """What one report comes to: the rows to upsert, and the fields to add to the report in the cache."""

    ticket: dict  # keys from TICKET_COLUMNS
    sighting: dict  # keys from SIGHTING_COLUMNS
    cache: dict  # ticket_id, district_id, priority, band


@dataclass
class SyncStats:
    attached: int = 0
    pushed: int = 0
    pulled: int = 0
    failed: list[str] = field(default_factory=list)  # report ids that will be retried, up to 3 times


def attach(report: dict, cached: list[dict], world: World, now: float) -> Attachment:
    raise NotImplementedError("tickets-engine branch, see ATTACH.md")


def sync_once(cache: Cache, world: World, db=None, now: float | None = None) -> SyncStats:
    raise NotImplementedError("tickets-engine branch, see ATTACH.md")


def database(url: str, secret_key: str):
    raise NotImplementedError("tickets-engine branch, see ATTACH.md")
