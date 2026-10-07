from typing import get_args

import pytest
from fastapi.testclient import TestClient

from app.db.models import SosKind
from app.main import create_app
from app.routers import reports as reports_router
from app.services import hazards
from app.services.ticket_sync import engine

# The first bytes of a real MP4 (an `ftyp` box), then filler: the server reads the container from the bytes.
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 2048
MOV = b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00qt  " + b"\x00" * 64
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
AYALA = {"lat": 14.5547, "lng": 121.0244}


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path))


def sos(client, data=MP4, name="sos.mp4", **fields):
    return client.post("/sos", files={"video": (name, data, "video/mp4")}, data={**AYALA, **fields})


def test_an_sos_becomes_an_open_urgent_ticket_with_its_video(client):
    r = sos(client, heading="87.5")
    assert r.status_code == 201
    body = r.json()
    assert (body["category"], body["severity"], body["status"]) == ("sos", 3, "open")
    assert (body["lat"], body["lng"], body["heading"]) == (AYALA["lat"], AYALA["lng"], 87.5)
    assert body["photo_url"] == "" and body["video_url"] == f"/videos/{body['id']}.mp4"

    clip = client.get(body["video_url"])
    assert clip.status_code == 200 and clip.headers["content-type"] == "video/mp4"
    assert clip.content == MP4


def test_video_suggestion_is_visible_but_staff_still_selects_the_kind(client):
    report_id = sos(client).json()["id"]

    class StubClassifier:
        def classify(self, path):
            return "medical"

    client.app.state.sos_suggest.classifier = StubClassifier()
    client.app.state.sos_suggest.tick()
    suggested = client.get(f"/reports/{report_id}").json()
    assert suggested["suggested_sos_kind"] == "medical"
    assert suggested["sos_kind"] is None
    chosen = client.patch(f"/reports/{report_id}", json={"sos_kind": "fire_rescue"}).json()
    assert chosen["sos_kind"] == "fire_rescue"
    assert chosen["suggested_sos_kind"] == "medical"


def test_the_clip_can_be_sought_into(client):
    url = sos(client).json()["video_url"]
    part = client.get(url, headers={"Range": "bytes=4-7"})
    assert part.status_code == 206 and part.content == b"ftyp"


def test_mov_and_webm_are_kept_with_their_own_extension(client):
    assert sos(client, MOV, "a.mov").json()["video_url"].endswith(".mov")
    assert sos(client, WEBM, "a.webm").json()["video_url"].endswith(".webm")


def test_the_type_comes_from_the_bytes_not_the_filename(client):
    assert sos(client, JPEG, "sneaky.mp4").status_code == 422
    assert sos(client, MP4, "clip.jpg").json()["video_url"].endswith(".mp4")


def test_a_video_over_the_cap_is_refused(client, monkeypatch):
    monkeypatch.setattr(reports_router, "MAX_VIDEO_BYTES", 1024)
    assert sos(client).status_code == 413


def test_an_sos_from_outside_the_city_is_refused(client):
    assert sos(client, lat="40.7", lng="-74.0").status_code == 422


def test_a_video_is_required(client):
    assert client.post("/sos", data=AYALA).status_code == 422


def test_an_sos_cannot_be_filed_through_the_photo_endpoint(client):
    r = client.post("/reports", files={"photo": ("a.jpg", JPEG, "image/jpeg")}, data={**AYALA, "category": "sos"})
    assert r.status_code == 422 and "/sos" in r.json()["detail"]


def test_the_public_list_leaves_sos_out_and_the_dashboard_can_ask_for_it(client):
    client.post("/reports", files={"photo": ("a.jpg", JPEG, "image/jpeg")}, data={**AYALA, "category": "other"})
    sos_id = sos(client).json()["id"]
    assert [r["category"] for r in client.get("/reports").json()] == ["other"]
    listed = client.get("/reports", params={"include_sos": "true"}).json()
    assert [r["category"] for r in listed] == ["sos", "other"], "newest first"
    assert listed[0]["id"] == sos_id


def test_an_sos_can_still_be_read_by_id_and_moved_through_the_workflow(client):
    sos_id = sos(client).json()["id"]
    assert client.get(f"/reports/{sos_id}").json()["video_url"].startswith("/videos/")
    for status in ("verified", "assigned", "fixed"):
        assert client.patch(f"/reports/{sos_id}", json={"status": status}).json()["status"] == status


def test_an_sos_is_never_a_no_go_zone_for_routes():
    report = {"id": "s", "category": "sos", "status": "open", "lat": 14.5547, "lng": 121.0244}
    other = {**report, "id": "h", "category": "pothole"}
    assert hazards.avoid_polygons([report], []) is None
    assert len(hazards.avoid_polygons([report, other], [])["coordinates"]) == 1
    line = [[121.0244, 14.5546], [121.0244, 14.5548]]
    assert hazards.near_route(line, [report, other]) == ["h"]


def photo_report(client, **fields):
    return client.post(
        "/reports", files={"photo": ("a.jpg", JPEG, "image/jpeg")}, data={**AYALA, "category": "pothole", **fields}
    ).json()["id"]


def test_a_new_ticket_can_be_confirmed_to_verified_or_rejected_and_reopened(client):
    first, second = photo_report(client), photo_report(client)
    assert client.patch(f"/reports/{first}", json={"status": "verified"}).json()["status"] == "verified"
    assert client.patch(f"/reports/{second}", json={"status": "rejected", "status_note": "Not a real hazard."}).json()["status"] == "rejected"
    assert client.patch(f"/reports/{second}", json={"status": "open"}).json()["status"] == "open", "reopened"
    assert client.patch(f"/reports/{second}", json={"status": "nonsense"}).status_code == 422


def test_a_rejected_ticket_is_hidden_from_the_public_list_but_kept_and_still_readable(client):
    keep, drop = photo_report(client), photo_report(client)
    client.patch(f"/reports/{drop}", json={"status": "rejected", "status_note": "Not a real hazard."})
    assert [r["id"] for r in client.get("/reports").json()] == [keep]
    everything = client.get("/reports", params={"include_rejected": "true"}).json()
    assert sorted(r["id"] for r in everything) == sorted([keep, drop])
    got = client.get(f"/reports/{drop}").json()
    assert got["status"] == "rejected" and got["photo_url"], "its data is still there"
    assert client.get(got["photo_url"]).status_code == 200, "and so is its file"


def test_sos_and_rejected_filters_are_independent(client):
    sos_id = sos(client).json()["id"]
    client.patch(f"/reports/{sos_id}", json={"status": "rejected", "status_note": "Not a real hazard."})
    assert client.get("/reports", params={"include_sos": "true"}).json() == [], "a rejected SOS stays hidden"
    both = client.get("/reports", params={"include_sos": "true", "include_rejected": "true"}).json()
    assert [r["id"] for r in both] == [sos_id]
    assert client.get("/reports", params={"include_rejected": "true"}).json() == [], "rejected, but still an SOS"


def test_a_rejected_report_is_not_a_no_go_zone_until_it_is_reopened():
    report = {"id": "h", "category": "pothole", "status": "open", "lat": 14.5547, "lng": 121.0244}
    line = [[121.0244, 14.5546], [121.0244, 14.5548]]
    assert hazards.avoid_polygons([report], []) is not None
    rejected = {**report, "status": "rejected"}
    assert hazards.avoid_polygons([rejected], []) is None
    assert hazards.near_route(line, [rejected]) == []
    assert hazards.near_route(line, [{**rejected, "status": "open"}]) == ["h"]


def test_an_sos_arrives_unsorted_and_the_dashboard_sorts_it_by_who_must_respond(client):
    body = sos(client).json()
    assert body["sos_kind"] is None
    r = client.patch(f"/reports/{body['id']}", json={"sos_kind": "police"})
    assert r.status_code == 200 and (r.json()["sos_kind"], r.json()["status"]) == ("police", "open")
    assert client.get(f"/reports/{body['id']}").json()["sos_kind"] == "police"
    assert client.get("/reports", params={"include_sos": "true"}).json()[0]["sos_kind"] == "police"
    both = client.patch(f"/reports/{body['id']}", json={"sos_kind": "medical", "status": "verified"}).json()
    assert (both["sos_kind"], both["status"]) == ("medical", "verified")


def test_only_an_sos_takes_a_kind_and_only_one_of_the_three(client):
    rid = photo_report(client)
    before = client.get(f"/reports/{rid}").json()
    r = client.patch(f"/reports/{rid}", json={"sos_kind": "police", "status": "assigned"})
    assert r.status_code == 422 and r.json()["detail"] == "Only an SOS has a kind."
    assert client.get(f"/reports/{rid}").json() == before, "the status did not change either"
    sos_id = sos(client).json()["id"]
    for body in ({"sos_kind": "firefighters"}, {"sos_kind": "Police"}, {}, {"status": None}):
        assert client.patch(f"/reports/{sos_id}", json=body).status_code == 422
    assert client.get(f"/reports/{sos_id}").json()["sos_kind"] is None
    assert client.patch("/reports/nope", json={"sos_kind": "police"}).status_code == 404


def test_the_kinds_are_the_models_kinds_in_the_same_order():
    assert get_args(SosKind) == tuple(engine.sos.KINDS)  # models/ticket_sos/sos.py, as the engine uses it
