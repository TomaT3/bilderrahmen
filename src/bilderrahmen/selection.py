"""Tagesbild-Auswahl per Shuffle-Bag und dauerhafter Zustand in einer JSON-Datei."""

from __future__ import annotations

import json
import os
import random
import threading
from datetime import date
from pathlib import Path
from typing import Any, Callable, Sequence


class StateStore:
    """Hält den Zustand aller Geräte in einer JSON-Datei; Schreiben atomar über eine temporäre Datei."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self._data: dict[str, Any] = {}
        if path.exists():
            self._data = json.loads(path.read_text(encoding="utf-8"))

    def device(self, device_id: str) -> dict[str, Any]:
        return self._data.setdefault("devices", {}).setdefault(device_id, {})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)


def pick_for_day(
    state: dict[str, Any],
    item_ids: Sequence[str],
    day: date,
    rng: Callable[[list[str]], None] = random.shuffle,
) -> str | None:
    """Liefert die Bild-ID für `day`.

    Das Bild steht mit dem ersten Aufruf am Tag fest und bleibt dann für den Tag gleich, solange es noch im Album ist.
    Die Shuffle-Bag sorgt dafür, dass jedes Bild einmal kommt, bevor sich eines wiederholt. Neue Bilder kommen in
    die nächste Runde, gelöschte fallen heraus.
    """
    available = set(item_ids)
    if not available:
        return None

    current = state.get("current")
    if current and current.get("date") == day.isoformat() and current.get("item") in available:
        return current["item"]

    bag = [i for i in state.get("bag", []) if i in available]
    if not bag:
        bag = sorted(available)
        rng(bag)
        # Nicht dasselbe Bild zweimal hintereinander, wenn eine neue Runde beginnt
        if len(bag) > 1 and current and bag[0] == current.get("item"):
            bag.append(bag.pop(0))

    chosen = bag.pop(0)
    state["bag"] = bag
    state["current"] = {"date": day.isoformat(), "item": chosen}
    return chosen
