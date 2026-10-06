import json
import math
from concurrent.futures import ThreadPoolExecutor
from typing import get_args

import pytest
from fastapi.testclient import TestClient

from app.config import CITY_BOUNDS, CITY_MARGIN
from app.db.models import Category
from app.db.store import ReportStore
from app.main import create_app
from app.routers import reports
from app.services.priority import SEVERITY

# The server only checks magic bytes, so a header plus padding is a valid "photo".
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
AYALA = {"lat": "14.5547", "lng": "121.0244"}
WEST, SOUTH, EAST, NORTH = CITY_BOUNDS
DASHBOARD = "http://localhost:5173"  # Vite's dev server


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
        ({"heading": "-1"}, JPEG, 422),
        ({"heading": "nan"}, JPEG, 422),  # would be written to reports.json as bare NaN
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


def test_photo_of_exactly_10_mb_is_taken_and_one_byte_more_is_not(client):
    ten_mb = b"\xff\xd8\xff" + b"\x00" * (10 * 1024 * 1024 - 3)
    assert post(client, ten_mb).status_code == 201
    assert post(client, ten_mb + b"\x00").status_code == 413


@pytest.mark.parametrize(
    "field, edge, beyond",
    [
        ("lat", SOUTH - CITY_MARGIN, -math.inf),
        ("lat", NORTH + CITY_MARGIN, math.inf),
        ("lng", WEST - CITY_MARGIN, -math.inf),
        ("lng", EAST + CITY_MARGIN, math.inf),
    ],
)
def test_city_edge_plus_margin_is_in_and_the_next_float_out(client, field, edge, beyond):
    # repr() round-trips, so the server parses the very float it compares with.
    assert post(client, **{field: repr(edge)}).status_code == 201
    assert post(client, **{field: repr(math.nextafter(edge, beyond))}).status_code == 422


def test_heading_takes_0_and_360(client):
    for heading in (0.0, 360.0):
        assert post(client, heading=str(heading)).json()["heading"] == heading


def test_patch_moves_updated_at_and_keeps_created_at(client, monkeypatch):
    before = post(client).json()
    monkeypatch.setattr(reports, "_now", lambda: "2030-01-01T00:00:00+00:00")
    after = client.patch(f"/reports/{before['id']}", json={"status": "verified"}).json()
    assert after["updated_at"] == "2030-01-01T00:00:00+00:00" != before["updated_at"]
    assert after["created_at"] == before["created_at"]
    assert client.get(f"/reports/{before['id']}").json() == after


def test_severity_for_every_category(client):
    expected = {
        "open_manhole": 3,
        "flooded_drain": 3,
        "pothole": 2,
        "broken_streetlight": 2,
        "blocked_sidewalk": 2,
        "other": 1,
    }
    # A new category needs a severity, or it silently ranks as low.
    assert set(expected) == set(get_args(Category)) == set(SEVERITY)
    for category, level in expected.items():
        assert post(client, category=category).json()["severity"] == level


def test_photos_are_served_as_images(client):
    for photo, kind in ((JPEG, "image/jpeg"), (PNG, "image/png")):
        assert client.get(post(client, photo).json()["photo_url"]).headers["content-type"] == kind


def test_cors_lets_the_dashboard_in_and_no_one_else(client):
    def allowed(origin):
        # The preflight a browser sends before the dashboard's PATCH.
        headers = {
            "Origin": origin,
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "content-type",
        }
        return client.options("/reports/x", headers=headers).headers.get("access-control-allow-origin")

    assert allowed(DASHBOARD) == DASHBOARD
    assert allowed("https://evil.example") is None
    get = client.get("/reports", headers={"Origin": DASHBOARD})
    assert get.headers["access-control-allow-origin"] == DASHBOARD
    get = client.get("/reports", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in get.headers


def test_store_keeps_every_report_from_many_threads(tmp_path):
    store = ReportStore(tmp_path / "reports.json")
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lambda i: store.add({"id": str(i)}), range(200)))
    on_disk = json.loads((tmp_path / "reports.json").read_text())
    assert sorted(r["id"] for r in on_disk) == sorted(str(i) for i in range(200))
    assert [p.name for p in tmp_path.iterdir()] == ["reports.json"]  # no .tmp left behind


def test_photos_cannot_escape_storage(client):
    post(client)  # so storage/reports.json exists
    # Encoded, because httpx would tidy a plain "/../" away before it reached the server.
    r = client.get("/photos/%2e%2e/reports.json")
    assert r.status_code == 404 and b"photo_url" not in r.content
