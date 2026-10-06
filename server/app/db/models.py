"""The report shape. Mirrored by dashboard/src/types/api.ts and mobile/lib/api/api_client.dart."""
from typing import Literal

from pydantic import BaseModel

Category = Literal[
    "pothole", "open_manhole", "flooded_drain", "broken_streetlight", "blocked_sidewalk", "other"
]
Status = Literal["open", "verified", "assigned", "fixed"]


class Report(BaseModel):
    id: str
    category: Category
    severity: int  # 1 low .. 3 urgent, from the category (services/priority.py)
    lat: float
    lng: float
    heading: float | None  # compass heading when the photo was taken
    note: str
    photo_url: str  # path on this server, e.g. /photos/<id>.jpg
    status: Status
    created_at: str  # ISO 8601, UTC
    updated_at: str


class StatusUpdate(BaseModel):
    status: Status
