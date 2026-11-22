"""HTTP-Schnittstelle für die Rahmen (öffentlich über cloudflared) und Status (nur LAN-Port)."""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request, Response

from .config import Config, Device
from .photos import PhotoSource
from .render import preview_png, render
from .schedule import sleep_seconds
from .selection import StateStore, pick_for_day

log = logging.getLogger("bilderrahmen")

# Die Firmware im Ordner firmware/ schickt diese Header bei jedem Abruf mit
STATUS_HEADERS = {
    "x-frame-battery-millivolts": "battery_mv",
    "x-frame-wifi-rssi": "rssi",
    "x-frame-wakeup": "wakeup",
    "x-frame-firmware-version": "firmware",
}
SLEEP_HEADER = "X-Sleep-Seconds"


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=401, headers={"WWW-Authenticate": 'Basic realm="bilderrahmen"'})


def _check_auth(request: Request, config: Config, device_id: str) -> Device:
    device = config.devices.get(device_id)
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("basic "):
        raise _unauthorized()
    try:
        user, _, password = base64.b64decode(header[6:], validate=True).decode("utf-8").partition(":")
    except (binascii.Error, UnicodeDecodeError):
        raise _unauthorized()
    # Immer beide Vergleiche ausführen, damit die Antwortzeit nichts über gültige Geräte verrät
    expected = device.password if device else "x" * 32
    ok_user = hmac.compare_digest(user.encode(), device_id.encode())
    ok_pw = hmac.compare_digest(password.encode(), expected.encode())
    if device is None or not (ok_user and ok_pw):
        raise _unauthorized()
    return device


def create_app(
    config: Config,
    source: PhotoSource,
    data_dir: Path,
    status_port: int | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    store = StateStore(data_dir / "state.json")
    cache_dir = data_dir / "cache"
    zone = ZoneInfo(config.timezone)

    def record_status(device: Device, request: Request, served: str) -> None:
        info = {field: request.headers[h] for h, field in STATUS_HEADERS.items() if h in request.headers}
        info["last_seen"] = now().isoformat()
        info["served"] = served
        with store.lock:
            store.device(device.id)["status"] = info
            store.save()
        log.info(json.dumps({"event": "frame_request", "device": device.id, **info}))

    def daily_image(device: Device) -> tuple[str, Path]:
        day = now().astimezone(zone).date()
        items = source.list_items(device.album)
        with store.lock:
            state = store.device(device.id)
            item = pick_for_day(state, items, day)
            state["album_count"] = len(items)
            store.save()
        if item is None:
            raise HTTPException(status_code=404, detail="Album ist leer")
        path = cache_dir / device.id / f"{day.isoformat()}_{item}.bin"
        if not path.exists():
            raw = render(source.download(device.album, item), device.orientation)
            path.parent.mkdir(parents=True, exist_ok=True)
            for old in path.parent.glob("*.bin"):
                old.unlink()
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(raw)
            tmp.replace(path)
            log.info(json.dumps({"event": "rendered", "device": device.id, "item": item, "day": day.isoformat()}))
        return f'"{day.isoformat()}-{item}"', path

    @app.get("/frame/{device_id}/image.bin")
    def image(device_id: str, request: Request) -> Response:
        device = _check_auth(request, config, device_id)
        headers = {SLEEP_HEADER: str(sleep_seconds(now(), device.wake, config.timezone))}
        try:
            etag, path = daily_image(device)
        except HTTPException:
            record_status(device, request, "error")
            raise
        except Exception:
            log.exception("Tagesbild für %s fehlgeschlagen", device.id)
            record_status(device, request, "error")
            # Rahmen behält das alte Bild; die Firmware versucht es später erneut
            raise HTTPException(status_code=503, detail="Bild nicht verfügbar")
        headers["ETag"] = etag
        headers["Cache-Control"] = "no-cache"
        if request.headers.get("if-none-match") == etag:
            record_status(device, request, "not_modified")
            return Response(status_code=304, headers=headers)
        record_status(device, request, "image")
        return Response(content=path.read_bytes(), media_type="application/octet-stream", headers=headers)

    def require_lan_port(request: Request) -> None:
        # Nur über den LAN-Port erreichbar; cloudflared zeigt ausschließlich auf den Rahmen-Port
        server = request.scope.get("server")
        if status_port is None or not server or server[1] != status_port:
            raise HTTPException(status_code=404)

    @app.get("/preview/{device_id}.png")
    def preview(device_id: str, request: Request) -> Response:
        """Zeigt das heutige Bild so, wie es ungefähr auf dem Panel aussieht (zum Abstimmen der Farben)."""
        require_lan_port(request)
        device = config.devices.get(device_id)
        if device is None:
            raise HTTPException(status_code=404)
        _, path = daily_image(device)
        return Response(content=preview_png(path.read_bytes()), media_type="image/png")

    @app.get("/status")
    def status(request: Request) -> dict:
        require_lan_port(request)
        with store.lock:
            return {
                dev_id: {
                    "album": dev.album,
                    "album_count": store.device(dev_id).get("album_count"),
                    "current": store.device(dev_id).get("current"),
                    "remaining_in_round": len(store.device(dev_id).get("bag", [])),
                    "status": store.device(dev_id).get("status"),
                }
                for dev_id, dev in config.devices.items()
            }

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    return app
