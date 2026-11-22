import io
import struct

from PIL import Image

from bilderrahmen.render import PANEL_H, PANEL_W, USED_INDICES, render


def photo(w, h, color=(200, 120, 40), exif_orientation=None, marker=False):
    img = Image.new("RGB", (w, h), color)
    if marker:
        # obere Hälfte schwarz, untere weiß
        img.paste((0, 0, 0), (0, 0, w, h // 2))
        img.paste((255, 255, 255), (0, h // 2, w, h))
    buf = io.BytesIO()
    kwargs = {}
    if exif_orientation:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        kwargs["exif"] = exif
    img.save(buf, "JPEG", quality=95, **kwargs)
    return buf.getvalue()


def parse_bmp(data):
    magic, size, _, _, offset = struct.unpack_from("<2sIHHI", data, 0)
    hdr = struct.unpack_from("<IiiHHIIiiII", data, 14)
    return magic, size, offset, hdr


def bmp_indices(data):
    _, _, offset, hdr = parse_bmp(data)
    w, h = hdr[1], hdr[2]
    row_bytes = ((w * 4 + 31) // 32) * 4
    rows = []
    for r in range(h):
        raw = data[offset + r * row_bytes : offset + (r + 1) * row_bytes]
        px = []
        for b in raw[: w // 2]:
            px += [b >> 4, b & 0x0F]
        rows.append(px)
    rows.reverse()  # bottom-up -> top-down
    return rows


def test_bmp_header_is_4bit_panel_size():
    data = render(photo(4000, 3000))
    magic, size, offset, hdr = parse_bmp(data)
    assert magic == b"BM"
    assert size == len(data)
    assert hdr[1:5] == (PANEL_W, PANEL_H, 1, 4)
    assert hdr[5] == 0  # unkomprimiert
    assert offset == 14 + 40 + 16 * 4
    assert len(data) == offset + PANEL_W // 2 * PANEL_H


def test_only_panel_colors_used():
    rows = bmp_indices(render(photo(3000, 4000, (90, 160, 210))))
    used = {p for row in rows for p in row}
    assert used <= set(USED_INDICES)
    assert len(used) >= 2  # Mischfarbe -> Dithering mit mehreren Farben


def test_landscape_device_rotates_landscape_photo():
    # Querformat-Foto, oben schwarz / unten weiß, für einen quer hängenden Rahmen:
    # nach 90° Drehung gegen den Uhrzeigersinn liegt Schwarz links, Weiß rechts
    rows = bmp_indices(render(photo(1600, 1200, marker=True), "landscape"))
    mid = rows[PANEL_H // 2]
    assert mid[10] == 0  # schwarz
    assert mid[PANEL_W - 10] == 1  # weiß


def test_exif_rotation_applied():
    # Pixel liegen quer (oben schwarz), EXIF 6 = 90° im Uhrzeigersinn drehen -> schwarz rechts
    rows = bmp_indices(render(photo(1600, 1200, marker=True, exif_orientation=6), "portrait"))
    mid = rows[PANEL_H // 2]
    assert mid[PANEL_W - 10] == 0
    assert mid[10] == 1


def test_other_orientation_gets_white_border():
    # Querformat-Foto in Hochformat-Rahmen: eingepasst, oben und unten weißer Rand
    rows = bmp_indices(render(photo(1600, 1200, (0, 0, 0)), "portrait"))
    assert set(rows[5]) == {1}
    assert set(rows[PANEL_H // 2]) == {0}
