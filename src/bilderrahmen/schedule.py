"""Aufwachzeit des Rahmens berechnen (Header X-OpenPaper-Sleep-Seconds)."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

MIN_SLEEP = 60
MAX_SLEEP = 86400
# Wacht der Rahmen etwas zu früh auf, soll er nicht nach ein paar Sekunden noch einmal aufwachen,
# sondern gleich bis zum nächsten Tag schlafen.
EARLY_TOLERANCE = timedelta(minutes=15)


def sleep_seconds(now: datetime, wake: time, tz: str) -> int:
    """Sekunden bis zur nächsten Aufwachzeit `wake` (Ortszeit in `tz`), begrenzt auf 60..86400."""
    zone = ZoneInfo(tz)
    local_now = now.astimezone(zone)
    reference = local_now + EARLY_TOLERANCE
    target_day = reference.date()
    target = datetime.combine(target_day, wake, tzinfo=zone)
    if target <= reference:
        target = datetime.combine(target_day + timedelta(days=1), wake, tzinfo=zone)
    # Über UTC rechnen, damit Sommer-/Winterzeit-Wechsel richtig zählen
    seconds = int((target.astimezone(ZoneInfo("UTC")) - local_now.astimezone(ZoneInfo("UTC"))).total_seconds())
    return max(MIN_SLEEP, min(MAX_SLEEP, seconds))
