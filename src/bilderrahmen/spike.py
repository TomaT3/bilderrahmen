"""Prüft den Zugriff auf Synology Photos: `python -m bilderrahmen.spike "<Albumname>"`.

Nutzt SYNO_URL, SYNO_USER, SYNO_PASSWORD (und optional SYNO_VERIFY_TLS=false). Listet das Album, lädt das erste
Foto, rechnet es um und legt Original, BMP und Vorschau im aktuellen Ordner ab.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .photos import SynologyPhotos
from .render import preview_png, render


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    album = sys.argv[1]
    verify = os.environ.get("SYNO_VERIFY_TLS", "true").lower() != "false"
    photos = SynologyPhotos(os.environ["SYNO_URL"], os.environ["SYNO_USER"], os.environ["SYNO_PASSWORD"], verify=verify)
    items = photos.list_items(album)
    print(f"Album {album!r}: {len(items)} Fotos")
    if not items:
        return 1
    original = photos.download(album, items[0])
    print(f"Foto {items[0]}: {len(original)} Bytes geladen")
    bmp = render(original)
    Path("spike_original.bin").write_bytes(original)
    Path("spike.bmp").write_bytes(bmp)
    Path("spike_preview.png").write_bytes(preview_png(bmp))
    print("Geschrieben: spike_original.bin, spike.bmp, spike_preview.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
