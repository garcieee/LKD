"""The shapes everything else uses: a Sighting (one report from one phone), a TicketSpot (what matching knows
about an existing ticket), TicketFacts (what the priority score needs) and a Breakdown (why a ticket ranks
where it does). Plain dataclasses, no I/O.
"""
from dataclasses import dataclass

HAZARDS = ("pothole", "open_manhole", "flooded_drain", "broken_streetlight", "blocked_sidewalk", "other")
# Barriers for persons with disability (PWD). They came after the evaluations in eval/, which cover HAZARDS only.
ACCESSIBILITY = ("missing_ramp", "blocked_tactile_paving", "broken_elevator", "unsafe_sidewalk")
CATEGORIES = HAZARDS + ACCESSIBILITY
STATUSES = ("open", "verified", "assigned", "fixed")


@dataclass(frozen=True)
class Sighting:
    """One report from one phone."""

    id: str
    category: str
    lat: float
    lng: float
    accuracy_m: float | None = None  # what the phone says: a radius with 68% confidence
    device_id: str | None = None
    created_at: float = 0.0  # seconds since the epoch, UTC
    note: str = ""
    urgent: bool = False  # the phone's one-tap "urgent" button


@dataclass(frozen=True)
class TicketSpot:
    """What matching needs to know about an existing ticket."""

    id: str
    category: str
    lat: float
    lng: float
    accuracy_m: float | None = None  # accuracy of the sighting the spot comes from
    status: str = "open"
    last_activity_at: float = 0.0
    fixed_at: float | None = None


@dataclass(frozen=True)
class TicketFacts:
    """What the priority score needs to know about a ticket."""

    category: str
    reporters: int  # unique people who reported or confirmed it
    gone_votes: int = 0  # unique people who said it is gone
    days_open: float = 0.0
    foot_traffic: float = 0.5  # 0..1, see ranking/exposure.py
    danger: bool = False  # a danger flag in a note, or enough urgent taps


@dataclass(frozen=True)
class Breakdown:
    """Why a ticket ranks where it does."""

    score: float  # 0..100
    band: str
    parts: dict[str, float]  # danger, reports, foot_traffic, waiting: each 0..1
    belief: float  # how sure we are it is still there, 0..1
    gate: float  # the multiplier that belief puts on the score
    floor_applied: bool  # the category's safety floor lifted the score
    bonus: float  # points added for danger
