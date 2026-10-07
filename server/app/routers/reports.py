"""POST, GET and PATCH /reports: photo reports from the app become tickets on the dashboard.

POST /sos files an SOS the same way, from a video: an urgent ticket that tops the dashboard queue."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile

from app.config import in_city
from app.db.models import NOTE_FIELD, Category, Report, TicketChange
from app.services.priority import severity
from app.services.ticket_sync import engine

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


def _public(report: Report) -> Report:
    """Without the dashboard's notes to the reporter: those are for the person who filed the ticket (/my-tickets)."""
    return report.model_copy(update={"verified_note": None, "rejected_note": None, "resolved_note": None})


@router.get("/reports", response_model=list[Report])
def list_reports(request: Request, include_sos: bool = False, include_rejected: bool = False):
    """Newest first. SOS tickets are left out unless asked for (`include_sos=true`, which the dashboard does),
    so the public app's map and AR view never show where someone called for help. Rejected tickets (judged not
    real at the dashboard) are left out unless `include_rejected=true`.

    ponytail: the API has no accounts, so this only keeps SOS out of the app's own lists; anyone who knows
    the query can still ask. Put the dashboard behind a login before anyone real depends on SOS.
    """
    # Stored in arrival order, so reversed is newest first. The dashboard (which asks for SOS or rejected ones)
    # sees the notes; everyone else gets the list without them.
    staff = include_sos or include_rejected
    return [
        _out(r) if staff else _public(_out(r))
        for r in reversed(request.app.state.store.all())
        if (include_sos or r["category"] != "sos") and (include_rejected or r["status"] != "rejected")
    ]


MAX_MINE = 100


@router.get("/my-tickets", response_model=list[Report])
def my_tickets(request: Request, ids: str = Query("", description="report ids, comma-separated")):
    """The reports a phone filed, by id, in the order asked, with the dashboard's notes to the reporter.

    There are no accounts: an id is only known to the phone that filed it, so asking for it is the proof it is theirs.
    An SOS and a rejected ticket come back too, which the public list never shows. An id that is not found (pruned,
    or mistyped) is left out. At most MAX_MINE.
    """
    wanted = list(dict.fromkeys(i.strip() for i in ids.split(",") if i.strip()))[:MAX_MINE]
    by_id = {r["id"]: r for r in request.app.state.store.all()}
    return [_out(by_id[i]) for i in wanted if i in by_id]


@router.get("/reports/{report_id}", response_model=Report)
def get_report(report_id: str, request: Request):
    for report in request.app.state.store.all():
        if report["id"] == report_id:
            return _out(report)
    raise HTTPException(404, "No such report.")


@router.patch("/reports/{report_id}", response_model=Report)
def update_report(report_id: str, body: TicketChange, request: Request):
    """A new status, an SOS's kind (who must respond), a handler, or any of them: only the fields sent change.
    A status may carry a `status_note` for the reporter: required to reject, optional to confirm or resolve.

    A handler (who was assigned to fix it) is picked after the ticket is verified, so only a ticket that is, or becomes,
    assigned or fixed takes one. It goes on the report and on every report of its ticket. A status or kind goes, once
    the loop has given the report its ticket, to the ticket (lakad.db and its history) and to every report of it, so
    the rows of one hazard never disagree. Before that it goes onto the report, and the loop carries it into the ticket.
    """
    state = request.app.state
    report = next((r for r in state.store.all() if r["id"] == report_id), None)
    if report is None:
        raise HTTPException(404, "No such report.")
    if body.sos_kind and report["category"] != "sos":
        raise HTTPException(422, "Only an SOS has a kind.")
    if body.handler and (body.status or report["status"]) not in ("assigned", "fixed"):
        raise HTTPException(422, "A handler is assigned once the ticket is verified.")
    ticket_id, db = report.get("ticket_id"), state.sync.db
    # No sign-in: the whole city's tickets ("all"), and no one to name in the history.
    done = bool(ticket_id)
    if done and body.sos_kind:
        done = engine.set_sos_kind(db, state.store, ticket_id, body.sos_kind, "all") is not None
    if done and body.status:
        done = engine.set_status(db, state.store, ticket_id, body.status, "all", None) is not None
    if not done:  # not on a ticket yet, or its ticket is missing from lakad.db
        state.store.update(report_id, **body.model_dump(exclude_none=True, exclude={"handler", "status_note"}), updated_at=_now())
    # The handler and the note for this status go on every report of the ticket: its rows agree on who has it and on
    # what the reporter was told, as they do on its status. A status with no note clears the old one: that was for an
    # earlier decision.
    extra = {"handler": body.handler} if body.handler else {}
    if body.status in NOTE_FIELD:
        extra[NOTE_FIELD[body.status]] = body.status_note
    if extra:
        mates = [r["id"] for r in state.store.all() if ticket_id and r.get("ticket_id") == ticket_id]
        for rid in mates or [report_id]:
            state.store.update(rid, **extra, updated_at=_now())
    return _out(next(r for r in state.store.all() if r["id"] == report_id))
