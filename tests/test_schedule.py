from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from bilderrahmen.schedule import sleep_seconds

TZ = "Europe/Berlin"
BERLIN = ZoneInfo(TZ)


def at(*args):
    return datetime(*args, tzinfo=BERLIN)


def test_evening_sleeps_until_next_morning():
    assert sleep_seconds(at(2026, 11, 22, 20, 0), time(6, 0), TZ) == 10 * 3600


def test_just_after_wake_caps_at_one_day():
    # 06:01 -> nächster Termin morgen 06:00 = 23:59 h
    assert sleep_seconds(at(2026, 11, 22, 6, 1), time(6, 0), TZ) == 86400 - 60


def test_slightly_early_wake_does_not_rewake_after_seconds():
    # Rahmen wacht 2 min zu früh auf: nicht nach 2 min erneut, sondern bis morgen (gekappt)
    assert sleep_seconds(at(2026, 11, 22, 5, 58), time(6, 0), TZ) == 86400


def test_before_wake_window():
    assert sleep_seconds(at(2026, 11, 22, 3, 0), time(6, 0), TZ) == 3 * 3600


def test_dst_spring_forward():
    # Nacht 28./29.3.2026: 02:00 -> 03:00, die Nacht hat nur 23 h
    assert sleep_seconds(at(2026, 3, 28, 22, 0), time(6, 0), TZ) == 7 * 3600


def test_dst_fall_back():
    # Nacht 24./25.10.2026: 03:00 -> 02:00, die Nacht hat 25 h
    assert sleep_seconds(at(2026, 10, 24, 22, 0), time(6, 0), TZ) == 9 * 3600


def test_utc_input():
    now = datetime(2026, 11, 22, 19, 0, tzinfo=timezone.utc)  # 20:00 in Berlin
    assert sleep_seconds(now, time(6, 0), TZ) == 10 * 3600
