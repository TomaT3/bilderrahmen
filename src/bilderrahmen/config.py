"""Gerätekonfiguration aus devices.yaml, Geheimnisse aus Umgebungsvariablen."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from typing import Mapping

import yaml

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


@dataclass(frozen=True)
class Device:
    id: str
    album: str
    password: str
    orientation: str = "portrait"  # portrait (1200x1600) oder landscape (Rahmen hängt quer)
    wake: time = time(6, 0)
    settings: Mapping[str, object] = field(default_factory=dict)  # zusätzliche Felder für settings.json


@dataclass(frozen=True)
class Config:
    devices: Mapping[str, Device]
    timezone: str = "Europe/Berlin"
    public_url: str = ""  # z. B. https://rahmen.example.de, für downloadUrl in settings.json


def password_env_name(device_id: str) -> str:
    return "FRAME_PASSWORD_" + device_id.upper().replace("-", "_")


def load_config(path: Path, env: Mapping[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    devices: dict[str, Device] = {}
    for item in raw.get("devices", []):
        dev_id = str(item["id"])
        if not _ID_RE.match(dev_id):
            raise ValueError(f"Ungültige Geräte-ID {dev_id!r} (erlaubt: a-z, 0-9, -)")
        if dev_id in devices:
            raise ValueError(f"Geräte-ID {dev_id!r} doppelt")
        orientation = item.get("orientation", "portrait")
        if orientation not in ("portrait", "landscape"):
            raise ValueError(f"{dev_id}: orientation muss portrait oder landscape sein")
        env_name = password_env_name(dev_id)
        password = env.get(env_name, "")
        if len(password) < 16:
            raise ValueError(f"{dev_id}: {env_name} fehlt oder ist kürzer als 16 Zeichen")
        hh, mm = str(item.get("wake", "06:00")).split(":")
        devices[dev_id] = Device(
            id=dev_id,
            album=str(item["album"]),
            password=password,
            orientation=orientation,
            wake=time(int(hh), int(mm)),
            settings=dict(item.get("settings", {})),
        )
    return Config(
        devices=devices,
        timezone=str(raw.get("timezone", "Europe/Berlin")),
        public_url=str(env.get("PUBLIC_URL", raw.get("public_url", ""))).rstrip("/"),
    )
