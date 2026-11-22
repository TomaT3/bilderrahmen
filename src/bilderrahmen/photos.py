"""Zugriff auf Synology Photos über die Web-API (eigener Nur-Lese-Benutzer)."""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

log = logging.getLogger(__name__)

# Fehlercodes, bei denen die Session abgelaufen oder ungültig ist
_SESSION_ERRORS = {106, 107, 119}


class PhotosError(RuntimeError):
    pass


class PhotoSource(Protocol):
    def list_items(self, album: str) -> list[str]: ...

    def download(self, album: str, item_id: str) -> bytes: ...


@dataclass
class _Album:
    id: int
    passphrase: str | None  # gesetzt bei Alben, die mit dem Benutzer geteilt wurden


class SynologyPhotos:
    """Liest Alben des Benutzers und mit ihm geteilte Alben; nur Fotos, keine Videos."""

    def __init__(self, base_url: str, user: str, password: str, verify: bool | str = True, timeout: float = 60):
        self._client = httpx.Client(base_url=base_url.rstrip("/"), verify=verify, timeout=timeout)
        self._user = user
        self._password = password
        self._sid: str | None = None
        self._lock = threading.Lock()
        self._thumb_keys: dict[str, str] = {}

    # --- Low level -------------------------------------------------------------------------------------------
    def _login(self) -> None:
        resp = self._client.get(
            "/webapi/entry.cgi",
            params={
                "api": "SYNO.API.Auth",
                "version": "6",
                "method": "login",
                "account": self._user,
                "passwd": self._password,
                "session": "bilderrahmen",
                "format": "sid",
            },
        )
        data = resp.json()
        if not data.get("success"):
            raise PhotosError(f"Login fehlgeschlagen (Code {data.get('error', {}).get('code')})")
        self._sid = data["data"]["sid"]

    def _request(self, api: str, method: str, version: int, raw: bool = False, **params: Any) -> Any:
        with self._lock:
            for attempt in (1, 2):
                if self._sid is None:
                    self._login()
                query = {"api": api, "method": method, "version": str(version), "_sid": self._sid}
                for key, value in params.items():
                    query[key] = json.dumps(value) if isinstance(value, (list, dict)) else str(value)
                resp = self._client.get("/webapi/entry.cgi", params=query)
                is_json = resp.headers.get("content-type", "").startswith("application/json")
                if raw and resp.status_code == 200 and not is_json:
                    return resp.content
                data = resp.json()
                if data.get("success"):
                    return data.get("data")
                code = data.get("error", {}).get("code")
                if code in _SESSION_ERRORS and attempt == 1:
                    self._sid = None
                    continue
                raise PhotosError(f"{api}.{method} fehlgeschlagen (Code {code})")
        raise PhotosError("unerreichbar")  # pragma: no cover

    def _paged(self, api: str, method: str, version: int, key: str = "list", **params: Any) -> list[dict]:
        out: list[dict] = []
        offset, limit = 0, 500
        while True:
            data = self._request(api, method, version, offset=offset, limit=limit, **params)
            chunk = data.get(key, [])
            out.extend(chunk)
            if len(chunk) < limit:
                return out
            offset += limit

    # --- Alben und Bilder ------------------------------------------------------------------------------------
    def _find_album(self, name: str) -> _Album:
        for album in self._paged("SYNO.Foto.Browse.Album", "list", 2):
            if album.get("name") == name:
                return _Album(id=album["id"], passphrase=None)
        for album in self._paged("SYNO.Foto.Sharing.Misc", "list_shared_with_me_album", 2):
            if album.get("name") == name:
                return _Album(id=album["id"], passphrase=album.get("passphrase"))
        raise PhotosError(f"Album {name!r} nicht gefunden (weder eigenes noch geteiltes)")

    def _album_params(self, album: _Album) -> dict[str, Any]:
        return {"passphrase": album.passphrase} if album.passphrase else {"album_id": album.id}

    def list_items(self, album: str) -> list[str]:
        alb = self._find_album(album)
        items = self._paged(
            "SYNO.Foto.Browse.Item", "list", 1, additional=["thumbnail"], **self._album_params(alb)
        )
        ids = []
        for item in items:
            if item.get("type", "photo") != "photo":
                continue
            item_id = str(item["id"])
            thumb = (item.get("additional") or {}).get("thumbnail") or {}
            if thumb.get("cache_key"):
                self._thumb_keys[item_id] = thumb["cache_key"]
            ids.append(item_id)
        return ids

    def download(self, album: str, item_id: str) -> bytes:
        alb = self._find_album(album)
        extra = {"passphrase": alb.passphrase} if alb.passphrase else {}
        try:
            return self._request("SYNO.Foto.Download", "download", 2, raw=True, unit_id=[int(item_id)], **extra)
        except (PhotosError, ValueError) as exc:
            # Rückfall: größtes Vorschaubild (lange Seite ca. 1280 px), besser als gar kein Bild
            cache_key = self._thumb_keys.get(item_id)
            if not cache_key:
                raise
            log.warning("Original nicht ladbar (%s), nehme Vorschaubild", exc)
            return self._request(
                "SYNO.Foto.Thumbnail", "get", 2, raw=True,
                id=int(item_id), cache_key=cache_key, type="unit", size="xl", **extra,
            )
