from datetime import date, timedelta

from bilderrahmen.selection import StateStore, pick_for_day


def no_shuffle(items):
    pass


def days(n, start=date(2026, 11, 1)):
    return [start + timedelta(days=i) for i in range(n)]


def test_each_photo_once_before_repeat():
    state = {}
    ids = [f"p{i}" for i in range(5)]
    shown = [pick_for_day(state, ids, d) for d in days(5)]
    assert sorted(shown) == sorted(ids)


def test_same_photo_all_day():
    state = {}
    ids = ["a", "b", "c"]
    first = pick_for_day(state, ids, date(2026, 11, 1))
    assert pick_for_day(state, ids, date(2026, 11, 1)) == first
    assert pick_for_day(state, ids, date(2026, 11, 2)) != first


def test_removed_photo_drops_out():
    state = {}
    pick_for_day(state, ["a", "b", "c"], date(2026, 11, 1), rng=no_shuffle)  # zeigt a, Rest b, c
    nxt = pick_for_day(state, ["a", "c"], date(2026, 11, 2), rng=no_shuffle)
    assert nxt == "c"


def test_current_photo_removed_same_day_picks_other():
    state = {}
    first = pick_for_day(state, ["a", "b"], date(2026, 11, 1), rng=no_shuffle)
    remaining = ["b"] if first == "a" else ["a"]
    assert pick_for_day(state, remaining, date(2026, 11, 1)) == remaining[0]


def test_new_photo_joins_next_round():
    state = {}
    ids = ["a", "b"]
    shown = [pick_for_day(state, ids, d, rng=no_shuffle) for d in days(2)]
    assert shown == ["a", "b"]
    ids = ["a", "b", "c"]
    next_round = [pick_for_day(state, ids, d, rng=no_shuffle) for d in days(3, date(2026, 11, 3))]
    assert sorted(next_round) == ["a", "b", "c"]


def test_no_back_to_back_repeat_across_rounds():
    state = {}
    ids = ["a", "b"]
    assert pick_for_day(state, ids, date(2026, 11, 1), rng=no_shuffle) == "a"
    assert pick_for_day(state, ids, date(2026, 11, 2), rng=no_shuffle) == "b"
    # neue Runde, ungemischt wäre b vorne -> darf nicht zweimal hintereinander kommen
    assert pick_for_day(state, ids, date(2026, 11, 3), rng=lambda l: l.reverse()) == "a"


def test_empty_album():
    assert pick_for_day({}, [], date(2026, 11, 1)) is None


def test_state_store_roundtrip(tmp_path):
    store = StateStore(tmp_path / "state.json")
    pick_for_day(store.device("oma"), ["a"], date(2026, 11, 1))
    store.save()
    again = StateStore(tmp_path / "state.json")
    assert again.device("oma")["current"] == {"date": "2026-11-01", "item": "a"}
