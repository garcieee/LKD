"""The report and ticket shapes. Mirrored by dashboard/src/types/api.ts and mobile/lib/api/api_client.dart."""
from typing import Literal

from pydantic import BaseModel

# "sos" is not a hazard a person picks: only POST /sos files one, from the app's hold-to-record button.
Category = Literal[
    "pothole", "open_manhole", "flooded_drain", "broken_streetlight", "blocked_sidewalk", "other", "sos"
]
# "rejected": a person at the dashboard looked at a new ticket and decided it is not real. It is hidden everywhere
# (public list, map, routes) but kept, and can be reopened.
Status = Literal["open", "verified", "assigned", "fixed", "rejected"]


class Hazard(BaseModel):
    """What a report and a ticket both show."""

    id: str
    category: Category
    severity: int  # 1 low .. 3 urgent, from the category (services/priority.py)
    lat: float
    lng: float
    heading: float | None  # compass heading when the photo was taken
    note: str
    photo_url: str  # path on this server, e.g. /photos/<id>.jpg. Empty for an SOS, which has a video instead
    video_url: str | None = None  # SOS only: path on this server, e.g. /videos/<id>.mp4
    status: Status
    created_at: str  # ISO 8601, UTC
    updated_at: str


class Report(Hazard):
    # Set by the ticket loop (models/tickets/engine.py) a few seconds after the report arrives.
    ticket_id: str | None = None  # the ticket this report is a sighting of; a ticket's id is its first report's
    district_id: int | None = None  # 1 or 2, or None outside both districts
    priority: float | None = None  # 0..100, the ticket's
    band: str | None = None  # Critical, High, Medium or Low


class Ticket(Hazard):
    """One hazard, however many reports it has: GET and PATCH /tickets, analysts only. Its id is its first report's,
    and its photo, note and heading are that report's; lat and lng are its most accurate sighting's."""

    priority: float  # 0..100
    band: str  # Critical, High, Medium or Low
    district_id: int | None  # 1 or 2; None outside both, seen by citywide analysts only
    reporters: int


class StatusUpdate(BaseModel):
    status: Status
