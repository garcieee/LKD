"""Who was assigned to a ticket: picked at the dashboard after Confirm, saved on the report and its ticket's reports."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app

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


def patch(client, rid, **body):
    return client.patch(f"/reports/{rid}", json=body)


def test_a_new_ticket_has_no_handler(client):
    rid = post(client)
    assert client.get(f"/reports/{rid}").json()["handler"] is None


def test_assigning_moves_to_assigned_and_saves_the_name(client):
    rid = post(client)
    patch(client, rid, status="verified")
    saved = patch(client, rid, status="assigned", handler="Ana Reyes").json()
    assert (saved["status"], saved["handler"]) == ("assigned", "Ana Reyes")
    assert client.get(f"/reports/{rid}").json()["handler"] == "Ana Reyes", "and it is still there on the next read"


def test_changing_the_handler_alone_keeps_the_status(client):
    rid = post(client)
    patch(client, rid, status="verified")
    patch(client, rid, status="assigned", handler="Ana Reyes")
    saved = patch(client, rid, handler="Jose Cruz").json()
    assert (saved["status"], saved["handler"]) == ("assigned", "Jose Cruz")


def test_a_name_is_trimmed_and_a_blank_or_huge_one_is_refused(client):
    rid = post(client)
    patch(client, rid, status="assigned")
    assert patch(client, rid, handler="  Ana Reyes  ").json()["handler"] == "Ana Reyes"
    for bad in ("", "   ", "x" * 61):
        assert patch(client, rid, handler=bad).status_code == 422, repr(bad)
    assert client.get(f"/reports/{rid}").json()["handler"] == "Ana Reyes", "refused names change nothing"


def test_a_ticket_takes_a_handler_only_once_it_is_verified(client):
    rid = post(client)  # open
    assert patch(client, rid, handler="Ana Reyes").status_code == 422
    assert patch(client, rid, status="verified", handler="Ana Reyes").status_code == 422, "verified is not assigned yet"
    assert patch(client, rid, status="rejected", handler="Ana Reyes").status_code == 422
    assert client.get(f"/reports/{rid}").json()["handler"] is None
    patch(client, rid, status="assigned")
    assert patch(client, rid, handler="Ana Reyes").status_code == 200


def test_a_resolved_ticket_keeps_its_handler(client):
    rid = post(client)
    patch(client, rid, status="assigned", handler="Ana Reyes")
    saved = patch(client, rid, status="fixed").json()
    assert (saved["status"], saved["handler"]) == ("fixed", "Ana Reyes")
    assert patch(client, rid, status="assigned").json()["handler"] == "Ana Reyes", "a reopen keeps the name to edit"


def test_every_report_of_a_ticket_gets_the_handler(app, client):
    a, b = post(client), post(client, lat=AYALA[0] + FIVE_M)
    other = post(client, lat=AYALA[0] + 0.01)  # about 1.1 km away: its own ticket
    app.state.sync.tick()
    patch(client, b, status="assigned", handler="Ana Reyes")
    listed = {r["id"]: r for r in client.get("/reports").json()}
    assert listed[a]["handler"] == listed[b]["handler"] == "Ana Reyes"
    assert listed[other]["handler"] is None
    assert [t["status"] for t in app.state.sync.db.tickets() if t["id"] == a] == ["assigned"]


def test_an_sos_takes_a_handler_too(client):
    data = {"lat": repr(AYALA[0]), "lng": repr(AYALA[1])}
    sid = client.post("/sos", data=data, files={"video": ("a.mp4", MP4, "video/mp4")}).json()["id"]
    saved = patch(client, sid, status="assigned", handler="Mark Villanueva").json()
    assert (saved["category"], saved["handler"]) == ("sos", "Mark Villanueva")
