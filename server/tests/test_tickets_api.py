"""GET and PATCH /tickets: who may see and change which tickets. Supabase is never called: auth._rows is replaced by
a table of tokens, except in the tests of _rows itself, where urlopen is."""
import base64
import io
import json
import urllib.error

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import config
from app.main import create_app
from app.services import auth

D1, D1B = (14.5547, 121.0244), (14.55474, 121.0244)  # Urdaneta, District 1, and a spot 4 m north of it
D2 = (14.5643, 121.04156)  # Guadalupe Viejo, District 2
NOWHERE = (14.5508, 121.0509)  # Bonifacio Global City, Taguig: inside the server's city box, in no district

USER_D1, USER_D2 = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
USER_CITY, USER_NOBODY = "cccccccc-cccc-4ccc-8ccc-cccccccccccc", "33333333-3333-4333-8333-333333333333"


def token(user_id):
    """The shape of a Supabase access token (header.payload.signature) for user_id. Only Supabase checks the
    signature, and it is faked here."""
    payload = base64.urlsafe_b64encode(json.dumps({"sub": user_id}).encode()).rstrip(b"=").decode()
    return f"eyJ0eXAiOiJKV1QifQ.{payload}.signature"


TOK_D1, TOK_D2, TOK_CITY, TOK_NOBODY = (token(u) for u in (USER_D1, USER_D2, USER_CITY, USER_NOBODY))
ROLES = {
    TOK_D1: [{"user_id": USER_D1, "district_id": 1, "citywide": False}],
    TOK_D2: [{"user_id": USER_D2, "district_id": 2, "citywide": False}],
    TOK_CITY: [{"user_id": USER_CITY, "district_id": None, "citywide": True}],
    TOK_NOBODY: [],  # signed in, but no row in analysts
}
TICKET_KEYS = {"id", "category", "severity", "lat", "lng", "heading", "note", "photo_url", "video_url", "status",
               "created_at", "updated_at", "priority", "band", "district_id", "reporters"}


@pytest.fixture(autouse=True)
def supabase(monkeypatch):
    """Sign-in configured, with Supabase's answer looked up in ROLES. Yields the tokens it was asked about."""
    monkeypatch.setattr(config, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    asked = []

    def rows(token, user_id):
        asked.append(token)
        if token not in ROLES:
            raise HTTPException(401, "Your sign-in is invalid or has expired.")
        return ROLES[token]

    monkeypatch.setattr(auth, "_rows", rows)
    auth._roles.clear()
    yield asked
    auth._roles.clear()


@pytest.fixture
def app(tmp_path):
    """Tickets d1 (two reports), d2 and nowhere, a day old, oldest first."""
    app = create_app(tmp_path)
    for i, (rid, (lat, lng)) in enumerate([("d1", D1), ("d1b", D1B), ("d2", D2), ("nowhere", NOWHERE)]):
        at = f"2026-10-06T0{i}:00:00+00:00"
        app.state.store.add({"id": rid, "category": "pothole", "lat": lat, "lng": lng, "heading": 10.0 * i,
                             "note": "", "photo_url": f"/photos/{rid}.jpg", "status": "open", "created_at": at,
                             "updated_at": at})
    assert app.state.sync.tick().attached == 4
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def as_(token):
    return {"Authorization": f"Bearer {token}"}


def listed(client, token):
    r = client.get("/tickets", headers=as_(token))
    assert r.status_code == 200, r.text
    return [t["id"] for t in r.json()]


def test_a_district_analyst_sees_only_their_district(client):
    assert listed(client, TOK_D1) == ["d1"]
    assert listed(client, TOK_D2) == ["d2"]


def test_citywide_sees_every_ticket_newest_first_the_one_with_no_district_included(client):
    assert listed(client, TOK_CITY) == ["nowhere", "d2", "d1"]


def test_a_ticket_has_the_report_fields_plus_its_ranking(client):
    ticket = client.get("/tickets", headers=as_(TOK_D1)).json()[0]
    assert set(ticket) == TICKET_KEYS
    assert (ticket["reporters"], ticket["district_id"], ticket["heading"], ticket["severity"]) == (2, 1, 0.0, 2)
    assert 0 <= ticket["priority"] <= 100 and ticket["band"] in ("Critical", "High", "Medium", "Low")


def test_no_token_or_a_bad_one_is_401(client):
    assert client.get("/tickets").status_code == 401
    assert client.get("/tickets", headers={"Authorization": f"Basic {TOK_D1}"}).status_code == 401
    assert client.get("/tickets", headers={"Authorization": "Bearer "}).status_code == 401
    assert client.get("/tickets", headers=as_(token("44444444-4444-4444-8444-444444444444"))).status_code == 401
    assert client.patch("/tickets/d1", json={"status": "fixed"}).status_code == 401


def test_a_token_that_is_not_a_jwt_is_401_without_asking_supabase(client, supabase):
    for bad in ("expired", "a.b", "a.e30.c", "a." + base64.urlsafe_b64encode(b'{"sub": "x,or=(citywide.is.true)"}').decode() + ".c"):
        assert client.get("/tickets", headers=as_(bad)).status_code == 401
    assert supabase == []


def test_signed_in_without_an_analyst_row_is_403(client):
    assert client.get("/tickets", headers=as_(TOK_NOBODY)).status_code == 403
    assert client.patch("/tickets/d1", headers=as_(TOK_NOBODY), json={"status": "fixed"}).status_code == 403


@pytest.mark.parametrize("answer", [
    [{"user_id": USER_CITY, "district_id": None, "citywide": True}],  # someone else's row only
    [{"user_id": USER_CITY, "district_id": None, "citywide": True},  # everyone's rows, as with RLS switched off
     {"user_id": USER_D1, "district_id": 1, "citywide": False}],
])
def test_rows_that_are_not_exactly_the_callers_own_are_refused_not_guessed(client, answer):
    ROLES[TOK_D1], kept = answer, ROLES[TOK_D1]
    try:
        assert client.get("/tickets", headers=as_(TOK_D1)).status_code == 503
        assert auth._roles == {}  # a refusal is never remembered
    finally:
        ROLES[TOK_D1] = kept


def test_sign_in_not_configured_is_503(client, monkeypatch):
    monkeypatch.setattr(config, "SUPABASE_URL", "")
    assert client.get("/tickets", headers=as_(TOK_CITY)).status_code == 503
    assert client.patch("/tickets/d1", headers=as_(TOK_CITY), json={"status": "fixed"}).status_code == 503


def test_a_change_outside_your_districts_is_404_like_a_missing_ticket_and_changes_nothing(app, client):
    before = app.state.sync.db.tickets()
    outside = client.patch("/tickets/d2", headers=as_(TOK_D1), json={"status": "fixed"})
    no_district = client.patch("/tickets/nowhere", headers=as_(TOK_D1), json={"status": "fixed"})
    missing = client.patch("/tickets/nope", headers=as_(TOK_D1), json={"status": "fixed"})
    assert outside.status_code == no_district.status_code == missing.status_code == 404
    assert outside.json() == no_district.json() == missing.json()
    assert app.state.sync.db.tickets() == before
    assert {r["status"] for r in app.state.store.all()} == {"open"}
    assert app.state.sync.db._conn.execute("select count(*) from ticket_events").fetchone()[0] == 0


def test_a_change_inside_your_district_lands_in_lakad_db_and_on_the_public_map_with_who_made_it(app, client):
    r = client.patch("/tickets/d1", headers=as_(TOK_D1), json={"status": "assigned"})
    assert r.status_code == 200 and r.json()["status"] == "assigned" and r.json()["reporters"] == 2
    assert {t["id"]: t["status"] for t in app.state.sync.db.tickets()} == {"d1": "assigned", "d2": "open", "nowhere": "open"}
    assert {r["id"]: r["status"] for r in client.get("/reports").json()} == {
        "d1": "assigned", "d1b": "assigned", "d2": "open", "nowhere": "open"}
    events = app.state.sync.db._conn.execute("select ticket_id, actor, from_status, to_status from ticket_events").fetchall()
    assert [tuple(e) for e in events] == [("d1", USER_D1, "open", "assigned")]


def test_citywide_may_change_a_ticket_with_no_district(client):
    r = client.patch("/tickets/nowhere", headers=as_(TOK_CITY), json={"status": "rejected"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"


def test_an_unknown_status_is_422(client):
    assert client.patch("/tickets/d1", headers=as_(TOK_D1), json={"status": "done"}).status_code == 422


def test_the_dashboard_may_send_its_token_across_origins(client):
    headers = {"Origin": "http://localhost:5173", "Access-Control-Request-Method": "PATCH",
               "Access-Control-Request-Headers": "authorization,content-type"}
    r = client.options("/tickets/d1", headers=headers)
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "authorization" in r.headers["access-control-allow-headers"].lower()


def test_a_role_is_remembered_for_a_minute(client, supabase):
    listed(client, TOK_D1)
    listed(client, TOK_D1)
    assert supabase == [TOK_D1]


# ---- the Supabase call itself -------------------------------------------------------------------------------------

class Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_rows_asks_supabase_for_the_callers_own_row_with_the_publishable_key_and_their_token(monkeypatch):
    monkeypatch.undo()  # the real _rows, not the table above
    monkeypatch.setattr(config, "SUPABASE_URL", "https://example.supabase.co/")
    monkeypatch.setattr(config, "SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    seen = {}

    def urlopen(request, timeout):
        seen.update(url=request.full_url, method=request.get_method(), headers=dict(request.header_items()), timeout=timeout)
        return Answer(json.dumps(ROLES[TOK_D1]).encode())

    monkeypatch.setattr(auth.urllib.request, "urlopen", urlopen)
    assert auth._rows(TOK_D1, USER_D1) == ROLES[TOK_D1]
    assert seen["url"] == ("https://example.supabase.co/rest/v1/analysts?select=user_id,district_id,citywide"
                           f"&user_id=eq.{USER_D1}")
    assert seen["method"] == "GET" and seen["timeout"] == auth.TIMEOUT_S
    assert seen["headers"]["Apikey"] == "sb_publishable_test" and seen["headers"]["Authorization"] == f"Bearer {TOK_D1}"


@pytest.mark.parametrize("failure, code", [
    (urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(b'{"message":"JWT expired"}')), 401),
    (urllib.error.HTTPError("u", 403, "Forbidden", {}, io.BytesIO(b"{}")), 403),
    (urllib.error.HTTPError("u", 500, "Server Error", {}, io.BytesIO(b"{}")), 503),
    (urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b"{}")), 503),
    (urllib.error.URLError("no route to host"), 503),
    (TimeoutError("timed out"), 503),
])
def test_rows_fails_closed_and_never_repeats_the_token(monkeypatch, failure, code):
    monkeypatch.undo()
    monkeypatch.setattr(config, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")

    def urlopen(request, timeout):
        raise failure

    monkeypatch.setattr(auth.urllib.request, "urlopen", urlopen)
    with pytest.raises(HTTPException) as caught:
        auth._rows("secret-token", USER_D1)
    assert caught.value.status_code == code
    assert "secret-token" not in caught.value.detail and "sb_publishable_test" not in caught.value.detail


def test_an_answer_that_is_not_a_list_of_rows_fails_closed(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(config, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setattr(auth.urllib.request, "urlopen", lambda request, timeout: Answer(b'{"message": "odd"}'))
    with pytest.raises(HTTPException) as caught:
        auth._rows(TOK_D1, USER_D1)
    assert caught.value.status_code == 503
