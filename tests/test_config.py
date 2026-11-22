from datetime import time

import pytest

from bilderrahmen.config import load_config

YAML = """
timezone: Europe/Berlin
devices:
  - id: oma-opa
    album: Rahmen Oma+Opa
    orientation: landscape
    wake: "07:30"
"""


def write(tmp_path, text=YAML):
    path = tmp_path / "devices.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_device_with_password_from_env(tmp_path):
    cfg = load_config(write(tmp_path), {"FRAME_PASSWORD_OMA_OPA": "x" * 20})
    dev = cfg.devices["oma-opa"]
    assert dev.album == "Rahmen Oma+Opa"
    assert dev.orientation == "landscape"
    assert dev.wake == time(7, 30)
    assert dev.password == "x" * 20


def test_missing_or_short_password_rejected(tmp_path):
    with pytest.raises(ValueError, match="FRAME_PASSWORD_OMA_OPA"):
        load_config(write(tmp_path), {"FRAME_PASSWORD_OMA_OPA": "kurz"})


def test_invalid_id_rejected(tmp_path):
    with pytest.raises(ValueError, match="Geräte-ID"):
        load_config(write(tmp_path, "devices:\n  - id: Oma/../x\n    album: a\n"), {})


def test_orientation_defaults_to_landscape(tmp_path):
    cfg = load_config(write(tmp_path, "devices:\n  - id: oma\n    album: a\n"), {"FRAME_PASSWORD_OMA": "x" * 20})
    assert cfg.devices["oma"].orientation == "landscape"
