import base64
import io
from datetime import datetime, time, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from bilderrahmen.app import create_app
from bilderrahmen.config import Config, Device

PW = "geheim-geheim-geheim"


class FakePhotos:
    def __init__(self, items):
        self.items = items
        self.downloads = 0

    def list_items(self, album):
        assert album == "Rahmen Oma"
        return list(self.items)

    def download(self, album, item_id):
        self.downloads += 1
        buf = io.BytesIO()
        Image.new("RGB", (1200, 1600), (30, 90, 200)).save(buf, "JPEG")
        return buf.getvalue()


class Clock:
    def __init__(self):
        self.value = datetime(2026, 11, 22, 5, 0, tzinfo=timezone.utc)  # 06:00 Berlin

    def __call__(self):
        return self.value


def auth(user="oma", pw=PW):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()}


@pytest.fixture
def env(tmp_path):
    config = Config(devices={"oma": Device(id="oma", album="Rahmen Oma", password=PW, wake=time(6, 0))})
    photos = FakePhotos(["1", "2", "3"])
    clock = Clock()
    app = create_app(config, photos, tmp_path, status_port=8081, now=clock)
    return TestClient(app), photos, clock


@pytest.mark.parametrize(
    "headers",
    [{}, auth(pw="falsch-falsch-falsch"), auth(user="opa"), {"Authorization": "Basic !!!"}, {"Authorization": "Bearer x"}],
)
def test_image_requires_auth(env, headers):
    client, photos, _ = env
    resp = client.get("/frame/oma/image.bin", headers=headers)
    assert resp.status_code == 401
    assert photos.downloads == 0


def test_unknown_device_is_401(env):
    client, _, _ = env
    assert client.get("/frame/opa/image.bin", headers=auth(user="opa")).status_code == 401


def test_image_served_with_sleep_and_etag(env):
    client, _, _ = env
    resp = client.get("/frame/oma/image.bin", headers=auth())
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/octet-stream"
    assert len(resp.content) == 192_000
    assert resp.headers["ETag"].startswith('"2026-11-22-')
    assert int(resp.headers["X-Sleep-Seconds"]) == 86400  # 06:00 -> morgen 06:00


def test_same_day_etag_gives_304_and_no_rerender(env):
    client, photos, _ = env
    first = client.get("/frame/oma/image.bin", headers=auth())
    resp = client.get("/frame/oma/image.bin", headers={**auth(), "If-None-Match": first.headers["ETag"]})
    assert resp.status_code == 304
    assert "X-Sleep-Seconds" in resp.headers
    assert photos.downloads == 1


def test_next_day_new_image(env):
    client, _, clock = env
    first = client.get("/frame/oma/image.bin", headers=auth()).headers["ETag"]
    clock.value = datetime(2026, 11, 23, 5, 0, tzinfo=timezone.utc)
    resp = client.get("/frame/oma/image.bin", headers={**auth(), "If-None-Match": first})
    assert resp.status_code == 200
    assert resp.headers["ETag"] != first
    assert resp.headers["ETag"].split("-")[-1] != first.split("-")[-1]


def test_empty_album_is_404(env):
    client, photos, _ = env
    photos.items = []
    assert client.get("/frame/oma/image.bin", headers=auth()).status_code == 404


def test_source_failure_is_503(env):
    client, photos, _ = env

    def boom(album):
        raise RuntimeError("NAS weg")

    photos.list_items = boom
    assert client.get("/frame/oma/image.bin", headers=auth()).status_code == 503


def test_status_headers_recorded_and_status_only_on_lan_port(env, tmp_path):
    client, _, _ = env
    client.get(
        "/frame/oma/image.bin",
        headers={**auth(), "X-Frame-Battery-Millivolts": "3920", "X-Frame-WiFi-RSSI": "-61"},
    )
    # TestClient meldet sich als Server "testserver:80" -> nicht der Status-Port
    assert client.get("/status").status_code == 404
    lan = TestClient(client.app, base_url="http://nas:8081")
    status = lan.get("/status").json()["oma"]
    assert status["status"]["battery_mv"] == "3920"
    assert status["status"]["rssi"] == "-61"
    assert status["album_count"] == 3


def test_preview_only_on_lan_port(env):
    client, _, _ = env
    assert client.get("/preview/oma.png").status_code == 404
    lan = TestClient(client.app, base_url="http://nas:8081")
    resp = lan.get("/preview/oma.png")
    assert resp.status_code == 200
    img = Image.open(io.BytesIO(resp.content))
    assert img.size == (800, 480)


def test_openpaper_endpoints_are_gone(env):
    client, _, _ = env
    assert client.get("/frame/oma/image.bmp", headers=auth()).status_code == 404
    assert client.get("/frame/oma/settings.json", headers=auth()).status_code == 404
