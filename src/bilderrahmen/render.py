"""Foto für ein Spectra-6-Panel (13,3", 1200x1600) aufbereiten und als 4-Bit-BMP ausgeben."""

from __future__ import annotations

import io
import struct

from PIL import Image, ImageEnhance, ImageOps

try:  # HEIC-Fotos vom iPhone
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

PANEL_W, PANEL_H = 1200, 1600  # nativ Hochformat

# Palettenindex = Farbcode des Spectra-6-Controllers (4 ist unbelegt). Liest die Firmware die Indizes direkt,
# stimmen sie; liest sie die RGB-Werte der Farbtabelle, stimmen diese ebenfalls.
# "measured" sind die Farben, wie das Panel sie tatsächlich zeigt; gegen sie wird gedithert.
PALETTE = {
    0: ("black", (0, 0, 0), (25, 30, 33)),
    1: ("white", (255, 255, 255), (232, 232, 232)),
    2: ("yellow", (255, 255, 0), (239, 222, 68)),
    3: ("red", (255, 0, 0), (178, 19, 24)),
    5: ("blue", (0, 0, 255), (33, 87, 186)),
    6: ("green", (0, 255, 0), (18, 95, 32)),
}
USED_INDICES = tuple(PALETTE)


def _fit(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Gleiche Ausrichtung: auf Format zuschneiden. Andere Ausrichtung: einpassen mit weißem Rand."""
    tw, th = size
    same_orientation = (img.width >= img.height) == (tw >= th)
    if same_orientation:
        return ImageOps.fit(img, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.4))
    contained = ImageOps.contain(img, size, method=Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, (255, 255, 255))
    canvas.paste(contained, ((tw - contained.width) // 2, (th - contained.height) // 2))
    return canvas


def _dither(img: Image.Image) -> list[int]:
    """Floyd-Steinberg gegen die gemessenen Panelfarben; liefert Palettenindizes (Controller-Codes) pro Pixel."""
    order = list(USED_INDICES)
    flat: list[int] = []
    for idx in order:
        flat.extend(PALETTE[idx][2])
    # Restliche Einträge mit der ersten Farbe füllen, damit nur die sechs Farben gewählt werden können
    flat.extend(list(PALETTE[order[0]][2]) * (256 - len(order)))
    pal_img = Image.new("P", (1, 1))
    pal_img.putpalette(flat)
    quantized = img.quantize(palette=pal_img, dither=Image.Dither.FLOYDSTEINBERG)
    lookup = [order[i] if i < len(order) else order[0] for i in range(256)]
    return list(quantized.tobytes().translate(bytes(lookup)))


def write_bmp4(indices: list[int], width: int, height: int) -> bytes:
    """Unkomprimiertes 4-Bit-BMP (bottom-up) mit 16er-Farbtabelle."""
    row_bytes = ((width * 4 + 31) // 32) * 4
    palette = bytearray()
    for i in range(16):
        rgb = PALETTE[i][1] if i in PALETTE else (0, 0, 0)
        palette += bytes((rgb[2], rgb[1], rgb[0], 0))  # BGRA
    pixel_offset = 14 + 40 + len(palette)
    image_size = row_bytes * height
    out = bytearray()
    out += struct.pack("<2sIHHI", b"BM", pixel_offset + image_size, 0, 0, pixel_offset)
    out += struct.pack("<IiiHHIIiiII", 40, width, height, 1, 4, 0, image_size, 2835, 2835, 16, 0)
    out += palette
    for y in range(height - 1, -1, -1):
        row = indices[y * width : (y + 1) * width]
        packed = bytearray(row_bytes)
        for x in range(0, width, 2):
            hi = row[x]
            lo = row[x + 1] if x + 1 < width else 0
            packed[x // 2] = (hi << 4) | lo
        out += packed
    return bytes(out)


def preview_png(bmp: bytes) -> bytes:
    """4-Bit-BMP -> PNG mit den gemessenen Panelfarben, verkleinert auf die halbe Größe."""
    img = Image.open(io.BytesIO(bmp)).convert("P")
    pal = img.getpalette() or []
    for idx, (_, pure, measured) in PALETTE.items():
        pal[idx * 3 : idx * 3 + 3] = list(measured)
    img.putpalette(pal)
    out = io.BytesIO()
    img.convert("RGB").resize((PANEL_W // 2, PANEL_H // 2), Image.Resampling.BOX).save(out, "PNG")
    return out.getvalue()


def render(photo: bytes, orientation: str = "portrait") -> bytes:
    """Foto (JPEG/PNG/HEIC …) -> 4-Bit-BMP in 1200x1600 für den Rahmen."""
    img = Image.open(io.BytesIO(photo))
    img = ImageOps.exif_transpose(img).convert("RGB")
    if orientation == "landscape":
        img = _fit(img, (PANEL_H, PANEL_W)).transpose(Image.Transpose.ROTATE_90)
    else:
        img = _fit(img, (PANEL_W, PANEL_H))
    img = ImageEnhance.Color(img).enhance(1.2)
    img = ImageEnhance.Contrast(img).enhance(1.1)
    return write_bmp4(_dither(img), PANEL_W, PANEL_H)
