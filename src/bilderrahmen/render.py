"""Foto für das Spectra-6-Panel des Waveshare ESP32-S3-PhotoPainter (7,3", 800x480) aufbereiten.

Ausgabe ist der rohe Bildpuffer, den der Waveshare-Treiber EPD_7in3e erwartet: 4 Bit pro Pixel, zwei Pixel pro
Byte (hohes Nibble = linkes Pixel), Zeilen von oben nach unten, Werte = Farbcodes des Controllers.
"""

from __future__ import annotations

import io

from PIL import Image, ImageEnhance, ImageOps

try:  # HEIC-Fotos vom iPhone
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

PANEL_W, PANEL_H = 800, 480  # nativ Querformat
RAW_SIZE = PANEL_W * PANEL_H // 2

# Index = Farbcode des Spectra-6-Controllers (4 ist unbelegt), wie EPD_7in3e_BLACK … EPD_7in3e_GREEN im
# Waveshare-Treiber. "measured" sind die Farben, wie das Panel sie tatsächlich zeigt; gegen sie wird gedithert.
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


def pack_raw4(indices: list[int]) -> bytes:
    """Controller-Codes pro Pixel (zeilenweise von oben) -> Panelpuffer, hohes Nibble = linkes Pixel."""
    if len(indices) != PANEL_W * PANEL_H:
        raise ValueError(f"{len(indices)} Pixel statt {PANEL_W * PANEL_H}")
    it = iter(indices)
    return bytes((hi << 4) | lo for hi, lo in zip(it, it))


def preview_png(raw: bytes) -> bytes:
    """Panelpuffer -> PNG mit den gemessenen Panelfarben in Panelgröße."""
    if len(raw) != RAW_SIZE:
        raise ValueError(f"{len(raw)} Bytes statt {RAW_SIZE}")
    pixels = bytearray(len(raw) * 2)
    pixels[0::2] = bytes(b >> 4 for b in raw)
    pixels[1::2] = bytes(b & 0x0F for b in raw)
    img = Image.frombytes("P", (PANEL_W, PANEL_H), bytes(pixels))
    pal = [0] * 768
    for idx, (_, _, measured) in PALETTE.items():
        pal[idx * 3 : idx * 3 + 3] = list(measured)
    img.putpalette(pal)
    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG")
    return out.getvalue()


def render(photo: bytes, orientation: str = "landscape") -> bytes:
    """Foto (JPEG/PNG/HEIC …) -> Panelpuffer (800x480, 4 Bit) für den Rahmen."""
    img = Image.open(io.BytesIO(photo))
    img = ImageOps.exif_transpose(img).convert("RGB")
    if orientation == "portrait":
        # Rahmen hängt hochkant: im Hochformat zuschneiden, dann in die native Querlage drehen
        img = _fit(img, (PANEL_H, PANEL_W)).transpose(Image.Transpose.ROTATE_90)
    else:
        img = _fit(img, (PANEL_W, PANEL_H))
    img = ImageEnhance.Color(img).enhance(1.2)
    img = ImageEnhance.Contrast(img).enhance(1.1)
    return pack_raw4(_dither(img))
