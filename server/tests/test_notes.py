"""Notes to the reporter: why a ticket was rejected (required), and what to know on confirming or resolving it
(optional). And /my-tickets: how a phone sees its own tickets, notes and all."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.routers import reports

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 64
AYALA = (14.5547, 121.0244)
FIVE_M = 5 / 111_195  # degrees of latitude


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path)


@pytest.fixture
def client(app):
    return TestClient(app)  # no lifespan: the ticket loop runs only when a test calls tick()


def post(client, lat=AYALA[0]) -> str:
    data = {"category": "pothole", "lat": repr(lat), "lng": repr(AYALA[1])}
    return client.post("/reports", data=data, files={"photo": ("a.jpg", JPEG, "image/jpeg")}).json()["id"]


def sos(client) -> str:
    data = {"lat": repr(AYALA[0]), "lng": repr(AYALA[1])}
    return client.post("/sos", data=data, files={"video": ("a.mp4", MP4, "video/mp4")}).json()["id"]


def patch(client, rid, **body):
    return client.patch(f"/reports/{rid}", json=body)


def test_a_new_report_has_no_notes(client):
    r = client.get(f"/reports/{post(client)}").json()
    assert (r["verified_note"], r["rejected_note"], r["resolved_note"]) == (None, None, None)


def test_rejecting_needs_a_reason_and_keeps_it(client):
    rid = post(client)
    for body in ({"status": "rejected"}, {"status": "rejected", "status_note": ""}, {"status": "rejected", "status_note": "   "}):
        r = patch(client, rid, **body)
        assert r.status_code == 422 and "why" in str(r.json()).lower(), body
    assert client.get(f"/reports/{rid}").json()["status"] == "open", "a refused rejection changes nothing"
    saved = patch(client, rid, status="rejected", status_note="  Duplicate of an earlier report.  ").json()
    assert (saved["status"], saved["rejected_note"]) == ("rejected", "Duplicate of an earlier report.")


def test_an_sos_needs_a_reason_to_be_rejected_too(client):
    sid = sos(client)
    assert patch(client, sid, status="rejected").status_code == 422
    assert patch(client, sid, status="rejected", status_note="A test call.").json()["rejected_note"] == "A test call."


def test_confirming_and_resolving_take_an_optional_note(client):
    rid = post(client)
    assert patch(client, rid, status="verified").json()["verified_note"] is None, "no note is fine"
    saved = patch(client, rid, status="verified", status_note="A crew has been told.").json()
    assert saved["verified_note"] == "A crew has been told."
    patch(client, rid, status="assigned", handler="Ana Reyes")
    done = patch(client, rid, status="fixed", status_note="Filled and sealed.").json()
    assert (done["status"], done["resolved_note"], done["verified_note"]) == ("fixed", "Filled and sealed.", "A crew has been told.")


def test_a_status_with_no_note_clears_the_old_one_for_that_decision(client):
    rid = post(client)
    patch(client, rid, status="rejected", status_note="Not clear what it shows.")
    patch(client, rid, status="open")
    assert patch(client, rid, status="verified", status_note="Looks real after all.").json()["verified_note"]
    again = patch(client, rid, status="rejected", status_note="Sorry, a mistake.").json()
    assert again["rejected_note"] == "Sorry, a mistake."
    reopened = patch(client, rid, status="open").json()
    assert reopened["rejected_note"] == "Sorry, a mistake.", "reopening leaves the record; the dashboard shows it only while rejected"
    assert patch(client, rid, status="verified").json()["verified_note"] is None, "confirming again with no note drops the old note"


def test_a_note_only_goes_with_confirming_rejecting_or_resolving(client):
    rid = post(client)
    for status in ("open", "assigned"):
        assert patch(client, rid, status=status, status_note="hello").status_code == 422, status
    assert client.patch(f"/reports/{rid}", json={"status_note": "hello"}).status_code == 422, "no status to go with"
    assert patch(client, rid, status="verified", status_note="x" * 281).status_code == 422


def test_every_report_of_a_ticket_gets_the_note(app, client):
    a, b = post(client), post(client, lat=AYALA[0] + FIVE_M)
    app.state.sync.tick()
    patch(client, b, status="rejected", status_note="Already fixed last week.")
    listed = {r["id"]: r for r in client.get("/reports", params={"include_rejected": "true"}).json()}
    assert listed[a]["rejected_note"] == listed[b]["rejected_note"] == "Already fixed last week."


def test_the_public_list_leaves_the_notes_out_and_the_dashboard_gets_them(client):
    rid = post(client)
    patch(client, rid, status="verified", status_note="A crew has been told.")
    assert client.get("/reports").json()[0]["verified_note"] is None
    assert client.get("/reports", params={"include_sos": "true"}).json()[0]["verified_note"] == "A crew has been told."
    assert client.get(f"/reports/{rid}").json()["verified_note"] == "A crew has been told."


def test_my_tickets_returns_the_asked_ids_in_order_with_their_notes(client):
    a, b, c = post(client), post(client), post(client)
    patch(client, b, status="verified", status_note="Seen.")
    got = client.get("/my-tickets", params={"ids": f"{c},{a}"}).json()
    assert [r["id"] for r in got] == [c, a], "in the order asked, and only those"
    assert client.get("/my-tickets", params={"ids": b}).json()[0]["verified_note"] == "Seen."


def test_my_tickets_includes_an_sos_and_a_rejected_ticket_which_the_public_list_hides(client):
    sid, rid = sos(client), post(client)
    patch(client, rid, status="rejected", status_note="Not a hazard.")
    assert client.get("/reports").json() == []
    got = {r["id"]: r for r in client.get("/my-tickets", params={"ids": f"{sid},{rid}"}).json()}
    assert got[sid]["category"] == "sos" and got[rid]["rejected_note"] == "Not a hazard."


def test_my_tickets_skips_unknown_ids_and_repeats_and_blanks(client):
    a = post(client)
    got = client.get("/my-tickets", params={"ids": f" {a} ,nope,{a},,"}).json()
    assert [r["id"] for r in got] == [a]
    assert client.get("/my-tickets").json() == []
    assert client.get("/my-tickets", params={"ids": ""}).json() == []


def test_my_tickets_asks_for_at_most_a_hundred(client):
    ids = [post(client) for _ in range(3)]
    asked = ",".join(ids + [f"fake{n}" for n in range(150)])
    assert len(client.get("/my-tickets", params={"ids": asked}).json()) == 3
    from app.routers import reports

    assert reports.MAX_MINE == 100


@pytest.mark.parametrize("on_ticket", [False, True], ids=["before the ticket loop", "on its ticket"])
def test_my_tickets_updated_at_moves_on_every_change_the_phone_tells_the_person_about(app, client, monkeypatch, on_ticket):
    """The phone's notifications rest on this: it asks /my-tickets and calls a ticket news when `updated_at` is later
    than what it knew. So a new status, a new handler and a new note must each move it, and a read must not."""
    seconds = iter(range(1_900_000_000, 1_900_100_000, 60))  # 2030, a minute apart: later than any real clock here
    iso = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds")  # noqa: E731
    monkeypatch.setattr(reports, "_now", lambda: iso(next(seconds)))
    set_status = reports.engine.set_status  # the ticket path reads the real clock: give it the same stepping one
    monkeypatch.setattr(reports.engine, "set_status", lambda db, cache, tid, status, scope, actor: set_status(db, cache, tid, status, scope, actor, now=next(seconds)))

    rid = post(client)
    if on_ticket:
        app.state.sync.tick()
        assert client.get(f"/reports/{rid}").json()["ticket_id"]

    def stamp() -> str:
        return client.get("/my-tickets", params={"ids": rid}).json()[0]["updated_at"]

    seen = stamp()
    assert stamp() == seen, "asking does not change anything"
    for what, body in [
        ("confirming, with a note", {"status": "verified", "status_note": "A crew has been told."}),
        ("assigning", {"status": "assigned", "handler": "Ana Reyes"}),
        ("a new handler alone", {"handler": "Jose Cruz"}),
        ("resolving, with a note", {"status": "fixed", "status_note": "Filled and sealed."}),
        ("reopening", {"status": "open"}),
        ("confirming again, with a new note", {"status": "verified", "status_note": "Looks real after all."}),
        ("the same status again, with a new note", {"status": "verified", "status_note": "Crew is on the way."}),
    ]:
        assert patch(client, rid, **body).status_code == 200, what
        now = stamp()
        assert now > seen, f"{what} must move updated_at, or the phone would never say so"
        seen = now
