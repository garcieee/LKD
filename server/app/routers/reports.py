"""POST, GET and PATCH /reports: photo reports from the app become tickets on the dashboard.

POST /sos files an SOS the same way, from a video: an urgent ticket that tops the dashboard queue."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.config import in_city
from app.db.models import Category, Report, StatusUpdate
from app.services.priority import severity

router = APIRouter()

MAX_PHOTO_BYTES = 10 * 1024 * 1024
# The app records at most 30 s at about 2.5 Mbit/s (under 10 MB); the cap leaves room for another phone's encoder.
MAX_VIDEO_BYTES = 40 * 1024 * 1024
# Detect the type from the bytes, never from the client's filename or content type.
IMAGE_TYPES = {b"\xff\xd8\xff": "jpg", b"\x89PNG\r\n\x1a\n": "png"}


def _video_ext(data: bytes) -> str | None:
    """The container of a video, from its bytes: MP4/3GP/MOV start with an `ftyp` box, WebM with an EBML header."""
    if data[4:8] == b"ftyp":
        return "mov" if data[8:12] == b"qt  " else "mp4"
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _out(report: dict) -> Report:
    return Report(**report, severity=severity(report["category"]))


@router.post("/reports", status_code=201, response_model=Report)
def create_report(
    request: Request,
    photo: UploadFile = File(...),
    category: Category = Form(...),
    lat: float = Form(...),
    lng: float = Form(...),
    heading: float | None = Form(None, ge=0, le=360),
    note: str = Form("", max_length=280),
):
    if category == "sos":
        raise HTTPException(422, "An SOS is sent as a video to /sos.")
    if not in_city(lat, lng):
        raise HTTPException(422, "That location is outside the city.")

    data = photo.file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "Photo is larger than 10 MB.")
    ext = next((e for magic, e in IMAGE_TYPES.items() if data.startswith(magic)), None)
    if ext is None:
        raise HTTPException(422, "Photo must be a JPEG or PNG.")

    report_id = uuid.uuid4().hex
    (request.app.state.photo_dir / f"{report_id}.{ext}").write_bytes(data)
    now = _now()
    report = {
        "id": report_id,
        "category": category,
        "lat": lat,
        "lng": lng,
        "heading": heading,
        "note": note.strip(),
        "photo_url": f"/photos/{report_id}.{ext}",
        "status": "open",
        "created_at": now,
        "updated_at": now,
    }
    return _out(request.app.state.store.add(report))


@router.post("/sos", status_code=201, response_model=Report)
def create_sos(
    request: Request,
    video: UploadFile = File(...),
    lat: float = Form(...),
    lng: float = Form(...),
    heading: float | None = Form(None, ge=0, le=360),
    note: str = Form("", max_length=280),
):
    """An SOS from the app's hold-to-record button: the clip, filed straight away as an open, urgent ticket."""
    if not in_city(lat, lng):
        raise HTTPException(422, "That location is outside the city.")

    data = video.file.read(MAX_VIDEO_BYTES + 1)
    if len(data) > MAX_VIDEO_BYTES:
        raise HTTPException(413, "Video is larger than 40 MB.")
    ext = _video_ext(data)
    if ext is None:
        raise HTTPException(422, "The SOS must be an MP4, MOV or WebM video.")

    report_id = uuid.uuid4().hex
    (request.app.state.video_dir / f"{report_id}.{ext}").write_bytes(data)
    now = _now()
    report = {
        "id": report_id,
        "category": "sos",
        "lat": lat,
        "lng": lng,
        "heading": heading,
        "note": note.strip(),
        "photo_url": "",
        "video_url": f"/videos/{report_id}.{ext}",
        "status": "open",
        "created_at": now,
        "updated_at": now,
    }
    return _out(request.app.state.store.add(report))


@router.get("/reports", response_model=list[Report])
def list_reports(request: Request, include_sos: bool = False, include_rejected: bool = False):
    """Newest first. SOS tickets are left out unless asked for (`include_sos=true`, which the dashboard does),
    so the public app's map and AR view never show where someone called for help. Rejected tickets (judged not
    real at the dashboard) are left out unless `include_rejected=true`.

    ponytail: the API has no accounts yet, so this only keeps SOS out of the app's own lists; anyone who knows
    the query can still ask. Put the dashboard behind a login before anyone real depends on SOS.
    """
    # Stored in arrival order, so reversed is newest first.
    return [
        _out(r)
        for r in reversed(request.app.state.store.all())
        if (include_sos or r["category"] != "sos") and (include_rejected or r["status"] != "rejected")
    ]


@router.get("/reports/{report_id}", response_model=Report)
def get_report(report_id: str, request: Request):
    for report in request.app.state.store.all():
        if report["id"] == report_id:
            return _out(report)
    raise HTTPException(404, "No such report.")


@router.patch("/reports/{report_id}", response_model=Report)
def update_status(report_id: str, body: StatusUpdate, request: Request):
    report = request.app.state.store.update(report_id, status=body.status, updated_at=_now())
    if report is None:
        raise HTTPException(404, "No such report.")
    return _out(report)
