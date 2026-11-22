import io

from PIL import Image

from bilderrahmen.render import PANEL_H, PANEL_W, RAW_SIZE, USED_INDICES, pack_raw4, preview_png, render


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


def raw_rows(data):
    """Raw-Puffer -> Zeilen mit Controller-Codes, von oben nach unten."""
    assert len(data) == RAW_SIZE
    rows = []
    for r in range(PANEL_H):
        raw = data[r * PANEL_W // 2 : (r + 1) * PANEL_W // 2]
        px = []
        for b in raw:
            px += [b >> 4, b & 0x0F]
        rows.append(px)
    return rows


def test_panel_is_800x480_landscape():
    assert (PANEL_W, PANEL_H) == (800, 480)
    assert RAW_SIZE == 192_000


def test_raw_is_exact_panel_buffer():
    assert len(render(photo(4000, 3000))) == RAW_SIZE


def test_pack_raw4_high_nibble_is_left_pixel_top_row_first():
    indices = [0] * (PANEL_W * PANEL_H)
    indices[0], indices[1] = 2, 3  # erste Zeile, Pixel 0 und 1
    indices[PANEL_W] = 5  # zweite Zeile, Pixel 0
    data = pack_raw4(indices)
    assert data[0] == 0x23
    assert data[PANEL_W // 2] == 0x50


def test_only_panel_colors_used():
    rows = raw_rows(render(photo(4000, 3000, (90, 160, 210))))
    used = {p for row in rows for p in row}
    assert used <= set(USED_INDICES)
    assert len(used) >= 2  # Mischfarbe -> Dithering mit mehreren Farben


def test_landscape_is_default_and_not_rotated():
    # Querformat-Foto, oben schwarz / unten weiß, quer hängender Rahmen: bleibt oben schwarz
    rows = raw_rows(render(photo(1600, 960, marker=True)))
    assert rows[10][PANEL_W // 2] == 0
    assert rows[PANEL_H - 10][PANEL_W // 2] == 1


def test_portrait_device_rotates_portrait_photo():
    # Hochformat-Foto, oben schwarz / unten weiß, hochkant hängender Rahmen:
    # nach 90° Drehung gegen den Uhrzeigersinn liegt Schwarz links, Weiß rechts
    rows = raw_rows(render(photo(960, 1600, marker=True), "portrait"))
    mid = rows[PANEL_H // 2]
    assert mid[10] == 0
    assert mid[PANEL_W - 10] == 1


def test_exif_rotation_applied():
    # Pixel liegen hochkant (oben schwarz), EXIF 6 = 90° im Uhrzeigersinn drehen -> schwarz rechts
    rows = raw_rows(render(photo(960, 1600, marker=True, exif_orientation=6)))
    mid = rows[PANEL_H // 2]
    assert mid[PANEL_W - 10] == 0
    assert mid[10] == 1


def test_other_orientation_gets_white_border():
    # Hochformat-Foto in Querformat-Rahmen: eingepasst, links und rechts weißer Rand
    rows = raw_rows(render(photo(1200, 1600, (0, 0, 0))))
    mid = rows[PANEL_H // 2]
    assert mid[5] == 1 and mid[PANEL_W - 5] == 1
    assert mid[PANEL_W // 2] == 0


def test_preview_png_from_raw():
    img = Image.open(io.BytesIO(preview_png(render(photo(1600, 960)))))
    assert img.size == (PANEL_W, PANEL_H)
