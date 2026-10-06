import pytest
from fastapi.testclient import TestClient

from app.main import create_app

# The server only checks magic bytes, so a header plus padding is a valid "photo".
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
AYALA = {"lat": "14.5547", "lng": "121.0244"}


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path))


def post(client, photo=JPEG, **fields):
    data = {"category": "pothole", **AYALA, **fields}
    return client.post("/reports", data=data, files={"photo": ("snap.jpg", photo, "image/jpeg")})


def test_report_round_trip(client, tmp_path):
    r = post(client, heading="87.5", note="  deep, by the jeepney stop  ")
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "open" and body["severity"] == 2 and body["heading"] == 87.5
    assert body["note"] == "deep, by the jeepney stop"
    assert client.get(body["photo_url"]).content == JPEG
    assert client.get("/reports").json() == [body]
    assert client.get(f"/reports/{body['id']}").json() == body
    # It is on disk as JSON, so a fresh server sees it.
    assert TestClient(create_app(tmp_path)).get("/reports").json() == [body]


def test_newest_first_and_png(client):
    first = post(client).json()
    second = post(client, PNG, category="open_manhole").json()
    assert second["photo_url"].endswith(".png") and second["severity"] == 3
    assert first["heading"] is None
    assert [r["id"] for r in client.get("/reports").json()] == [second["id"], first["id"]]


def test_status_workflow(client):
    rid = post(client).json()["id"]
    r = client.patch(f"/reports/{rid}", json={"status": "assigned"})
    assert r.status_code == 200 and r.json()["status"] == "assigned"
    assert client.get(f"/reports/{rid}").json()["status"] == "assigned"
    assert client.patch(f"/reports/{rid}", json={"status": "done"}).status_code == 422
    assert client.patch("/reports/nope", json={"status": "fixed"}).status_code == 404
    assert client.get("/reports/nope").status_code == 404


@pytest.mark.parametrize(
    "fields, photo, code",
    [
        ({"category": "ufo"}, JPEG, 422),
        ({"lat": "14.6500"}, JPEG, 422),  # Quezon City
        ({"lng": "nan"}, JPEG, 422),
        ({"heading": "400"}, JPEG, 422),
        ({"note": "x" * 281}, JPEG, 422),
        ({}, b"GIF89a" + b"\x00" * 64, 422),  # neither JPEG nor PNG
        ({}, b"", 422),
        ({}, b"\xff\xd8\xff" + b"\x00" * (10 * 1024 * 1024), 413),
    ],
)
def test_rejects_bad_input_and_saves_nothing(client, tmp_path, fields, photo, code):
    assert post(client, photo, **fields).status_code == code
    assert client.get("/reports").json() == []
    assert list((tmp_path / "photos").iterdir()) == []


def test_photos_cannot_escape_storage(client):
    post(client)  # so storage/reports.json exists
    # Encoded, because httpx would tidy a plain "/../" away before it reached the server.
    r = client.get("/photos/%2e%2e/reports.json")
    assert r.status_code == 404 and b"photo_url" not in r.content
