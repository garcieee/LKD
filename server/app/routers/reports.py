"""POST, GET and PATCH /reports: photo reports from the app become tickets on the dashboard."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.config import in_city
from app.db.models import Category, Report, StatusUpdate
from app.services.priority import severity

router = APIRouter()

MAX_PHOTO_BYTES = 10 * 1024 * 1024
# Detect the type from the bytes, never from the client's filename or content type.
IMAGE_TYPES = {b"\xff\xd8\xff": "jpg", b"\x89PNG\r\n\x1a\n": "png"}


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


@router.get("/reports", response_model=list[Report])
def list_reports(request: Request):
    # Stored in arrival order, so reversed is newest first.
    return [_out(r) for r in reversed(request.app.state.store.all())]


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
