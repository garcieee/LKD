"""Which open ticket does a new report join, if any?

Same category only ("other" never auto-merges: two unrelated things can both be "other"). The nearest ticket
inside the accuracy-aware radius wins. A ticket fixed within REOPEN_WINDOW_DAYS can still be joined, which
reopens it (the fix did not hold), but a ticket that is still open is always preferred over one that was fixed.
"""
from collections.abc import Iterable
from dataclasses import dataclass
import math

from .. import settings as s
from ..types import Sighting, TicketSpot
from .geo import distance_m, match_radius_m

DAY = 86_400.0


@dataclass(frozen=True)
class Match:
    ticket_id: str
    distance_m: float
    radius_m: float
    reopens: bool  # the ticket was fixed recently, so joining it reopens it


def _joinable(ticket: TicketSpot, now: float) -> tuple[bool, bool]:
    """(can be joined, joining reopens it)."""
    if ticket.status != "fixed":
        return True, False
    recent = ticket.fixed_at is not None and 0 <= now - ticket.fixed_at <= s.REOPEN_WINDOW_DAYS * DAY
    return recent, recent


def find_match(sighting: Sighting, tickets: Iterable[TicketSpot], now: float) -> Match | None:
    """The ticket this sighting joins, or None to start a new one."""
    if sighting.category == "other":
        return None
    best: tuple[tuple, Match] | None = None
    for t in tickets:
        if t.category != sighting.category:
            continue
        ok, reopens = _joinable(t, now)
        if not ok:
            continue
        d = distance_m(sighting.lat, sighting.lng, t.lat, t.lng)
        r = match_radius_m(sighting.accuracy_m, t.accuracy_m)
        if d > r:
            continue
        key = (reopens, d, -t.last_activity_at)  # open before fixed, then nearest, then most recently active
        if best is None or key < best[0]:
            best = (key, Match(t.id, d, r, reopens))
    return best[1] if best else None


def possible_duplicates(
    sighting: Sighting, tickets: Iterable[TicketSpot], now: float, wider: float = 2.0, limit: int = 5
) -> list[Match]:
    """Nearby tickets staff may want to merge by hand: other categories at the same spot, or the same category
    just past the auto-merge radius. Never includes a ticket find_match would already join."""
    out = []
    for t in tickets:
        ok, reopens = _joinable(t, now)
        if not ok:
            continue
        d = distance_m(sighting.lat, sighting.lng, t.lat, t.lng)
        r = match_radius_m(sighting.accuracy_m, t.accuracy_m)
        merged = t.category == sighting.category and sighting.category != "other" and d <= r
        if not merged and d <= wider * r:
            out.append(Match(t.id, d, r, reopens))
    return sorted(out, key=lambda m: m.distance_m)[:limit]


def _valid(accuracy_m: float | None) -> bool:
    return accuracy_m is not None and math.isfinite(accuracy_m) and accuracy_m > 0


def anchor_after(spot: TicketSpot, sighting: Sighting) -> tuple[float, float, float | None]:
    """The ticket's spot once this sighting joins: the sighting with the smallest reported accuracy is the anchor,
    so the spot never drifts as reports pile up."""
    better = _valid(sighting.accuracy_m) and (not _valid(spot.accuracy_m) or sighting.accuracy_m < spot.accuracy_m)
    if better:
        return sighting.lat, sighting.lng, sighting.accuracy_m
    return spot.lat, spot.lng, spot.accuracy_m
