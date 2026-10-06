"""The report shape. Mirrored by dashboard/src/types/api.ts and mobile/lib/api/api_client.dart."""
from typing import Literal

from pydantic import BaseModel, model_validator

# "sos" is not a hazard a person picks: only POST /sos files one, from the app's hold-to-record button.
# The four after "blocked_sidewalk" are accessibility barriers for persons with disability (services/hazards.py).
Category = Literal[
    "pothole", "open_manhole", "flooded_drain", "broken_streetlight", "blocked_sidewalk",
    "missing_ramp", "blocked_tactile_paving", "broken_elevator", "unsafe_sidewalk", "other", "sos"
]
# "rejected": a person at the dashboard looked at a new ticket and decided it is not real. It is hidden everywhere
# (public list, map, routes) but kept, and can be reopened.
Status = Literal["open", "verified", "assigned", "fixed", "rejected"]
# Who must respond to an SOS, picked at the dashboard. Mirrors models/ticket_sos/sos.py KINDS (tests/test_sos.py keeps
# them equal) and dashboard/src/types/api.ts.
SosKind = Literal["police", "medical", "fire_rescue"]


class Report(BaseModel):
    id: str
    category: Category
    severity: int  # 1 low .. 3 urgent, from the category (services/priority.py)
    lat: float
    lng: float
    heading: float | None  # compass heading when the photo was taken
    note: str
    photo_url: str  # path on this server, e.g. /photos/<id>.jpg. Empty for an SOS, which has a video instead
    video_url: str | None = None  # SOS only: path on this server, e.g. /videos/<id>.mp4
    sos_kind: SosKind | None = None  # SOS only: who must respond, set at the dashboard; None until sorted
    status: Status
    created_at: str  # ISO 8601, UTC
    updated_at: str
    # Set by the ticket loop (models/tickets/engine.py) a few seconds after the report arrives.
    ticket_id: str | None = None  # the ticket this report is a sighting of; a ticket's id is its first report's
    district_id: int | None = None  # 1 or 2, or None outside both districts
    priority: float | None = None  # 0..100, the ticket's
    band: str | None = None  # Critical, High, Medium or Low


class TicketChange(BaseModel):
    """PATCH /reports/{id}: a new status, an SOS's kind, or both."""

    status: Status | None = None
    sos_kind: SosKind | None = None

    @model_validator(mode="after")
    def _not_empty(self):
        if self.status is None and self.sos_kind is None:
            raise ValueError("Send a status, an sos_kind, or both.")
        return self
