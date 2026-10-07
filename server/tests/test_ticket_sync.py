"""The ticket loop inside the server: a temp store and a temp lakad.db, driven one turn at a time with tick()."""
import sqlite3
import time
from typing import get_args

import pytest
from fastapi.testclient import TestClient

from app import config
from app.db.models import Category
from app.main import create_app
from app.services.ticket_sync import engine, settings

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 64
AYALA = (14.5547, 121.0244)  # Urdaneta, District 1
FIVE_M = 5 / 111_195  # degrees of latitude


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path)


@pytest.fixture
def client(app):
    return TestClient(app)  # not a context manager: the loop does not start, tick() drives it


def post(client, lat=AYALA[0], lng=AYALA[1], category="pothole") -> dict:
    data = {"category": category, "lat": repr(lat), "lng": repr(lng)}
    return client.post("/reports", data=data, files={"photo": ("a.jpg", JPEG, "image/jpeg")}).json()


def sos(client) -> dict:
    data = {"lat": repr(AYALA[0]), "lng": repr(AYALA[1])}
    return client.post("/sos", data=data, files={"video": ("a.mp4", MP4, "video/mp4")}).json()


def test_a_tick_puts_reports_metres_apart_on_one_ticket(app, client):
    a, b = post(client), post(client, lat=AYALA[0] + FIVE_M)
    far = post(client, lat=AYALA[0] + 0.01)  # about 1.1 km north
    assert client.get("/reports").json()[0]["ticket_id"] is None  # nothing until the loop has run
    stats = app.state.sync.tick()
    assert stats.attached == 3 and stats.failed == []
    listed = {r["id"]: r for r in client.get("/reports").json()}
    assert listed[a["id"]]["ticket_id"] == listed[b["id"]]["ticket_id"] == a["id"]
    assert listed[far["id"]]["ticket_id"] == far["id"]
    assert listed[b["id"]]["district_id"] == 1 and 0 < listed[b["id"]]["priority"] <= 100
    assert listed[a["id"]]["priority"] == listed[b["id"]]["priority"] and listed[a["id"]]["band"]
    rows = {t["id"]: t for t in app.state.sync.db.tickets()}
    assert set(rows) == {a["id"], far["id"]} and rows[a["id"]]["reporters"] == 2
    assert app.state.sync.tick().attached == 0  # a second turn finds nothing to do


def test_a_change_on_one_row_goes_to_its_ticket_and_every_report_of_it(app, client):
    a, b = post(client), post(client, lat=AYALA[0] + FIVE_M)
    app.state.sync.tick()
    assert client.patch(f"/reports/{b['id']}", json={"status": "assigned"}).json()["status"] == "assigned"
    assert {r["id"]: r["status"] for r in client.get("/reports").json()} == {a["id"]: "assigned", b["id"]: "assigned"}
    assert [t["status"] for t in app.state.sync.db.tickets()] == ["assigned"]
    events = app.state.sync.db._conn.execute("select ticket_id, actor, from_status, to_status from ticket_events")
    assert [tuple(e) for e in events] == [(a["id"], None, "open", "assigned")]


def test_an_sos_sorted_after_the_loop_has_its_kind_on_the_ticket_too(app, client):
    sid = sos(client)["id"]
    app.state.sync.tick()
    saved = client.patch(f"/reports/{sid}", json={"sos_kind": "police", "status": "verified"}).json()
    assert (saved["sos_kind"], saved["status"]) == ("police", "verified")
    t = app.state.sync.db.tickets()[0]
    assert (t["sos_kind"], t["status"]) == ("police", "verified")


def test_every_category_the_server_takes_gets_its_ticket(app, client):
    # The server's categories and lakad.db's category check are written separately: a drift would 201 the report
    # and then fail the loop quietly, three times.
    ids = [post(client, category=c)["id"] for c in get_args(Category) if c != "sos"] + [sos(client)["id"]]
    stats = app.state.sync.tick()
    assert stats.failed == [] and stats.attached == len(ids)


def test_a_failing_save_counts_a_try_and_after_three_the_report_is_skipped(app, client, monkeypatch):
    rid = post(client)["id"]

    def broken(*args):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(app.state.sync.db, "save", broken)
    for _ in range(settings.SYNC_MAX_TRIES):
        assert app.state.sync.tick().failed == [rid]
    assert app.state.sync.tick().failed == []  # gave up: it no longer blocks or slows the queue
    report = app.state.store.all()[0]
    assert report["sync_tries"] == settings.SYNC_MAX_TRIES and "disk I/O error" in report["sync_error"]
    assert "ticket_id" not in report and app.state.sync.db.tickets() == []
    listed = client.get("/reports").json()  # the extra cache keys never leak into the API
    assert len(listed) == 1 and "sync_error" not in listed[0] and listed[0]["ticket_id"] is None
    health = client.get("/health").json()
    assert health["ok"] and health["tickets"]["pending"] == 0 and health["tickets"]["failed"] == 1
    assert health["tickets"]["last_run"]


def test_health_counts_reports_waiting_for_the_loop(app, client):
    post(client)
    assert client.get("/health").json()["tickets"] == {"pending": 1, "failed": 0, "last_run": None}
    app.state.sync.tick()
    assert client.get("/health").json()["tickets"]["pending"] == 0


def test_reports_of_a_ticket_closed_long_ago_leave_reports_json_and_stay_in_lakad_db(app, client):
    rid = post(client)["id"]
    app.state.sync.tick()
    engine.set_status(app.state.sync.db, app.state.store, rid, "fixed", "all", "analyst-1",
                      now=time.time() - (settings.CACHE_KEEP_DAYS + 1) * 86_400)
    assert app.state.sync.tick().pruned == 1
    assert client.get("/reports").json() == [] and app.state.sync.db.tickets()[0]["id"] == rid


def test_the_loop_runs_inside_the_lifespan_only(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SYNC_EVERY_S", 0.05)
    monkeypatch.setattr(config, "TICKETS_SYNC", True)
    app = create_app(tmp_path)
    rid = post(TestClient(app))["id"]
    time.sleep(0.3)
    assert "ticket_id" not in app.state.store.all()[0]  # a plain TestClient never starts it
    with TestClient(app):
        deadline = time.monotonic() + 10
        while not app.state.store.all()[0].get("ticket_id") and time.monotonic() < deadline:
            time.sleep(0.05)
    assert app.state.store.all()[0]["ticket_id"] == rid


def test_the_loop_stays_off_when_tickets_sync_is_off(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SYNC_EVERY_S", 0.05)
    monkeypatch.setattr(config, "TICKETS_SYNC", False)
    app = create_app(tmp_path)
    with TestClient(app) as client:
        post(client)
        time.sleep(0.3)
    assert "ticket_id" not in app.state.store.all()[0]


def test_an_sos_sorted_before_the_loop_reaches_it_gets_its_ticket_with_that_kind(app, client):
    sos_id = sos(client)["id"]
    assert client.patch(f"/reports/{sos_id}", json={"sos_kind": "fire_rescue"}).status_code == 200
    assert app.state.sync.tick().attached == 1
    t = app.state.sync.db.tickets()[0]
    assert (t["id"], t["sos_kind"], t["priority"], t["band"]) == (sos_id, "fire_rescue", 100.0, "Critical")


def test_reports_change_and_list_sos_and_rejected_ones_only_when_asked(client):
    rid = post(client)["id"]
    sos_id = sos(client)["id"]
    assert client.patch(f"/reports/{rid}", json={"status": "rejected", "status_note": "Not a real hazard."}).json()["status"] == "rejected"
    assert client.get("/reports").json() == []
    listed = client.get("/reports", params={"include_sos": "true", "include_rejected": "true"}).json()
    assert [r["id"] for r in listed] == [sos_id, rid]
