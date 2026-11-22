import json

import httpx
import pytest

from bilderrahmen.photos import PhotosError, SynologyPhotos


class FakeNas:
    """Bildet die benötigten Teile der Synology-Web-API nach."""

    def __init__(self):
        self.logins = 0
        self.valid_sid = None
        self.calls = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        q = dict(request.url.params)
        api, method = q["api"], q["method"]
        self.calls.append((api, method, q))
        if api == "SYNO.API.Auth":
            if q["passwd"] != "pw":
                return httpx.Response(200, json={"success": False, "error": {"code": 400}})
            self.logins += 1
            self.valid_sid = f"sid{self.logins}"
            return httpx.Response(200, json={"success": True, "data": {"sid": self.valid_sid}})
        if q.get("_sid") != self.valid_sid:
            return httpx.Response(200, json={"success": False, "error": {"code": 119}})
        if api == "SYNO.Foto.Browse.Album":
            return ok({"list": [{"id": 1, "name": "Eigenes"}]})
        if api == "SYNO.Foto.Sharing.Misc":
            return ok({"list": [{"id": 9, "name": "Rahmen Oma", "passphrase": "abc"}]})
        if api == "SYNO.Foto.Browse.Item":
            assert q.get("passphrase") == "abc" or q.get("album_id") == "1"
            return ok({"list": [
                {"id": 11, "type": "photo", "additional": {"thumbnail": {"cache_key": "11_x"}}},
                {"id": 12, "type": "video"},
                {"id": 13, "type": "photo"},
            ]})
        if api == "SYNO.Foto.Download":
            assert json.loads(q["unit_id"]) == [11]
            return httpx.Response(200, content=b"JPEGDATA", headers={"content-type": "image/jpeg"})
        raise AssertionError(f"unerwartet: {api}.{method}")


def ok(data):
    return httpx.Response(200, json={"success": True, "data": data})


def client(nas, password="pw"):
    photos = SynologyPhotos("https://nas:5001", "bilderrahmen", password)
    photos._client = httpx.Client(base_url="https://nas:5001", transport=httpx.MockTransport(nas.handler))
    return photos


def test_shared_album_lists_only_photos():
    nas = FakeNas()
    assert client(nas).list_items("Rahmen Oma") == ["11", "13"]


def test_own_album_by_id():
    nas = FakeNas()
    assert client(nas).list_items("Eigenes") == ["11", "13"]


def test_download_original_with_passphrase():
    nas = FakeNas()
    photos = client(nas)
    assert photos.download("Rahmen Oma", "11") == b"JPEGDATA"
    download = [c for c in nas.calls if c[0] == "SYNO.Foto.Download"][0]
    assert download[2]["passphrase"] == "abc"


def test_relogin_after_session_expired():
    nas = FakeNas()
    photos = client(nas)
    photos.list_items("Rahmen Oma")
    nas.valid_sid = "abgelaufen"
    assert photos.list_items("Rahmen Oma") == ["11", "13"]
    assert nas.logins == 2


def test_wrong_password_raises():
    with pytest.raises(PhotosError, match="Login"):
        client(FakeNas(), password="falsch").list_items("Rahmen Oma")


def test_missing_album_raises():
    with pytest.raises(PhotosError, match="nicht gefunden"):
        client(FakeNas()).list_items("Gibt es nicht")
